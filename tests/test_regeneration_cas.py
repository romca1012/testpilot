"""18/09/2026 : C19 sur staging conserve du technique mais aucun bouton de régénération.
L'exécution locale 146 porte son erreur dans scenario_result, pas execution.error_message.
"""
import base64
import json
from types import SimpleNamespace

import pytest

from testpilot import config
from testpilot.analysis.plan import TestPlan
from testpilot.api.services import generation_service as service
from testpilot.generation.agent import GenerationAgent
from testpilot.generation.prompt import build_initial_message
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import (
    CaseGroupRepo,
    CaseRepo,
    ExecutionRepo,
    ReviewRepo,
    VersionRepo,
    ensure_default_module,
)
from testpilot.verdict.review_gate import evaluate_gate


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "regeneration.db")
    c = get_initialized_db()
    yield c
    c.close()


def existing_case(conn):
    mid = ensure_default_module(conn, "parc")
    gid = CaseGroupRepo(conn).create(module_id=mid, title="Parc IT", spec_content="Contexte " * 500 + "FIN : back-office uniquement")
    cid = CaseRepo(conn).create(title="Créer équipement", module_id=mid, group_id=gid, feature_slug="equipement")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="Ancien contexte", spec_hash="ancien", feature_content="ancien Gherkin", steps_content="ancien Python", title="Créer équipement", preconditions="DSI", test_steps=json.dumps(["Confirmer"]), expected_result="Équipement créé")
    CaseRepo(conn).set_current_version(cid, vid)
    return cid, vid, gid


def plan(slug, content):
    return TestPlan(module_name=slug, models=[], scenarios=[], personas=[], portal_routes=[], risks=[], raw_spec=content)


def test_c19_technique_existant_reutilise_section_complete_au_dela_3000_caracteres(conn):
    cid, vid, gid = existing_case(conn)
    _, params = service.start_automation(conn, cid)
    assert params["regeneration"] is True
    assert params["slug"] == "equipement"
    assert params["spec_content"] == CaseGroupRepo(conn).get(gid)["spec_content"]
    assert "FIN : back-office uniquement" in build_initial_message(plan(params["slug"], params["spec_content"]), metier=params["metier"])
    assert VersionRepo(conn).get(vid)["feature_content"] == "ancien Gherkin"


def test_regeneration_nouvelle_version_pipeline_lint_et_gate_humain(conn, monkeypatch, tmp_path):
    cid, vid, _ = existing_case(conn)
    seen = []
    monkeypatch.setattr("testpilot.connectors.factory.build_connector", lambda p: SimpleNamespace(connect=lambda: None, disconnect=lambda: None, rules=lambda: ""))
    from testpilot.execution.behave_runner import BehaveRunner
    from testpilot.llm.adapter import LLMAdapter, LLMResponse, ToolUseBlock

    monkeypatch.setattr(config, "GENERATED_DIR", tmp_path / "generated")
    monkeypatch.setattr("testpilot.analysis.spec_analyzer.SpecAnalyzer.analyze_spec_content", lambda self, slug, content: plan(slug, content))
    feature = "# language: fr\nFonctionnalité: Régénération\n  Scénario: Conservation\n    Quand je vérifie la régénération\n"
    steps = 'from behave import when\n@when("je vérifie la régénération")\ndef step(context):\n    raise RuntimeError("le dry-run ne doit pas exécuter ce step")\n'
    def response(self, **kw):
        return LLMResponse(stop_reason="tool_use", tool_calls=[
            ToolUseBlock(id="f", name="write_feature_file", input={"content": feature}),
            ToolUseBlock(id="s", name="write_steps_file", input={"content": steps}),
        ]), None
    monkeypatch.setattr(LLMAdapter, "call_with_tools", response)
    dry_runs = []
    real_dry_run = BehaveRunner.dry_run
    def dry_run(self, module):
        result = real_dry_run(self, module)
        dry_runs.append(result.success)
        return result
    monkeypatch.setattr(BehaveRunner, "dry_run", dry_run)
    def lint(c, case, versions, version_id):
        seen.append(version_id)
        return []
    monkeypatch.setattr(service, "lint_warnings_for_version", lint)
    job, params = service.start_automation(conn, cid)
    service.run_automation(job, **params)
    assert service.get_job(conn, job)["status"] == "done"
    versions = VersionRepo(conn).list_for_case(cid)
    assert len(versions) == 2
    current = CaseRepo(conn).get(cid)["current_version_id"]
    assert current != vid and seen == [current]
    assert VersionRepo(conn).get(vid)["feature_content"] == "ancien Gherkin"
    assert VersionRepo(conn).get(current)["feature_content"] == feature
    assert dry_runs == [True]
    assert evaluate_gate(ReviewRepo(conn), current).needs_review


def test_execution_146_erreur_scenario_capture_et_commentaire_humain(conn, tmp_path):
    cid, vid, _ = existing_case(conn)
    repo = ExecutionRepo(conn)
    failed = repo.create(test_case_id=cid, version_id=vid)
    conn.execute("UPDATE execution SET execution_status='success', functional_status='donnee_invalide' WHERE id=?", (failed,))
    conn.execute("INSERT INTO repair_attempt (execution_id,attempt_number,human_comment,created_at) VALUES (?,1,?,?)", (failed, "Le SIREN invalide est volontaire", "2026-09-18"))
    conn.commit()
    repo.add_scenario_result(execution_id=failed, scenario_name="SIREN invalide", execution_status="success", functional_status="donnee_invalide", error_summary="DonneeRefuseeError: numero_siren", step_text="Envoyer")
    captures = tmp_path / "echec" / "screenshots"
    captures.mkdir(parents=True)
    (captures / "01-error.png").write_bytes(b"capture mesuree")
    (captures / "02-passed.png").write_bytes(b"autre scenario")
    repo.set_artifacts_path(failed, str(captures.parent))
    newer = repo.create(test_case_id=cid, version_id=vid)
    conn.execute("UPDATE execution SET execution_status='success', functional_status='conforme' WHERE id=?", (newer,))
    conn.commit()
    blocks = service._regeneration_failure_context(conn, cid)
    evidence = blocks[0]["text"]
    assert "DonneeRefuseeError: numero_siren" in evidence
    assert "Le SIREN invalide est volontaire" in evidence
    assert f'"execution_id": {failed}' in evidence
    images = [b for b in blocks if b["type"] == "image"]
    assert len(images) == 1
    assert base64.b64decode(images[0]["source"]["data"]) == b"capture mesuree"


def test_c19_sans_execution_ne_fabrique_aucun_echec(conn):
    cid, _, _ = existing_case(conn)
    assert service._regeneration_failure_context(conn, cid) == []


def test_generation_transmet_les_preuves_dans_message_multimodal(monkeypatch):
    blocks = [{"type": "text", "text": "échec réel"}, {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "YWJj"}}]
    seen = []
    monkeypatch.setattr("testpilot.generation.agent.run_loop", lambda **kw: seen.append(kw["state"].messages[0]))
    GenerationAgent().generate(plan("parc", "spécification"), failure_context=blocks)
    assert seen[0]["content"][1:] == blocks


def test_regeneration_corrigee_reste_a_relire_apres_second_controle(conn, monkeypatch):
    from testpilot.generation.correction_agent import CorrectionProposal

    cid, vid, _ = existing_case(conn)
    checks = []
    def lint(c, case, versions, version_id):
        checks.append(version_id)
        return [{"kind": "always_true_constant", "message": "assert True"}] if version_id == vid else []
    monkeypatch.setattr(service, "lint_warnings_for_version", lint)
    monkeypatch.setattr("testpilot.generation.correction_agent.propose_correction", lambda **kw: CorrectionProposal(
        changed=True, feature_content="corrigé", steps_content="corrigé", summary="assertion vérifiée"))
    service._finaliser_version_generee(conn, cid, vid, module_name="parc", dry_runner=object(), require_review=True)
    current = CaseRepo(conn).get(cid)["current_version_id"]
    assert current != vid
    assert checks == [vid, current]
    assert evaluate_gate(ReviewRepo(conn), current).needs_review


def test_api_c19_avec_technique_accepte_la_regeneration(conn, monkeypatch):
    from fastapi.testclient import TestClient

    from testpilot.api.app import app

    cid, _, _ = existing_case(conn)
    monkeypatch.setattr(service, "run_automation", lambda *args, **kw: None)
    response = TestClient(app).post(f"/api/cases/{cid}/automate")
    assert response.status_code == 202
    assert response.json()["status"] == "running"
