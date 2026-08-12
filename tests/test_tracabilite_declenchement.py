"""Traçabilité des exécutions automatiques (migration 32, 2026-08-12) : QUI a déclenché un run,
pas seulement « Automatique ».

Avant cette migration, `ExecutionRepo.finalize` signait TOUJOURS `test_result.created_by` avec le
réglage `service_account_name` — l'humain qui avait cliqué « Lancer » n'était nulle part. La
mention « Automatique » (mode/trigger) reste inchangée ; c'est le VALEUR de `created_by` qui
change : le vrai compte connecté, avec repli sur le compte de service seulement si aucun acteur
n'a pu être résolu (aucun cas de ce genre aujourd'hui — filet pour un déclenchement futur sans
session).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import access
from testpilot.api.app import app
from testpilot.api.deps import get_conn
from testpilot.api.services import run_service
from testpilot.store.db import _migrate_32_triggered_by, get_initialized_db
from testpilot.store.repositories import (
    CaseRepo,
    ExecutionRepo,
    ModuleRepo,
    ProjectRepo,
    ResultRepo,
    ReviewRepo,
    RunRepo,
    UserRepo,
    VersionRepo,
)


@pytest.fixture
def conn(tmp_path):
    c = get_initialized_db(tmp_path / "tracabilite.db")
    yield c
    c.close()


def _cas_pret(conn, project_id: int | None = None) -> tuple[int, int]:
    """Un cas avec une version APPROUVÉE, prêt à être lancé (gate ouvert). Rattaché à un projet
    connecté quand `project_id` est fourni (nécessaire pour `trigger_run`, qui vérifie la
    connexion DU projet via le module du cas — pas une colonne directe sur `test_case`)."""
    module_id = ModuleRepo(conn).create(project_id=project_id, name="M") if project_id else None
    cid = CaseRepo(conn).create(title="Cas", module_id=module_id, feature_slug="cas")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="s", spec_hash="h",
                                   feature_content="# f", steps_content="# s")
    CaseRepo(conn).set_current_version(cid, vid)
    ReviewRepo(conn).create(test_case_id=cid, version_id=vid, decision="approved",
                            reviewer="validation-metier", comment="")
    return cid, vid


def _rattacher_a_un_run(conn, project_id: int, case_id: int, execution_id: int) -> None:
    """`ResultRepo.enregistrer_execution` n'inscrit au registre QUE les exécutions rattachées à
    une campagne (`run_id`) — sans ce rattachement, `finalize` rend `None` (hors registre, pas
    un défaut) et il n'y a rien à lire sur `created_by`."""
    rid = RunRepo(conn).create(project_id=project_id, name="R", selection_mode="frozen",
                               case_ids=[case_id])
    conn.execute("UPDATE execution SET run_id=? WHERE id=?", (rid, execution_id))
    conn.commit()


# ── La migration ──────────────────────────────────────────────────────────────

def test_le_schema_neuf_porte_triggered_by(conn):
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(execution)")}
    assert "triggered_by" in cols


def test_migration_32_est_idempotente(tmp_path):
    import sqlite3
    raw = sqlite3.connect(str(tmp_path / "x.db"))
    raw.row_factory = sqlite3.Row
    raw.execute("CREATE TABLE execution (id INTEGER PRIMARY KEY)")
    _migrate_32_triggered_by(raw)
    _migrate_32_triggered_by(raw)  # rejoué
    cols = [r["name"] for r in raw.execute("PRAGMA table_info(execution)")]
    assert cols.count("triggered_by") == 1, "triggered_by ajouté une seule fois"
    raw.close()


# ── ExecutionRepo : capture et signature ───────────────────────────────────────

def test_create_trace_le_declencheur(conn):
    cid, vid = _cas_pret(conn)
    eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid, triggered_by="Awa")
    assert ExecutionRepo(conn).get(eid)["triggered_by"] == "Awa"


def test_create_sans_declencheur_laisse_la_colonne_vide(conn):
    """Vide, pas une valeur devinée — `finalize` sait retomber sur le compte de service."""
    cid, vid = _cas_pret(conn)
    eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid)
    assert ExecutionRepo(conn).get(eid)["triggered_by"] == ""


def test_finalize_signe_avec_le_declencheur_reel_pas_le_compte_de_service(conn):
    pid = ProjectRepo(conn).create(name="P")
    cid, vid = _cas_pret(conn, project_id=pid)
    eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid, triggered_by="Awa")
    _rattacher_a_un_run(conn, pid, cid, eid)

    result_id = ExecutionRepo(conn).finalize(
        eid, execution_status="success", functional_status="conforme",
        scenarios_total=1, scenarios_passed=1, scenarios_failed=0,
        cost_usd=0.0, iterations=0, duration_seconds=1.0, comment="")

    resultat = ResultRepo(conn).get(result_id)
    assert resultat["created_by"] == "Awa"
    assert resultat["created_by"] != config.SERVICE_ACCOUNT_NAME


def test_finalize_replie_sur_le_compte_de_service_si_aucun_declencheur(conn):
    """Non-régression : le comportement d'AVANT cette migration reste le filet, jamais le défaut."""
    pid = ProjectRepo(conn).create(name="P")
    cid, vid = _cas_pret(conn, project_id=pid)
    eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid)  # triggered_by vide
    _rattacher_a_un_run(conn, pid, cid, eid)

    result_id = ExecutionRepo(conn).finalize(
        eid, execution_status="success", functional_status="conforme",
        scenarios_total=1, scenarios_passed=1, scenarios_failed=0,
        cost_usd=0.0, iterations=0, duration_seconds=1.0, comment="")

    resultat = ResultRepo(conn).get(result_id)
    assert resultat["created_by"] == config.SERVICE_ACCOUNT_NAME


# ── run_service.trigger_run transmet l'acteur ──────────────────────────────────

def test_trigger_run_transmet_le_declencheur_a_l_execution(conn, monkeypatch):
    pid = ProjectRepo(conn).create(name="P", connector_type="odoo", base_url="http://x:8069",
                                   database="db", username="qa", password="secret")
    cid, vid = _cas_pret(conn, project_id=pid)

    eid, _, _, _ = run_service.trigger_run(conn, cid, triggered_by="Awa")

    assert ExecutionRepo(conn).get(eid)["triggered_by"] == "Awa"


def test_trigger_run_sans_declencheur_laisse_la_colonne_vide(conn):
    pid = ProjectRepo(conn).create(name="P", connector_type="odoo", base_url="http://x:8069",
                                   database="db", username="qa", password="secret")
    cid, vid = _cas_pret(conn, project_id=pid)

    eid, _, _, _ = run_service.trigger_run(conn, cid)

    assert ExecutionRepo(conn).get(eid)["triggered_by"] == ""


# ── Une réparation hérite du déclencheur du run d'origine ─────────────────────

def test_une_reparation_herite_du_declencheur_du_run_d_origine(conn, monkeypatch):
    """Une tentative de réparation n'est pas un nouveau geste humain — juste la suite du même
    run. Même patron de test que `test_reparation_isole_le_verdict.py` : le circuit de
    décision (`repair_service.run_repair_loop`) est remplacé par un appel direct à `run_once`."""
    cid, vid = _cas_pret(conn)
    eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid, triggered_by="Awa")

    created_eids: list[int] = []

    def fake_run_repair_loop(c, *, case_id, version_id, module_name, outcome, run_once,
                             connector, dry_runner):
        run_once(version_id)
        raise AssertionError("ne doit jamais être atteint : run_once doit avoir levé")

    def fake_execute_and_persist(c, execution_id, case_id, module_name, runner):
        created_eids.append(execution_id)
        raise RuntimeError("plantage délibéré, pour arrêter la boucle après une tentative")

    monkeypatch.setattr(run_service.repair_service, "run_repair_loop", fake_run_repair_loop)
    monkeypatch.setattr(run_service, "_execute_and_persist", fake_execute_and_persist)

    with pytest.raises(RuntimeError):
        run_service._maybe_repair(conn, case_id=cid, version_id=vid, module_name="cas",
                                  outcome=object(), runner=object(), triggered_by="Awa")

    assert len(created_eids) == 1
    retry_eid = created_eids[0]
    assert retry_eid != eid
    assert ExecutionRepo(conn).get(retry_eid)["triggered_by"] == "Awa"


# ── Bout en bout : l'API capture le VRAI compte connecté ──────────────────────

def _compte(conn, username: str, password: str, role: str) -> int:
    return UserRepo(conn).create(username=username,
                                 password_hash=access.hacher_mot_de_passe(password), role=role)


def _connecte(client, username: str, password: str):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text


@pytest.fixture
def client(conn):
    app.dependency_overrides[get_conn] = lambda: conn
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_lancer_un_run_via_l_api_trace_le_vrai_compte_connecte(
        conn, client, monkeypatch, tmp_path):
    """Bout en bout, sur la route réellement câblée (`POST /api/cases/{id}/runs`) : c'est le
    compte de SESSION qui signe l'exécution, pas un mot générique."""
    # ⚠️ Le middleware d'auth ouvre SA PROPRE connexion via `config.DB_PATH` (même piège que
    # `test_reglages_instance.py`) — sans cet alignement, le jeton de « Awa » serait résolu
    # contre une autre base que celle de ce test.
    db_path = conn.execute("PRAGMA database_list").fetchone()[2]
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", db_path)

    pid = ProjectRepo(conn).create(name="P", connector_type="odoo", base_url="http://x:8069",
                                   database="db", username="qa", password="secret")
    cid, vid = _cas_pret(conn, project_id=pid)

    _compte(conn, "Awa", "mdp12345", access.ROLE_TESTEUR)
    _connecte(client, "Awa", "mdp12345")

    # `run_execution` (tâche de fond) est neutralisé — seul le déclenchement (synchrone, avant
    # la mise en tâche de fond) est sous test ici, pas un vrai run Behave.
    appels = []
    monkeypatch.setattr(run_service, "run_execution",
                        lambda eid, module, cid_, vid_, **kw: appels.append(kw))

    r = client.post(f"/api/cases/{cid}/runs")
    assert r.status_code == 202
    eid = r.json()["execution_id"]

    assert ExecutionRepo(conn).get(eid)["triggered_by"] == "Awa"
    assert appels == [{"triggered_by": "Awa"}]
