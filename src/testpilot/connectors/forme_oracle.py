"""La FORME des réponses de l'oracle d'un projet (lot VH-08, décision A51 du porteur, 2026-10-16) — jamais une valeur.

Mesuré (banc d'agents, campagne base-7 du 2026-10-11) : 4 des 7 tests faux tenaient à l'oracle — l'agent n'en connaissait que
le NOM des requêtes et devinait leur réponse (« le champ "panier" vaut "{}" » sur un objet, « renvoie N résultats » sur un
objet). Ce module dit à quoi ressemble une réponse : objet ou liste, noms des champs, type de chaque valeur.

Ce qu'il ne dit JAMAIS : une valeur (texte, nombre, date), ni le NOMBRE d'éléments d'une liste. Une forme dit où lire et quel
step employer ; la valeur attendue d'un « Alors » vient toujours du cas validé (règle d'A44 : observer sert à connaître le
format, jamais la valeur). Un compte relevé après un essai deviendrait sinon l'attendu « renvoie 1 résultat ».

Seules les requêtes GET sont appelées : une lecture. Une requête POST peut écrire — elle n'est jamais appelée pour en relever
la forme. Module PUR pour `forme` et `rendre` ; `relever` exécute les requêtes qu'on lui donne, sans rien décider.
"""

from __future__ import annotations

import json
import re

PROFONDEUR_MAX = 6
CLES_MAX = 40
ELEMENTS_LUS = 20          # une liste : la forme de ses éléments est la réunion de celle des 20 premiers

TEXTE, NOMBRE, BOOLEEN, VIDE = "texte", "nombre", "vrai/faux", "vide"
# Revue du 2026-10-16 (bloquant) : quand une application range ses données PAR CLÉ (`{"panier": {"<référence>": 2}}`), ces
# clés sont des valeurs. Un objet dont les clés ne sont pas sûres d'être des noms de champs n'est pas détaillé.
CLES_DE_DONNEES = "objet dont les clés sont des données (non montrées)"
# Revue du 2026-10-16 (2e passe) : un élément seul n'a rien à quoi comparer ses clés. Une clé vue SEULEMENT à l'essai n'est
# montrée que si elle a la syntaxe d'un nom de champ — une référence (« sauce-labs-backpack »), un numéro (« CMD-0042 ») ou
# un libellé à espaces n'en ont pas. Résidu assumé : une donnée écrite en snake_case passerait.
_NOM_DE_CHAMP = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def forme(valeur, profondeur: int = 0):
    """La forme masquée d'une valeur JSON : un dict de formes, `{"liste": forme_des_elements | None}`, ou un type nommé.
    `{"liste": None}` : liste vide, la forme de ses éléments est inconnue."""
    if profondeur >= PROFONDEUR_MAX:
        return "…"
    if isinstance(valeur, bool):
        return BOOLEEN
    if isinstance(valeur, (int, float)):
        return NOMBRE
    if isinstance(valeur, str):
        return TEXTE
    if valeur is None:
        return VIDE
    if isinstance(valeur, dict):
        return {str(cle): forme(v, profondeur + 1) for cle, v in list(valeur.items())[:CLES_MAX]}
    if isinstance(valeur, list):
        lus = valeur[:ELEMENTS_LUS]
        objets = [e for e in lus if isinstance(e, dict)]
        if len(objets) > 1 and len({frozenset(o) for o in objets}) > 1:
            # Des éléments aux clés différentes : ces clés peuvent être des données (une ligne par référence…).
            return {"liste": CLES_DE_DONNEES}
        elements = [forme(e, profondeur + 1) for e in lus]
        return {"liste": _reunir(elements) if elements else None}
    return TEXTE


def _est_liste(f) -> bool:
    return isinstance(f, dict) and set(f) == {"liste"}


def _reunir(formes: list):
    """Une forme pour plusieurs éléments : les champs de tous les objets ; un type différent d'un élément à l'autre se dit
    « texte ou nombre »."""
    objets = [f for f in formes if isinstance(f, dict) and not _est_liste(f)]
    if objets and len(objets) == len(formes):
        reunie: dict = {}
        for objet in objets:
            for cle, f in objet.items():
                reunie[cle] = f if cle not in reunie else _reunir([reunie[cle], f])
        return dict(list(reunie.items())[:CLES_MAX])
    listes = [f for f in formes if _est_liste(f)]
    if listes and len(listes) == len(formes):
        connues = [f["liste"] for f in listes if f["liste"] is not None]
        return {"liste": _reunir(connues) if connues else None}
    return _union([f if isinstance(f, str) else ("objet" if not _est_liste(f) else "liste") for f in formes])


def _union(types: list[str]) -> str:
    """« nombre ou texte » : chaque type une fois, dans un ordre fixe — le nombre d'alternances ne trahit jamais combien
    d'éléments ont été lus (revue du 2026-10-16)."""
    uniques = sorted({t.strip() for type_ in types for t in type_.split(" ou ") if t.strip()})
    return " ou ".join(uniques)


def rendre(f, retrait: int = 0) -> list[str]:
    """Des lignes lisibles : `champ : type`, une liste annoncée avec la forme de ses éléments."""
    pas = "  " * retrait
    if _est_liste(f):
        if f["liste"] is None:
            return [f"{pas}liste vide : la forme de ses éléments n'est pas connue"]
        if isinstance(f["liste"], dict) and not _est_liste(f["liste"]):
            return [f"{pas}liste d'objets, chacun :"] + rendre(f["liste"], retrait + 1)
        return [f"{pas}liste de : {_type(f['liste'])}"]
    if isinstance(f, dict):
        lignes = []
        for cle, sous in f.items():
            if isinstance(sous, str):
                lignes.append(f"{pas}{cle} : {sous}")
            elif _est_liste(sous) and sous["liste"] is None:
                lignes.append(f"{pas}{cle} : liste vide (forme de ses éléments inconnue)")
            elif _est_liste(sous) and isinstance(sous["liste"], dict) and not _est_liste(sous["liste"]):
                lignes.append(f"{pas}{cle} : liste d'objets, chacun :")
                lignes += rendre(sous["liste"], retrait + 1)
            elif _est_liste(sous):
                lignes.append(f"{pas}{cle} : liste de {_type(sous['liste'])}")
            else:
                lignes.append(f"{pas}{cle} : objet")
                lignes += rendre(sous, retrait + 1)
        return lignes or [f"{pas}objet vide"]
    return [f"{pas}{f}"]


def _type(f) -> str:
    if isinstance(f, str):
        return f
    return "listes" if _est_liste(f) else "objets"


def rendre_tout(formes: dict) -> list[str]:
    """Toutes les requêtes relevées : « « nom » : objet » suivi de ses champs. Une requête illisible est dite comme telle."""
    lignes = []
    for nom, f in formes.items():
        if isinstance(f, dict) and set(f) == {"illisible"}:
            lignes.append(f"- « {nom} » : réponse non relevée ({f['illisible']})")
            continue
        corps = rendre(f, 2)
        tete = "objet" if isinstance(f, dict) and not _est_liste(f) else ""
        lignes.append(f"- « {nom} » : {tete}".rstrip() if tete else f"- « {nom} » :")
        lignes += corps
    return lignes


def requetes_en_lecture(queries_json: str | None) -> list[str]:
    """Les noms des requêtes déclarées en GET — les seules appelées pour relever une forme."""
    try:
        requetes = json.loads(queries_json or "[]")
    except ValueError:
        return []
    if not isinstance(requetes, list):
        return []
    return [str(r["name"]) for r in requetes if isinstance(r, dict) and r.get("name")
            and str(r.get("method") or "GET").upper() == "GET"]


def relever(executer, noms: list[str]) -> dict:
    """{nom: forme} pour chaque requête : `executer(nom)` rend la réponse JSON décodée. Une requête qui échoue est notée
    illisible (sans son message, qui pourrait citer une adresse ou un secret) — jamais une forme devinée."""
    formes = {}
    for nom in noms:
        try:
            formes[nom] = forme(executer(nom))
        except Exception as exc:   # best-effort : un relevé manqué ne doit jamais faire échouer une exploration ni un essai
            formes[nom] = {"illisible": type(exc).__name__}
    return formes


def _sans_cles_de_donnees(f, *, element: bool):
    """Une forme relevée PENDANT un essai, dont on ne garde que ce qui est sûr d'être un nom de champ : les clés d'un ÉLÉMENT
    de liste (toutes identiques d'un élément à l'autre, sinon `forme` l'a déjà masqué) ; jamais celles d'un objet seul, qui
    peuvent être des données (`{"<référence>": 2}`)."""
    if _est_liste(f):
        return {"liste": None if f["liste"] is None else _sans_cles_de_donnees(f["liste"], element=True)}
    if isinstance(f, dict):
        if not f:
            return f
        if not element or not all(_NOM_DE_CHAMP.match(cle) for cle in f):
            return CLES_DE_DONNEES
        return {cle: _sans_cles_de_donnees(sous, element=False) for cle, sous in f.items()}
    return f


def completer(base, essai):
    """La forme de l'EXPLORATION complétée par celle relevée à la fin d'un essai (décision A51, revue du 2026-10-16).

    Les clés d'un objet viennent de l'exploration seule : un objet vide à l'exploration et rempli à l'essai a des clés qui
    sont des données — non montrées. Une liste vide à l'exploration reçoit la forme de ses éléments vue à l'essai. Le
    résultat est CUMULÉ (exploration ∪ essais) : il ne dit jamais l'état du moment — ni qu'une liste est vide maintenant,
    ni qu'un champ vaut vide maintenant. Seule information acquise par un essai, assumée par A51 : qu'un élément a existé."""
    if essai is None or (isinstance(essai, dict) and set(essai) == {"illisible"}):
        return base
    if _est_liste(base):
        if not _est_liste(essai) or essai["liste"] is None:
            return base
        if base["liste"] is None:
            return {"liste": _sans_cles_de_donnees(essai["liste"], element=True)}
        return {"liste": completer(base["liste"], essai["liste"])}
    if isinstance(base, dict):
        if not base:
            return CLES_DE_DONNEES if isinstance(essai, dict) and not _est_liste(essai) and essai else base
        if isinstance(essai, dict) and not _est_liste(essai):
            return {cle: completer(sous, essai.get(cle)) for cle, sous in base.items()}
        return base
    if base == VIDE and isinstance(essai, str) and essai not in (VIDE, CLES_DE_DONNEES):
        return _union([essai, VIDE])
    return base


def completer_tout(cumul: dict, essai: dict) -> dict:
    """Le cumul de chaque requête de l'exploration, complété par un essai. Une requête jamais relevée à l'exploration n'est
    pas montrée : rien à quoi comparer ses clés."""
    return {nom: completer(base, (essai or {}).get(nom)) for nom, base in cumul.items()}


def nouveautes(avant: dict, apres: dict) -> dict:
    """Les requêtes dont le cumul a changé : ce qu'un essai vient d'apprendre à l'IA.

    Rejeu de M2 (2026-10-17) : le cumul ENTIER revenait après chaque essai — 6 fois sur un même cas — sans rien de nouveau la
    plupart du temps. L'IA l'a déjà reçu (message initial, essais précédents) ; seul ce qui change lui est redit."""
    return {nom: f for nom, f in apres.items() if f != (avant or {}).get(nom)}
