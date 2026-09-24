"""Lot 03 (D3) — aucune assertion NUE dans un chemin `Alors` de la bibliothèque de steps.

Une assertion nue (`assert`, `raise AssertionError`, `expect(` posé à la main) ne consigne pas de
constat : un `Alors` qui n'en contient que des nues passerait pour « n'avoir rien prouvé » (`aucun_constat`)
alors qu'il vérifie bel et bien. Chaque vérification passe donc par `constater*` ou par un helper décoré
`@constat`. Ce test lit le code par AST : il échoue si quelqu'un réintroduit une assertion nue.
"""

from __future__ import annotations

import ast
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
_LIB = RACINE / "behave_runtime" / "steps_library"
_CONSTATER = {"constater", "constater_visible", "constater_texte"}

# Un `Alors` légitimement SANS constat : il attend seulement la fin d'une soumission (aucune
# vérification) ; un scénario qui n'aurait que lui tombe en `aucun_constat`, ce qui est voulu.
_ALORS_SANS_CONSTAT = {"step_wait_form"}


def _arbre(chemin: Path) -> ast.Module:
    return ast.parse(chemin.read_text(encoding="utf-8"))


def _noms_decorateurs(func) -> set[str]:
    out = set()
    for d in func.decorator_list:
        cible = d.func if isinstance(d, ast.Call) else d
        out.add(cible.id if isinstance(cible, ast.Name) else getattr(cible, "attr", ""))
    return out


def _est_nue(noeud) -> bool:
    if isinstance(noeud, ast.Assert):
        return True
    if isinstance(noeud, ast.Raise) and noeud.exc is not None:
        cible = noeud.exc.func if isinstance(noeud.exc, ast.Call) else noeud.exc
        return isinstance(cible, ast.Name) and cible.id == "AssertionError"
    if isinstance(noeud, ast.Call):
        cible = noeud.func
        return (isinstance(cible, ast.Name) and cible.id == "expect") or (
            isinstance(cible, ast.Attribute) and cible.attr == "expect")
    return False


def _appels(func) -> set[str]:
    noms = set()
    for n in ast.walk(func):
        if isinstance(n, ast.Call):
            noms.add(n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, "attr", ""))
    return noms


def _etapes_alors():
    for chemin in sorted((_LIB).glob("*/*.py")):
        for n in _arbre(chemin).body:
            if isinstance(n, ast.FunctionDef) and "then" in _noms_decorateurs(n):
                yield chemin.parent.name, n


def _helpers() -> dict[str, ast.FunctionDef]:
    return {n.name: n for n in _arbre(_LIB / "_base_helpers.py").body if isinstance(n, ast.FunctionDef)}


def test_aucun_step_alors_ne_contient_d_assertion_nue():
    fautes = [f"{dossier}/{f.name}:{n.lineno}" for dossier, f in _etapes_alors()
              for n in ast.walk(f) if _est_nue(n)]

    assert fautes == [], f"assertions nues dans un `Alors` — utilise constater(...) : {fautes}"


def test_tout_step_alors_constate_ou_est_explicitement_sans_constat():
    helpers = _helpers()
    # les fonctions qui consignent un constat (point fixe, comme le garde d'écriture)
    constatent = set(_CONSTATER) | {n for n, f in helpers.items() if "constat" in _noms_decorateurs(f)}
    change = True
    while change:
        change = False
        for nom, f in helpers.items():
            if nom not in constatent and _appels(f) & constatent:
                constatent.add(nom)
                change = True
    sans = [f"{d}/{f.name}" for d, f in _etapes_alors()
            if f.name not in _ALORS_SANS_CONSTAT and not (_appels(f) & constatent)]

    assert sans == [], f"`Alors` qui ne consigne aucun constat : {sans}"


def test_les_helpers_atteints_depuis_un_alors_n_ont_pas_d_assertion_nue():
    """On descend dans les helpers appelés depuis un `Alors` SAUF dans ceux décorés `@constat` (leur
    contrat est justement de consigner l'issue d'`AssertionError` internes) et dans `constater*`."""
    helpers = _helpers()
    vus: set[str] = set()
    pile = [n for _, f in _etapes_alors() for n in _appels(f) if n in helpers]
    fautes = []
    while pile:
        nom = pile.pop()
        if nom in vus:
            continue
        vus.add(nom)
        f = helpers[nom]
        if nom in _CONSTATER or "constat" in _noms_decorateurs(f):
            continue
        fautes += [f"{nom}:{n.lineno}" for n in ast.walk(f) if _est_nue(n)]
        pile += [a for a in _appels(f) if a in helpers]

    assert fautes == [], f"assertion nue dans un helper d'`Alors` : {fautes}"


def test_le_test_est_falsifiable_une_assertion_nue_est_bien_detectee():
    """Garde-fou du garde-fou : sans lui, un test vide passerait pour une preuve d'absence."""
    arbre = ast.parse("def f():\n    assert x\n    raise AssertionError('a')\n    expect(y)\n")

    assert sum(_est_nue(n) for n in ast.walk(arbre)) == 3
