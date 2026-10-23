"""Pilotage du navigateur réel d'une session en direct — sous-lot C du lot « Enregistrement
assisté du chemin de connexion » (étapes 4, 5, 7).

Playwright **synchrone**, comme partout ailleurs dans ce dépôt (`scripts/crawl_domaine.py`,
`behave_runtime/`) — jamais mélangé à la boucle asyncio qui porte la route WebSocket. Le
navigateur tourne dans un **thread dédié**, propriétaire de tout son cycle de vie (Playwright,
navigateur, contexte, page, session CDP) du début à la fin ; la route WebSocket (coroutine)
communique avec lui par deux files thread-safe (`entrantes`/`sortantes`), jamais par appel direct
à une méthode Playwright depuis un autre thread (interdit par Playwright lui-même).

La place dans la file de concurrence partagée (`guardrails/concurrency.py`, sous-lot B) est tenue
pour la durée ENTIÈRE du thread — exactement la garantie que `JobQueue.held()` existe pour offrir,
pas seulement le temps d'une tâche de fond ponctuelle.
"""

from __future__ import annotations

import base64
import logging
import queue
import sys
import threading
import time
import types
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from testpilot.connectors.contexte_navigateur import depuis_projet
from testpilot.generation import accname
from testpilot.guardrails import concurrency

logger = logging.getLogger(__name__)

# CDP borne la taille des images du relais vidéo à ces dimensions — fixées à la taille RÉELLE du
# viewport (pas de mise à l'échelle) : les coordonnées (x, y) qu'un clic envoie correspondent alors
# 1:1 aux coordonnées de la page, sans traduction. Limite connue, documentée dans le rapport de fin
# de sous-lot : un écran client plus petit que le viewport devra downscaler l'affichage lui-même
# et retraduire ses clics — hors périmètre de ce sous-lot (aucun écran n'existe encore).
_QUALITE_JPEG = 60

# Plafond de l'attente de stabilisation de la page avant d'ouvrir la session (voir `_piloter`).
_ATTENTE_STABILISATION_MS = 4000

# Entre deux commandes, le fil du navigateur doit continuer de RELEVER les événements de Playwright : l'API synchrone ne
# distribue un événement (ici `Page.screencastFrame`) que pendant un de ses propres appels. Mesuré le 2026-10-12 (/dev,
# portail d'intégration Odoo, puis reproduit sur une page locale) : la boucle attendait la commande suivante sur une file
# Python, les images produites par un clic restaient donc en attente et ne partaient qu'AU CLIC SUIVANT — l'écran affichait
# toujours l'état d'avant (le formulaire ouvert par le clic n'apparaissait pas, « il faut cliquer deux fois »). La boucle
# relève maintenant les événements par tranches de cette durée ; c'est aussi le délai maximal avant de traiter un clic.
_RELEVE_EVENEMENTS_MS = 50

# Extension (2026-09-30) : après l'écran de pré-connexion, 3 clics guidés supplémentaires
# identifient le champ identifiant, le champ mot de passe et le bouton de soumission — motivée par
# un échec réel en production (`tenter_connexion_generique` devine le champ identifiant par
# premier match DOM et soumet à l'aveugle via la touche Entrée, deux paris qui ont raté sur une
# application réelle malgré des identifiants valides). Jamais de valeur/texte capturé ici non
# plus : seulement le rôle/nom résolu par AccName, même garde que le reste de la capture.
_CHAMPS_FORMULAIRE_CONNEXION = ("champ_identifiant", "champ_mdp", "bouton_soumission")

# Les commandes dont `attendre_clics_traites` attend le traitement (étape 7b : un parcours en a quatre).
_COMMANDES_COMPTEES = frozenset({"clic", "saisie", "choix", "verifier", "commencer"})


# Étape 7b (A109) : un clic sur un champ ne fait que le désigner — la valeur arrive ensuite par « saisie » ou « choix ».
_ROLES_DE_SAISIE = frozenset({"textbox", "searchbox", "spinbutton", "combobox"})
# Laisse la page réagir à une action avant d'en relever l'adresse (une navigation déclenchée par un clic n'est pas
# synchrone). Borné : la page peut ne jamais se stabiliser.
_ATTENTE_APRES_ACTION_MS = 1500
# Le champ sous le point : de quoi écrire l'étape de la bibliothèque (`je renseigne le champ "<nom technique>"…` — la
# cascade `locate_field` cherche d'abord `name`, puis `data-test`) et proposer les choix d'une liste. Un widget Odoo porte
# son `name` sur le conteneur (`<div name="partner_id"><input…>`) : l'ancêtre le plus proche qui en a un.
_CHAMP_SOUS_LE_POINT_JS = r"""
({x, y}) => {
  const el = document.elementFromPoint(x, y);
  const champ = el && el.closest('input, textarea, select, [contenteditable="true"]');
  if (!champ) return null;
  const tag = champ.tagName.toLowerCase();
  const porteur = champ.closest('[name]');
  return {
    tag, type: (champ.getAttribute('type') || '').toLowerCase(),
    nom_technique: (porteur && porteur.getAttribute('name')) || champ.getAttribute('data-test')
      || champ.getAttribute('data-testid') || '',
    options: tag === 'select'
      ? Array.from(champ.options).map(o => (o.label || o.textContent || '').trim()).filter(Boolean).slice(0, 200) : [],
    secret: (champ.getAttribute('type') || '').toLowerCase() === 'password'
      || /(current|new)-password/.test(champ.getAttribute('autocomplete') || '')
      || /(^|[^a-z])(password|passwd|pwd|mdp|mot.?de.?passe)([^a-z]|$)/i.test((champ.getAttribute('name') || '') + ' ' + (champ.id || '')),
    // Une liste à recherche (autocomplétion, many2one…) : remplir le texte ne CHOISIT pas l'enregistrement — l'étape
    // générique « je renseigne le champ » n'y suffit pas, l'agent écrira l'étape qui convient (revue du 2026-10-23).
    relation: (champ.getAttribute('role') || '') === 'combobox' || champ.hasAttribute('aria-autocomplete')
      || !!champ.closest('.o_field_many2one'),
  };
}
"""

# Le champ qui reçoit VRAIMENT la saisie est-il un mot de passe (même affiché en clair) ?
_EST_SECRET_JS = ("el => (el.getAttribute('type') || '').toLowerCase() === 'password'"
                  " || /(current|new)-password/.test(el.getAttribute('autocomplete') || '')"
                  " || /(^|[^a-z])(password|passwd|pwd|mdp|mot.?de.?passe)([^a-z]|$)/i.test((el.getAttribute('name') || '') + ' ' + (el.id || ''))")

# Rôles dont le nom accessible ne vient JAMAIS du contenu (étiquette d'un champ). Revue du 2026-10-23, 2e passe (bloquant,
# mesuré avec Chromium) : un bouton, un lien, un onglet tirent leur nom de ce qu'ils affichent — le bouton Odoo
# « 3 Factures », le lien « Panier (2) – 59,90 € » — donc jamais leur nom pour une vérification.
_ROLES_SANS_CONTENU = frozenset({"textbox", "searchbox", "spinbutton", "combobox", "listbox", "slider"})

# La désignation TECHNIQUE de l'élément visé, ou d'un ancêtre PROCHE (3 niveaux au plus) — jamais son texte. Au-delà, on
# désignerait un conteneur de toute la page (`#wrapwrap` d'Odoo, mesuré) : l'agent devrait deviner, mieux vaut refuser.
_DESIGNATION_TECHNIQUE_JS = r"""
({x, y}) => {
  let el = document.elementFromPoint(x, y);
  for (let niveau = 0; el && niveau <= 3; niveau += 1, el = el.parentElement) {
    // Un `id` qui finit par des chiffres est généré (`partner_id_0` d'Odoo) : il change d'une session à l'autre.
    const id = el.getAttribute('id') || '';
    const nom = el.getAttribute('data-test') || el.getAttribute('data-testid') || el.getAttribute('name')
      || (/\d$/.test(id) ? '' : id);
    if (nom) return nom.slice(0, 120);
  }
  return '';
}
"""


def _mot_de_passe_visible(page) -> bool | None:
    """Dupliqué de `behave_runtime/steps_library/_base_helpers.py::_mot_de_passe_visible` — même
    convention que `accname.ElementIntrouvableError` (dupliqué, pas importé) : l'API et le
    sous-processus Behave restent deux paquets séparés, ni ne dépend de l'autre. `None` = page
    illisible (navigation en cours) — jamais traité comme « pas de champ mot de passe » ici,
    l'appelant garde la capture active tant qu'il n'a pas vu `True` explicitement."""
    try:
        champs = page.locator("input[type='password']")
        return any(champs.nth(i).is_visible() for i in range(min(champs.count(), 5)))
    except Exception:
        return None


class SessionLive:
    """Un navigateur réel, piloté à distance, pour la durée d'une session d'enregistrement.

    Cycle de vie garanti : `demarrer()` lance le thread ; quel que soit ce qui se passe ensuite
    (erreur, clic ambigu, coupure), `demander_fermeture()` + `attendre_fermeture()` garantissent
    que le navigateur, le contexte et la place dans la file de concurrence sont TOUJOURS libérés —
    le `with` imbriqué (`held()` puis `sync_playwright()`) le fait même sur une exception non
    prévue par ce module.
    """

    def __init__(self, *, project: dict, queue_label: str, mode: str = "connexion", connexion: dict | None = None):
        self._project = project
        self._queue_label = queue_label
        # Étape 7b (A109) : `parcours` = le chemin d'un CAS, joué après une connexion automatique (`connexion` : les
        # paramètres du projet, comme l'exploration) ; `connexion` = l'enregistrement du chemin de connexion (historique).
        self._mode = mode
        self._connexion = connexion
        self._actions: list[dict] = []
        self._champ_actif: dict | None = None
        self._capture_parcours = True   # faux après une connexion automatique en échec, jusqu'à « commencer »
        self.entrantes: queue.Queue[dict] = queue.Queue()
        self.sortantes: queue.Queue[dict] = queue.Queue()
        self.pret = threading.Event()
        self.fermee = threading.Event()
        self._fermeture_demandee = threading.Event()
        self._verrou_etapes = threading.Lock()
        self._etapes: list[dict] = []
        self._capture_active = True
        # Bascule à `True` dès que le mot de passe devient visible (voir `_traiter_clic`) — reste
        # `True` pour le reste de la session, jamais retraversé en sens inverse (le navigateur réel
        # n'est jamais renavigué en arrière par un simple `recommencer`, voir `reinitialiser_etapes`).
        self._mode_formulaire = False
        self._login_form: dict[str, dict] = {}
        self._cdp = None
        self._thread = threading.Thread(target=self._boucle, name="session-live", daemon=True)
        # Synchronisation clics envoyés / clics traités — trouvé en revue verdict-reviewer
        # (2026-09-29, reproduit avec un vrai Chromium) : sans ça, `confirmer` ou `recommencer`
        # pouvaient s'exécuter AVANT qu'un clic déjà mis en file n'ait été traité par le thread
        # navigateur — une séquence « confirmée » silencieusement incomplète (clic perdu) ou une
        # étape qui ressuscite après un « recommencer » (clic traité APRÈS la remise à zéro).
        # `_clics_recus` est incrémenté au moment même où le clic est mis en file (même verrou que
        # la mise en file elle-même, jamais deux écritures séparées qui rouvriraient la fenêtre) ;
        # `_clics_traites`, par le thread navigateur, une fois le clic réellement appliqué.
        self._verrou_compteurs = threading.Lock()
        self._clics_recus = 0
        self._clics_traites = 0

    def demarrer(self) -> None:
        self._thread.start()

    def demander_fermeture(self) -> None:
        self._fermeture_demandee.set()

    def attendre_fermeture(self, timeout: float | None = None) -> None:
        self._thread.join(timeout=timeout)

    def soumettre_clic(self, commande: dict) -> None:
        """Point d'entrée UNIQUE pour un clic entrant — incrémente `_clics_recus` et met en file
        sous le MÊME verrou, pour qu'`attendre_clics_traites` ne puisse jamais lire un compteur en
        retard sur la file elle-même."""
        with self._verrou_compteurs:
            self._clics_recus += 1
            self.entrantes.put(commande)

    def attendre_clics_traites(self, timeout: float) -> bool:
        """Bloque (appelé via `asyncio.to_thread`, jamais depuis la boucle asyncio elle-même)
        jusqu'à ce que tous les clics déjà soumis aient été traités par le thread navigateur, ou
        jusqu'à `timeout`. Rend `False` sur timeout — l'appelant (la route WebSocket) doit alors
        REFUSER de confirmer/recommencer plutôt que d'agir sur un état potentiellement encore en
        mouvement."""
        fin = time.monotonic() + timeout
        while time.monotonic() < fin:
            with self._verrou_compteurs:
                if self._clics_traites >= self._clics_recus:
                    return True
            time.sleep(0.02)
        with self._verrou_compteurs:
            return self._clics_traites >= self._clics_recus

    def reinitialiser_etapes(self) -> None:
        """« Recommencer » (étape 6) : vide la liste en mémoire, rien n'a jamais été écrit.
        N'appeler qu'après `attendre_clics_traites` — sinon un clic encore en file pourrait
        s'ajouter APRÈS ce vidage.

        Ne touche PAS `_mode_formulaire` : le navigateur réel n'est jamais renavigué en arrière
        par un recommencer — si le mot de passe est déjà visible sur la page à cet instant, il le
        restera après, donc le mode formulaire (guidage des 3 clics) doit rester actif plutôt que
        de re-proposer une capture de pré-connexion qui a déjà eu lieu pour de vrai."""
        with self._verrou_etapes:
            self._etapes = []
            self._login_form = {}
            self._actions = []
        self._champ_actif = None

    def retirer_action(self, rang: int) -> bool:
        """Étape 7b : la personne retire une action de son parcours (un geste de trop). N'appeler qu'après
        `attendre_clics_traites`, comme `reinitialiser_etapes`."""
        with self._verrou_etapes:
            if not 0 <= rang < len(self._actions):
                return False
            del self._actions[rang]
            return True

    @property
    def actions(self) -> list[dict]:
        with self._verrou_etapes:
            return list(self._actions)

    @property
    def etapes(self) -> list[dict]:
        with self._verrou_etapes:
            return list(self._etapes)

    @property
    def login_form(self) -> dict[str, dict] | None:
        """Le descripteur complet (3 champs), ou `None` si les 3 clics guidés n'ont pas tous
        abouti — jamais un descripteur partiel, injouable et jamais stocké comme tel."""
        with self._verrou_etapes:
            if len(self._login_form) != len(_CHAMPS_FORMULAIRE_CONNEXION):
                return None
            return dict(self._login_form)

    # ── Le thread dédié ──────────────────────────────────────────────────────────────────────

    def _boucle(self) -> None:
        try:
            with concurrency.get_queue().held(self._queue_label):
                with sync_playwright() as p:
                    # `--headless=old` : mesuré (pas supposé), le mode headless « nouveau »
                    # (défaut de Playwright/Chromium depuis 2024) ne délivre JAMAIS d'événement
                    # `Page.screencastFrame` — 0 frame reçue en 2 s d'attente sur une page qui
                    # change activement, contre un flux normal en mode `old`. Rapporté ailleurs
                    # comme une limite connue du nouveau mode headless vis-à-vis de CDP Page
                    # domain, pas une erreur de configuration de ce module.
                    navigateur = p.chromium.launch(headless=True, args=["--headless=old"])
                    try:
                        self._piloter(navigateur)
                    finally:
                        navigateur.close()
        except Exception:
            logger.exception("session live (projet %s) : échec du pilotage du navigateur",
                             self._project.get("id"))
            self.sortantes.put({"type": "erreur", "detail": "navigateur"})
        finally:
            self.pret.set()  # débloque un éventuel attendeur même si on n'a jamais démarré
            self.fermee.set()

    def _piloter(self, navigateur) -> None:
        contexte_navigateur = depuis_projet(self._project)
        contexte = navigateur.new_context(**contexte_navigateur.kwargs())
        try:
            page = contexte.new_page()
            page.goto(self._project.get("base_url") or "about:blank", timeout=15000)
            # Mesuré le 2026-10-07 (portail d'intégration Odoo, SSO) : `goto` rend la main à
            # l'événement `load`, mais le JavaScript de la page continue d'initialiser son
            # formulaire. Un premier clic envoyé pendant cette phase ouvrait le bloc de connexion,
            # puis la page le refermait (champ mot de passe resté invisible) : « il faut cliquer
            # deux fois ». On laisse la page se stabiliser AVANT de déclarer la session prête.
            # Bornée : certaines applications (long-polling) n'atteignent jamais `networkidle`.
            try:
                page.wait_for_load_state("networkidle", timeout=_ATTENTE_STABILISATION_MS)
            except PlaywrightTimeoutError:
                logger.debug("session live (projet %s) : page jamais « idle » en %s ms — on "
                             "démarre quand même", self._project.get("id"), _ATTENTE_STABILISATION_MS)
            if self._mode == "parcours":
                self._se_connecter(page, contexte_navigateur)
            self._cdp = contexte.new_cdp_session(page)
            self._cdp.on("Page.screencastFrame", self._sur_image)
            self._cdp.send("Page.startScreencast", {
                "format": "jpeg", "quality": _QUALITE_JPEG,
                "maxWidth": contexte_navigateur.largeur,
                "maxHeight": contexte_navigateur.hauteur,
            })
            # CDP n'émet une frame qu'au moment d'un changement visuel réel — mesuré : une page
            # chargée puis immobile ne produit JAMAIS de première frame toute seule. Sans cette
            # capture explicite (API Playwright de haut niveau, indépendante des aléas de CDP), la
            # personne verrait un écran vide jusqu'à son premier clic, incapable de savoir où
            # cliquer.
            self.sortantes.put({
                "type": "image",
                "data": base64.b64encode(page.screenshot(type="jpeg", quality=_QUALITE_JPEG)).decode("ascii"),
            })
            self.pret.set()
            while not self._fermeture_demandee.is_set():
                try:
                    commande = self.entrantes.get_nowait()
                except queue.Empty:
                    # Pas de commande : on rend la main à Playwright, qui distribue les images en attente
                    # (voir `_RELEVE_EVENEMENTS_MS`). Jamais une attente sur la file elle-même.
                    page.wait_for_timeout(_RELEVE_EVENEMENTS_MS)
                    continue
                try:
                    self._traiter(page, commande)
                except Exception:
                    logger.exception("session live (projet %s) : commande en échec",
                                     self._project.get("id"))
                finally:
                    # Compté même en échec : un clic qui plante ne doit jamais bloquer
                    # `attendre_clics_traites` pour le reste de la session (sinon un seul clic en
                    # erreur empêcherait à jamais toute confirmation/réinitialisation ultérieure).
                    if commande.get("type") in _COMMANDES_COMPTEES:
                        with self._verrou_compteurs:
                            self._clics_traites += 1
        finally:
            try:
                self._cdp and self._cdp.send("Page.stopScreencast")
            except Exception:
                pass
            contexte.close()

    def _sur_image(self, params: dict) -> None:
        self.sortantes.put({"type": "image", "data": params["data"]})
        try:
            self._cdp.send("Page.screencastFrameAck", {"sessionId": params["sessionId"]})
        except Exception:
            pass  # la session peut déjà être en cours de fermeture

    def _traiter(self, page, commande: dict) -> None:
        if self._mode == "parcours":
            self._traiter_parcours(page, commande)
        elif commande.get("type") == "clic":
            self._traiter_clic(page, commande)

    # ── Étape 7b : le parcours d'un cas ─────────────────────────────────────────────────────

    def _se_connecter(self, page, contexte_navigateur) -> None:
        """Connexion AUTOMATIQUE avec le compte du projet, la même que l'exploration (`crawl_relogin_hook`) : la personne
        commence là où le test commencera, et son parcours ne contient jamais la connexion. En échec (revue du 2026-10-23),
        rien n'est capturé tant qu'elle ne dit pas « je suis connecté » (`commencer`) : se connecter à la main n'entre
        jamais dans le parcours — un identifiant y serait gardé, et le test rejouerait un formulaire déjà franchi."""
        if not self._connexion:
            return
        racine = Path(__file__).resolve().parents[4]
        for chemin in (racine / "behave_runtime" / "steps_library",):
            if str(chemin) not in sys.path:   # même montage que `exploration_service._crawl` (connecteur Odoo)
                sys.path.insert(0, str(chemin))
        from testpilot.connectors.factory import build_connector

        try:
            build_connector(self._connexion).crawl_relogin_hook()(
                types.SimpleNamespace(page=page, contexte_navigateur=contexte_navigateur.kwargs()))
            self.sortantes.put({"type": "connexion_auto", "ok": True})
        except Exception as exc:
            # Le type d'erreur au journal, jamais son texte à l'écran (il peut citer l'identifiant).
            logger.warning("parcours (projet %s) : connexion automatique impossible (%s)",
                           self._project.get("id"), type(exc).__name__)
            self._capture_parcours = False
            self.sortantes.put({"type": "connexion_auto", "ok": False})

    def _garder(self, page, action: dict) -> None:
        if not self._capture_parcours:
            return   # connexion à la main en cours : le geste part à la page, jamais au parcours
        try:
            page.wait_for_load_state("networkidle", timeout=_ATTENTE_APRES_ACTION_MS)
        except PlaywrightTimeoutError:
            pass
        action["page"] = page.url
        with self._verrou_etapes:
            self._actions.append(action)
            rang = len(self._actions) - 1
        self.sortantes.put({"type": "action_capturee", "rang": rang, **action})

    def _traiter_parcours(self, page, commande: dict) -> None:
        type_ = commande.get("type")
        if type_ == "clic":
            self._parcours_clic(page, float(commande["x"]), float(commande["y"]))
        elif type_ == "verifier":
            self._parcours_verifier(page, float(commande["x"]), float(commande["y"]))
        elif type_ == "saisie":
            self._saisir(page, str(commande.get("valeur") or ""))
        elif type_ == "choix":
            self._choisir(page, str(commande.get("valeur") or ""))
        elif type_ == "commencer":
            # « Je suis connecté » : la capture commence ICI, sur une liste vide.
            with self._verrou_etapes:
                self._actions = []
            self._champ_actif = None
            self._capture_parcours = True
            self.sortantes.put({"type": "capture_commencee"})

    def _parcours_clic(self, page, x: float, y: float) -> None:
        try:
            resolu = accname.calculer(page, x, y)
            ambigu = None
        except accname.ElementIntrouvableError as exc:
            resolu, ambigu = None, str(exc)
        champ = page.evaluate(_CHAMP_SOUS_LE_POINT_JS, {"x": x, "y": y})
        self._cliquer_reellement(x, y)
        if champ is not None:
            # Désigner un champ n'est pas une action du test : la valeur suit (saisie, ou choix pour une liste). Un champ
            # ambigu pour AccName reste désignable : l'étape écrite le retrouve par son NOM TECHNIQUE.
            self._champ_actif = {"role": (resolu or {}).get("role") or ("combobox" if champ["tag"] == "select" else "textbox"),
                                 "nom": (resolu or {}).get("name") or champ["nom_technique"],
                                 "champ": champ["nom_technique"], "secret": champ["secret"],
                                 "liste": champ["tag"] == "select", "relation": champ["relation"]}
            self.sortantes.put({"type": "champ_designe", "nom": self._champ_actif["nom"],
                                "secret": self._champ_actif["secret"], "options": champ["options"]})
            return
        self._champ_actif = None
        if ambigu:
            self.sortantes.put({"type": "clic_ambigu", "detail": ambigu})
            return
        if resolu is None:
            self.sortantes.put({"type": "clic_non_enregistre", "raison": "element_non_reconnu"})
            return
        self._garder(page, {"action": "clic", "role": resolu["role"], "nom": resolu["name"]})

    def _parcours_verifier(self, page, x: float, y: float) -> None:
        """« C'est ici que je vérifie » : l'élément est désigné, JAMAIS cliqué, et RIEN de ce qu'il affiche n'est gardé — le
        résultat attendu vient du cas validé (A39). Revue du 2026-10-23 (bloquant, deux passes) : le texte d'un montant, ou
        celui d'un bouton « 3 Factures », partait comme « nom » à l'agent, qui l'écrivait comme attendu (un bug du jour
        devenait conforme). D'abord la désignation technique (`data-test`, `name`, `id`) ; à défaut, l'étiquette d'un CHAMP
        (`_ROLES_SANS_CONTENU`) ; sinon refusé."""
        try:
            resolu = accname.calculer(page, x, y)
        except accname.ElementIntrouvableError:
            resolu = None   # ambigu par son nom : la désignation technique peut encore le distinguer
        technique = page.evaluate(_DESIGNATION_TECHNIQUE_JS, {"x": x, "y": y})
        if technique:
            resolu = {"role": (resolu or {}).get("role") or "element", "name": technique}
        elif resolu is None or resolu["role"] not in _ROLES_SANS_CONTENU:
            resolu = None
        if resolu is None:
            self.sortantes.put({"type": "clic_non_enregistre", "raison": "element_sans_designation"})
            return
        self._garder(page, {"action": "verifier", "role": resolu["role"], "nom": resolu["name"]})

    def _saisir(self, page, valeur: str) -> None:
        champ = self._champ_actif
        if champ is None or champ["liste"]:
            self.sortantes.put({"type": "erreur", "detail": "aucun_champ_designe"})
            return
        actif = page.evaluate_handle("() => document.activeElement").as_element()
        if actif is None:
            self.sortantes.put({"type": "erreur", "detail": "aucun_champ_designe"})
            return
        # Revue du 2026-10-23 : le secret se décide AUSSI au moment de saisir, sur le champ qui reçoit vraiment la valeur
        # (mot de passe affiché en clair par un bouton « voir », focus déplacé par la page).
        secret = champ["secret"] or bool(actif.evaluate(_EST_SECRET_JS))
        try:
            actif.fill(valeur)
        except Exception as exc:
            # Jamais `logger.exception` : le message de Playwright pourrait citer la valeur.
            logger.warning("parcours (projet %s) : saisie impossible (%s)", self._project.get("id"), type(exc).__name__)
            self.sortantes.put({"type": "erreur", "detail": "saisie_impossible"})
            return
        if secret:
            # Un mot de passe n'entre jamais dans le parcours : ni sa valeur, ni l'action (l'agent ne pourrait que l'inventer).
            self.sortantes.put({"type": "clic_non_enregistre", "raison": "mot_de_passe"})
            self._champ_actif = None
            return
        self._garder(page, {"action": "saisie", "role": champ["role"], "nom": champ["nom"], "champ": champ["champ"],
                            "secret": False, "valeur": valeur, "relation": champ["relation"]})

    def _choisir(self, page, valeur: str) -> None:
        champ = self._champ_actif
        actif = page.evaluate_handle("() => document.activeElement").as_element() if champ else None
        if champ is None or not champ["liste"] or actif is None:
            self.sortantes.put({"type": "erreur", "detail": "aucune_liste_designee"})
            return
        try:
            actif.select_option(label=valeur)
        except Exception as exc:
            logger.warning("parcours (projet %s) : choix impossible (%s)", self._project.get("id"), type(exc).__name__)
            self.sortantes.put({"type": "erreur", "detail": "choix_impossible"})
            return
        self._garder(page, {"action": "choix", "role": champ["role"], "nom": champ["nom"], "champ": champ["champ"],
                            "secret": False, "valeur": valeur})

    def _basculer_en_mode_formulaire(self) -> None:
        self._capture_active = False
        self._mode_formulaire = True
        self.sortantes.put({"type": "capture_arretee", "raison": "mot_de_passe_visible"})
        self.sortantes.put({"type": "formulaire_connexion_invite",
                            "champ": _CHAMPS_FORMULAIRE_CONNEXION[0]})

    def _traiter_clic(self, page, commande: dict) -> None:
        x, y = float(commande["x"]), float(commande["y"])
        # Formulaire à UN SEUL écran (identifiant et mot de passe déjà visibles ensemble, ex.
        # SauceDemo) : le mot de passe est visible AVANT même ce premier clic — bascule en mode
        # formulaire guidé AVANT de le traiter, sinon il partirait à tort dans `_etapes` (écran
        # intercalé) au lieu de `champ_identifiant`, décalant toute la séquence des 3 clics
        # suivants (bug mesuré le 2026-09-30, capture sur SauceDemo : `champ_identifiant` et
        # `champ_mdp` identiques, `bouton_soumission` vide).
        if self._capture_active and _mot_de_passe_visible(page):
            self._basculer_en_mode_formulaire()

        resolu = None
        ambigu = False
        if self._capture_active or self._mode_formulaire:
            try:
                resolu = accname.calculer(page, x, y)
            except accname.ElementIntrouvableError as exc:
                # Ambigu : jamais capturé en silence sur le premier trouvé — signalé, pas retenu.
                ambigu = True
                self.sortantes.put({"type": "clic_ambigu", "detail": str(exc)})
        if self._mode_formulaire and resolu is not None and resolu.get("role") == accname.ROLE_DEPLIANT:
            # Les 3 emplacements du formulaire (identifiant, mot de passe, bouton) sont rejoués par
            # `get_by_role(...).fill/click` : un jeton `summary` n'y existe pas et y échouerait à
            # CHAQUE rejeu, après avoir été confirmé comme « formulaire complet » (revue
            # 2026-10-07). Un bloc dépliant n'a sa place que dans l'étape de pré-connexion.
            resolu = None
            self.sortantes.put({"type": "clic_non_enregistre", "raison": "depliant_pendant_le_formulaire"})
            self._cliquer_reellement(x, y)
            return

        self._cliquer_reellement(x, y)

        if resolu is None and not ambigu and (self._capture_active or self._mode_formulaire):
            # Mesuré le 2026-10-07 (page de connexion SSO du portail d'intégration Odoo) : un clic
            # sur un bloc dépliant (`<summary>`, rôle `group` pour Playwright) ou sur du texte nu
            # n'a aucun (rôle, nom) rejouable. Il partait à la page mais n'était PAS retenu, sans le
            # moindre signal : la personne croyait l'étape enregistrée, le rejeu ne la reproduirait
            # jamais. Le clic reste envoyé (la page doit réagir comme pour un humain) ; seul son
            # défaut d'enregistrement est désormais dit. Jamais en plus d'un `clic_ambigu` : deux
            # messages contradictoires pour un même clic (revue 2026-10-07).
            self.sortantes.put({"type": "clic_non_enregistre", "raison": "element_non_reconnu"})

        if self._mode_formulaire:
            if resolu is not None:
                self._traiter_clic_formulaire(resolu)
            return

        if resolu is not None:
            with self._verrou_etapes:
                self._etapes.append(resolu)
            self.sortantes.put({"type": "etape_capturee", **resolu})
        # Formulaire à DEUX écrans : CE clic vient de franchir l'écran intercalé et a révélé le
        # mot de passe — bascule après coup, pour que le clic SUIVANT soit le premier du
        # formulaire guidé (comportement historique, inchangé).
        if self._capture_active and _mot_de_passe_visible(page):
            self._basculer_en_mode_formulaire()

    def _traiter_clic_formulaire(self, resolu: dict) -> None:
        """3 clics guidés (identifiant, mot de passe, bouton) APRÈS l'écran de pré-connexion —
        jamais de valeur/texte, seulement le rôle/nom résolu par AccName (même mécanisme que
        `_traiter_clic`). Un clic surnuméraire (le formulaire est déjà complet) est ignoré plutôt
        que d'écraser une clé déjà capturée."""
        with self._verrou_etapes:
            index = len(self._login_form)
            if index >= len(_CHAMPS_FORMULAIRE_CONNEXION):
                return
            cle = _CHAMPS_FORMULAIRE_CONNEXION[index]
            self._login_form[cle] = resolu
            complet = len(self._login_form) == len(_CHAMPS_FORMULAIRE_CONNEXION)
        self.sortantes.put({"type": "formulaire_connexion_champ_capture", "champ": cle, **resolu})
        if complet:
            self.sortantes.put({"type": "formulaire_connexion_complet"})
        else:
            self.sortantes.put({"type": "formulaire_connexion_invite",
                                "champ": _CHAMPS_FORMULAIRE_CONNEXION[index + 1]})

    def _cliquer_reellement(self, x: float, y: float) -> None:
        for type_evenement in ("mousePressed", "mouseReleased"):
            self._cdp.send("Input.dispatchMouseEvent", {
                "type": type_evenement, "x": x, "y": y, "button": "left", "clickCount": 1,
            })
