"""Client de l'oracle backend HTTP (lot 07e, C5, D7 — périmètre HTTP ; l'oracle SQL en lecture
seule est un sous-lot séparé, plus tard).

Une requête nommée est déclarée dans les RÉGLAGES DU PROJET (``oracle_config``), jamais écrite
par l'agent de génération : ce module n'expose donc aucune façon de construire une requête libre
(pas de méthode ``get``/``post`` prenant un chemin quelconque) — seulement ``executer(nom)``, qui
résout un nom contre le catalogue déclaré.

``urllib`` (bibliothèque standard), comme le reste du paquet applicatif pour ses propres appels
HTTP (`connectors/_web_helpers.py::http_probe`) — jamais `requests` : cette dépendance externe
est celle que `generation/tools/write.py::_FORBIDDEN_IMPORTS` interdit dans un step ÉCRIT PAR
L'AGENT, pas dans le socle.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from urllib.parse import urlencode, urljoin


class OracleIndisponible(Exception):
    """L'oracle est configuré mais injoignable — `verifier_connexion` refuse plutôt que de laisser
    tourner un cas dont le `ground_truth` promis (`backend_verified`) ne pourrait jamais se
    vérifier."""


class RequeteOracleInconnue(Exception):
    """Un step référence une requête nommée absente des réglages du projet — prérequis manquant,
    jamais un défaut de l'application testée."""


def _en_tetes(auth: dict) -> dict[str, str]:
    type_ = (auth or {}).get("type") or "aucune"
    if type_ == "bearer":
        return {"Authorization": f"Bearer {auth.get('token', '')}"}
    if type_ == "basic":
        jeton = base64.b64encode(
            f"{auth.get('username', '')}:{auth.get('password', '')}".encode("utf-8")).decode("ascii")
        return {"Authorization": f"Basic {jeton}"}
    if type_ == "en-tete":
        nom = auth.get("name") or ""
        return {nom: auth.get("value", "")} if nom else {}
    return {}


class OracleHttp:
    """Un oracle HTTP configuré : adresse, authentification, et requêtes NOMMÉES du projet."""

    def __init__(self, base_url: str, auth: dict | None = None, queries: list[dict] | None = None,
                 timeout: int = 10):
        self._base_url = (base_url or "").rstrip("/")
        self._auth = auth or {}
        self._queries = {q["name"]: q for q in (queries or [])
                         if isinstance(q, dict) and q.get("name")}
        self._timeout = timeout

    def verifier_joignable(self) -> None:
        """Lève `OracleIndisponible` si le serveur ne répond PAS DU TOUT (DNS, réseau, timeout).

        ⚠️ Une réponse HTTP d'erreur (4xx/5xx, y compris 404/401) PROUVE que le serveur existe et
        répond — ce n'est pas « injoignable ». Seule l'absence totale de réponse l'est.
        """
        req = urllib.request.Request(self._base_url or "/", method="GET", headers=_en_tetes(self._auth))
        try:
            urllib.request.urlopen(req, timeout=self._timeout).close()
        except urllib.error.HTTPError:
            return
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise OracleIndisponible(f"l'oracle « {self._base_url} » ne répond pas : {exc}") from exc

    def executer(self, nom_requete: str) -> object:
        """Exécute la requête NOMMÉE et rend le JSON décodé (liste, objet, ou `None`)."""
        requete = self._queries.get(nom_requete)
        if requete is None:
            disponibles = ", ".join(sorted(self._queries)) or "aucune"
            raise RequeteOracleInconnue(
                f"aucune requête d'oracle nommée « {nom_requete} » n'est déclarée dans les réglages "
                f"du projet (disponibles : {disponibles})")
        methode = str(requete.get("method") or "GET").upper()
        chemin = str(requete.get("path") or "")
        params = requete.get("params") or {}
        url = urljoin(self._base_url + "/", chemin.lstrip("/"))
        entetes = {"Accept": "application/json", **_en_tetes(self._auth)}
        data = None
        if methode == "GET":
            if params:
                url = f"{url}?{urlencode(params)}"
        else:
            data = json.dumps(params).encode("utf-8")
            entetes["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, method=methode, headers=entetes)
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            corps = resp.read().decode("utf-8")
        return json.loads(corps) if corps.strip() else None


def compte_resultats(reponse: object) -> int:
    """Le nombre de résultats d'une réponse d'oracle : une LISTE compte ses éléments ; un objet
    unique compte pour 1 ; l'absence de réponse (`None`) pour 0."""
    if reponse is None:
        return 0
    if isinstance(reponse, list):
        return len(reponse)
    return 1


def _segments(chemin: str) -> list:
    segments: list[str | int] = []
    for morceau in chemin.replace("[", ".").replace("]", "").split("."):
        morceau = morceau.strip()
        if morceau:
            segments.append(int(morceau) if morceau.lstrip("-").isdigit() else morceau)
    return segments


def champ(reponse: object, chemin: str) -> object:
    """Navigue un JSON décodé par un chemin en points (`data.statut`, `resultats[0].nom`).

    Lève `KeyError`/`TypeError`/`IndexError` EXPLICITES si le chemin n'existe pas — jamais une
    valeur devinée (même discipline que le reste du verdict : un signal absent ne se remplace pas).
    """
    courant = reponse
    for segment in _segments(chemin):
        if isinstance(segment, int):
            if not isinstance(courant, list):
                raise TypeError(f"« {segment} » suppose une liste, reçu {type(courant).__name__} "
                                f"(chemin « {chemin} »)")
            courant = courant[segment]
        else:
            if not isinstance(courant, dict):
                raise TypeError(f"« {segment} » suppose un objet, reçu {type(courant).__name__} "
                                f"(chemin « {chemin} »)")
            if segment not in courant:
                raise KeyError(f"« {segment} » absent de la réponse de l'oracle (chemin « {chemin} »)")
            courant = courant[segment]
    return courant
