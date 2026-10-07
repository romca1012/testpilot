"""Q1 (D16, D17) — la preuve PAR `Alors`, de bout en bout : Behave + Playwright RÉELS, sous-processus complet.

Avant Q1, un scénario était `conforme` dès UN constat réussi sous un `Alors`, même si un autre `Alors`
assertif n'avait rien constaté. Ces tests le verrouillent sur la fixture locale « torture » (aucun réseau) :

- deux `Alors` assertifs dont l'un ne constate rien (branche non prise) → `indetermine`, cause `aucun_constat` ;
- l'attente « j'attends la soumission du formulaire » placée APRÈS un `Alors` qui constate n'abaisse pas
  un verdict par ailleurs prouvé (elle est déclarée non assertive, D17) ;
- deux `Alors` qui constatent chacun → `conforme` (falsifiabilité inverse : la règle ne devient pas systématique).

Exclue de `pytest -q` (marker `conformance`) : navigateur réel.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

from testpilot.execution.behave_runner import BehaveRunner
from testpilot.execution.executor import Executor
from testpilot.verdict import status as st

_STEPS_LIB = Path(__file__).resolve().parent.parent / "behave_runtime" / "steps_library"
sys.path.insert(0, str(_STEPS_LIB))
_TORTURE = (Path(__file__).resolve().parent / "fixtures" / "torture_app" / "login1.html").resolve()

pytestmark = pytest.mark.conformance

_STEPS = '''
from behave import then
from _base_helpers import constater, constater_visible


@then("l'identifiant est affiché")
def step_ok(context):
    constater_visible(context.page.get_by_text("Identifiant"), "aucun champ identifiant")


@then("la page de connexion est ouverte")
def step_url(context):
    constater("login1" in context.page.url, "mauvaise page")


@then("la vérification est dans une branche non prise")
def step_branche(context):
    if "page-qui-n-existe-pas" in context.page.url:
        constater(True, "jamais exécuté")
'''

_FEATURE = """Fonctionnalité: Preuve par Alors
  Scénario: {titre}
    Soit j'accède à la page d'accueil de l'application
{alors}
"""


def _rejouer(alors: list[str], titre: str):
    dossier = Path(tempfile.mkdtemp(prefix="q1_gen_"))
    module = "q1_cas"
    corps = "\n".join(f"    {ligne}" for ligne in alors)
    (dossier / f"{module}.feature").write_text(_FEATURE.format(titre=titre, alors=corps), encoding="utf-8")
    (dossier / f"{module}_steps.py").write_text(_STEPS, encoding="utf-8")
    runner = BehaveRunner(connection={"WEB_URL": _TORTURE.as_uri(), "WEB_USER": "", "WEB_PASSWORD": ""},
                          connector_type="web", generated_dir=dossier)
    outcome = Executor(runner, max_retries=0).execute(module)
    return outcome, st.derive_verdict(outcome, connector_type="web")


def test_deux_alors_dont_un_ne_constate_rien_ne_donnent_pas_conforme():
    """L'ancien code disait `conforme` : un constat réussi suffisait, le second `Alors` pouvait être vide."""
    outcome, verdict = _rejouer(
        ["Alors l'identifiant est affiché", "Et la vérification est dans une branche non prise"],
        "un Alors vide")

    scenario = outcome.real_run.scenarios[0]
    assert scenario.status == "passed", "Behave le juge vert…"
    assert scenario.constats_reussis == 1, "…et un constat a bien réussi (c'est l'ancien critère)"
    assert (verdict.execution_status, verdict.functional_status) == (st.EXEC_SUCCESS, st.FUNC_INDETERMINE)
    assert verdict.scenarios[0].cause_category == "alors_sans_constat"
    assert "branche non prise" in verdict.scenarios[0].step_text  # l'Alors fautif est NOMMÉ (trace)


def test_deux_alors_qui_constatent_chacun_donnent_conforme():
    _, verdict = _rejouer(
        ["Alors l'identifiant est affiché", "Et la page de connexion est ouverte"], "deux constats")

    assert (verdict.execution_status, verdict.functional_status) == (st.EXEC_SUCCESS, st.FUNC_CONFORME)


def test_une_attente_apres_un_alors_prouve_ne_baisse_pas_le_verdict():
    """D17 : « j'attends la soumission du formulaire » est non assertif — il ne compte ni comme preuve
    ni comme `Alors` vide."""
    _, verdict = _rejouer(
        ["Alors l'identifiant est affiché", "Et j'attends la soumission du formulaire"], "attente après preuve")

    assert (verdict.execution_status, verdict.functional_status) == (st.EXEC_SUCCESS, st.FUNC_CONFORME)
