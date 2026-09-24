"""Décision 0010 — la bibliothèque PARTAGÉE ne doit pas contenir de vérification creuse.

`0008` gardait le code GÉNÉRÉ (lint au gate). Angle mort : le socle **partagé** que le pipeline
demande justement de réutiliser (`0003`) n'était gardé par rien. Un `@then` à `pass` y est plus
grave qu'une tautologie générée — il est **au catalogue**, donc proposé à tous les cas futurs.

Ces tests figent la suppression et empêchent le retour du motif.
"""

import ast
from pathlib import Path

import pytest

from testpilot.generation import steps_library

_LIB = Path("behave_runtime/steps_library")

# Steps de la bibliothèque dont le corps délègue à un helper qui assertit, ou qui sont des
# ATTENTES portant un double décorateur @when/@then. Le lint 0008 ne suit pas les appels : il les
# signale à tort. Liste explicite plutôt que lint aveugle — un faux positif toléré en silence
# finirait par masquer un vrai.
_DELEGUENT_OU_ATTENDENT = {
    "step_wait_form",          # attente (@when + @then), pas une assertion
    "step_no_dup",             # → no_duplicate() : assert len(ids) <= 1
    "step_validation_error",   # → validation_error_inline() : raise AssertionError (via _poll_until)
    "step_no_partial_record",  # assertit directement
    "step_notification_error", # → validation_error_notification() : expect(...).to_be_visible()
    "step_validation_error_shown", # idem, _odoo_steps.py — délègue au MÊME helper (audit 2026-09-17)
    # ⚠️ Les trois suivants délèguent une VRAIE assertion (vérifié), mais leur helper contient un
    # `warnings.warn(...) + return` quand le snapshot initial manque : dans CE cas le @then passe
    # sans rien vérifier. Défaut RÉEL de la même famille que 0010, signalé au porteur — non
    # corrigé ici pour ne pas élargir le périmètre sans arbitrage.
    "step_count_not_inc",          # → check_count_not_increased() : assert current <= initial
    "step_count_increased_by_one", # → check_count_increased_by_one() : assert current == initial+1
    "step_no_error",               # → no_error_with_keywords() : assert kw not in error_text
}


_CONSTATER = {"constater", "constater_visible", "constater_texte"}


def _assertit(noeud) -> bool:
    """Assertion nue OU constat consigné (`constater*`, lot 03 : la forme d'assertion de la
    bibliothèque, qui consigne en plus la preuve runtime)."""
    for n in ast.walk(noeud):
        if isinstance(n, (ast.Assert, ast.Raise)):
            return True
        if isinstance(n, ast.Call):
            cible = n.func
            nom = cible.id if isinstance(cible, ast.Name) else getattr(cible, "attr", "")
            if nom in _CONSTATER:
                return True
    return False


def _fonctions_then(path: Path):
    """(nom, nœud) des fonctions portant au moins un décorateur @then."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for deco in node.decorator_list:
            fn = deco.func if isinstance(deco, ast.Call) else deco
            nom = getattr(fn, "id", None) or getattr(fn, "attr", None)
            if nom == "then":
                yield node.name, node
                break


def test_le_step_effet_de_bord_a_bien_disparu():
    """Il faisait `pass` : une vérification qui ne vérifiait rien, AU CATALOGUE (0010)."""
    labels = {s.label for s in steps_library.catalogue()}
    fautif = [l for l in labels if "effet de bord" in l]
    assert not fautif, (
        f"Le step à `pass` est de retour au catalogue : {fautif}. Sa promesse (« aucun modèle "
        f"Odoo ») n'est pas tenable — voir 0010 avant de le réintroduire.")


def test_aucun_then_de_la_bibliotheque_nest_un_corps_vide():
    """Garde du motif, pas seulement du cas trouvé : un `@then` à `pass`/`...` ne peut PAS échouer.

    C'est un « conforme » déclaratif (§4.2) et un faux-négatif (§4.4) offert à tous les cas qui
    réutilisent la bibliothèque.
    """
    creux = []
    for py in sorted(_LIB.rglob("*.py")):
        for nom, node in _fonctions_then(py):
            corps = [n for n in node.body if not isinstance(n, ast.Expr)
                     or not isinstance(n.value, ast.Constant)]   # ignore la docstring
            if not corps or all(isinstance(n, ast.Pass) for n in corps):
                creux.append(f"{py.name}::{nom}")
    assert not creux, (
        f"Ces `@then` partagés n'affirment rien et passeront quoi que fasse l'application : "
        f"{creux}. Un step de vérification qui ne vérifie rien ne doit pas exister (0010).")


def test_chaque_then_partage_assertit_ou_delegue_explicitement():
    """Tout `@then` de la bibliothèque assertit lui-même, OU figure dans la liste des délégations
    connues. Un nouveau `@then` sans assertion visible force à se poser la question ici plutôt
    que de passer inaperçu."""
    suspects = []
    for py in sorted(_LIB.rglob("*.py")):
        for nom, node in _fonctions_then(py):
            assertit = _assertit(node)
            if not assertit and nom not in _DELEGUENT_OU_ATTENDENT:
                suspects.append(f"{py.name}::{nom}")
    assert not suspects, (
        f"`@then` partagé sans assertion ni délégation déclarée : {suspects}. S'il délègue à un "
        f"helper qui assertit, ajoutez-le à _DELEGUENT_OU_ATTENDENT en le vérifiant — sinon "
        f"c'est une vérification creuse (0010).")


@pytest.mark.parametrize("nom_helper, doit_assertir", [
    ("no_duplicate", True),
    ("validation_error_inline", True),
])
def test_les_delegations_declarees_assertissent_vraiment(nom_helper, doit_assertir):
    """La liste de délégations ci-dessus n'est une excuse que si les helpers assertissent
    RÉELLEMENT — sinon elle deviendrait un moyen commode de faire taire le garde."""
    source = (_LIB / "_base_helpers.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == nom_helper), None)
    assert fn is not None, f"helper {nom_helper} introuvable"
    assertit = _assertit(fn)
    assert assertit is doit_assertir, (
        f"{nom_helper} est déclaré comme « délègue une assertion » mais n'assertit rien.")
