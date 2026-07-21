"""Le RUN — une campagne de N cas (décision `0022` n°8, incrément 1a : créer / lister / détailler).

Aujourd'hui une « exécution » est un run MONO-cas. La cible : un `test_run` regroupe des cas à
jouer ensemble, et le résultat d'un cas vit sur le couple cas × run. Ces tests figent :
- créer un run ne lance RIEN (naît en brouillon, `0022` 8.c.1) ;
- mode `frozen` = sélection matérialisée ; mode `all` = VIVANTE (les nouveaux cas rejoignent) ;
- référence par ID, jamais de copie de cas (contrainte §7) ;
- le détail donne chaque cas AVEC son résultat dans CE run (ou « non testé »).
"""

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import app as app_mod
from testpilot.store.db import get_initialized_db, _migrate_15_test_run
from testpilot.store.repositories import (
    CaseRepo,
    ExecutionRepo,
    RunRepo,
    ensure_default_module,
)


@pytest.fixture
def conn(tmp_path):
    c = get_initialized_db(tmp_path / "run.db")
    yield c
    c.close()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    return TestClient(app_mod.app)


def _cas(conn, mid, titre):
    return CaseRepo(conn).create(title=titre, module_id=mid, feature_slug=titre.lower())


# ── La migration ──────────────────────────────────────────────────────────────

def test_le_schema_neuf_porte_test_run_et_run_id(conn):
    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"test_run", "test_run_case"} <= tables
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(execution)")}
    assert "run_id" in cols


def test_migration_15_est_idempotente(tmp_path):
    import sqlite3
    raw = sqlite3.connect(str(tmp_path / "x.db"))
    raw.row_factory = sqlite3.Row
    raw.execute("CREATE TABLE execution (id INTEGER PRIMARY KEY)")
    _migrate_15_test_run(raw)
    _migrate_15_test_run(raw)  # rejoué
    cols = [r["name"] for r in raw.execute("PRAGMA table_info(execution)")]
    assert cols.count("run_id") == 1, "run_id ajouté une seule fois"
    raw.close()


# ── Repo : sélection figée vs vivante ─────────────────────────────────────────

def test_selection_figee_materialise_les_cas_choisis(conn):
    mid = ensure_default_module(conn, "m")
    c1, c2, c3 = _cas(conn, mid, "a"), _cas(conn, mid, "b"), _cas(conn, mid, "c")
    repo = RunRepo(conn)

    rid = repo.create(project_id=1, name="Sprint 1", selection_mode="frozen", case_ids=[c1, c3])

    assert repo.case_ids(rid) == sorted([c1, c3])
    assert repo.get(rid)["status"] == "draft", "un run naît en brouillon (rien lancé)"


def test_selection_TOUS_est_vivante(conn):
    """Mode `all` : un cas ajouté APRÈS la création du run le rejoint automatiquement (§8.a)."""
    mid = ensure_default_module(conn, "m")
    _cas(conn, mid, "a")
    repo = RunRepo(conn)
    rid = repo.create(project_id=1, name="Tout", selection_mode="all")
    assert len(repo.case_ids(rid)) == 1

    _cas(conn, mid, "b")  # ajouté après

    assert len(repo.case_ids(rid)) == 2, "le nouveau cas a rejoint le run vivant"


def test_cases_avec_resultats_rattache_l_execution_DU_run(conn):
    """Le résultat d'un cas est celui de son exécution DANS CE run — pas une autre."""
    mid = ensure_default_module(conn, "m")
    c1 = _cas(conn, mid, "a")
    from testpilot.store.repositories import VersionRepo
    vid = VersionRepo(conn).create(test_case_id=c1, spec_content="", spec_hash="h",
                                   feature_content="# f", steps_content="# s")
    repo = RunRepo(conn)
    rid = repo.create(project_id=1, name="R", selection_mode="frozen", case_ids=[c1])
    # Une exécution rattachée à CE run.
    eid = ExecutionRepo(conn).create(test_case_id=c1, version_id=vid)
    conn.execute("UPDATE execution SET run_id=? WHERE id=?", (rid, eid))
    ExecutionRepo(conn).finalize(eid, execution_status="success", functional_status="conforme",
                                 scenarios_total=1, scenarios_passed=1, scenarios_failed=0,
                                 duration_seconds=1.0, iterations=0, cost_usd=0.0)

    cases = repo.cases_with_results(rid)

    assert len(cases) == 1
    assert cases[0]["result"]["execution_status"] == "success"


def test_un_cas_sans_execution_dans_le_run_est_non_teste(conn):
    mid = ensure_default_module(conn, "m")
    c1 = _cas(conn, mid, "a")
    repo = RunRepo(conn)
    rid = repo.create(project_id=1, name="R", selection_mode="frozen", case_ids=[c1])

    cases = repo.cases_with_results(rid)

    assert cases[0]["result"] is None, "non testé, pas de résultat fabriqué"


# ── API ───────────────────────────────────────────────────────────────────────

def _projet_avec_cas(client, n=2):
    pid = client.post("/api/projects", json={"name": "P"}).json()["id"]
    mid = client.post(f"/api/projects/{pid}/modules", json={"name": "M"}).json()["id"]
    ids = []
    for i in range(n):
        r = client.post(f"/api/modules/{mid}/cases/manual", json={
            "title": f"Cas {i}", "test_steps": ["a"], "expected_result": "r"})
        ids.append(r.json()["id"])
    return pid, ids


def test_api_creer_lister_detailler_un_run(client):
    pid, ids = _projet_avec_cas(client, 2)

    created = client.post(f"/api/projects/{pid}/runs", json={
        "name": "Campagne 1", "selection_mode": "frozen", "case_ids": ids})
    assert created.status_code == 201
    rid = created.json()["id"]
    assert created.json()["status"] == "draft"
    assert created.json()["case_count"] == 2

    assert any(r["id"] == rid for r in client.get(f"/api/projects/{pid}/runs").json())

    detail = client.get(f"/api/runs/{rid}")
    assert detail.status_code == 200
    assert len(detail.json()["cases"]) == 2
    assert all(c["execution_status"] is None for c in detail.json()["cases"]), "aucun run lancé"


def test_api_creer_ne_lance_rien(client):
    """Créer une campagne ne doit produire AUCUNE exécution (`0022` 8.c.1)."""
    pid, ids = _projet_avec_cas(client, 1)
    client.post(f"/api/projects/{pid}/runs", json={
        "name": "R", "selection_mode": "frozen", "case_ids": ids})

    assert client.get(f"/api/executions?project_id={pid}").json() == []


def test_api_selection_figee_vide_refusee(client):
    pid, _ = _projet_avec_cas(client, 1)
    r = client.post(f"/api/projects/{pid}/runs", json={
        "name": "R", "selection_mode": "frozen", "case_ids": []})
    assert r.status_code == 422


def test_api_filtrage_dynamique_refuse_clairement(client):
    pid, _ = _projet_avec_cas(client, 1)
    r = client.post(f"/api/projects/{pid}/runs", json={
        "name": "R", "selection_mode": "dynamic"})
    assert r.status_code == 422
    assert "dynamique" in r.json()["detail"]


def test_api_run_ou_projet_inconnu_404(client):
    assert client.get("/api/runs/999").status_code == 404
    assert client.post("/api/projects/999/runs", json={"name": "R", "selection_mode": "all"}).status_code == 404
