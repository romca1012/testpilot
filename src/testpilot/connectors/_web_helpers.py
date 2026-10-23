"""Perception UI PURE, partagée entre TOUS les connecteurs web (Odoo, générique, …).

Extrait de ``connectors/odoo.py`` (audit multi-connecteurs, 2026-09-08) : ces fonctions
n'ont jamais rien eu de spécifique à Odoo — elles lisent une page RENDUE (formulaire, lien,
réponse HTTP), jamais l'API RPC. Les dupliquer dans chaque nouveau connecteur aurait fait
deux endroits où corriger un bug d'extraction de formulaire (ex. un type de champ mal
reconnu) sans que le second ne le sache jamais.

``odoo.py`` réexporte ``build_probe_url``/``extract_form`` pour ne pas casser les imports
existants (``from testpilot.connectors.odoo import build_probe_url, extract_form``).
"""

from __future__ import annotations

import logging
import re
import urllib.error
import urllib.request
from urllib.parse import urljoin

try:  # module « pur » : jamais de dépendance dure à Playwright (tests sur fausses pages)
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
except ImportError:  # pragma: no cover — sans Playwright, aucune vraie page à lire non plus
    PlaywrightError = Exception

    class PlaywrightTimeoutError(Exception):
        """Sans Playwright, personne ne lève ce type : l'attente de stabilisation n'avale alors aucune autre erreur."""

logger = logging.getLogger(__name__)

# Cas réel mesuré sur OrangeHRM (demo publique, 2026-10-01) : le champ identifiant n'a AUCUN
# attribut `type` littéral (`<input name="username">`) — HTML le traite comme texte par défaut,
# mais `input[type='text']` ne matche que l'attribut LITTÉRAL, pas la valeur IDL par défaut du
# navigateur (`getAttribute('type')` rend `null` ; seule la propriété `.type` calculée vaut
# `"text"`). `input:not([type])` couvre ce cas sans élargir à tort : un champ `password`/`hidden`/
# `checkbox`/… porte TOUJOURS son attribut `type` explicitement, donc `:not([type])` ne les
# matche jamais. Centralisé ici : les 3 usages (schéma à un écran, schéma à deux écrans, détection
# du premier écran minimal) partageaient le même défaut.
_SELECTEUR_CHAMP_TEXTE_IDENTIFIANT = "input:not([type]), input[type='text'], input[type='email']"

# Champs de formulaire à ignorer : jetons techniques, pas des champs métier.
_IGNORED_FIELD_PREFIXES = ("_",)
_IGNORED_FIELD_NAMES = {"csrf_token"}


def build_probe_url(base_url: str, path_pattern: str, sample_id: int | None = None) -> str:
    """Construit l'URL absolue à sonder. Pur (aucun réseau).

    ``{id}`` dans le motif est substitué par ``sample_id`` s'il est fourni.
    """
    pattern = path_pattern or "/"
    if "{id}" in pattern and sample_id is not None:
        pattern = pattern.replace("{id}", str(sample_id))
    elif "{id}" in pattern:
        pattern = pattern.replace("{id}", "")
    return urljoin(base_url.rstrip("/") + "/", pattern.lstrip("/"))


def extract_form(page) -> dict:
    """Extrait champs + mécanisme de soumission d'une page rendue. Pur vis-à-vis du réseau.

    ``page`` est un objet duck-typé (Playwright Page ou fake de test) exposant
    ``query_selector_all`` / ``query_selector``. Retour :
    ``{fields:[{name,required,type[,cadre]}], submission:{mechanism,endpoint,trigger_selector}}``.
    """
    return _extraire_formulaire(page)


def _champs(racine, cadre: list[str] | None = None) -> list[dict]:
    """Les champs d'un document (la page, ou un cadre : un `Frame` Playwright expose les mêmes `query_selector_all`)."""
    fields: list[dict] = []
    seen: set[str] = set()
    for el in racine.query_selector_all("input, select, textarea"):
        name = el.get_attribute("name") or el.get_attribute("id") or ""
        if not name or name in seen:
            continue
        if name in _IGNORED_FIELD_NAMES or name.startswith(_IGNORED_FIELD_PREFIXES):
            continue
        seen.add(name)
        tag = (el.get_attribute("__tag__") or "").lower()  # fake de test
        input_type = el.get_attribute("type") or tag or "text"
        fields.append({
            "name": name,
            "required": el.get_attribute("required") is not None,
            "type": input_type,
        })
        if cadre:
            fields[-1]["cadre"] = list(cadre)
        if hasattr(el, 'evaluate'):
            fields[-1].update(el.evaluate('''el => ({
                tag: el.tagName.toLowerCase(),
                label: el.labels?.[0]?.textContent?.trim() || el.getAttribute('aria-label') || '',
                visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
                options: el.tagName === 'SELECT' ? Array.from(el.options).map(
                    o => [o.value, o.textContent.trim()]) : [],
                min: el.getAttribute('min'), max: el.getAttribute('max'),
                maxlength: el.getAttribute('maxlength'), pattern: el.getAttribute('pattern'),
                minlength: el.getAttribute('minlength'), inputmode: el.getAttribute('inputmode'),
                placeholder: el.getAttribute('placeholder'), title: el.getAttribute('title'),
                data_mask: el.getAttribute('data-mask'),
                inputmask: el.getAttribute('data-inputmask') || el.getAttribute('inputmask')
            })'''))
    return fields


def _cadres(page):
    """Les cadres ENFANTS de la page (ceux que `_base_helpers.cadre` atteint), avec les noms qui les désignent. Une fausse
    page de test sans `frames` n'en a aucun ; un cadre illisible (détaché, autre origine refusée) est ignoré."""
    principal = getattr(page, "main_frame", None)
    for frame in getattr(page, "frames", None) or []:
        if frame is principal or getattr(frame, "parent_frame", None) is not principal:
            continue
        try:
            balise = frame.frame_element()
            noms = [v for v in (balise.get_attribute(a) for a in ("name", "title", "id")) if v]
        except PlaywrightError:
            continue
        if noms:
            yield frame, noms


def _extraire_formulaire(page) -> dict:
    fields = _champs(page)
    # Étape 2 (A61, 2026-10-20) : les champs d'un cadre (iframe) enfant de la page, marqués du nom du cadre (`name`, `title`
    # ou `id` de la balise — la règle même de `_base_helpers.cadre` à l'exécution). Sans eux, un test qui saisit « dans le
    # cadre "X" » n'avait jamais de preuve et restait à relire.
    for frame, noms in _cadres(page):
        # Revue (C2) : un cadre de publicité ou de consentement qui se recharge pendant le relevé ne doit pas effacer les
        # champs de la page principale.
        try:
            fields += _champs(frame, cadre=noms)
        except PlaywrightError:
            continue

    submission = _detect_submission(page)
    html = page.query_selector('html')
    return {"fields": fields, "submission": submission, "liens": _liens_visibles(page),
            "url": getattr(page, 'url', ''),
            "language": html.get_attribute('lang') or '' if html else ''}


def _liens_visibles(page) -> list:
    """Textes des liens VISIBLES (≤ 60 liens, ≤ 80 caractères chacun) — le catalogue d'une page
    (lot 12). Best-effort : une page factice sans `evaluate` (tests) ou un échec rend `[]`."""
    evaluer = getattr(page, "evaluate", None)
    if evaluer is None:
        return []
    try:
        liens = evaluer("""() => Array.from(new Set(Array.from(document.querySelectorAll('a[href]'))
            .filter(a => a.offsetWidth || a.offsetHeight || a.getClientRects().length)
            .map(a => (a.innerText || a.getAttribute('title') || '').trim().replace(/\\s+/g, ' '))
            .filter(t => t && t.length <= 80))).slice(0, 60)""")
    except Exception:
        return []
    return liens if isinstance(liens, list) else []


def _detect_submission(page) -> dict:
    """Déduit le mécanisme de soumission : endpoint du <form> + sélecteur déclencheur."""
    form = page.query_selector("form")
    endpoint = form.get_attribute("action") if form else ""
    trigger = page.query_selector("button[type='submit'], input[type='submit'], button.btn-primary")
    trigger_selector = ""
    if trigger is not None:
        name = trigger.get_attribute("name")
        # Ne pas inventer un bouton submit si seul un bouton JS a été observé.
        trigger_selector = f"[name='{name}']" if name else ''
        if not name and trigger.get_attribute('type') == 'submit':
            trigger_selector = "button[type='submit'], input[type='submit']"
    return {
        "mechanism": "button_click" if trigger is not None else "unknown",
        "endpoint": endpoint or "",
        "trigger_selector": trigger_selector,
    }


class ConnexionGeneriqueImpossibleError(Exception):
    """Ni le schéma à UN écran (identifiant + mot de passe ensemble) ni celui à DEUX écrans
    (identifiant seul, puis mot de passe sur l'écran suivant) n'a permis de repérer un formulaire
    de connexion exploitable — étape 3.1 du plan de consolidation (2026-09-15, audit « Le pari
    Mabl/Testim »). Le cas le plus probable est un SSO/un second facteur (2FA), tous deux hors du
    périmètre d'une détection générique par champs de formulaire : un jeton de session externe ou
    un code à usage unique ne sont pas des données que `user`/`password` peuvent fournir.

    ⚠️ **Une classe DÉDIÉE, plutôt qu'un retour `False` silencieux comme avant cette étape** — un
    échec d'authentification à ce stade laissait l'exploration/la perception continuer SANS
    connexion, sans que rien ne dise pourquoi, ce qui produit un annuaire ou une inspection de
    formulaire mesurée sur la mauvaise page (celle de connexion) sans le moindre signal distinct
    d'un « pas de connexion nécessaire ici » légitime.
    """


class SequenceConnexionObsoleteError(Exception):
    """Une étape de la séquence de connexion enregistrée (lot « Enregistrement assisté du chemin
    de connexion », sous-lot D) ne se retrouve plus, ou n'identifie plus un élément UNIQUE, sur la
    page rejouée — l'application a changé depuis l'enregistrement. Jamais une tentative silencieuse
    de deviner autre chose à sa place (étape 8 de la consigne) : la personne doit refaire
    l'enregistrement.
    """


# ── Confirmation post-connexion : `networkidle` seul ne suffit pas (cause réelle du crawl
# bloqué à 3 routes sur `yros`, mesuré et diagnostiqué le 2026-09-30) ────────────────────────────
#
# ⚠️ **Pourquoi ceci existe.** `page.wait_for_load_state("networkidle")`, appelé juste après le
# clic sur le bouton de connexion, ne détecte AUCUNE navigation à attendre quand l'authentification
# répond par un `fetch`/XHR suivi d'une redirection côté client (History API) — cas courant d'une
# SPA moderne. Mesuré sur une reproduction locale : juste après `networkidle`, `page.url` pointe
# encore sur la page de connexion ; la vraie redirection arrive ~0.6s plus tard. L'appelant
# (`crawl_roots`, `connexion_reussie`) lisait alors l'URL/le DOM de la page de connexion — le crawl
# repartait du même endroit qu'avant la connexion, sans lever la moindre erreur.
_PAS_ATTENTE_POST_CONNEXION_MS = 100
# 100 × 100 ms = 10 s bornées, jamais un blocage indéfini. Était 2 s (20 itérations) jusqu'au
# 2026-10-01 : cas réel « yros » — le backend d'authentification (un proxy tiers, pas l'origine de
# la page) met jusqu'à ~8 s à répondre, largement au-delà des 2 s initiales. Mesuré via une attente
# diagnostique de 8 s qui, une fois ajoutée, a laissé l'exploration aboutir (10 routes mesurées,
# contre 1 seule — la page de connexion elle-même — auparavant). Sans conséquence sur les
# applications rapides (SauceDemo, OrangeHRM…) : la boucle sort dès que la confirmation est
# obtenue, elle n'attend la borne maximale que si l'application la justifie réellement.
_ITERATIONS_ATTENTE_POST_CONNEXION = 100

# Cas réel « yros » (2026-10-01) : un bouton à deux états (« Sélectionner » → « Choisi ») dont le
# LIBELLÉ change immédiatement, mais dont la confirmation RÉELLE (acceptée par l'application, pas
# seulement affichée) suit avec un court délai. Un humain laisse naturellement ce délai s'écouler
# entre deux clics ; `rejouer_sequence_connexion` les enchaînait sans aucune pause, assez vite pour
# cliquer l'étape suivante avant que la confirmation réelle n'ait eu lieu — l'étape suivante
# s'exécutait alors sur un état pas encore réellement acquis, sans jamais lever d'erreur (confirmé
# par les journaux de production : les 3 étapes enregistrées se rejouent sans exception, mais la
# page reste sur l'écran de pré-connexion). Délai FIXE, pas une attente réseau
# (`wait_for_load_state`) : la confirmation peut être purement côté client (JS), sans aucun appel
# serveur à attendre.
_DELAI_ENTRE_ETAPES_SEQUENCE_MS = 300

# Plafond de l'attente de stabilisation de la page AVANT LE PREMIER clic rejoué. Mesuré le
# 2026-10-07 sur la page de connexion SSO du portail d'intégration Odoo : un clic envoyé juste après
# `domcontentloaded` (c'est ce que fait `odoo_login.playwright_login`) tombe avant que le JavaScript
# de la page ait fini d'initialiser son formulaire — le bloc s'ouvre puis est refermé, le champ
# reste invisible et le rejeu échoue sur « champ introuvable ». Mesure : 4 essais sur l'instance
# d'intégration, navigateur neuf à chaque fois — clic immédiat : champ invisible 4/4 ; clic après
# stabilisation (≤ 4 s) : visible 4/4. Coût : ≥ 0,5 s, jusqu'à 4 s si la page n'est jamais « idle »
# (Odoo, bus de long-polling : la borne l'empêche de bloquer).
_STABILISATION_AVANT_PREMIER_CLIC_MS = 4000


# Cas réel « yros » (2026-10-06, régression de l'exploration à 3 routes) : à l'envoi, le formulaire
# est REMPLACÉ par un état de chargement — le champ mot de passe disparaît donc tout de suite — alors
# que la réponse du proxy d'authentification n'arrive que ~8 s plus tard. « Champ mot de passe
# disparu » seul sortait de l'attente trop tôt et le crawl partait non authentifié. On exige donc
# aussi que les requêtes XHR/fetch lancées par l'envoi soient terminées. Signal RUNTIME (événements
# réseau de Playwright), jamais un texte affiché.
_TYPES_REQUETES_SUIVIES = frozenset({"xhr", "fetch", "document"})
# Itérations CONSÉCUTIVES sans requête en cours exigées avant de conclure (une redirection ou un
# second appel peut démarrer juste après la fin du premier).
_PAS_CALMES_REQUIS = 3
# Quand SEUL le champ a disparu (URL inchangée), la requête d'authentification peut ne partir que
# quelques centaines de ms après (état de chargement d'abord, `fetch` ensuite — chronologie yros :
# POST émis au moment où l'ancien code rendait déjà la main) : 1 s de calme exigée.
_PAS_CALMES_REQUIS_URL_INCHANGEE = 10
# 150 × 100 ms = 15 s : marge au-dessus des ~8 s mesurés, toujours bornée.
_ITERATIONS_ATTENTE_POST_CONNEXION_AVEC_SUIVI = 150


class _SuiviRequetes:
    """Compte les requêtes XHR/fetch/document démarrées et pas encore terminées.

    Sans `page.on` (doubles de test, pages exotiques) : se dégrade en « rien en cours », donc au
    comportement historique de `_attendre_confirmation_post_connexion`.
    """

    def __init__(self, page) -> None:
        self._page = page
        self._en_cours: set[int] = set()
        self.actif = False
        self._abonnements: list[tuple[str, object]] = []

    @staticmethod
    def _suivie(requete) -> bool:
        return getattr(requete, "resource_type", None) in _TYPES_REQUETES_SUIVIES

    def _debut(self, requete) -> None:
        if self._suivie(requete):
            self._en_cours.add(id(requete))

    def _fin(self, requete) -> None:
        self._en_cours.discard(id(requete))

    @property
    def en_cours(self) -> int:
        return len(self._en_cours)

    def __enter__(self) -> "_SuiviRequetes":
        on = getattr(self._page, "on", None)
        if not callable(on):
            return self
        try:
            for evenement, rappel in (("request", self._debut), ("requestfinished", self._fin),
                                      ("requestfailed", self._fin)):
                on(evenement, rappel)
                self._abonnements.append((evenement, rappel))
            self.actif = True
        except Exception:  # pragma: no cover — dégradation silencieuse, jamais bloquante
            logger.debug("[connexion] suivi des requêtes indisponible", exc_info=True)
        return self

    def __exit__(self, *exc) -> None:
        retirer = getattr(self._page, "remove_listener", None)
        if callable(retirer):
            for evenement, rappel in self._abonnements:
                try:
                    retirer(evenement, rappel)
                except Exception:  # pragma: no cover
                    pass
        self._abonnements.clear()


def _confirmation_post_connexion_obtenue(page, url_avant: str) -> bool:
    """Un signe RUNTIME que la tentative de connexion a progressé — jamais un texte affiché.

    L'URL a changé OU le champ mot de passe a disparu du DOM : une SPA peut faire l'un sans
    l'autre (redirection sans changement visible de formulaire, ou inverse), donc `OR`, jamais
    les deux à la fois.
    """
    try:
        return page.url != url_avant or page.query_selector("input[type='password']") is None
    except PlaywrightError:
        # Cas réel mesuré sur OrangeHRM (démo publique, 2026-10-06) : juste après l'envoi du formulaire,
        # la page REDIRIGE en changeant de document — `query_selector` lève alors « Unable to adopt
        # element handle from a different document » en plein sondage. Ce n'est ni une réussite ni un
        # échec de connexion : la navigation est simplement en cours. « Pas encore confirmé » (False) et on
        # re-sonde au tour suivant ; jamais « confirmé » sur une erreur (pas de faux succès), et la
        # promesse de `_attendre_confirmation_post_connexion` (« ne lève jamais ») est enfin tenue.
        return False


def _attendre_confirmation_post_connexion(page, url_avant: str,
                                          suivi: "_SuiviRequetes | None" = None) -> None:
    """Complète `networkidle` par un signe RUNTIME borné — ne lève jamais : au pire, rend
    la main après le délai sans certitude. C'est à l'appelant (`connexion_reussie`,
    `crawl_roots`) de juger l'état obtenu, jamais à cette fonction de décider si la connexion
    a réussi.

    Avec `suivi` actif, la confirmation n'est acceptée que lorsque plus aucune requête
    XHR/fetch lancée par l'envoi n'est en cours (voir `_SuiviRequetes`) : un formulaire qui
    disparaît pendant le chargement n'est PAS une connexion obtenue.
    """
    suivi_actif = suivi is not None and suivi.actif
    bornes = (_ITERATIONS_ATTENTE_POST_CONNEXION_AVEC_SUIVI if suivi_actif
              else _ITERATIONS_ATTENTE_POST_CONNEXION)
    calmes = 0
    for _ in range(bornes):
        if _confirmation_post_connexion_obtenue(page, url_avant):
            if not suivi_actif:
                return
            calmes = calmes + 1 if suivi.en_cours == 0 else 0
            requis = (_PAS_CALMES_REQUIS if page.url != url_avant
                      else _PAS_CALMES_REQUIS_URL_INCHANGEE)
            if calmes >= requis:
                return
        else:
            calmes = 0
        page.wait_for_timeout(_PAS_ATTENTE_POST_CONNEXION_MS)


# Même valeur que `testpilot.generation.accname.ROLE_DEPLIANT` (dupliquée, pas importée : ce module
# tourne aussi dans le sous-processus Behave, qui ne dépend pas du paquet de génération) — l'égalité
# des deux est verrouillée par `tests/test_etape_depliant.py`.
ROLE_DEPLIANT = "summary"


def localiser_etape(page, role: str, name: str):
    """Le `Locator` d'une étape enregistrée (`{"role", "name"}`).

    Un rôle ARIA passe par `get_by_role(..., exact=True)` (voir `rejouer_sequence_connexion` pour
    le pourquoi d'`exact`). Le jeton `ROLE_DEPLIANT` (`summary`, bascule d'un bloc
    dépliant) n'existe pas côté Playwright : on retrouve le `<summary>` dont le texte est EXACTEMENT
    le nom enregistré — blancs normalisés des deux côtés, jamais une sous-chaîne (même garde contre
    un clic réussi sur le mauvais élément). L'unicité est exigée au clic par le mode strict de
    Playwright, comme pour `get_by_role`.

    Limite connue : cliquer un bloc déjà ouvert le REFERME (bascule non idempotente). Si
    l'application l'ouvre par défaut au rejeu alors qu'il était fermé à l'enregistrement, les champs
    restent invisibles : l'échec est bruyant (`FormulaireConnexionObsoleteError`), jamais silencieux.
    """
    if role == ROLE_DEPLIANT:
        motif = r"^\s*" + r"\s+".join(re.escape(mot) for mot in name.split()) + r"\s*$"
        # `visible=True` : comme `get_by_role`, qui ignore les éléments masqués (un bloc dupliqué en
        # `display:none` pour une variante mobile ne doit pas rendre le rejeu ambigu).
        return page.locator("summary").filter(has_text=re.compile(motif)).filter(visible=True)
    return page.get_by_role(role, name=name, exact=True)


def _laisser_la_page_se_stabiliser(page) -> None:
    """Attente BORNÉE que la page ait fini de s'initialiser avant le premier clic rejoué : un clic
    trop tôt est annulé par le JavaScript de la page, sans la moindre erreur (voir
    `_STABILISATION_AVANT_PREMIER_CLIC_MS`). Un dépassement n'est pas une erreur : on rejoue quand
    même, le clic échouera bruyamment s'il le faut. Une page sans `wait_for_load_state` (doublure de
    test) est laissée telle quelle."""
    attendre = getattr(page, "wait_for_load_state", None)
    if not callable(attendre):
        return
    try:
        attendre("networkidle", timeout=_STABILISATION_AVANT_PREMIER_CLIC_MS)
    except PlaywrightTimeoutError:
        logger.debug("[connexion] page jamais « idle » en %s ms — le chemin est rejoué quand même",
                     _STABILISATION_AVANT_PREMIER_CLIC_MS)


def rejouer_sequence_connexion(page, etapes: list[dict], *, timeout_ms: int = 5000,
                               attendre_reseau: bool = True) -> bool:
    """Rejoue, DANS L'ORDRE, une séquence enregistrée (sous-lot C : liste de `{"role", "name"}`
    calculés par l'algorithme AccName déterministe — jamais un texte deviné) via
    ``page.get_by_role(role, name=name, exact=True).click()``. Rend ``False`` sans rien faire si
    `etapes` est vide (rien n'a jamais été enregistré pour ce projet — comportement historique
    inchangé).

    Précède `tenter_connexion_generique`, ne le remplace pas : fait seulement franchir un éventuel
    écran intercalé AVANT le formulaire de connexion (sélection de pays, bannière…) — le
    remplissage identifiant/mot de passe reste la responsabilité de `tenter_connexion_generique`,
    appelée juste après par l'appelant.

    ⚠️ **`exact=True` est OBLIGATOIRE ici** — bloquant trouvé et vérifié avec un vrai Chromium en
    revue verdict-reviewer (2026-09-29) : sans lui, `get_by_role` fait par défaut un matching PAR
    SOUS-CHAÎNE et insensible à la casse (« FRANCE » matche un `name` enregistré « France », un
    bouton renommé « Continuer votre progression… » matche toujours un `name` enregistré
    « Continuer »). Un clic aurait alors réussi SANS LEVER, sur un élément qui n'est plus le bon —
    exactement le « repli silencieux sur une autre hypothèse » que l'étape 8 de la consigne
    interdit. `exact=True` retombe sur l'égalité stricte du nom accessible calculé par AccName
    (sous-lot A), seule comparaison cohérente avec ce que `accname.calculer` a réellement mesuré.

    Un élément introuvable OU ambigu (`get_by_role` retrouve plusieurs correspondances — Playwright
    lève déjà en mode strict par défaut) arrête net avec `SequenceConnexionObsoleteError` : jamais
    de repli sur une hypothèse, jamais de nouvelle tentative en boucle (garde-fou étape 9, un seul
    essai par session — c'est l'APPELANT qui décide de ne jamais réessayer, cette fonction ne
    boucle déjà pas elle-même).

    `attendre_reseau=False` (extension 2026-09-30, essai connecteur Odoo) : certaines applications
    (Odoo, bus de long-polling) ne stabilisent JAMAIS `networkidle` — l'attendre quand même y
    coûterait le timeout complet à chaque appel, pour rien. L'appelant qui sait déjà comment
    reconnaître SA propre fin de navigation (ex. `page.wait_for_url(...)`, comme
    `odoo_login.py::playwright_login`) désactive cette attente et fait la sienne juste après.

    ⚠️ **Une courte pause FIXE suit chaque clic** (`_DELAI_ENTRE_ETAPES_SEQUENCE_MS`, 300 ms) —
    indépendante de `attendre_reseau` : un humain laisse naturellement ce temps s'écouler entre
    deux clics, le rejeu automatique ne le faisait pas et pouvait enchaîner une étape avant que la
    précédente n'ait eu le temps d'être réellement prise en compte par l'application (cas réel
    « yros », 2026-10-01 — voir la constante). Volontairement un délai TEMPOREL, pas une attente
    réseau : la confirmation visée peut être purement côté client, sans aucun appel serveur.
    """
    if not etapes:
        return False
    _laisser_la_page_se_stabiliser(page)
    for etape in etapes:
        role, name = etape.get("role", ""), etape.get("name", "")
        try:
            localiser_etape(page, role, name).click(timeout=timeout_ms)
        except Exception as exc:
            raise SequenceConnexionObsoleteError(
                f"étape enregistrée « rôle={role!r}, nom={name!r} » introuvable ou ambiguë sur "
                f"{getattr(page, 'url', '?')} — l'application a changé depuis l'enregistrement du "
                "chemin de connexion. Refaites l'enregistrement (session en direct) avant de "
                "relancer.") from exc
        page.wait_for_timeout(_DELAI_ENTRE_ETAPES_SEQUENCE_MS)
    if attendre_reseau:
        page.wait_for_load_state("networkidle")
    return True


def _ressemble_a_un_premier_ecran_de_connexion(page) -> bool:
    """Un écran minimal — EXACTEMENT un champ texte/email, plus un contrôle de soumission — pas
    n'importe quelle page qui porte un champ texte quelconque (recherche, newsletter…).

    ⚠️ **Ce garde existe pour éviter un FAUX POSITIF du schéma à deux écrans** (étape 3.1) : sans
    lui, la détection soumettrait n'importe quel champ texte/email trouvé sur une page SANS mot de
    passe, en pariant qu'il s'agit d'un premier écran de connexion — un pari qui se paierait cher
    sur une page de recherche ou d'inscription à une newsletter. Un vrai premier écran de connexion
    à deux étapes (ex. Google, Microsoft) est délibérément minimal ; ce n'est pas le cas d'une page
    de contenu ordinaire qui porte un champ texte parmi d'autres.
    """
    champs = page.query_selector_all(_SELECTEUR_CHAMP_TEXTE_IDENTIFIANT)
    if len(champs) != 1:
        return False
    return page.query_selector("button, input[type='submit']") is not None


# Une page ouverte en `domcontentloaded` n'a, pour une application à rendu côté client (Vue, React…), souvent
# RIEN rendu encore. Mesuré le 2026-10-06 sur OrangeHRM (démo publique) : à l'instant où le runtime tentait la
# connexion, la page affichait 0 champ, 0 élément interactif, 0 texte ; le formulaire n'apparaissait qu'environ
# 0,5 s plus tard. La détection concluait « pas de formulaire », ne soumettait rien, et les 4 cas du banc étaient
# `blocked` — alors que la même connexion aboutit dès qu'on attend l'affichage du formulaire.
_PAS_ATTENTE_RENDU_MS = 100
# 80 × 100 ms = 8 s bornées. Une page qui n'a TOUJOURS aucun élément interactif au bout de 8 s n'a pas de
# formulaire à remplir : la détection continue alors comme avant (au pire, 8 s de latence, jamais un blocage).
_ITERATIONS_ATTENTE_RENDU = 80
# Une page qui affiche déjà du TEXTE mais aucun élément interactif est, le plus souvent, une page rendue qui n'en a pas
# (page d'accueil statique). Mesuré le 2026-10-12 : l'attendre 8 s coûtait 8 s à CHAQUE scénario dont la page d'entrée
# n'a ni champ, ni bouton, ni lien (contrôle navigateur de la CI : 8 min -> plus de 15, job annulé ; un test d'un seul
# scénario : 6,6 s -> 14,7 s). La borne longue ne vaut donc que pour une page encore VIDE — le cas mesuré sur OrangeHRM
# (0 champ, 0 élément interactif, 0 texte). Avec du texte, un court délai de grâce couvre un écran d'attente bref.
_ITERATIONS_GRACE_AVEC_TEXTE = 10   # 1 s
_SELECTEUR_ELEMENT_INTERACTIF = "input, button, select, textarea, a[href]"


def attendre_page_rendue(page) -> bool:
    """Attend, de façon BORNÉE, que la page ait rendu au moins un élément interactif.

    Rend `True` dès qu'il y en a un (aussitôt si la page est déjà rendue : aucune latence pour SauceDemo,
    par exemple), `False` si la borne est atteinte : 8 s pour une page encore VIDE, 1 s de grâce pour une page
    qui affiche déjà du texte sans élément interactif. Ne lève jamais : une erreur de navigation de Playwright
    (document remplacé pendant le sondage) vaut « pas encore rendu », comme dans
    `_confirmation_post_connexion_obtenue`. N'attend jamais sur `about:blank` (aucune page à rendre).

    ⚠️ Ne décide RIEN sur la connexion : elle laisse seulement à la page le temps d'exister avant que la
    détection ne la lise. Le critère de réussite d'une connexion (`connexion_reussie`) est inchangé — pas de
    faux succès possible par cette voie."""
    if not (getattr(page, "url", "") or "") or str(page.url).startswith("about:"):
        return False
    sondages_avec_texte = 0
    for _ in range(_ITERATIONS_ATTENTE_RENDU):
        try:
            if page.query_selector(_SELECTEUR_ELEMENT_INTERACTIF) is not None:
                return True
            if _page_affiche_du_texte(page):
                sondages_avec_texte += 1
                if sondages_avec_texte > _ITERATIONS_GRACE_AVEC_TEXTE:
                    return False   # rendue, sans élément interactif : rien de plus à attendre
        except PlaywrightError:
            pass  # document en cours de remplacement : on re-sonde au tour suivant
        page.wait_for_timeout(_PAS_ATTENTE_RENDU_MS)
    return False


def _page_affiche_du_texte(page) -> bool:
    """La page a-t-elle rendu du texte visible ? Une page sans `evaluate` (doublure de test) est tenue pour vide : la
    borne longue s'applique, comme avant."""
    evaluer = getattr(page, "evaluate", None)
    if not callable(evaluer):
        return False
    return bool(evaluer("() => !!(document.body && document.body.innerText && document.body.innerText.trim())"))


def tenter_connexion_generique(page, user: str, password: str) -> bool:
    """Détection de connexion GÉNÉRIQUE (pas de convention d'URL à connaître, à la différence
    d'Odoo) — partagée entre ``GenericWebConnector`` (exécution) et le crawl générique
    (exploration, audit multi-connecteurs 2026-09-08) : les deux affrontent le même problème,
    « repérer un formulaire de connexion sur une page qu'on n'a jamais vue ».

    **Schéma à UN écran** (historique, comportement inchangé) : un mot de passe est l'identifiant
    le plus fiable d'un formulaire de connexion — on cherche ``input[type=password]``, on prend le
    premier champ texte/email de la PAGE comme identifiant (scope volontairement simple, pas un
    `closest('form')` — un premier jet à affiner si un formulaire réel la met en défaut), on
    remplit et on valide.

    **Schéma à DEUX écrans** (étape 3.1 du plan de consolidation, 2026-09-15 — de nombreuses
    applications SaaS modernes, ex. Google/Microsoft, demandent l'identifiant seul avant de
    révéler le mot de passe sur un second écran) : si aucun mot de passe n'apparaît mais que la
    page RESSEMBLE à un premier écran minimal (`_ressemble_a_un_premier_ecran_de_connexion`), on
    soumet l'identifiant seul puis on cherche le mot de passe sur l'écran suivant. Ni l'un ni
    l'autre schéma ne matchant (SSO/2FA) → `ConnexionGeneriqueImpossibleError`, explicite et
    distincte, plutôt qu'un échec silencieux dans un état ambigu.

    Identifiant/mot de passe VIDES, ou aucun indice de formulaire de connexion sur la page : on
    considère l'application accessible sans connexion et on continue tel quel — mieux vaut
    explorer sans authentification que de bloquer sur une hypothèse de connexion fausse.

    Retourne ``True`` si une tentative a réellement été soumise (jamais si la page ou les
    identifiants ne s'y prêtaient pas).

    Après la soumission FINALE (mot de passe rempli), `networkidle` est complété par une attente
    bornée d'un signe RUNTIME que la connexion a progressé (URL changée ou champ mot de passe
    disparu) — voir `_attendre_confirmation_post_connexion` : `networkidle` seul ne détecte rien
    quand l'authentification répond par `fetch`/XHR puis redirige côté client (SPA), cause mesurée
    du crawl qui repart de la page de connexion (`yros`, 2026-09-30).
    """
    if not user or not password:
        return False

    attendre_page_rendue(page)
    url_avant = getattr(page, "url", "")
    champ_mdp = page.query_selector("input[type='password']")
    if champ_mdp is not None:
        champ_identifiant = page.query_selector(_SELECTEUR_CHAMP_TEXTE_IDENTIFIANT)
        if champ_identifiant is None:
            logger.warning("[connexion-générique] mot de passe détecté sans champ identifiant"
                            " — connexion non tentée")
            return False
        with _SuiviRequetes(page) as suivi:
            champ_identifiant.fill(user, force=True)
            champ_mdp.fill(password, force=True)
            champ_mdp.press("Enter")
            page.wait_for_load_state("networkidle")
            _attendre_confirmation_post_connexion(page, url_avant, suivi)
        return True

    if not _ressemble_a_un_premier_ecran_de_connexion(page):
        return False  # pas d'indice de connexion du tout : comportement historique inchangé

    champ_identifiant_seul = page.query_selector(_SELECTEUR_CHAMP_TEXTE_IDENTIFIANT)
    champ_identifiant_seul.fill(user, force=True)
    champ_identifiant_seul.press("Enter")
    page.wait_for_load_state("networkidle")

    champ_mdp_ecran_suivant = page.query_selector("input[type='password']")
    if champ_mdp_ecran_suivant is None:
        raise ConnexionGeneriqueImpossibleError(
            "aucun champ mot de passe trouvé après soumission de l'identifiant sur "
            f"{getattr(page, 'url', '?')} — probablement un SSO/second facteur (2FA), hors du "
            "périmètre de cette détection générique.")
    url_avant_ecran_2 = getattr(page, "url", "")
    with _SuiviRequetes(page) as suivi:
        champ_mdp_ecran_suivant.fill(password, force=True)
        champ_mdp_ecran_suivant.press("Enter")
        page.wait_for_load_state("networkidle")
        _attendre_confirmation_post_connexion(page, url_avant_ecran_2, suivi)
    return True


# ── Lire un message d'erreur réellement affiché (2026-09-16 — audit « Le pari Mabl/Testim »,
# amendement §4.3-bis étendu) ─────────────────────────────────────────────────────────────────
#
# ⚠️ **Pourquoi ceci existe.** Un cas généré affirmait qu'un compte verrouillé affiche « Sorry,
# this user has been locked out. » — l'application affiche en réalité « Epic sadface: Sorry,
# this user has been locked out. ». L'agent avait DEVINÉ ce texte depuis sa mémoire d'entraînement
# au lieu de l'observer : rien dans le pipeline de génération ne lit jamais le DOM réel avant
# d'écrire une assertion sur un texte affiché (`inspect_page_form`/`discover_route` n'observent
# que la STRUCTURE des formulaires, jamais leur CONTENU). Playwright Codegen — l'outil officiel
# équivalent — ne demande JAMAIS ce texte à l'auteur : il lit l'`innerText` réel de l'élément visé
# au moment de l'enregistrement. On applique le même principe ici : observer avant d'écrire.

_SELECTEURS_MESSAGE_ERREUR = (
    '[role="alert"], .error, .alert-danger, .is-invalid, '
    ".o_notification.border-danger, [class*='s_website_form_field'].o_has_error, "
    "[class*='bg-red-'], [class*='text-red-'], [class*='border-red-']"
)
# ⚠️ Les 3 derniers motifs couvrent la convention Tailwind CSS très répandue pour un état
# d'erreur/danger (`bg-red-50`, `text-red-700`, `border-red-500`…) — cas réel mesuré (2026-10-01,
# diagnostic « yros ») : un bandeau d'erreur réel (`<div class="... bg-red-50 border-l-4
# border-red-500 text-red-700 ...">Informations de connexion incorrectes</div>`) sans AUCUN
# `role="alert"` ni classe Bootstrap/Odoo, invisible à la liste précédente. Générique à toute
# application Tailwind, pas spécifique à une instance cliente (§6 CLAUDE.md).
# ⚠️ MÊME liste, au caractère près, que `behave_runtime/steps_library/_base_helpers.py::
# validation_error_inline` — validée contre DEUX applications réelles distinctes (SauceDemo :
# `[role="alert"]` ; the-internet.herokuapp.com : `.error`), durcie le 2026-09-14 après un faux
# négatif réel. Dupliquée ici plutôt qu'importée : `_base_helpers` vit hors du paquet `testpilot`
# (voir `OdooConnector.crawl_relogin_hook`, même contrainte) et n'est chargeable qu'après un
# montage de `sys.path` que ce module, appelé bien plus tôt (génération), n'a aucune raison de
# faire. Toute évolution de cette liste doit être reportée dans les deux fichiers.


def lire_message_erreur_visible(page) -> str:
    """Le texte du premier message d'erreur VISIBLE et NON VIDE, ou `""` si aucun ne l'est.

    ⚠️ **Un élément peut matcher le sélecteur, être visible, ET n'avoir aucun texte** — vérifié en
    conditions réelles sur SauceDemo (2026-09-16) : la bannière d'erreur s'y compose de plusieurs
    éléments `.error`/`[role="alert"]` imbriqués, dont un conteneur vide et le bouton « X » de
    fermeture (lui aussi visible, lui aussi sans texte) AVANT le `<h3 data-test="error">` qui
    porte le vrai message. S'arrêter au premier élément VISIBLE, sans regarder s'il a du texte,
    aurait rendu une chaîne vide au lieu du message réel — on continue donc tant que le texte lu
    est vide, jamais seulement tant que l'élément est invisible.

    Best-effort, jamais fatal : un élément qui disparaît entre le comptage et la lecture est
    ignoré, pas une exception qui remonte."""
    candidats = page.locator(_SELECTEURS_MESSAGE_ERREUR)
    for i in range(min(candidats.count(), 8)):
        try:
            candidat = candidats.nth(i)
            if not candidat.is_visible():
                continue
            texte = candidat.inner_text().strip()
            if texte:
                return texte
        except Exception:
            continue
    return ""


class FormulaireConnexionObsoleteError(Exception):
    """Un des 3 rôles/noms enregistrés (champ identifiant, champ mot de passe, bouton de
    soumission — capturés par 3 clics guidés, `live_session_service.py`) ne se retrouve plus, ou
    n'identifie plus un élément UNIQUE, sur la page rejouée — l'application a changé depuis
    l'enregistrement. Même esprit que `SequenceConnexionObsoleteError` (sous-lot D) : jamais une
    tentative silencieuse de deviner autre chose à la place, jamais un repli à MI-CHEMIN sur
    `tenter_connexion_generique` (un identifiant rempli via le bon champ enregistré, puis un mot de
    passe rempli au hasard par une détection différente, serait pire que ne rien tenter).
    """


def remplir_et_soumettre_formulaire_connexion(
        page, login_form: dict, user: str, password: str, *, timeout_ms: int = 5000,
        attendre_reseau: bool = True) -> None:
    """Remplit et soumet le formulaire de connexion via les rôles/noms ENREGISTRÉS (extension du
    lot « Enregistrement assisté du chemin de connexion », 2026-09-30) — jamais la détection
    générique par balayage du DOM (`tenter_connexion_generique`), qui devine le champ identifiant
    par premier match DOM et soumet à l'aveugle via la touche Entrée : deux paris qui ont raté sur
    une application réelle en production, malgré des identifiants valides (staging, 2026-09-30 —
    voir `docs/RAPPORT-CORRECTIF-WEBSOCKETS-DEPENDANCE-MANQUANTE-2026-09-30.md` pour le contexte
    de la même campagne de diagnostic, bug distinct).

    ``get_by_role(role, name=name, exact=True)`` — même garde que `rejouer_sequence_connexion`
    (sous-lot D) : `exact=True` retombe sur l'égalité stricte du nom accessible calculé par
    AccName, seule comparaison cohérente avec ce que la capture a réellement mesuré (sans lui,
    un `name` enregistré « Se connecter » matcherait aussi un bouton renommé « Se connecter à
    votre espace », par sous-chaîne — un clic réussirait alors SANS LEVER sur un élément qui n'est
    peut-être plus le bon).

    Un rôle/nom introuvable ou ambigu arrête net avec `FormulaireConnexionObsoleteError` — c'est à
    l'APPELANT de décider s'il retente autre chose (ex. `tenter_connexion_generique`), cette
    fonction ne boucle jamais elle-même et ne retente jamais une autre hypothèse en silence.

    `attendre_reseau=False` — même paramètre, même raison que `rejouer_sequence_connexion` :
    certaines applications (Odoo, bus de long-polling) ne stabilisent jamais `networkidle`.

    Après le clic, `networkidle` est complété par une attente bornée (2 s) d'un signe RUNTIME que
    la connexion a progressé (URL changée ou champ mot de passe disparu) — voir
    `_attendre_confirmation_post_connexion` : `networkidle` seul ne détecte rien quand
    l'authentification répond par `fetch`/XHR puis redirige côté client (SPA), cause mesurée du
    crawl qui repart de la page de connexion (`yros`, 2026-09-30).
    """
    url_avant = getattr(page, "url", "")
    with _SuiviRequetes(page) as suivi:
        for cle, valeur in (("champ_identifiant", user), ("champ_mdp", password)):
            champ = login_form[cle]
            try:
                page.get_by_role(champ["role"], name=champ["name"], exact=True).fill(
                    valeur, timeout=timeout_ms)
            except Exception as exc:
                raise FormulaireConnexionObsoleteError(
                    f"champ « {cle} » (rôle={champ['role']!r}, nom={champ['name']!r}) introuvable "
                    f"ou ambigu sur {getattr(page, 'url', '?')} — l'application a changé depuis "
                    "l'enregistrement du formulaire de connexion. Refaites l'enregistrement "
                    "(session en direct) avant de relancer.") from exc

        bouton = login_form["bouton_soumission"]
        try:
            page.get_by_role(bouton["role"], name=bouton["name"], exact=True).click(
                timeout=timeout_ms)
        except Exception as exc:
            raise FormulaireConnexionObsoleteError(
                f"bouton de soumission (rôle={bouton['role']!r}, nom={bouton['name']!r}) "
                f"introuvable ou ambigu sur {getattr(page, 'url', '?')} — l'application a changé "
                "depuis l'enregistrement du formulaire de connexion. Refaites l'enregistrement "
                "(session en direct) avant de relancer.") from exc
        if attendre_reseau:
            page.wait_for_load_state("networkidle")
            _attendre_confirmation_post_connexion(page, url_avant, suivi)


def tenter_connexion_et_lire_resultat(page, user: str, password: str, *,
                                       login_form: dict | None = None) -> dict:
    """Remplit et soumet le formulaire de connexion avec CES identifiants précis (utile/erroné/
    verrouillé...), puis rend ce qui s'affiche VRAIMENT — pour que l'agent de génération vérifie
    un message avant de l'écrire dans une assertion, au lieu de le deviner.

    `login_form` (extension 2026-09-30) : si un descripteur a été enregistré pour ce projet, il
    est TOUJOURS préféré à la détection générique — même règle que `_tenter_connexion_generique`
    (`generic_web.py`). Une `FormulaireConnexionObsoleteError` est rendue comme n'importe quelle
    autre erreur d'identification (`error` porté, jamais une exception qui remonte) : ce chemin
    reste un best-effort d'OBSERVATION, jamais un chemin qui doit réussir pour continuer.

    Rend toujours un dict, jamais une exception : `error` porte la raison si l'identification a
    échoué (SSO/2FA détecté, aucun formulaire trouvé, identifiants vides, formulaire enregistré
    obsolète) — l'appelant reste alors sans donnée observée, exactement comme avant l'ajout de
    cette fonction.
    """
    if login_form:
        try:
            remplir_et_soumettre_formulaire_connexion(page, login_form, user, password)
        except FormulaireConnexionObsoleteError as exc:
            return {"submitted": False, "url": getattr(page, "url", ""), "message": "", "error": str(exc)}
        return {"submitted": True, "url": page.url, "message": lire_message_erreur_visible(page), "error": ""}
    try:
        soumis = tenter_connexion_generique(page, user, password)
    except ConnexionGeneriqueImpossibleError as exc:
        return {"submitted": False, "url": getattr(page, "url", ""), "message": "", "error": str(exc)}
    if not soumis:
        return {"submitted": False, "url": getattr(page, "url", ""), "message": "",
                "error": "aucun formulaire de connexion détecté sur cette page, ou identifiants vides"}
    return {"submitted": True, "url": page.url, "message": lire_message_erreur_visible(page), "error": ""}


# ── Soumettre un VRAI formulaire de calibration (2026-09-16 — amendement §4.3-bis étendu) ──────
#
# ⚠️ **Réservé aux formulaires qu'un connecteur sait aussi ANNULER.** Contrairement à
# `tenter_connexion_et_lire_resultat` (une connexion ne crée jamais de donnée, on peut la
# retenter à l'infini), soumettre un formulaire métier CRÉE potentiellement un enregistrement
# réel. Cette fonction n'est donc appelée que par un connecteur qui a les moyens de nettoyer
# derrière lui (Odoo, RPC `delete`) — jamais par le connecteur générique, qui n'a aucune garantie
# de suppression et refuse explicitement (`GenericWebConnector.attempt_form_submission`).

_SELECTEURS_MESSAGE_CONFIRMATION = _SELECTEURS_MESSAGE_ERREUR + ", .alert, .alert-success, .o_notification"
# ⚠️ Contrairement à `_SELECTEURS_MESSAGE_ERREUR`, `.alert` NU (sans qualificatif) est INCLUS ici
# volontairement : `validation_error_inline` l'exclut parce qu'il cherche SPÉCIFIQUEMENT une
# erreur (un `.alert` de succès y serait un faux positif). Ici, on veut n'IMPORTE QUEL message
# réellement affiché, succès ou erreur — c'est l'appelant (le test généré) qui décide ensuite ce
# que ce texte doit valoir, pas cette fonction.


def lire_message_confirmation_visible(page) -> str:
    """Comme `lire_message_erreur_visible`, élargi aux messages de SUCCÈS — l'issue attendue
    après soumission d'un formulaire de calibration n'est pas forcément une erreur."""
    candidats = page.locator(_SELECTEURS_MESSAGE_CONFIRMATION)
    for i in range(min(candidats.count(), 8)):
        try:
            candidat = candidats.nth(i)
            if not candidat.is_visible():
                continue
            texte = candidat.inner_text().strip()
            if texte:
                return texte
        except Exception:
            continue
    return ""


def soumettre_formulaire_et_lire_resultat(page, valeurs: dict) -> dict:
    """Remplit CES champs (par nom technique) sur le formulaire réel, le soumet, et rend ce qui
    s'affiche VRAIMENT. Ne nettoie RIEN (aucun accès RPC ici) : c'est à l'appelant — le seul à
    savoir identifier et supprimer ce qui vient d'être créé — de s'en charger après coup.

    Rend toujours un dict, jamais une exception. `error` porte la raison si aucun des champs
    fournis n'a été trouvé, ou si aucun déclencheur de soumission n'a été détecté.
    """
    trouves = 0
    for nom, valeur in valeurs.items():
        champ = page.query_selector(f"[name='{nom}']")
        if champ is None:
            continue
        champ.fill(str(valeur), force=True)
        trouves += 1
    if not trouves:
        return {"submitted": False, "url": getattr(page, "url", ""), "message": "",
                "error": "aucun des champs fournis n'a été trouvé sur cette page"}

    declencheur = _detect_submission(page).get("trigger_selector") or ""
    bouton = page.query_selector(declencheur) if declencheur else None
    if bouton is None:
        return {"submitted": False, "url": getattr(page, "url", ""), "message": "",
                "error": "aucun déclencheur de soumission détecté sur cette page"}

    bouton.click()
    page.wait_for_load_state("networkidle")
    return {"submitted": True, "url": page.url,
           "message": lire_message_confirmation_visible(page), "error": ""}


def http_probe(url: str) -> dict:
    """Sonde HTTP HEAD→GET. Isolée pour être surchargée hors-ligne en test.

    ⚠️ **Bug corrigé (2026-09-11, SauceDemo sur /dev).** La branche `HTTPError` RENDAIT
    immédiatement dès le HEAD, sans jamais essayer le GET annoncé par le nom de la fonction
    (« HEAD→GET ») — seule la branche `URLError`/`OSError`, elle, `continue`ait vers le GET.
    Beaucoup de serveurs (WAF, certains hébergeurs statiques) répondent 405 « Method Not Allowed »
    à un HEAD tout en servant très bien le GET correspondant : `discover_route` (outil LLM de la
    passe technique) rapportait alors une route comme cassée alors qu'elle ne l'était pas — l'IA
    prend cette observation pour un fait mesuré (§6), pas une supposition, donc une fausse alerte
    ici pouvait faire échouer ou mal orienter toute une génération. Même filet qu'`URLError` :
    on tente le GET avant de conclure quoi que ce soit, et seul l'échec du DERNIER moyen essayé
    devient le verdict rendu.
    """
    methodes = ("HEAD", "GET")
    dernier_statut, dernier_motif = 0, ""
    for i, method in enumerate(methodes):
        est_dernier = i == len(methodes) - 1
        try:
            req = urllib.request.Request(url, method=method)
            with urllib.request.urlopen(req, timeout=10) as resp:
                return {"url": url, "status": resp.status, "method": method, "note": "accessible"}
        except urllib.error.HTTPError as exc:
            dernier_statut, dernier_motif = exc.code, (exc.reason or "réponse HTTP d'erreur")
            if est_dernier:
                return {"url": url, "status": dernier_statut, "method": method, "note": dernier_motif}
            continue
        except (urllib.error.URLError, OSError) as exc:
            dernier_statut, dernier_motif = 0, str(getattr(exc, "reason", exc))
            if est_dernier:
                return {"url": url, "status": 0, "method": method,
                        "note": f"injoignable : {dernier_motif}"}
            continue
    return {"url": url, "status": dernier_statut, "method": methodes[-1], "note": dernier_motif}


# ── Instantané des éléments interactifs d'une page (lot 09, C9) ─────────────────────────────────
#
# ⚠️ **Dupliqué depuis `behave_runtime/steps_library/_adaptive_resolution.py::_JS_CANDIDATS`**,
# jamais importé : `src/testpilot` n'importe jamais `behave_runtime` (API et sous-processus
# Behave restent deux paquets séparés — même convention déjà en place pour
# `_mot_de_passe_visible`/`ElementIntrouvableError`, vérifié : aucune occurrence contraire dans
# tout le dépôt). Plafond ramené à 120 (le brief du lot) contre 200 côté résolution adaptative :
# usage différent — ici, montrer une page ENTIÈRE à l'agent de génération avant qu'il écrive un
# test, pas choisir UN candidat de clic après un échec de sélecteur.

_MAX_ELEMENTS_SNAPSHOT = 120

_JS_ELEMENTS_INTERACTIFS = """(max) => {
    const selecteur = 'input, select, textarea, button, a, [role], [tabindex]';
    const elements = Array.from(document.querySelectorAll(selecteur))
        .filter(el => el.offsetParent !== null || el.getClientRects().length > 0)
        .slice(0, max);
    return elements.map(el => {
        const label = el.labels && el.labels.length ? el.labels[0].innerText : '';
        const nom = (el.getAttribute('aria-label') || label || el.placeholder ||
                     el.innerText || el.value || el.name || '').trim().slice(0, 80);
        // Le TEXTE AFFICHÉ, quand il diffère du nom : `nom` fusionne aria-label, libellé et texte, et l'agent prenait alors un
        // nom accessible pour du texte visible (`:has-text()` ne cherche que le texte affiché). Mesuré le 2026-10-08 : un
        // bouton « Ajouter » (aria-label « Ajouter Clavier mécanique au panier ») était visé par `:has-text('Ajouter Clavier…')`.
        const texte = (el.innerText || '').trim().slice(0, 80);
        const resultat = {
            role: el.getAttribute('role') || el.tagName.toLowerCase(),
            nom: nom,
            type: el.getAttribute('type') || '',
        };
        if (texte && texte !== nom) resultat.texte = texte;
        return resultat;
    });
}"""


def elements_interactifs_visibles(page, *, max_elements: int = _MAX_ELEMENTS_SNAPSHOT) -> list[dict]:
    """Rôle + nom accessible + type de chaque élément interactif RÉELLEMENT visible sur `page` —
    jamais une image, jamais un texte deviné. Tronqué proprement à `max_elements` (défaut 120,
    lot 09) : une page normale en a bien moins, un plafond dépassé est un signe d'écran
    anormalement chargé, pas une raison de faire exploser la taille du prompt.

    Ne lève jamais : une page fermée ou un contexte détruit pendant l'évaluation rend une liste
    vide plutôt qu'une exception — perception best-effort, comme le reste de ce module.
    """
    try:
        return page.evaluate(_JS_ELEMENTS_INTERACTIFS, max_elements) or []
    except Exception as exc:
        logger.warning("[perception] instantané d'accessibilité impossible (%s)",
                       type(exc).__name__)
        return []
