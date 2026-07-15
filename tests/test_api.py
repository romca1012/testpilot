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
    cid = CaseRepo(conn).create(title="Demande de matériel", feature_slug="demande_materiel", author="qa")
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
    cid = CaseRepo(conn).create(title="vide", feature_slug="vide")
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


# Contenu EXACT du step tautologique de l'écart 2 (run #2, cas 2) — cf. test_assertion_lint.
_ECART_2_STEPS = '''
from behave import then

@then("le formulaire traite la chaîne longue de manière cohérente")
def step_long_string_coherent(context):
    page = context.page
    current_url = page.url
    if "/your-ticket-has-been-submitted" in current_url:
        context.long_string_accepted = True
    else:
        error_visible = page.locator(".alert-danger").count() > 0
        context.long_string_accepted = False
        assert error_visible or "/your-ticket-has-been-submitted" not in current_url
'''


def test_lint_assertion_infalsifiable_signale_au_gate_sans_bloquer(client):
    """Décision 0008 phase C : une assertion tautologique (contenu EXACT de l'écart 2) doit
    remonter comme avertissement AU GATE, sans jamais changer l'état du gate lui-même."""
    conn = _conn()
    cid = CaseRepo(conn).create(title="Cas tautologie", feature_slug="tauto", author="qa")
    vid = VersionRepo(conn).create(
        test_case_id=cid, spec_content="spec", spec_hash="h",
        feature_content="# language: fr\nFonctionnalité: x", steps_content=_ECART_2_STEPS)
    CaseRepo(conn).set_current_version(cid, vid)
    conn.close()

    gate = client.get(f"/api/cases/{cid}").json()["gate"]
    kinds = {w["kind"] for w in gate["lint_warnings"]}
    assert "tautology_negation_in_else" in kinds, "le motif exact de l'écart 2 doit être signalé au gate"
    # Non-bloquant : l'avertissement n'ouvre PAS le gate (relecture toujours requise).
    assert gate["allowed"] is False
    assert gate["needs_review"] is True


def test_lint_gate_sans_avertissement_sur_assertion_saine(client):
    conn = _conn()
    cid, _ = _seed_case(conn, approved=False)  # steps sains (« from behave import * »)
    conn.close()
    gate = client.get(f"/api/cases/{cid}").json()["gate"]
    assert gate["lint_warnings"] == []


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
