"""§8 (Inc. 1.1) — API : référentiel à deux axes + gate de relecture ACTIONNABLE.

Hors-ligne : l'exécuteur Behave réel est remplacé par un fake déterministe. On vérifie le
câblage des endpoints, la séparation des deux axes jusqu'à la réponse, et surtout que le
gate est franchissable via l'API (approbation → exécution autorisée).
"""

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import app as app_mod
from testpilot.api.services import run_service
from testpilot.execution.behave_result import BehaveResult, BehaveScenario
from testpilot.execution.executor import ExecutionOutcome
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, ReviewRepo, VersionRepo


class _FakeExecutor:
    """Exécuteur déterministe : un scénario passant, aucun Behave réel."""

    def __init__(self, runner=None):
        pass

    def execute(self, module_name):
        real = BehaveResult(success=True, returncode=0, passed=1,
                            scenarios=[BehaveScenario("cas nominal", "passed")], failures=[])
        return ExecutionOutcome(module_name=module_name, dry_run_passed=True, real_run=real)


def _seed_case(conn, *, approved: bool) -> tuple[int, int]:
    cid = CaseRepo(conn).create(title="Demande de matériel", module="demande_materiel", author="qa")
    vid = VersionRepo(conn).create(
        test_case_id=cid, spec_content="spec", spec_hash="h1",
        feature_content="# language: fr\nFonctionnalité: Demande de matériel",
        steps_content="from behave import *")
    CaseRepo(conn).set_current_version(cid, vid)
    if approved:
        ReviewRepo(conn).create(test_case_id=cid, version_id=vid, decision="approved", reviewer="qa")
    return cid, vid


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    # Exécuteur réel -> fake (pas de Behave/Odoo dans les tests).
    monkeypatch.setattr(run_service, "Executor", _FakeExecutor)
    run_service._RUNNING.clear()
    return TestClient(app_mod.app)


def _conn():
    return get_initialized_db(config.DB_PATH)


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_list_and_detail_expose_two_axes(client):
    conn = _conn()
    cid, vid = _seed_case(conn, approved=False)
    conn.close()

    cases = client.get("/api/cases").json()
    assert any(c["id"] == cid for c in cases)

    detail = client.get(f"/api/cases/{cid}").json()
    assert detail["current_version_id"] == vid
    assert detail["versions"][0]["feature_content"].startswith("# language: fr")
    # Gate : version non approuvée → exécution refusée, relecture requise.
    assert detail["gate"]["allowed"] is False
    assert detail["gate"]["needs_review"] is True


def test_run_refuse_si_non_approuve(client):
    conn = _conn()
    cid, _ = _seed_case(conn, approved=False)
    conn.close()
    resp = client.post(f"/api/cases/{cid}/runs")
    assert resp.status_code == 409
    assert "relecture" in resp.json()["detail"].lower()


def test_run_refuse_si_pas_de_version(client):
    conn = _conn()
    cid = CaseRepo(conn).create(title="vide", module="vide")
    conn.close()
    resp = client.post(f"/api/cases/{cid}/runs")
    assert resp.status_code == 409
    assert "version" in resp.json()["detail"].lower()


def test_gate_actionnable_puis_execution_et_rapport(client):
    conn = _conn()
    cid, vid = _seed_case(conn, approved=False)
    conn.close()

    # 1. Approbation via l'API — le gate doit s'ouvrir.
    review = client.post(f"/api/cases/{cid}/review", json={"approved": True}).json()
    assert review["decision"] == "approved"
    assert review["gate"]["allowed"] is True

    # 2. Déclenchement — les BackgroundTasks du TestClient s'exécutent avant la réponse.
    run = client.post(f"/api/cases/{cid}/runs")
    assert run.status_code == 202
    eid = run.json()["execution_id"]

    # 3. Exécution finalisée : deux axes distincts, run terminé.
    execu = client.get(f"/api/executions/{eid}").json()
    assert execu["execution_status"] == "success"
    assert execu["functional_status"] == "conforme"
    assert execu["running"] is False
    assert execu["scenarios"][0]["scenario_name"] == "cas nominal"

    # 4. Rapport à deux axes (JSON + HTML) reconstruit depuis la base.
    rep = client.get(f"/api/executions/{eid}/report").json()
    assert rep["execution_status"] == "success" and rep["functional_status"] == "conforme"
    html = client.get(f"/api/executions/{eid}/report.html").text
    assert "Axe exécution" in html and "Axe fonctionnel" in html


def test_rejet_repositionne_le_cas_a_relire(client):
    conn = _conn()
    cid, _ = _seed_case(conn, approved=True)
    conn.close()
    review = client.post(f"/api/cases/{cid}/review", json={"approved": False, "comment": "à revoir"}).json()
    assert review["decision"] == "rejected"
    assert review["validation_status"] == "to_review"
    assert review["gate"]["allowed"] is False


def test_liste_executions_globale(client):
    conn = _conn()
    cid, _ = _seed_case(conn, approved=True)
    conn.close()
    client.post(f"/api/cases/{cid}/runs")
    runs = client.get("/api/executions").json()
    assert len(runs) >= 1
    assert runs[0]["test_case_id"] == cid
