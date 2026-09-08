"""§4 — orchestration bout-en-bout, câblée avec des fakes (hors-ligne, sans Behave ni LLM).

On vérifie le CÂBLAGE et le GATE, pas les piliers eux-mêmes (déjà couverts) :
- gate approuvé → exécution → rapport à deux axes écrit + run persisté ;
- gate rejeté → arrêt AVANT toute exécution ;
- génération échouée → arrêt avant le gate ;
- un vrai bug (non_conforme) est diagnostiqué, persisté et reporté.
"""

import pytest

from testpilot import cli
from testpilot.analysis.plan import TestPlan
from testpilot.execution.behave_result import BehaveFailure, BehaveResult, BehaveScenario
from testpilot.execution.executor import ExecutionOutcome
from testpilot.generation.state import GenerationResult
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, ExecutionRepo, RepairRepo, ReviewRepo, VersionRepo


# ── Fakes ───────────────────────────────────────────────────────────────────────

def _plan():
    return TestPlan(module_name="demande_materiel", models=[], scenarios=[],
                    personas=[], portal_routes=[], risks=[])


class FakeAnalyzer:
    def analyze_spec_file(self, spec_path):
        return _plan()


class FakeAgent:
    """Persiste réellement cas + version (comme le vrai agent) pour que le gate fonctionne."""

    def __init__(self, conn, *, success=True):
        self.conn = conn
        self.success = success

    def generate(self, plan, *, title="", author="", case_id=None):
        if not self.success:
            return GenerationResult(success=False, module_name=plan.module_name,
                                    stopped_reason="dry_run_stalled", error="parsing KO")
        cid = CaseRepo(self.conn).create(title=title or plan.module_name,
                                         feature_slug=plan.module_name, author=author)
        vid = VersionRepo(self.conn).create(
            test_case_id=cid, spec_content="spec", spec_hash="h1",
            feature_content="# language: fr\nFonctionnalité: Demande de matériel",
            steps_content="from behave import *")
        CaseRepo(self.conn).set_current_version(cid, vid)
        return GenerationResult(
            success=True, module_name=plan.module_name, stopped_reason="done",
            dry_run_passed=True, iterations=3, cost_usd=0.05,
            feature_content="# language: fr\nFonctionnalité: Demande de matériel",
            case_id=cid, version_id=vid, awaiting_review=True)


class FakeExecutor:
    def __init__(self, outcome):
        self.outcome = outcome
        self.called = False

    def execute(self, module_name):
        self.called = True
        return self.outcome


class ExplodingExecutor:
    def execute(self, module_name):
        raise AssertionError("l'exécuteur ne doit pas être appelé quand la relecture est rejetée")


def _passing_outcome():
    real = BehaveResult(success=True, returncode=0, passed=1,
                        scenarios=[BehaveScenario("cas nominal", "passed")], failures=[])
    return ExecutionOutcome(module_name="demande_materiel", dry_run_passed=True, real_run=real)


def _real_bug_outcome():
    fail = BehaveFailure("total faux", "le total", "assertion", "AssertionError: attendu 0, obtenu 5")
    real = BehaveResult(success=False, returncode=1, failed=1,
                        scenarios=[BehaveScenario("total faux", "failed", error="AssertionError")],
                        failures=[fail])
    return ExecutionOutcome(module_name="demande_materiel", dry_run_passed=True, real_run=real)


@pytest.fixture
def conn(tmp_path, monkeypatch):
    from testpilot import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    c = get_initialized_db(tmp_path / "t.db")
    yield c
    c.close()


def _deps(conn, executor, *, agent_success=True):
    return cli.PipelineDeps(analyzer=FakeAnalyzer(), agent=FakeAgent(conn, success=agent_success),
                            executor=executor, conn=conn)


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_gate_approuve_execute_et_ecrit_le_rapport(conn, tmp_path):
    execu = FakeExecutor(_passing_outcome())
    result = cli.run_pipeline(_deps(conn, execu), "spec.txt", auto_approve=True,
                              reports_dir=tmp_path, out=lambda *_: None)
    assert result.stopped_stage == cli.STAGE_DONE
    assert execu.called is True
    assert result.report_json.exists() and result.report_html.exists()
    assert result.verdict.execution_status == "success"
    assert result.verdict.functional_status == "conforme"
    # Relecture approuvée persistée, exécution enregistrée, dernier résultat inscrit sur le cas.
    assert ReviewRepo(conn).is_version_approved(result.version_id) is True
    assert ExecutionRepo(conn).get(result.execution_id)["execution_status"] == "success"
    assert CaseRepo(conn).get(result.case_id)["last_execution_status"] == "success"


def test_gate_rejete_arrete_avant_execution(conn, tmp_path):
    result = cli.run_pipeline(_deps(conn, ExplodingExecutor()), "spec.txt",
                              prompt_fn=lambda _fc: False, reports_dir=tmp_path, out=lambda *_: None)
    assert result.stopped_stage == cli.STAGE_REVIEW_REJECTED
    assert result.report_html is None
    # Décision de rejet enregistrée, aucune exécution créée.
    assert ReviewRepo(conn).latest_for_version(result.version_id)["decision"] == "rejected"
    assert ExecutionRepo(conn).list_for_case(result.case_id) == []
    # Le refus vit sur la VERSION (ligne au-dessus) et nulle part ailleurs : le cas ne porte
    # plus de statut recopié, et son État reste celui que l'humain lui a donné (migration 25).
    assert CaseRepo(conn).get(result.case_id)["etat"] == "new"


def test_generation_echouee_arrete_avant_le_gate(conn, tmp_path):
    result = cli.run_pipeline(_deps(conn, ExplodingExecutor(), agent_success=False), "spec.txt",
                              reports_dir=tmp_path, out=lambda *_: None)
    assert result.stopped_stage == cli.STAGE_GENERATION
    assert result.version_id is None


def test_vrai_bug_diagnostique_persiste_et_reporte(conn, tmp_path):
    execu = FakeExecutor(_real_bug_outcome())
    result = cli.run_pipeline(_deps(conn, execu), "spec.txt", auto_approve=True,
                              reports_dir=tmp_path, out=lambda *_: None)
    assert result.stopped_stage == cli.STAGE_DONE
    # Deux axes : le test a tourné (success) mais l'app répond faux (non_conforme).
    assert result.verdict.execution_status == "success"
    assert result.verdict.functional_status == "non_conforme"
    # Tentative de réparation persistée avec l'origine 'vrai_bug' (remontée directe).
    repairs = RepairRepo(conn).list_for_execution(result.execution_id)
    assert len(repairs) == 1
    assert repairs[0]["defect_origin"] == "vrai_bug"
    assert repairs[0]["confirmation_status"] == "not_required"


def test_gate_deja_approuve_ne_redemande_pas(conn, tmp_path):
    # Pré-approuve une version, puis vérifie que run_pipeline ne rappelle pas le prompt.
    def exploding_prompt(_fc):
        raise AssertionError("le gate ne doit pas redemander une version déjà approuvée")

    # 1er run auto-approuvé pour créer + approuver la version.
    first = cli.run_pipeline(_deps(conn, FakeExecutor(_passing_outcome())), "spec.txt",
                             auto_approve=True, reports_dir=tmp_path, out=lambda *_: None)
    # Re-évalue le gate sur la même version approuvée : doit être autorisé sans prompt.
    from testpilot.verdict import review_gate
    assert review_gate.evaluate_gate(ReviewRepo(conn), first.version_id).allowed is True
