"""Environnements d'un projet (lot PT-04a, décisions A48 à A50 du porteur, 2026-10-16) — règles PURES, aucune I/O.

Un projet joue ses tests sur son environnement PAR DÉFAUT (son adresse, sa base, sa version, son oracle : ce qu'il a
toujours eu) ou sur un environnement AJOUTÉ (recette, préproduction…). Ce module dit :

- ce qu'un environnement ajouté doit déclarer pour être accepté (`valider`) — dont sa NATURE, obligatoire et sans défaut
  (A48) : « test », ou « production », qui n'est jamais joué ;
- ce que devient le projet quand un test est joué sur un environnement ajouté (`projet_sur`) : adresse, base, version et
  oracle remplacés, comptes inchangés (A49). Sans adresse d'oracle déclarée pour cet environnement, l'oracle du projet n'y
  est PAS repris — il interrogerait une autre application ; un step d'oracle y sort « bloqué » (prérequis manquant),
  jamais `conforme` ;
- le refus de la production, porté aussi jusqu'au harnais (`ODOO_ENV=prod`, sa garde d'aujourd'hui) en second verrou.

L'exploration, la génération et ses essais restent sur l'environnement par défaut (A50) : rien ici ne les concerne.
"""

from __future__ import annotations

import ast
import json
import re
from urllib.parse import urlparse

NATURE_TEST = "test"
NATURE_PRODUCTION = "production"
NATURES = (NATURE_TEST, NATURE_PRODUCTION)
LIBELLES_NATURE = {NATURE_TEST: "Test", NATURE_PRODUCTION: "Production"}   # CONTINUITE §4.7 : jamais la valeur brute à l'écran
NOM_PAR_DEFAUT = "Par défaut"
NOM_MAX = 60
ENVIRONNEMENTS_MAX = 20          # par projet, défaut compris : au-delà, une saisie par erreur
DEFAUT = 0                       # l'identifiant de l'environnement par défaut dans l'API et les planifications
GARDE_PRODUCTION = ("ODOO_ENV", "prod")   # la garde du harnais (`behave_runtime/environment.py`), jamais affaiblie


class EnvironnementInvalide(ValueError):
    """Une déclaration ou un choix refusé — le message se montre tel quel."""


def nom_affiche(nom: str | None) -> str:
    return (nom or "").strip() or NOM_PAR_DEFAUT


def _adresse(valeur: str, quoi: str, *, requise: bool) -> str:
    adresse = (valeur or "").strip()
    if not adresse:
        if requise:
            raise EnvironnementInvalide(f"{quoi} est requise")
        return ""
    morceaux = urlparse(adresse)
    if morceaux.scheme not in ("http", "https") or not morceaux.netloc:
        raise EnvironnementInvalide(f"{quoi} doit commencer par http:// ou https://")
    return adresse


def valider_nom(nom: str) -> str:
    propre = (nom or "").strip()
    if not propre:
        raise EnvironnementInvalide("le nom est requis")
    if len(propre) > NOM_MAX:
        raise EnvironnementInvalide(f"{NOM_MAX} caractères au plus pour le nom")
    return propre


def valider(*, nom: str, base_url: str, nature: str, connector_version: str = "", database: str = "",
            oracle_base_url: str = "") -> dict:
    """Les champs d'un environnement ajouté, nettoyés — ou `EnvironnementInvalide`. La nature n'a PAS de défaut (A48)."""
    if nature not in NATURES:
        raise EnvironnementInvalide("choisissez la nature : Test ou Production")
    return {"nom": valider_nom(nom), "base_url": _adresse(base_url, "l'adresse", requise=True), "nature": nature,
            "connector_version": (connector_version or "").strip(), "database": (database or "").strip(),
            "oracle_base_url": _adresse(oracle_base_url, "l'adresse de l'oracle", requise=False)}


def projet_sur(projet: dict | None, environnement: dict | None) -> dict | None:
    """Le projet tel qu'un test le voit sur `environnement` (None = par défaut : le projet tel quel).

    Remplacés : adresse, base, version, oracle (A49). Gardés : connecteur, comptes, navigateur, enregistrement de connexion.
    Un environnement sans adresse d'oracle n'en a pas (l'oracle du projet interrogerait une autre application)."""
    if projet is None or environnement is None:
        return projet
    vu = {**projet, "base_url": environnement["base_url"], "database": environnement.get("database", ""),
          "connector_version": environnement.get("connector_version", "")}
    if environnement.get("oracle_base_url"):
        vu["oracle_base_url"] = environnement["oracle_base_url"]
    else:
        vu["oracle_type"], vu["oracle_base_url"] = "", ""
    return vu


def est_production(environnement: dict | None) -> bool:
    return bool(environnement) and environnement.get("nature") != NATURE_TEST


def figer(environnement: dict, *, environment_id: int) -> str:
    """Ce qu'une campagne retient de son environnement au lancement (JSON) : modifier l'environnement ensuite ne change
    pas ce qu'elle joue."""
    champs = ("nom", "base_url", "database", "connector_version", "oracle_base_url", "nature")
    return json.dumps({"id": environment_id, **{c: environnement.get(c, "") for c in champs}}, ensure_ascii=False)


def lire_fige(texte: str | None) -> dict | None:
    """L'environnement figé d'une campagne, ou None (aucun). Illisible : `EnvironnementInvalide` — jamais l'environnement
    par défaut joué à la place d'un environnement qu'on ne sait plus lire."""
    if not (texte or "").strip():
        return None
    try:
        fige = json.loads(texte)
    except ValueError:
        fige = None
    lisible = (isinstance(fige, dict) and isinstance(fige.get("id"), int) and not isinstance(fige.get("id"), bool)
               and (fige["id"] == DEFAUT or bool(fige.get("base_url"))))
    if not lisible:
        raise EnvironnementInvalide("l'environnement figé de cette exécution est illisible")
    return fige


def ids_lus(texte: str | None, *, strict: bool = False) -> list[int]:
    """Les environnements d'une planification (`scheduled_run.environment_ids`, liste JSON, 0 = par défaut). Illisible :
    `[]` pour l'affichage ; avec `strict` (au déclenchement), `EnvironnementInvalide`."""
    if not (texte or "").strip():
        return []
    try:
        ids = json.loads(texte)
    except ValueError:
        ids = None
    if not isinstance(ids, list) or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids):
        if strict:
            raise EnvironnementInvalide("les environnements de la planification sont illisibles")
        return []
    return ids


_URL_ABSOLUE = re.compile(r"^https?://", re.IGNORECASE)
_ARGUMENT_GHERKIN = re.compile(r'"([^"\n]*)"')
_PORTS_PAR_DEFAUT = {"http": 80, "https": 443}


def origine(url: str) -> tuple[str, str, int | None]:
    """(schéma, hôte, port) normalisés : casse ignorée, port par défaut retiré — deux écritures de la même application
    comparent égal."""
    morceaux = urlparse((url or "").strip())
    schema = (morceaux.scheme or "").lower()
    try:
        port = morceaux.port
    except ValueError:
        port = None
    if port == _PORTS_PAR_DEFAUT.get(schema):
        port = None
    return schema, (morceaux.hostname or "").lower(), port


def adresses_d_une_autre_application(feature: str, steps: str, base_url: str) -> list[str]:
    """Les adresses ABSOLUES qu'un test écrit en dur et qui ne sont pas celles de l'environnement joué (revue du 2026-10-16).

    Lues dans la STRUCTURE, jamais dans la prose : les constantes chaîne du code des steps (arbre syntaxique) et les
    arguments entre guillemets des étapes Gherkin. Un test écrit sur l'environnement par défaut et rejoué ailleurs qui en
    contient une ouvrirait l'application d'origine : il n'est pas joué (« bloqué »), jamais réussi à tort."""
    trouvees: list[str] = []
    try:
        for noeud in ast.walk(ast.parse(steps or "")):
            if isinstance(noeud, ast.Constant) and isinstance(noeud.value, str) and _URL_ABSOLUE.match(noeud.value.strip()):
                trouvees.append(noeud.value.strip())
    except SyntaxError:
        pass   # un code illisible échoue de toute façon à l'exécution, en erreur technique
    trouvees += [a.strip() for a in _ARGUMENT_GHERKIN.findall(feature or "") if _URL_ABSOLUE.match(a.strip())]
    joue = origine(base_url)
    return list(dict.fromkeys(u for u in trouvees if origine(u) != joue))
