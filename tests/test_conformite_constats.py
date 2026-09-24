"""Lot 03 (D3) — le verdict prouvé de bout en bout : Behave + Playwright RÉELS, sous-processus complet.

Sur la fixture locale « torture » (aucun réseau) : un `Alors` qui constate → `conforme` ; un `Alors` qui
ne fait qu'attendre, ou dont l'assertion est dans une branche non prise → `indetermine` / `aucun_constat` ;
un constat qui échoue → `non_conforme`. Plus les `constater_visible/texte` face à une VRAIE page qui ne
satisfait pas la condition (falsifiabilité).

Exclue de `pytest -q` (marker `conformance`) : navigateur réel.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from testpilot import config
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
    constater("login1" in context.page.url, "mauvaise page")


@then("le bouton est en échec")
def step_ko(context):
    constater("page-qui-n-existe-pas" in context.page.url, "l'URL ne contient pas le fragment attendu")


@then("la vérification est dans une branche non prise")
def step_branche(context):
    if "page-qui-n-existe-pas" in context.page.url:
        constater(True, "jamais exécuté")
'''

_FEATURE = """Fonctionnalité: Preuve de vérification
  Scénario: {titre}
    Soit j'accède à la page d'accueil de l'application
    Alors {alors}
"""


def _rejouer(alors: str, titre: str):
    dossier = Path(tempfile.mkdtemp(prefix="l03_gen_"))
    module = "l03_cas"
    (dossier / f"{module}.feature").write_text(_FEATURE.format(titre=titre, alors=alors), encoding="utf-8")
    (dossier / f"{module}_steps.py").write_text(_STEPS, encoding="utf-8")
    runner = BehaveRunner(connection={"WEB_URL": _TORTURE.as_uri(), "WEB_USER": "", "WEB_PASSWORD": ""},
                          connector_type="web", generated_dir=dossier)
    outcome = Executor(runner, max_retries=0).execute(module)
    return outcome, st.derive_verdict(outcome, connector_type="web")


def test_un_alors_qui_constate_donne_conforme():
    outcome, verdict = _rejouer("l'identifiant est affiché", "constat réussi")

    assert outcome.real_run.scenarios[0].constats_reussis >= 1
    assert (verdict.execution_status, verdict.functional_status) == (st.EXEC_SUCCESS, st.FUNC_CONFORME)


def test_un_alors_qui_ne_fait_qu_attendre_n_est_jamais_conforme():
    outcome, verdict = _rejouer("j'attends la soumission du formulaire", "attente seule")

    assert outcome.real_run.scenarios[0].status == "passed", "Behave le juge vert…"
    assert outcome.real_run.scenarios[0].constats_reussis == 0
    assert (verdict.execution_status, verdict.functional_status) == (st.EXEC_SUCCESS, st.FUNC_INDETERMINE)
    assert verdict.scenarios[0].cause_category == "aucun_constat"
    assert st.statut_de_test(verdict.execution_status, verdict.functional_status) == st.STATUT_RETEST


def test_une_assertion_dans_une_branche_non_prise_n_est_jamais_conforme():
    outcome, verdict = _rejouer("la vérification est dans une branche non prise", "branche non prise")

    assert outcome.real_run.scenarios[0].status == "passed"
    assert verdict.functional_status == st.FUNC_INDETERMINE
    assert verdict.scenarios[0].cause_category == "aucun_constat"


def test_un_constat_qui_echoue_reste_un_non_conforme():
    outcome, verdict = _rejouer("le bouton est en échec", "constat en échec")

    assert (verdict.execution_status, verdict.functional_status) == (st.EXEC_SUCCESS, st.FUNC_NON_CONFORME)


# ── Falsifiabilité des helpers contre une VRAIE page ────────────────────────────────────────

@pytest.fixture(scope="module")
def page():
    import _base_helpers  # noqa: F401  (chemin déjà posé)

    with sync_playwright() as pw:
        navigateur = pw.chromium.launch(headless=True)
        p = navigateur.new_page()
        p.set_content("<h1 id='t'>Bonjour</h1><p id='cache' style='display:none'>secret</p>")
        yield p
        navigateur.close()


def test_constater_visible_reussit_sur_un_element_visible_et_echoue_sur_un_masque(page, tmp_path, monkeypatch):
    import _base_helpers as H

    monkeypatch.setenv(H.CONSTATS_FILE_ENV, str(tmp_path / "c.jsonl"))
    H.constater_visible(page.locator("#t"), "titre absent", timeout=1000)

    with pytest.raises(AssertionError, match="masqué"):
        H.constater_visible(page.locator("#cache"), "masqué", timeout=500)
    with pytest.raises(AssertionError):
        H.constater_visible(page.locator("#inexistant"), "absent", timeout=500)


def test_constater_texte_reussit_sur_le_bon_texte_et_echoue_sur_un_mauvais(page, tmp_path, monkeypatch):
    import _base_helpers as H

    monkeypatch.setenv(H.CONSTATS_FILE_ENV, str(tmp_path / "c.jsonl"))
    H.constater_texte(page.locator("#t"), "Bonjour", timeout=1000)
    H.constater_texte(page.locator("#t"), "Bonjour", timeout=1000, exact=True)

    with pytest.raises(AssertionError):
        H.constater_texte(page.locator("#t"), "Au revoir", timeout=500)
    with pytest.raises(AssertionError):
        H.constater_texte(page.locator("#t"), "Bonj", timeout=500, exact=True)
