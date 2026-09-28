"""La configuration de l'oracle backend optionnel d'un projet (lot 07e, C5, D7 — périmètre HTTP).

Pourquoi. Un cas sur le connecteur web générique ne peut recouper que ce que l'UI affiche
(``ground_truth = ui_only``, voir ``verdict/status.py``) — aucune vérité côté serveur. L'oracle
donne, PROJET PAR PROJET, un accès en LECTURE à une source indépendante (une API HTTP interne,
p.ex. un endpoint de recette) : des requêtes NOMMÉES, déclarées ici par le porteur du projet, que
les steps partagés interrogent (``l'oracle "<nom>" renvoie <n> résultat(s)``…) — jamais construites
par l'agent de génération, qui n'en voit que les NOMS (même garantie que D8 pour les comptes).

Module PUR : aucune I/O, aucun réseau, aucun LLM (même discipline que `auth_strategie.py` et
`contexte_navigateur.py`).
"""

from __future__ import annotations

import json

TYPE_AUCUN = ""
TYPE_HTTP = "http"
TYPES = (TYPE_AUCUN, TYPE_HTTP)

AUTH_AUCUNE = "aucune"
AUTH_BEARER = "bearer"
AUTH_BASIC = "basic"
AUTH_ENTETE = "en-tete"
AUTH_TYPES = (AUTH_AUCUNE, AUTH_BEARER, AUTH_BASIC, AUTH_ENTETE)

METHODES = ("GET", "POST")

# Aucune valeur d'enum brute à l'écran (CONTINUITE §4.7) : libellé français, DUPLIQUÉ côté frontend
# (même convention que `auth_strategie.LIBELLES`).
LIBELLES_TYPE = {
    TYPE_AUCUN: "Aucun oracle",
    TYPE_HTTP: "API HTTP",
}

# Nom de la variable d'environnement du sous-processus — DUPLIQUÉ dans `behave_runtime/environment.py`
# et `behave_runtime/steps_library/_base_helpers.py` (le harnais ne dépend pas du paquet applicatif),
# même motif que `auth_strategie.ENV_STRATEGIE`.
ENV_ORACLE = "TESTPILOT_ORACLE"


def erreurs(oracle_type: str, base_url: str, auth_json: str, queries_json: str) -> list[str]:
    """Messages MÉTIER (jamais un nom de colonne) si la configuration est incohérente ; vide sinon.

    Ne valide QUE la forme (JSON illisible, champs requis absents, nom de requête dupliqué) —
    jamais l'exactitude auprès du serveur réel : ça, seule une tentative réelle peut le dire
    (`verifier_connexion`, `OracleIndisponible`), pas un 422 à la saisie.
    """
    if oracle_type not in TYPES:
        attendu = ", ".join(t or "aucun" for t in TYPES)
        return [f"type d'oracle « {oracle_type} » inconnu (attendu : {attendu})"]
    if oracle_type == TYPE_AUCUN:
        return []
    problemes: list[str] = []
    if not base_url.strip():
        problemes.append("l'adresse de l'oracle est requise")
    if auth_json.strip():
        try:
            auth = json.loads(auth_json)
        except (ValueError, TypeError):
            problemes.append("l'authentification de l'oracle n'est pas un JSON valide")
        else:
            problemes += _erreurs_auth(auth)
    problemes += _erreurs_requetes(queries_json)
    return problemes


def _erreurs_auth(auth: object) -> list[str]:
    if not isinstance(auth, dict) or auth.get("type") not in AUTH_TYPES:
        return [f"le type d'authentification de l'oracle doit être : {', '.join(AUTH_TYPES)}"]
    type_ = auth["type"]
    if type_ == AUTH_BEARER and not auth.get("token"):
        return ["un jeton (« token ») est requis pour l'authentification par jeton de l'oracle"]
    if type_ == AUTH_BASIC and not (auth.get("username") and auth.get("password")):
        return ["un identifiant et un mot de passe sont requis pour l'authentification basique de l'oracle"]
    if type_ == AUTH_ENTETE and not (auth.get("name") and auth.get("value")):
        return ["un nom et une valeur d'en-tête sont requis pour l'authentification par en-tête de l'oracle"]
    return []


def _erreurs_requetes(queries_json: str) -> list[str]:
    try:
        requetes = json.loads(queries_json or "[]")
    except (ValueError, TypeError):
        return ["les requêtes nommées de l'oracle ne sont pas un JSON valide"]
    if not isinstance(requetes, list):
        return ["les requêtes nommées de l'oracle doivent être une liste"]
    problemes: list[str] = []
    noms: set[str] = set()
    for requete in requetes:
        if not isinstance(requete, dict):
            problemes.append("chaque requête nommée de l'oracle doit être un objet")
            continue
        nom = str(requete.get("name") or "").strip()
        methode = str(requete.get("method") or "GET").upper()
        chemin = str(requete.get("path") or "").strip()
        if not nom:
            problemes.append("une requête nommée de l'oracle n'a pas de nom")
        elif nom in noms:
            problemes.append(f"le nom de requête d'oracle « {nom} » est utilisé deux fois")
        else:
            noms.add(nom)
        if methode not in METHODES:
            problemes.append(f"la méthode « {methode} » de la requête « {nom or '?'} » n'est pas gérée "
                              f"(attendu : {', '.join(METHODES)})")
        if not chemin:
            problemes.append(f"la requête « {nom or '?'} » n'a pas de chemin")
    return problemes


def noms_declares(queries_json: str) -> list[str]:
    """Les NOMS des requêtes déclarées — la SEULE chose que la génération doit voir (même garantie
    que `comptes_libelles`, D8, précision 2) : jamais le chemin, la méthode ni les paramètres."""
    try:
        requetes = json.loads(queries_json or "[]")
    except (ValueError, TypeError):
        return []
    if not isinstance(requetes, list):
        return []
    return [str(r["name"]).strip() for r in requetes
            if isinstance(r, dict) and str(r.get("name") or "").strip()]
