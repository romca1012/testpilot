"""Garde anti-régression : un step GÉNÉRIQUE ne doit reconnaître qu'un standard du web, jamais un
détail d'implémentation d'une seule application — bug réel `validation_error_inline` (cas C37,
2026-09-14) : vivait dans `generic/`, sous un nom générique, mais ne reconnaissait QUE la classe
CSS `s_website_form_field.o_has_error` du website builder Odoo.

Deux filets, complémentaires :
- **dynamique** — `tests/test_conformite_connecteur_web.py` rejoue les steps génériques contre de
  VRAIES applications non-Odoo : la preuve qu'un comportement marche réellement, pas seulement
  qu'il ne contient pas tel mot.
- **statique, ICI** — repère tout marqueur Odoo qui se glisserait dans un step (ou un helper qu'il
  appelle) classé `generic/`, AVANT même de lancer un navigateur. Bloque le défaut à la revue de
  code plutôt que six semaines plus tard sur l'application d'un client.

⚠️ Restreint aux chaînes passées à un appel de type `.locator(...)`/`.get_by_role(...)` (etc.) —
PAS au texte brut du fichier : un docstring qui EXPLIQUE la règle (comme celui de
`generic/_generic_steps.py` lui-même, qui mentionne `context.odoo` pour dire que ce fichier ne
doit PAS y toucher) ne doit jamais se faire passer pour une violation.

Un marqueur Odoo trouvé n'est pas automatiquement une erreur : `_REPLIS_ODOO_JUSTIFIES` liste,
un par un, les helpers qui vérifient LÉGITIMEMENT un repli Odoo — À CONDITION qu'un signal
générique soit vérifié EN PREMIER, prouvé par la suite de conformité citée en commentaire.
"""

from __future__ import annotations

import ast
from pathlib import Path

_LIB = Path(__file__).resolve().parent.parent / "behave_runtime" / "steps_library"
_GENERIC = _LIB / "generic" / "_generic_steps.py"
_BASE_HELPERS = _LIB / "_base_helpers.py"

# Motifs qui n'existent QUE côté Odoo — jamais un mot générique comme "odoo" seul (qui apparaît
# légitimement en prose, ex. le docstring de generic/_generic_steps.py expliquant la séparation).
_MARQUEURS_ODOO = (
    "o_has_error", "s_website_form", "o_notification", "odoorpc", "context.odoo", "website_form",
)

# Helper (dans _base_helpers.py) → preuve que le repli Odoo qu'il contient est LÉGITIME (un signal
# générique vérifié en premier, confirmé par la suite de conformité citée).
_REPLIS_ODOO_JUSTIFIES = {
    "validation_error_inline": (
        "vérifie [role=alert] / .error / .alert-danger / .is-invalid AVANT le motif Odoo (repli, "
        "préservé) — preuve dynamique : test_conformite_connecteur_web.py::"
        "test_soumission_vide_affiche_une_erreur_reconnue"
    ),
    "no_error_with_keywords": (
        "vérifie [role=alert] / .alert-danger / .text-danger EN MÊME TEMPS que le motif Odoo "
        ".o_notification.border-danger — jamais comme seul chemin, contrairement au bug "
        "d'origine de validation_error_inline (trouvé par cette garde, 2026-09-14)"
    ),
}


def _appels_selecteurs(node: ast.AST) -> list[str]:
    """Chaînes passées à un appel `.xxx(...)` dans CE nœud — locator/get_by_role/get_by_text/…
    Les SEULS endroits où un marqueur Odoo change réellement le comportement d'un test ; jamais
    un docstring, un commentaire (invisible à l'AST) ou un message de log."""
    chaines = []
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
            for arg in n.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    chaines.append(arg.value)
    return chaines


def _fonctions(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    return {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}


def _est_step(fn: ast.FunctionDef) -> bool:
    for deco in fn.decorator_list:
        cible = deco.func if isinstance(deco, ast.Call) else deco
        nom = getattr(cible, "id", "")
        if nom in ("given", "when", "then"):
            return True
    return False


def _noms_appeles(fn: ast.FunctionDef) -> set[str]:
    return {n.func.id for n in ast.walk(fn)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}


def test_aucun_marqueur_odoo_inline_dans_un_step_generique():
    """Un step déclaré ici ne doit jamais coder LUI-MÊME un sélecteur Odoo — s'il en a besoin,
    c'est qu'il n'est pas générique et doit vivre dans `../odoo/`."""
    tree = ast.parse(_GENERIC.read_text(encoding="utf-8"))
    fautifs = []
    for fn in _fonctions(tree).values():
        if not _est_step(fn):
            continue
        for selecteur in _appels_selecteurs(fn):
            trouve = [m for m in _MARQUEURS_ODOO if m in selecteur]
            if trouve:
                fautifs.append((fn.name, selecteur, trouve))

    assert not fautifs, (
        f"step(s) générique(s) codant un sélecteur Odoo en dur — devrait vivre dans "
        f"steps_library/odoo/ : {fautifs}")


def test_aucun_helper_appele_par_un_step_generique_ne_cache_un_odoo_non_justifie():
    """Le vrai bug (2026-09-14) : pas dans `generic/` lui-même, mais dans le helper QU'IL
    appelle (`_base_helpers.py`). Tout marqueur Odoo trouvé y est TOLÉRÉ seulement s'il figure
    dans `_REPLIS_ODOO_JUSTIFIES`, avec la preuve qu'un signal générique passe en premier."""
    generic_tree = ast.parse(_GENERIC.read_text(encoding="utf-8"))
    appeles: set[str] = set()
    for fn in _fonctions(generic_tree).values():
        if _est_step(fn):
            appeles |= _noms_appeles(fn)

    base_tree = ast.parse(_BASE_HELPERS.read_text(encoding="utf-8"))
    helpers = _fonctions(base_tree)

    fautifs = []
    for nom in appeles:
        fn = helpers.get(nom)
        if fn is None:
            continue   # pas un helper de _base_helpers.py (ex. un import d'ailleurs) : hors sujet
        marqueurs_trouves = {
            m for selecteur in _appels_selecteurs(fn) for m in _MARQUEURS_ODOO if m in selecteur
        }
        if marqueurs_trouves and nom not in _REPLIS_ODOO_JUSTIFIES:
            fautifs.append((nom, sorted(marqueurs_trouves)))

    assert not fautifs, (
        f"helper(s) appelé(s) par un step générique contenant un marqueur Odoo NON justifié "
        f"(ajoute une entrée à _REPLIS_ODOO_JUSTIFIES avec une preuve de conformité si c'est "
        f"légitime) : {fautifs}")


def test_les_repos_justifies_existent_vraiment_et_restent_a_jour():
    """`_REPLIS_ODOO_JUSTIFIES` ne doit jamais devenir une liste de vœux : chaque entrée doit
    encore correspondre à un vrai helper, encore appelé par un step générique, qui contient
    encore RÉELLEMENT un marqueur Odoo — sinon c'est une exception qui ne sert plus à rien."""
    generic_tree = ast.parse(_GENERIC.read_text(encoding="utf-8"))
    appeles: set[str] = set()
    for fn in _fonctions(generic_tree).values():
        if _est_step(fn):
            appeles |= _noms_appeles(fn)

    base_tree = ast.parse(_BASE_HELPERS.read_text(encoding="utf-8"))
    helpers = _fonctions(base_tree)

    for nom in _REPLIS_ODOO_JUSTIFIES:
        assert nom in appeles, f"{nom} n'est plus appelé par aucun step générique — retire l'entrée"
        fn = helpers.get(nom)
        assert fn is not None, f"{nom} n'existe plus dans _base_helpers.py — retire l'entrée"
        marqueurs = {m for s in _appels_selecteurs(fn) for m in _MARQUEURS_ODOO if m in s}
        assert marqueurs, f"{nom} ne contient plus aucun marqueur Odoo — retire l'entrée"
