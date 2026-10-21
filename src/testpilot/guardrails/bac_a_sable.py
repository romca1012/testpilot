"""Garde du bac à sable (lot VH-07, décision D26) : un ESSAI de génération ne fausse jamais une exécution réelle.

**Le risque fermé ici.** Un essai (« exécuter puis écrire », `generation/tools/essai.py`) remet l'application à zéro avant et après
avoir joué ses actions. Deux façons de fausser un VERDICT, relevées à la relecture du lot (2026-10-10/11), avant toute mesure :

1. *Une remise à zéro pendant une exécution réelle* efface ce que le test en cours vient de créer — ou ce qu'un défaut de
   l'application vient de créer à tort. Un scénario négatif (« aucune commande n'est enregistrée ») verrait une application
   propre et sortirait `conforme` : un faux vert fabriqué par l'outil lui-même. La file de tâches (`concurrency.py`) plafonne
   le nombre de tâches simultanées, elle ne sépare pas deux tâches de la même application.
2. *Un essai dont la remise à zéro finale échoue* laisse ce qu'il a créé. L'exécution réelle suivante trouverait la commande de
   l'essai et pourrait sortir `conforme` sur une application qui n'enregistre rien.

**Les règles.**

- Par APPLICATION (origine : schéma, hôte, port — deux projets peuvent viser la même) : autant d'exécutions réelles que l'on veut
  en même temps (comme avant), OU une seule remise à zéro (un essai, ou le rétablissement ci-dessous) — jamais les deux. Une
  exécution réelle attend la fin d'un essai (borné à quelques minutes) ; un essai qui trouve une exécution en cours attend un
  court instant puis RENONCE (`BacASableOccupe`).
- Une remise à zéro n'est prouvée que par une réponse 2xx DIRECTE : une redirection (vers une page de connexion, vers un autre
  hôte) n'est jamais suivie — elle vaut échec.
- Un essai qui n'a pas pu remettre à zéro laisse une MARQUE : en mémoire toujours, sur disque autant que possible (elle survit
  alors au redémarrage). Toute exécution réelle de cette application RÉTABLIT d'abord — seule, aucune autre exécution en cours —
  la remise à zéro ; tant qu'elle échoue, ou que la marque ne peut pas être retirée, l'exécution n'est PAS jouée
  (`BacASableNonRemisAZero` → erreur technique, jamais un verdict). Le porteur du projet peut LEVER la marque après avoir remis
  lui-même l'application à zéro (`lever_la_marque`, réglages du projet) : c'est la seule sortie quand la route de remise à
  zéro a disparu. La marque est celle de l'APPLICATION : l'administrateur d'un projet qui la vise la lève pour tous les projets
  qui la visent (D38).

**Limites assumées.** L'exclusion vit dans le processus (un seul worker en production), comme `concurrency.py` ; la marque sur
disque vaut pour tous les processus. Deux noms d'une même application (`localhost` et `127.0.0.1`, `http` et `https`) sont deux
origines : ni exclusion ni marque partagées entre deux projets qui la désigneraient différemment. La marque est un fichier du
serveur : qui peut l'écrire peut faire émettre un POST vers un chemin de la même application.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from testpilot import config

logger = logging.getLogger(__name__)

# Attente d'un essai devant une exécution réelle en cours. Courte : une exécution dure des minutes, l'agent n'attend pas.
ATTENTE_ESSAI_S = 20.0
DELAI_REMISE_A_ZERO_S = 20


class BacASableOccupe(RuntimeError):
    """Une exécution réelle (ou un autre essai) tient l'application : aucun essai n'est joué."""


class BacASableNonRemisAZero(RuntimeError):
    """Un essai a laissé l'application dans son état et elle ne se remet toujours pas à zéro : aucune exécution n'est jouée."""


def cle_d_application(url: str | None) -> str | None:
    """L'ORIGINE d'une adresse (`schéma://hôte:port`, en minuscules, port par défaut explicité) — ce qui identifie une
    application, quel que soit le projet qui la vise. `None` si l'adresse ne se lit pas : aucune garde (comportement d'avant)."""
    try:
        lue = urlparse((url or "").strip())
        if lue.scheme not in ("http", "https") or not lue.hostname:
            return None
        port = lue.port or (443 if lue.scheme == "https" else 80)
    except ValueError:
        return None
    return f"{lue.scheme}://{lue.hostname.lower()}:{port}"


# ── Remise à zéro prouvée ─────────────────────────────────────────────────────────────────────────────────


class _SansRedirection(urllib.request.HTTPRedirectHandler):
    """`urllib` suit par défaut un 302 d'un POST en GET et ne juge que la réponse finale : `POST /reset` → 302 `/login` → 200
    passait pour une remise à zéro (relecture du 2026-10-11). Ici une redirection n'est pas suivie : elle lève."""

    def redirect_request(self, *args, **kwargs):
        return None


REPONSE_DE_REMISE_A_ZERO = '{"remis_a_zero": true}'


def remettre_a_zero(url: str, delai_s: int = DELAI_REMISE_A_ZERO_S) -> None:
    """`POST` sur l'adresse de remise à zéro. Toute réponse autre que 2xx directe (redirection comprise), ou aucune réponse,
    LÈVE : sans remise à zéro prouvée, ni essai ni exécution.

    Décision A75 (porteur, 2026-10-20) : la réponse doit AUSSI le dire — un corps JSON `{"remis_a_zero": true}`. Une adresse
    mal saisie (« / », une page d'accueil) répond 200 sur la plupart des applications : on aurait cru l'application remise à
    zéro, et l'IA aurait essayé ses actions dans de vraies données. Un 204 vide, un 200 en HTML ou `{"ok": true}` ne prouvent
    plus rien."""
    requete = urllib.request.Request(url, data=b"{}", method="POST", headers={"Content-Type": "application/json"})
    ouvreur = urllib.request.build_opener(_SansRedirection)
    with ouvreur.open(requete, timeout=delai_s) as reponse:
        if not 200 <= int(reponse.status) < 300:
            raise RuntimeError(f"la remise à zéro a répondu {reponse.status}")
        corps = reponse.read(4096)
    try:
        lu = json.loads(corps.decode("utf-8")) if corps else None
    except (UnicodeDecodeError, ValueError):
        lu = None
    if not (isinstance(lu, dict) and lu.get("remis_a_zero") is True):
        raise RuntimeError(f"la remise à zéro n'a pas confirmé : réponse attendue {REPONSE_DE_REMISE_A_ZERO}")


# ── Marque : « un essai a laissé cette application dans son état » ────────────────────────────────────────

# En mémoire D'ABORD (contre-relecture : si le disque refuse l'écriture, rien ne retenait le run suivant), sur disque ensuite.
_marques_en_memoire: dict[str, str] = {}


def _dossier_des_marques() -> Path:
    return config.DATA_DIR / "bac-a-sable"


def _marque(cle: str) -> Path:
    return _dossier_des_marques() / f"{hashlib.sha256(cle.encode('utf-8')).hexdigest()[:24]}.json"


def marquer_non_remis(cle: str | None, url_de_remise_a_zero: str) -> None:
    """Consigne qu'un essai n'a pas pu remettre l'application à zéro."""
    if not cle:
        return
    _marques_en_memoire[cle] = url_de_remise_a_zero
    try:
        _dossier_des_marques().mkdir(parents=True, exist_ok=True)
        _marque(cle).write_text(json.dumps({
            "application": cle, "remise_a_zero": url_de_remise_a_zero,
            "depuis": datetime.now(timezone.utc).isoformat(timespec="seconds")}, ensure_ascii=False), encoding="utf-8")
    except OSError:
        logger.error("[bac à sable] %s : marque « non remis à zéro » non écrite sur disque — elle ne survivra pas à un "
                     "redémarrage", cle, exc_info=True)


def non_remis(cle: str | None) -> dict | None:
    """La marque de cette application, ou `None`. Une marque illisible reste une marque (on ne joue pas sur un doute)."""
    if not cle:
        return None
    if cle in _marques_en_memoire:
        return {"application": cle, "remise_a_zero": _marques_en_memoire[cle]}
    chemin = _marque(cle)
    if not chemin.exists():
        return None
    try:
        lue = json.loads(chemin.read_text(encoding="utf-8"))
        return lue if isinstance(lue, dict) else {}
    except (OSError, ValueError):
        return {}


def _retirer_la_marque(cle: str) -> None:
    """Lève `OSError` si le fichier ne peut pas être retiré : la marque VAUT encore (elle ferait remettre à zéro au run suivant)."""
    chemin = _marque(cle)
    if chemin.exists():
        chemin.unlink()
    _marques_en_memoire.pop(cle, None)


def remettre_a_zero_et_demarquer(cle: str | None, url: str) -> None:
    """Pour un ESSAI (qui tient l'exclusion) : remise à zéro prouvée, donc plus rien de laissé — la marque éventuelle tombe.
    Lève si la remise à zéro n'est pas prouvée ou si la marque ne peut pas être retirée."""
    remettre_a_zero(url)
    if cle and non_remis(cle) is not None:
        _retirer_la_marque(cle)


def lever_la_marque(cle: str | None) -> bool:
    """Décision du PORTEUR du projet (réglages) : il a remis lui-même l'application à zéro. Rend True si une marque existait.
    La seule sortie quand la remise à zéro automatique ne peut plus aboutir (route disparue, marque illisible)."""
    if not cle or non_remis(cle) is None:
        return False
    _retirer_la_marque(cle)
    logger.warning("[bac à sable] %s : marque « non remis à zéro » levée par décision du porteur", cle)
    return True


def _retablir(cle: str) -> None:
    """Remet à zéro une application qu'un essai a laissée dans son état, ou lève. Appelé SOUS EXCLUSION (aucun run en cours)."""
    marque = non_remis(cle)
    if marque is None:
        return
    url = str(marque.get("remise_a_zero") or "")
    try:
        if cle_d_application(url) != cle:
            raise RuntimeError("marque illisible ou adresse d'une autre application")
        remettre_a_zero(url)
        _retirer_la_marque(cle)
    except Exception as exc:
        # Lot PT-01b (2026-10-13) : le message ne nomme plus la rubrique « Génération — bac à sable » — elle a quitté la
        # fenêtre du projet pour « Paramètres de test », et les deux écrans coexistent jusqu'au lot PT-07.
        raise BacASableNonRemisAZero(
            "un essai de génération a laissé cette application dans son état et son rétablissement échoue "
            f"({type(exc).__name__}) : l'exécution n'est pas jouée. Remettez l'application à zéro, puis déclarez-le dans les "
            "réglages du projet (remise à zéro).") from exc


# ── Exclusion remise à zéro / exécutions réelles, par application ─────────────────────────────────────────


class _Verrou:
    def __init__(self) -> None:
        self.condition = threading.Condition()
        self.executions = 0
        self.essai = False  # une remise à zéro est en cours : essai, ou rétablissement avant un run


_registre = threading.Lock()
_verrous: dict[str, _Verrou] = {}


def _verrou(cle: str) -> _Verrou:
    with _registre:
        return _verrous.setdefault(cle, _Verrou())


@contextmanager
def execution_reelle(cle: str | None):
    """Tenu pendant un run RÉEL de l'application. Attend la fin d'un essai en cours ; ne gêne aucune autre exécution réelle.
    Si un essai a laissé l'application dans son état : la rétablit d'abord, SEUL (aucune autre exécution en cours — sinon ce
    rétablissement serait lui-même une remise à zéro au milieu d'un run), ou lève `BacASableNonRemisAZero`.
    Sans clé (runner sans adresse : tests, ligne de commande sur la configuration globale) : rien — le comportement d'avant."""
    if not cle:
        yield
        return
    verrou = _verrou(cle)
    while True:
        with verrou.condition:
            while verrou.essai:
                verrou.condition.wait()
            # La marque n'est posée que par un essai, donc sous exclusion : la lire ici, verrou tenu et sans essai, est sûr.
            if non_remis(cle) is None:
                verrou.executions += 1
                break
            if verrou.essai or verrou.executions:
                # Attendre d'être seul, puis RELIRE la marque : un autre run l'a peut-être retirée entre-temps (sans cette
                # relecture, les runs arrivés pendant une marque étaient ensuite joués un par un).
                verrou.condition.wait()
                continue
            verrou.essai = True
        try:
            _retablir(cle)
        finally:
            with verrou.condition:
                verrou.essai = False
                verrou.condition.notify_all()
    try:
        yield
    finally:
        with verrou.condition:
            verrou.executions -= 1
            verrou.condition.notify_all()


@contextmanager
def essai(cle: str | None, attente_s: float | None = None):
    """Tenu pendant un essai, remises à zéro COMPRISES. Lève `BacASableOccupe` si une exécution réelle ou un autre essai tient
    encore l'application après l'attente. Un essai sans clé n'existe pas (`essai.construire` l'exige)."""
    if not cle:
        raise BacASableOccupe("l'application du projet n'est pas identifiable")
    verrou = _verrou(cle)
    limite = time.monotonic() + max(0.0, ATTENTE_ESSAI_S if attente_s is None else attente_s)
    with verrou.condition:
        while verrou.essai or verrou.executions:
            reste = limite - time.monotonic()
            if reste <= 0:
                raise BacASableOccupe(
                    "une exécution réelle est en cours sur cette application" if verrou.executions
                    else "une remise à zéro est déjà en cours sur cette application")
            verrou.condition.wait(reste)
        verrou.essai = True
    try:
        yield
    finally:
        with verrou.condition:
            verrou.essai = False
            verrou.condition.notify_all()


def reinitialiser_pour_les_tests() -> None:
    """Réservé aux tests : oublie verrous et marques en mémoire (aucun état ne fuit d'un test à l'autre)."""
    with _registre:
        _verrous.clear()
    _marques_en_memoire.clear()


@contextmanager
def execution_remise_a_zero(cle: str | None, url: str):
    """Décision A72 (porteur, 2026-10-20) : avant CHAQUE exécution réelle d'un cas, l'application déclarée « à remettre à
    zéro » y revient — puis le test est joué SEUL sur cette application (aucune autre exécution, aucun essai pendant ce
    temps : une remise à zéro au milieu d'un autre test effacerait ce qu'il vérifie). Sans remise à zéro prouvée (A75) :
    `BacASableNonRemisAZero`, le test n'est pas joué — jamais un verdict sur un état douteux (exemple mesuré : un client
    « Martin SARL » laissé par un test précédent faisait passer « je crée Martin SARL, alors il existe » sans création).
    La remise à zéro retire aussi une marque laissée par un essai (elle vaut rétablissement)."""
    cle = cle or cle_d_application(url)
    if not cle:
        raise BacASableNonRemisAZero(f"adresse de remise à zéro illisible ({url}) : le test n'est pas joué")
    verrou = _verrou(cle)
    with verrou.condition:
        while verrou.essai or verrou.executions:
            verrou.condition.wait()
        verrou.essai = True
    try:
        try:
            remettre_a_zero_et_demarquer(cle, url)
        except Exception as exc:
            raise BacASableNonRemisAZero(
                f"la remise à zéro avant le test a échoué ({type(exc).__name__} : {exc}) : le test n'est pas joué. Vérifiez "
                "l'adresse de remise à zéro du projet (Paramètres de test, État de départ).") from exc
        yield
    finally:
        with verrou.condition:
            verrou.essai = False
            verrou.condition.notify_all()
