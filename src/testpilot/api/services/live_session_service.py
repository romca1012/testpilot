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
import threading
import time

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

    def __init__(self, *, project: dict, queue_label: str):
        self._project = project
        self._queue_label = queue_label
        self.entrantes: queue.Queue[dict] = queue.Queue()
        self.sortantes: queue.Queue[dict] = queue.Queue()
        self.pret = threading.Event()
        self.fermee = threading.Event()
        self._fermeture_demandee = threading.Event()
        self._verrou_etapes = threading.Lock()
        self._etapes: list[dict] = []
        self._capture_active = True
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
        s'ajouter APRÈS ce vidage."""
        with self._verrou_etapes:
            self._etapes = []

    @property
    def etapes(self) -> list[dict]:
        with self._verrou_etapes:
            return list(self._etapes)

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
                    commande = self.entrantes.get(timeout=0.5)
                except queue.Empty:
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
                    if commande.get("type") == "clic":
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
        if commande.get("type") == "clic":
            self._traiter_clic(page, commande)

    def _traiter_clic(self, page, commande: dict) -> None:
        x, y = float(commande["x"]), float(commande["y"])
        resolu = None
        if self._capture_active:
            try:
                resolu = accname.calculer(page, x, y)
            except accname.ElementIntrouvableError as exc:
                # Ambigu : jamais capturé en silence sur le premier trouvé — signalé, pas retenu.
                self.sortantes.put({"type": "clic_ambigu", "detail": str(exc)})
        self._cliquer_reellement(x, y)
        if resolu is not None:
            with self._verrou_etapes:
                self._etapes.append(resolu)
            self.sortantes.put({"type": "etape_capturee", **resolu})
        if self._capture_active and _mot_de_passe_visible(page):
            self._capture_active = False
            self.sortantes.put({"type": "capture_arretee", "raison": "mot_de_passe_visible"})

    def _cliquer_reellement(self, x: float, y: float) -> None:
        for type_evenement in ("mousePressed", "mouseReleased"):
            self._cdp.send("Input.dispatchMouseEvent", {
                "type": type_evenement, "x": x, "y": y, "button": "left", "clickCount": 1,
            })
