"""Revue `verdict-reviewer` des décisions D30-D32 (2026-10-09) — chaque contournement reproduit par la revue, prouvé fermé.

B1 : une seconde édition du métier (titre seul) approuvait d'office une version restée à relire (D31 en attente, correction
     D30 à relire) — le test de l'ancienne attente ressortait `conforme`.
B2 : une écriture `context.X` ajoutée par la correction dans une fonction creuse (un `@step` d'action) échappait au gel.
C1 : une exécution non clôturée faisait repasser au vert un cas « Retest ».
C2 : rien ne prouvait que le run transmet le métier au runner (D32).
C3 : le classement « creuse » n'était pas aussi prudent qu'annoncé (`raise AssertionError`, helper par alias).
+ `global`/`nonlocal` refusés à l'écriture (réaffecter un helper lu par une vérification sans toucher la liaison de module).
"""

from __future__ import annotations

import ast
from types import SimpleNamespace

import pytest

from testpilot import config
from testpilot.api import schemas
from testpilot.api.routes import cases as route
from testpilot.api.services import generation_service, run_service
from testpilot.execution.behave_result import BehaveResult, BehaveScenario
from testpilot.generation import correction_agent
from testpilot.generation import gel_verifications as gel
from testpilot.generation.repair_diff import VERIFICATION_AFFAIBLIE
from testpilot.generation.tools import ToolContext
from testpilot.generation.tools import write as w
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import (
    CaseRepo,
    ExecutionRepo,
    ModuleRepo,
    ProjectRepo,
    ReviewRepo,
    VersionRepo,
    ensure_default_module,
)
from testpilot.verdict import review_gate
from testpilot.verdict import status as st


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(run_service, "_expliquer", lambda *a, **k: "")
    monkeypatch.setattr(run_service, "_joindre_captures", lambda *a, **k: None)
    c = get_initialized_db(tmp_path / "revue.db")
    yield c
    c.close()


def _run_vert(conn, cid: int, version_id: int) -> None:
    resultat = BehaveResult(success=True, returncode=0, dry_run=False)
    resultat.scenarios = [BehaveScenario(name="S", status="passed", duration=1.0)]
    resultat.passed = 1
    outcome = SimpleNamespace(real_run=resultat, dry_run_passed=True, retried=False, error=None, attempts=[])
    run_service._persist(conn, ExecutionRepo(conn).create(test_case_id=cid, version_id=version_id), cid,
                         st.derive_verdict(outcome, connector_type="web"), outcome, 0.1)


def _cas_vert(conn) -> tuple[int, int]:
    pid = ProjectRepo(conn).create(name="P")
    cid = CaseRepo(conn).create(title="Remise", module_id=ModuleRepo(conn).create(project_id=pid, name="M"),
                                feature_slug="remise")
    v1 = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="", feature_content="# test 10 %",
                                  steps_content="# steps", title="Remise", test_steps="Valider",
                                  expected_result="Remise de 10 %")
    CaseRepo(conn).set_current_version(cid, v1)
    ReviewRepo(conn).create(test_case_id=cid, version_id=v1, decision="approved", reviewer="humain", repair_budget=2)
    _run_vert(conn, cid, v1)
    return cid, v1


def _editer(conn, cid: int, **champs) -> int:
    return route.update_case_metier(cid, schemas.CaseMetierIn(**champs), conn=conn).version_id


def _points(conn, cid: int) -> set[str]:
    cas = CaseRepo(conn).get(cid)
    return {p["kind"] for p in generation_service.lint_warnings_for_version(
        conn, cas, VersionRepo(conn).list_for_case(cid), cas["current_version_id"])}


# ── B1 ────────────────────────────────────────────────────────────────────────────────────────────────────


def test_falsifiable_corriger_ensuite_le_titre_ne_blanchit_pas_une_attente_changee(conn):
    cid, _ = _cas_vert(conn)
    _editer(conn, cid, expected_result="Remise de 15 %")

    v3 = _editer(conn, cid, title="Remise fidélité")

    assert review_gate.evaluate_gate(ReviewRepo(conn), v3).allowed is False
    assert generation_service.ATTENTE_METIER_CHANGEE in _points(conn, cid)
    assert schemas.case_summary(CaseRepo(conn).get(cid)).statut == st.STATUT_RETEST


STEPS = ("from behave import then\nfrom _base_helpers import constater\n\n"
         "@then('le total vaut \"{m}\"')\ndef total(context, m):\n"
         "    constater(context.page.locator('#total').inner_text() == m, 'total')\n\n"
         "@then('la page est prête')\ndef prete(context):\n    assert True\n")


def test_falsifiable_corriger_le_titre_ne_blanchit_pas_une_correction_a_relire(conn, monkeypatch):
    mid = ensure_default_module(conn, "m")
    cid = CaseRepo(conn).create(title="C", module_id=mid, feature_slug="c")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="h", feature_content="# f",
                                   steps_content=STEPS)
    CaseRepo(conn).set_current_version(cid, vid)
    affaiblie = (STEPS.replace("    assert True\n", "    constater(context.page.locator('h1').is_visible(), 'p')\n")
                 .replace("inner_text() == m", "inner_text() != ''"))
    monkeypatch.setattr(correction_agent, "propose_correction", lambda **kw: correction_agent.CorrectionProposal(
        changed=True, feature_content="# f", steps_content=affaiblie, summary="ok", cost_usd=0.0, stopped_reason="done"))
    generation_service._finaliser_version_generee(conn, cid, vid, module_name="c", dry_runner=object())

    v_titre = _editer(conn, cid, title="C (coquille)")

    assert review_gate.evaluate_gate(ReviewRepo(conn), v_titre).allowed is False
    assert VERIFICATION_AFFAIBLIE in _points(conn, cid), "le signal suit le test recopié"


# ── B2 ────────────────────────────────────────────────────────────────────────────────────────────────────

AVEC_ACTION = """from behave import when, then, step
from _base_helpers import constater

@when('je relève le total')
def releve(context):
    context.total = context.page.locator('#total').inner_text()

@step('la confirmation est attendue')
def attendre(context):
    context.page.wait_for_timeout(100)

@then('le total vaut "{m}"')
def total(context, m):
    constater(context.total == m, 'total')
"""


def test_falsifiable_une_ecriture_ajoutee_dans_une_fonction_creuse_est_gelee():
    """Reproduit par la revue : le sous-total remplaçait le total lu par la vérification, et la correction était approuvée."""
    trichee = AVEC_ACTION.replace("    context.page.wait_for_timeout(100)\n",
                                  "    context.page.wait_for_timeout(100)\n"
                                  "    context.total = context.page.locator('.sous-total').inner_text()\n")

    assert gel.steps_modifies(AVEC_ACTION, trichee, creuses=w.verifications_creuses)


# ── C1 ────────────────────────────────────────────────────────────────────────────────────────────────────


def test_falsifiable_une_execution_non_cloturee_ne_rend_pas_le_vert(conn):
    cid, _ = _cas_vert(conn)
    v2 = _editer(conn, cid, expected_result="Remise de 15 %")
    ReviewRepo(conn).create(test_case_id=cid, version_id=v2, decision="approved", reviewer="humain", repair_budget=2)

    ExecutionRepo(conn).create(test_case_id=cid, version_id=v2)  # run lancé, pas encore (ou jamais) clôturé

    assert schemas.case_summary(CaseRepo(conn).get(cid)).statut == st.STATUT_RETEST
    lignes, _, _ = CaseRepo(conn).page(statut=st.STATUT_PASSED)
    assert cid not in {ligne["id"] for ligne in lignes}


# ── C2 ────────────────────────────────────────────────────────────────────────────────────────────────────


class _RunnerQuiEcoute:
    def __init__(self):
        self.metier = None

    def cibler_artefacts(self, _chemin):
        pass

    def cibler_execution(self, _execution_id):
        pass

    def cibler_metier(self, texte):
        self.metier = texte

    def dry_run(self, _module_name):
        return BehaveResult(success=True, returncode=0, dry_run=True)

    def real_run(self, _module_name):
        return BehaveResult(success=True, returncode=0, scenarios=[BehaveScenario(name="s", status="passed")])


def test_falsifiable_le_run_transmet_le_metier_de_la_version_au_runner(conn):
    pid = ProjectRepo(conn).create(name="P", connector_type="web", base_url="https://example.invalid", database="",
                                   username="", password="")
    cid = CaseRepo(conn).create(title="C", module_id=ModuleRepo(conn).create(project_id=pid, name="M"), feature_slug="d")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="", feature_content="Alors 9999",
                                   steps_content="", expected_result="Contrat jusqu'en 2027")
    CaseRepo(conn).set_current_version(cid, vid)
    runner = _RunnerQuiEcoute()

    run_service._execute_and_persist(conn, ExecutionRepo(conn).create(test_case_id=cid, version_id=vid), cid, "d", runner)

    assert runner.metier is not None and "2027" in runner.metier and "9999" not in runner.metier


# ── C3 et `global` ───────────────────────────────────────────────────────────────────────────────────────


def _creuses(code: str) -> set[str]:
    arbre = ast.parse(code)
    ids = w.verifications_creuses(arbre)
    return {f.name for f in ast.walk(arbre) if isinstance(f, ast.FunctionDef) and id(f) in ids}


@pytest.mark.parametrize("corps", [
    "    lu = context.page.title()\n    if lu != m:\n        raise AssertionError('total')\n",
    "    v = page_affiche_texte\n    v(context, m)\n",
])
def test_ce_qu_on_ne_sait_pas_juger_est_repute_reel(corps):
    code = "from behave import then\n\n@then('t \"{m}\"')\ndef t(context, m):\n" + corps

    assert _creuses(code) == set()


@pytest.mark.parametrize("instruction", ["global _lire_total", "nonlocal x"])
def test_falsifiable_global_et_nonlocal_sont_refuses_a_l_ecriture(tmp_path, instruction):
    code = ("from behave import when\n\ndef _f():\n    x = 1\n\n    def g():\n        " + instruction + "\n"
            "        x = 2\n    return g\n\n@when('a')\ndef a(context):\n    context.page.reload()\n")
    if instruction.startswith("global"):
        code = ("from behave import when\n\n@when('a')\ndef a(context):\n    " + instruction + "\n"
                "    _lire_total = lambda page: '129,51'\n")

    sortie = w.write_steps_file(ToolContext(module_name="m", generated_dir=tmp_path), code)

    assert not sortie.ok and instruction.split()[0] in sortie.observation
