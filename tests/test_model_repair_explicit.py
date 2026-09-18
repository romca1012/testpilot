"""18/09/2026 : deux sondes call_with_tools rendent model=None et prennent Sonnet.
La réparation et la correction doivent utiliser MODEL_REPAIR jusqu'au client SDK.
"""
from types import SimpleNamespace

import pytest

from testpilot import config
from testpilot.analysis.plan import TestPlan
from testpilot.api.services import generation_service, repair_service
from testpilot.generation import correction_agent, repair_agent
from testpilot.generation.agent import GenerationAgent
from testpilot.llm.adapter import LLMAdapter
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, ExecutionRepo, VersionRepo


@pytest.mark.parametrize("operation", ["repair", "correction", "generation"])
def test_modele_reel_transmis_au_sdk_et_non_seulement_etiquete(operation, monkeypatch):
    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(stop_reason="end_turn", content=[], usage=SimpleNamespace(input_tokens=10, output_tokens=10))
    monkeypatch.setattr(LLMAdapter, "_client_", lambda self: SimpleNamespace(messages=SimpleNamespace(create=create)))
    if operation == "repair":
        repair_agent.propose_fix(module_name="parc", scenarios=[], failures=[])
    elif operation == "correction":
        correction_agent.propose_correction(module_name="parc", lint_warnings=[], feature_content="", steps_content="")
    else:
        GenerationAgent().generate(TestPlan(module_name="parc", models=[], scenarios=[], personas=[], portal_routes=[], risks=[], raw_spec="parc"))
    assert len(calls) == 1
    assert calls[0]["model"] == (config.MODEL_GENERATION if operation == "generation" else config.MODEL_REPAIR)


def test_ledger_reparation_et_correction_aligne_sur_modele_transmis(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    conn = get_initialized_db(tmp_path / "model.db")
    try:
        cid = CaseRepo(conn).create(title="Cas", feature_slug="parc")
        vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="h", feature_content="", steps_content="")
        eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid)
        repair_service._record_cost(conn, eid, 0.02)
        generation_service._record_generation_cost(conn, case_id=cid, correction_usd=0.03)
        rows = conn.execute("SELECT phase,model,cost_usd FROM cost_ledger ORDER BY id").fetchall()
        assert [(r["phase"], r["model"]) for r in rows] == [("repair", config.MODEL_REPAIR), ("correction", config.MODEL_REPAIR)]
        assert [r["cost_usd"] for r in rows] == [0.02, 0.03]
    finally:
        conn.close()
