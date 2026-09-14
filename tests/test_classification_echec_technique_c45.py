"""Le défaut le plus important trouvé cette session (cas C45, SauceDemo, 2026-09-14) : un échec
TECHNIQUE de notre propre bibliothèque (« je n'ai rien trouvé à cliquer ») était classé comme un
VRAI DÉFAUT APPLICATIF — parce que le code technique et les vraies vérifications métier levaient
tous les deux le même `AssertionError` générique, que `defect_taxonomy` classe systématiquement
`assertion_mismatch` (verdict `non_conforme`, une accusation contre l'application).

C37 avait déjà donné ce même genre de leçon (`validation_error_inline`) ; celle-ci est plus large :
ce n'est pas UN step particulier qui accusait à tort, c'est la RÈGLE DE CLASSIFICATION elle-même,
qui touche `click_first_actionable` et tout ce qui en dépend (`click_button`, `select_product_*`,
`click_onglet`, …) — un défaut STRUCTUREL, pas local à un connecteur.

Correctif, même patron que `InvalidOptionValueError`/`DonneeRefuseeError` (décisions 0015/0019) :
deux classes DÉDIÉES (`ElementIntrouvableError`, `NavigationImpossibleError`), mappées dans
`defect_taxonomy._EXCEPTION_TO_CAUSE`, jamais un `AssertionError` nu pour un défaut technique.

En creusant, un DEUXIÈME défaut est apparu : `generic/_generic_steps.py::step_select_product_in_list`
dupliquait `_base_helpers.select_product_in_list` au lieu de l'appeler — un premier correctif posé
sur le helper partagé n'avait donc RIEN changé au comportement réel du step. Trouvé en reproduisant
le scénario réel contre https://www.saucedemo.com : le helper appelé directement réussissait, le
même scénario joué via Behave échouait encore. `tests/test_conformite_connecteur_web.py` couvre la
preuve dynamique contre une vraie application ; ce fichier verrouille la classification et la
délégation qui l'ont rendue possible.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "behave_runtime" / "steps_library"))

from _base_helpers import ElementIntrouvableError, NavigationImpossibleError  # noqa: E402

from testpilot.verdict import defect_taxonomy as dt  # noqa: E402

_RACINE = Path(__file__).resolve().parent.parent


def _charger_generic_steps():
    """Même helper que `test_generic_navigation_step.py` — module chargé directement, layout
    plat réel, aucun Playwright."""
    steps_lib = _RACINE / "behave_runtime" / "steps_library"
    sys.path.insert(0, str(steps_lib))
    spec = importlib.util.spec_from_file_location(
        "_generic_steps_sous_test_c45", steps_lib / "generic" / "_generic_steps.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ── 1. La classification : le cœur du correctif ────────────────────────────────

def test_element_introuvable_est_classe_technique_pas_metier():
    """Le défaut exact de C45 : `ElementIntrouvableError` doit rester HORS de
    `assertion_mismatch` — sinon toute la correction ne sert à rien."""
    assert dt._EXCEPTION_TO_CAUSE["ElementIntrouvableError"] == dt.WRONG_FIELD_NAME
    assert dt._EXCEPTION_TO_CAUSE["ElementIntrouvableError"] != dt.ASSERTION_MISMATCH


def test_navigation_impossible_est_classee_technique_pas_metier():
    assert dt._EXCEPTION_TO_CAUSE["NavigationImpossibleError"] == dt.WRONG_NAVIGATION
    assert dt._EXCEPTION_TO_CAUSE["NavigationImpossibleError"] != dt.ASSERTION_MISMATCH


def test_le_classement_se_fait_bien_sur_le_type_pas_sur_un_texte_devine():
    """Décision 0015 : le signal est le TYPE d'exception. Un message qui ressemblerait à une
    accusation métier ne doit RIEN changer si le type, lui, dit « technique »."""
    from dataclasses import dataclass

    @dataclass
    class FakeFailure:
        scenario_name: str = "S"
        step_text: str = ""
        failure_type: str = "unknown"
        traceback_summary: str = ""
        raw: str = ""

    f = FakeFailure(
        raw="_base_helpers.ElementIntrouvableError: Bouton 'Continue' : aucun élément "
            "actionnable sur https://www.saucedemo.com/checkout-step-one.html",
        step_text="Alors le formulaire bloque la progression")
    assert dt.classify_failure(f) == dt.WRONG_FIELD_NAME


def test_les_deux_classes_ne_sont_pas_des_AssertionError():
    """Sous-classer `AssertionError` referait exactement le bug : Behave affiche
    « ASSERT FAILED: » UNIQUEMENT pour `AssertionError`, ce qui masquerait le nom de la classe et
    ferait retomber le classement sur les mots-clés — la voie dégradée, pas le signal."""
    assert not issubclass(ElementIntrouvableError, AssertionError)
    assert not issubclass(NavigationImpossibleError, AssertionError)


# ── 2. La délégation : sans elle, le correctif du helper ne sert à rien ────────

def test_step_select_product_in_list_delegue_au_helper_partage():
    """LE piège trouvé en rejouant le scénario réel : ce step avait sa PROPRE copie de la
    logique, désynchronisée de `_base_helpers.select_product_in_list`. Un correctif sur le
    helper (le repli générique `a:has-text(...)`, cas C45) restait sans AUCUN effet sur ce
    step — le seul réellement invoqué par un `.feature` généré."""
    mod = _charger_generic_steps()
    contexte = SimpleNamespace(page="la-page-espionne")

    with patch.object(mod, "select_product_in_list") as espion:
        mod.step_select_product_in_list(contexte, "Sauce Labs Backpack")

    espion.assert_called_once_with("la-page-espionne", "Sauce Labs Backpack")


def test_step_select_product_partial_delegue_au_helper_partage():
    mod = _charger_generic_steps()
    contexte = SimpleNamespace(page="la-page-espionne")

    with patch.object(mod, "select_product_partial") as espion:
        mod.step_select_product_partial(contexte, "Backpack")

    espion.assert_called_once_with("la-page-espionne", "Backpack")
