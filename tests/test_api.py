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
from testpilot.store.repositories import (
    CaseRepo,
    ModuleRepo,
    ProjectRepo,
    ReviewRepo,
    VersionRepo,
)


class _FakeExecutor:
    """Exécuteur déterministe : un scénario passant, aucun Behave réel."""

    def __init__(self, runner=None):
        pass

    def execute(self, module_name):
        real = BehaveResult(success=True, returncode=0, passed=1,
                            scenarios=[BehaveScenario("cas nominal", "passed")], failures=[])
        return ExecutionOutcome(module_name=module_name, dry_run_passed=True, real_run=real)


def _module_connecte(conn) -> int:
    """Un module dont le PROJET porte une connexion complète.

    ⚠️ Requis depuis le 2026-07-24 : un cas rattaché à aucun projet — ou à un projet sans
    connexion — n'est plus exécutable, parce qu'on ne sait pas contre quelle application il
    tournerait. Ces tests exercent le câblage de l'API, pas ce refus : ils lui donnent donc une
    cible explicite (`tests/test_cible_et_repli_silencieux.py` couvre le refus lui-même).
    """
    pid = ProjectRepo(conn).create(name="Recette", connector_type="odoo",
                                   base_url="http://recette:8069", database="db",
                                   username="qa", password="p")
    return ModuleRepo(conn).create(project_id=pid, name="Demandes")


def _seed_case(conn, *, approved: bool) -> tuple[int, int]:
    cid = CaseRepo(conn).create(title="Demande de matériel", module_id=_module_connecte(conn),
                                feature_slug="demande_materiel", author="qa")
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

    project_id = CaseRepo(conn := _conn()).get(cid)["project_id"]
    conn.close()
    cases = client.get(f"/api/cases?project_id={project_id}").json()["items"]
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
    cid = CaseRepo(conn).create(
        title="vide", feature_slug="vide", module_id=_module_connecte(conn)
    )
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


class _FakeExecutorAvecRepli:
    """Run VERT qui a néanmoins dû résoudre un champ par son libellé (décision 0007 B+)."""

    def __init__(self, runner=None):
        pass

    def execute(self, module_name):
        real = BehaveResult(
            success=True, returncode=0, passed=1,
            scenarios=[BehaveScenario("cas nominal", "passed")], failures=[],
            field_fallbacks=["champ 'Raison de la demande' résolu via son libellé -> name='name'"])
        return ExecutionOutcome(module_name=module_name, dry_run_passed=True, real_run=real)


def test_repli_de_champ_visible_meme_sur_un_run_vert(client, monkeypatch):
    """Le cas que les logs seuls n'exposent pas : run vert + repli (verdict 0007 n°2).

    Behave masque les logs d'un scénario réussi. Si le repli ne remontait pas ici, un champ
    renommé côté application serait retrouvé par son libellé, le run virerait au vert, et la
    régression passerait inaperçue.
    """
    monkeypatch.setattr(run_service, "Executor", _FakeExecutorAvecRepli)
    conn = _conn()
    cid, _ = _seed_case(conn, approved=True)
    conn.close()

    eid = client.post(f"/api/cases/{cid}/runs").json()["execution_id"]
    execu = client.get(f"/api/executions/{eid}").json()

    # Le verdict n'est PAS dégradé par le repli (il informe, il ne juge pas)…
    assert execu["execution_status"] == "success"
    # … et il reste néanmoins visible.
    assert execu["field_fallbacks"] == [
        "champ 'Raison de la demande' résolu via son libellé -> name='name'"]

    # Visible aussi dans l'historique du cas : le signal doit survivre au run SUIVANT, sinon la
    # détection a posteriori rouvrirait un angle mort dans le temps.
    case = client.get(f"/api/cases/{cid}").json()
    assert case["executions"][0]["field_fallbacks"] == execu["field_fallbacks"]


def test_run_sans_repli_ne_remonte_rien(client):
    # Anti-faux-positif : sans repli, aucune pastille (l'exécuteur par défaut n'en produit pas).
    conn = _conn()
    cid, _ = _seed_case(conn, approved=True)
    conn.close()
    eid = client.post(f"/api/cases/{cid}/runs").json()["execution_id"]
    assert client.get(f"/api/executions/{eid}").json()["field_fallbacks"] == []


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
    cid = CaseRepo(conn).create(
        title="Cas tautologie", feature_slug="tauto", author="qa",
        module_id=_module_connecte(conn),
    )
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


def test_un_rejet_referme_le_gate_sans_toucher_a_l_etat_du_cas(client):
    """Un refus s'inscrit sur la VERSION, et nulle part ailleurs.

    ⚠️ Ce test vérifiait aussi qu'un rejet repositionnait le cas « à relire ». Ce statut a été
    supprimé (migration 25) : il redisait moins fidèlement ce que le gate dit déjà, et il
    reprenait à l'humain un champ — l'État — dont il doit rester le seul auteur. Ce que le refus
    doit produire, c'est **une exécution refusée** ; c'est ce qui est vérifié ici.
    """
    conn = _conn()
    cid, _ = _seed_case(conn, approved=True)
    conn.close()
    avant = client.get(f"/api/cases/{cid}").json()["case"]["etat"]
    review = client.post(f"/api/cases/{cid}/review", json={"approved": False, "comment": "à revoir"}).json()
    assert review["decision"] == "rejected"
    assert review["gate"]["allowed"] is False
    assert client.get(f"/api/cases/{cid}").json()["case"]["etat"] == avant


def test_liste_executions_globale(client):
    conn = _conn()
    cid, _ = _seed_case(conn, approved=True)
    conn.close()
    client.post(f"/api/cases/{cid}/runs")
    runs = client.get("/api/executions").json()
    assert len(runs) >= 1
    assert runs[0]["test_case_id"] == cid
