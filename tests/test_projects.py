"""§7 — hiérarchie Projet → Module → Cas : store, migration et API.

Couvre : repos projet/module, rattachement d'un cas (module_id) + slug technique séparé,
migration d'une base d'avant la hiérarchie, et les endpoints + filtres par projet.
"""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import app as app_mod
from testpilot.store.db import _migrate_1_project_module, get_initialized_db
from testpilot.store.repositories import (
    CaseRepo,
    ModuleRepo,
    ProjectRepo,
    ensure_default_module,
)


@pytest.fixture
def conn(tmp_path):
    c = get_initialized_db(tmp_path / "h.db")
    yield c
    c.close()


# ── Store ─────────────────────────────────────────────────────────────────────
def test_ensure_default_module_cree_projet_odoo(conn):
    mid = ensure_default_module(conn, "demande_materiel")
    module = ModuleRepo(conn).get(mid)
    assert module["name"] == "Demande materiel"        # slug prettifié
    assert module["project_name"] == "Odoo"
    # Idempotent : même slug → même module, pas de doublon.
    assert ensure_default_module(conn, "demande_materiel") == mid


def test_case_rattache_module_et_conserve_slug_technique(conn):
    mid = ensure_default_module(conn, "demande_materiel")
    cid = CaseRepo(conn).create(title="Demande", module_id=mid, feature_slug="demande_materiel")
    case = CaseRepo(conn).get(cid)
    assert case["module_id"] == mid
    assert case["feature_slug"] == "demande_materiel"   # technique préservé
    assert case["module_name"] == "Demande materiel"    # métier via jointure
    assert case["project_name"] == "Odoo"


def test_list_cases_filtre_par_projet_et_module(conn):
    projects, modules = ProjectRepo(conn), ModuleRepo(conn)
    p1 = projects.create(name="Odoo"); p2 = projects.create(name="Autre")
    m1 = modules.create(project_id=p1, name="Demande matériel")
    m2 = modules.create(project_id=p2, name="Divers")
    CaseRepo(conn).create(title="A", module_id=m1, feature_slug="a")
    CaseRepo(conn).create(title="B", module_id=m2, feature_slug="b")

    assert {c["title"] for c in CaseRepo(conn).list_all()} == {"A", "B"}
    assert {c["title"] for c in CaseRepo(conn).list_all(project_id=p1)} == {"A"}
    assert {c["title"] for c in CaseRepo(conn).list_all(module_id=m2)} == {"B"}


# ── Migration d'une base d'AVANT la hiérarchie ────────────────────────────────
def test_migration_depuis_ancien_schema(tmp_path):
    db = tmp_path / "old.db"
    raw = sqlite3.connect(str(db))
    raw.row_factory = sqlite3.Row  # comme connect() en prod (lignes indexables par nom)
    raw.execute(
        "CREATE TABLE test_case (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,"
        " module TEXT NOT NULL, validation_status TEXT NOT NULL DEFAULT 'never_executed',"
        " created_at TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL DEFAULT '')")
    raw.execute("CREATE TABLE project (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,"
                " description TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL)")
    raw.execute("CREATE TABLE module (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL,"
                " name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL)")
    raw.execute("INSERT INTO test_case (title, module) VALUES ('Demande', 'demande_materiel')")
    raw.commit()

    _migrate_1_project_module(raw)
    raw.commit()

    cols = {r["name"] for r in raw.execute("PRAGMA table_info(test_case)")}
    assert "module" not in cols                      # colonne obsolète supprimée
    assert {"module_id", "feature_slug"} <= cols
    case = dict(raw.execute("SELECT * FROM test_case WHERE id=1").fetchone())
    assert case["feature_slug"] == "demande_materiel"  # slug technique préservé
    module = dict(raw.execute("SELECT * FROM module WHERE id=?", (case["module_id"],)).fetchone())
    assert module["name"] == "Demande materiel"
    project = dict(raw.execute("SELECT name FROM project WHERE id=?", (module["project_id"],)).fetchone())
    assert project["name"] == "Odoo"
    raw.close()


# ── API ───────────────────────────────────────────────────────────────────────
@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    return TestClient(app_mod.app)


def test_api_projects_crud_et_modules(client):
    # Création projet
    p = client.post("/api/projects", json={"name": "Odoo"})
    assert p.status_code == 201
    pid = p.json()["id"]
    # Liste
    assert any(x["id"] == pid for x in client.get("/api/projects").json())
    # Création module sous le projet
    m = client.post(f"/api/projects/{pid}/modules", json={"name": "Demande matériel"})
    assert m.status_code == 201
    mods = client.get(f"/api/projects/{pid}/modules").json()
    assert mods[0]["name"] == "Demande matériel"
    # Module sous projet inexistant → 404
    assert client.post("/api/projects/999/modules", json={"name": "X"}).status_code == 404


def test_api_case_detail_expose_le_fil_d_ariane(client):
    conn = get_initialized_db(config.DB_PATH)
    mid = ensure_default_module(conn, "demande_materiel")
    cid = CaseRepo(conn).create(title="Demande", module_id=mid, feature_slug="demande_materiel")
    conn.close()

    detail = client.get(f"/api/cases/{cid}").json()
    assert detail["project"]["name"] == "Odoo"
    assert detail["module"]["name"] == "Demande materiel"
    assert detail["case"]["module"] == "Demande materiel"  # nom métier, pas le slug


def test_api_cases_filtre_project_id(client):
    conn = get_initialized_db(config.DB_PATH)
    m_odoo = ensure_default_module(conn, "demande_materiel")
    p_odoo = ModuleRepo(conn).get(m_odoo)["project_id"]
    other_p = ProjectRepo(conn).create(name="Autre")
    other_m = ModuleRepo(conn).create(project_id=other_p, name="Divers")
    CaseRepo(conn).create(title="Odoo-cas", module_id=m_odoo, feature_slug="a")
    CaseRepo(conn).create(title="Autre-cas", module_id=other_m, feature_slug="b")
    conn.close()

    odoo_cases = client.get(f"/api/cases?project_id={p_odoo}").json()
    assert {c["title"] for c in odoo_cases} == {"Odoo-cas"}  # jamais de mélange inter-projets
