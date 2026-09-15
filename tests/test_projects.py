"""§7 — hiérarchie Projet → Module → Cas : store, migration et API.

Couvre : repos projet/module, rattachement d'un cas (module_id) + slug technique séparé,
migration d'une base d'avant la hiérarchie, et les endpoints + filtres par projet.
"""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import app as app_mod
from testpilot.store.db import (
    _migrate_1_project_module,
    _migrate_2_project_connector,
    _migrate_38_connector_version,
    get_initialized_db,
)
from testpilot.store.repositories import (
    CaseRepo,
    CostRepo,
    ExecutionRepo,
    ModuleRepo,
    ProjectRepo,
    VersionRepo,
    ensure_default_module,
)


@pytest.fixture
def conn(tmp_path, monkeypatch):
    from testpilot import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    c = get_initialized_db(tmp_path / "h.db")
    yield c
    c.close()


# ── Store ─────────────────────────────────────────────────────────────────────
def test_ensure_default_module_rattache_a_un_projet(conn):
    mid = ensure_default_module(conn, "demande_materiel")
    module = ModuleRepo(conn).get(mid)
    assert module["name"] == "Demande materiel"        # slug prettifié
    # Projet par défaut nommé d'après l'application, JAMAIS « Odoo » (un connecteur).
    assert module["project_name"] == "Portail Sapian"
    assert ProjectRepo(conn).get(module["project_id"])["connector_type"] == "odoo"
    # Idempotent : même slug → même module, pas de doublon.
    assert ensure_default_module(conn, "demande_materiel") == mid


def test_case_rattache_module_et_conserve_slug_technique(conn):
    mid = ensure_default_module(conn, "demande_materiel")
    cid = CaseRepo(conn).create(title="Demande", module_id=mid, feature_slug="demande_materiel")
    case = CaseRepo(conn).get(cid)
    assert case["module_id"] == mid
    assert case["feature_slug"] == "demande_materiel"   # technique préservé
    assert case["module_name"] == "Demande materiel"    # métier via jointure
    assert case["project_name"] == "Portail Sapian"


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


def test_project_repo_connector_version_indeterminee_par_defaut(conn):
    """`ProjectRepo.create` sans `connector_version` : '' (indéterminée), jamais une valeur
    devinée — chaque connecteur a son propre format de version (migration 38)."""
    pid = ProjectRepo(conn).create(name="Odoo")
    assert ProjectRepo(conn).get(pid)["connector_version"] == ""


def test_project_repo_connector_version_persistee(conn):
    pid = ProjectRepo(conn).create(name="Odoo 17", connector_version="17")
    assert ProjectRepo(conn).get(pid)["connector_version"] == "17"


def test_project_repo_update_connection_edite_la_version(conn):
    pid = ProjectRepo(conn).create(name="Odoo")

    ProjectRepo(conn).update_connection(pid, connector_version="19")

    assert ProjectRepo(conn).get(pid)["connector_version"] == "19"


def test_un_connector_type_invalide_est_rejete_explicitement(conn):
    """Migration 44 : avant ce CHECK, une faute de frappe tombait en silence dans le connecteur
    générique — aucune erreur, aucun signal. Elle doit maintenant être refusée à l'écriture."""
    with pytest.raises(sqlite3.IntegrityError):
        ProjectRepo(conn).create(name="Faute de frappe", connector_type="odooo")


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
    assert project["name"] == "Odoo"   # migration 1 seule : renommé par la migration 2
    raw.close()


def test_migration_2_connecteur_remonte_au_projet(tmp_path):
    """Migration 2 : connecteur sur le projet, « Odoo » → « Portail Sapian », connector_type
    retiré du cas."""
    db = tmp_path / "v1.db"
    raw = sqlite3.connect(str(db))
    raw.row_factory = sqlite3.Row
    raw.execute("CREATE TABLE project (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,"
                " description TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT '')")
    raw.execute("CREATE TABLE test_case (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,"
                " connector_type TEXT NOT NULL DEFAULT 'odoo')")
    raw.execute("INSERT INTO project (name) VALUES ('Odoo')")
    raw.execute("INSERT INTO test_case (title) VALUES ('X')")
    raw.commit()

    _migrate_2_project_connector(raw)
    raw.commit()

    pcols = {r["name"] for r in raw.execute("PRAGMA table_info(project)")}
    assert {"connector_type", "base_url", "database", "username", "password"} <= pcols
    # « Odoo » (connecteur) devient un vrai nom d'application + sa connexion.
    proj = dict(raw.execute("SELECT * FROM project WHERE id=1").fetchone())
    assert proj["name"] == "Portail Sapian"
    assert proj["connector_type"] == "odoo"
    assert proj["base_url"]  # repris de la config
    # Le connecteur a quitté le cas.
    assert "connector_type" not in {r["name"] for r in raw.execute("PRAGMA table_info(test_case)")}
    raw.close()


def test_migration_38_ajoute_connector_version(tmp_path):
    """Migration 38 : la VERSION du connecteur, distincte du connecteur lui-même. Colonne
    ajoutée, vide par défaut — « indéterminée » reste un choix légitime, jamais une valeur
    forcée sur les projets déjà existants."""
    db = tmp_path / "v37.db"
    raw = sqlite3.connect(str(db))
    raw.row_factory = sqlite3.Row
    raw.execute("CREATE TABLE project (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,"
                " connector_type TEXT NOT NULL DEFAULT 'odoo', created_at TEXT NOT NULL DEFAULT '')")
    raw.execute("INSERT INTO project (name) VALUES ('Portail Sapian')")
    raw.commit()

    _migrate_38_connector_version(raw)
    raw.commit()

    pcols = {r["name"] for r in raw.execute("PRAGMA table_info(project)")}
    assert "connector_version" in pcols
    proj = dict(raw.execute("SELECT * FROM project WHERE id=1").fetchone())
    assert proj["connector_version"] == ""
    # Idempotente : rejouée sur une base déjà à la cible, elle ne casse rien.
    _migrate_38_connector_version(raw)
    raw.close()


# ── API ───────────────────────────────────────────────────────────────────────
@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
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


def test_api_connector_version_indeterminee_par_defaut(client):
    """Créer un projet SANS préciser de version : '' (indéterminée) — jamais une valeur
    devinée. Chaque connecteur a son propre format de version, aucune liste fermée à respecter."""
    p = client.post("/api/projects", json={"name": "Odoo"})
    assert p.json()["connector_version"] == ""


def test_api_connector_version_declaree_a_la_creation(client):
    p = client.post("/api/projects", json={"name": "Odoo 17", "connector_version": "17"})
    assert p.status_code == 201
    assert p.json()["connector_version"] == "17"
    # Relue depuis la liste, pas seulement dans la réponse de création.
    pid = p.json()["id"]
    releve = next(x for x in client.get("/api/projects").json() if x["id"] == pid)
    assert releve["connector_version"] == "17"


def test_api_connector_version_editable(client):
    pid = client.post("/api/projects", json={"name": "Odoo"}).json()["id"]

    r = client.patch(f"/api/projects/{pid}", json={"connector_version": "19"})

    assert r.status_code == 200
    assert r.json()["connector_version"] == "19"


def test_api_connector_version_peut_etre_revidee_explicitement(client):
    """Une chaîne vide EXPLICITE revient à « indéterminée » — distinct de ne pas fournir le
    champ du tout (même logique que le mot de passe, décision 0005)."""
    pid = client.post("/api/projects", json={"name": "Odoo", "connector_version": "17"}).json()["id"]

    r = client.patch(f"/api/projects/{pid}", json={"connector_version": ""})

    assert r.json()["connector_version"] == ""


def test_api_case_detail_expose_le_fil_d_ariane(client):
    conn = get_initialized_db(config.DB_PATH)
    mid = ensure_default_module(conn, "demande_materiel")
    cid = CaseRepo(conn).create(title="Demande", module_id=mid, feature_slug="demande_materiel")
    conn.close()

    detail = client.get(f"/api/cases/{cid}").json()
    assert detail["project"]["name"] == "Portail Sapian"
    assert detail["module"]["name"] == "Demande materiel"
    assert detail["case"]["module"] == "Demande materiel"  # nom métier, pas le slug


def test_api_delete_project_cascade(client):
    conn = get_initialized_db(config.DB_PATH)
    mid = ensure_default_module(conn, "demande_materiel")
    pid = ModuleRepo(conn).get(mid)["project_id"]
    cid = CaseRepo(conn).create(title="Demande", module_id=mid, feature_slug="demande_materiel")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="h",
                                   feature_content="", steps_content="")
    eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid)
    ExecutionRepo(conn).add_scenario_result(execution_id=eid, scenario_name="s",
                                            execution_status="success", functional_status="conforme")
    conn.close()

    # Suppression du projet → 204, et toute sa descendance QUITTE LES ÉCRANS.
    assert client.delete(f"/api/projects/{pid}").status_code == 204
    assert all(p["id"] != pid for p in client.get("/api/projects").json())
    assert client.get(f"/api/cases/{cid}").status_code == 404

    # ⚠️ Depuis le 2026-07-24, les LIGNES sont conservées (§7 : jamais de destruction sèche).
    # La cascade destructive existe toujours — c'est `purger()` — et c'est elle que ce test doit
    # exercer : il couvre l'ORDRE des suppressions sous les clés étrangères.
    conn = get_initialized_db(config.DB_PATH)
    assert conn.execute("SELECT COUNT(*) FROM test_case").fetchone()[0] == 1   # conservé
    ProjectRepo(conn).purger(pid)
    for table in ("module", "test_case", "test_case_version", "execution", "scenario_result"):
        n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        assert n == 0, f"{table} contient encore {n} ligne(s)"
    conn.close()


def test_api_delete_project_isole_les_autres(client):
    conn = get_initialized_db(config.DB_PATH)
    m1 = ensure_default_module(conn, "demande_materiel")
    p1 = ModuleRepo(conn).get(m1)["project_id"]
    p2 = ProjectRepo(conn).create(name="Sales CRM")
    m2 = ModuleRepo(conn).create(project_id=p2, name="Opportunités")
    CaseRepo(conn).create(title="Garde", module_id=m2, feature_slug="g")
    conn.close()

    client.delete(f"/api/projects/{p1}")
    # Le second projet et son cas sont intacts.
    assert any(p["id"] == p2 for p in client.get("/api/projects").json())
    assert {c["title"] for c in client.get(f"/api/cases?project_id={p2}").json()["items"]} == {"Garde"}


def test_delete_project_emporte_le_cout_de_generation_sans_execution(client):
    """Régression migration 12 : une ligne de coût de GÉNÉRATION n'a pas d'exécution
    (elle la précède, cf. `CostRepo.add_entry`). La cascade la nettoyait par `execution_id`
    seul → elle survivait à son projet, orpheline, et faussait le §9. Ce test échoue sur
    l'ancienne cascade (le coût de génération reste), passe depuis le correctif `test_case_id`."""
    conn = get_initialized_db(config.DB_PATH)
    mid = ensure_default_module(conn, "demande_materiel")
    pid = ModuleRepo(conn).get(mid)["project_id"]
    cid = CaseRepo(conn).create(title="Demande", module_id=mid, feature_slug="demande_materiel")
    # Le coût de génération : test_case_id renseigné, AUCUNE exécution (c'est tout le sujet).
    CostRepo(conn).add_entry(phase="generation", model="claude", cost_usd=0.10,
                             source="estimated", test_case_id=cid)
    conn.close()

    assert client.delete(f"/api/projects/{pid}").status_code == 204

    # La purge est le geste qui DÉTRUIT (§7) : c'est lui qui doit emporter le coût orphelin.
    conn = get_initialized_db(config.DB_PATH)
    ProjectRepo(conn).purger(pid)
    n = conn.execute("SELECT COUNT(*) FROM cost_ledger").fetchone()[0]
    conn.close()
    assert n == 0, f"cost_ledger contient encore {n} ligne(s) orpheline(s) après purge du projet"


def test_delete_case_emporte_le_cout_de_generation_sans_execution(conn):
    """Même régression, au niveau `CaseRepo.delete` : le coût de génération d'un cas
    supprimé ne doit pas survivre. La ligne à exécution rattachée part aussi."""
    mid = ensure_default_module(conn, "demande_materiel")
    cid = CaseRepo(conn).create(title="Demande", module_id=mid, feature_slug="demande_materiel")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="h",
                                   feature_content="", steps_content="")
    eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid)
    # Deux postes : génération (sans exécution) ET réparation (rattachée à une exécution).
    CostRepo(conn).add_entry(phase="generation", model="claude", cost_usd=0.10,
                             source="estimated", test_case_id=cid)
    CostRepo(conn).add_entry(phase="repair", model="claude", cost_usd=0.05,
                             source="estimated", execution_id=eid)
    assert conn.execute("SELECT COUNT(*) FROM cost_ledger").fetchone()[0] == 2

    # Supprimer masque ; purger détruit. Le coût orphelin est le sujet de ce test, donc c'est
    # la purge qu'il exerce — la couverture de la régression « migration 12 » est préservée.
    CaseRepo(conn).delete(cid)
    assert conn.execute("SELECT COUNT(*) FROM cost_ledger").fetchone()[0] == 2   # rien détruit

    CaseRepo(conn).purger(cid)

    n = conn.execute("SELECT COUNT(*) FROM cost_ledger").fetchone()[0]
    assert n == 0, f"cost_ledger contient encore {n} ligne(s) après purge du cas"


def test_api_rename_project(client):
    p = client.post("/api/projects", json={"name": "Odoo"}).json()
    r = client.patch(f"/api/projects/{p['id']}", json={"name": "Portail Sapian"})
    assert r.status_code == 200
    assert r.json()["name"] == "Portail Sapian"
    assert any(x["name"] == "Portail Sapian" for x in client.get("/api/projects").json())


def test_api_cases_filtre_project_id(client):
    conn = get_initialized_db(config.DB_PATH)
    m_odoo = ensure_default_module(conn, "demande_materiel")
    p_odoo = ModuleRepo(conn).get(m_odoo)["project_id"]
    other_p = ProjectRepo(conn).create(name="Autre")
    other_m = ModuleRepo(conn).create(project_id=other_p, name="Divers")
    CaseRepo(conn).create(title="Odoo-cas", module_id=m_odoo, feature_slug="a")
    CaseRepo(conn).create(title="Autre-cas", module_id=other_m, feature_slug="b")
    conn.close()

    odoo_cases = client.get(f"/api/cases?project_id={p_odoo}").json()["items"]
    assert {c["title"] for c in odoo_cases} == {"Odoo-cas"}  # jamais de mélange inter-projets
