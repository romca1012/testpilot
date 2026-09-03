"""Preuves du runtime PostgreSQL réel.

Ces tests sont opt-in afin que la suite locale SQLite reste autonome. La CI de production doit
fournir ``TESTPILOT_TEST_POSTGRES_URL`` vers une base jetable déjà migrée par Alembic.
"""

from __future__ import annotations

import os
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import access
from testpilot.api.app import app
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import (
    CaseRepo,
    ExecutionRepo,
    ModuleRepo,
    ProjectRepo,
    RunRepo,
    SettingRepo,
    UserRepo,
    VersionRepo,
)

URL = os.getenv("TESTPILOT_TEST_POSTGRES_URL", "")
pytestmark = pytest.mark.skipif(not URL, reason="PostgreSQL de test non configuré")


@pytest.fixture(autouse=True)
def postgres(monkeypatch):
    monkeypatch.setattr(config, "DB_URL", URL)


def test_repositories_crud_sur_postgresql():
    suffixe = uuid4().hex[:8]
    conn = get_initialized_db()
    try:
        pid = ProjectRepo(conn).create(name=f"Projet PG {suffixe}", connector_type="odoo",
                                       connector_version="19")
        mid = ModuleRepo(conn).create(project_id=pid, name="Facturation")
        cid = CaseRepo(conn).create_manual(module_id=mid, title="Créer une facture",
                                           test_steps='["ouvrir"]', expected_result="créée")
        case = CaseRepo(conn).get(cid)
        assert case["project_id"] == pid
        assert ProjectRepo(conn).get(pid)["connector_version"] == "19"
        assert VersionRepo(conn).get(case["current_version_id"])["title"] == "Créer une facture"
    finally:
        conn.close()


def test_api_utilise_postgresql_de_bout_en_bout():
    suffixe = uuid4().hex[:8]
    conn = get_initialized_db()
    try:
        UserRepo(conn).create(username=f"admin-{suffixe}",
                              password_hash=access.hacher_mot_de_passe("motdepasse"),
                              role=access.ROLE_ADMIN)
    finally:
        conn.close()

    with TestClient(app) as client:
        login = client.post("/api/auth/login", json={
            "username": f"admin-{suffixe}", "password": "motdepasse",
        })
        assert login.status_code == 200, login.text
        creation = client.post("/api/projects", json={
            "name": f"API PG {suffixe}", "connector_type": "odoo",
            "connector_version": "17", "base_url": "http://odoo.test",
        })
        assert creation.status_code == 201, creation.text
        assert creation.json()["connector_version"] == "17"
        assert any(p["id"] == creation.json()["id"] for p in client.get("/api/projects").json())


def test_postgresql_refuse_un_doublon_de_nom_independant_de_la_casse():
    suffixe = uuid4().hex[:8]
    conn = get_initialized_db()
    try:
        repo = ProjectRepo(conn)
        repo.create(name=f"Projet Casse {suffixe}")
        with pytest.raises(psycopg.IntegrityError):
            conn.execute(
                "INSERT INTO project (name, created_at) VALUES (?,?)",
                (f"PROJET CASSE {suffixe}", "2026-08-28T00:00:00+00:00"),
            )
        conn.rollback()
    finally:
        conn.close()


def test_ajouter_un_resultat_de_scenario_renvoie_un_id_valide_sur_postgresql():
    """Trouvé en pratique (2026-09-03) : `scenario_result` manquait de `_TABLES_AVEC_ID`
    (portable_connection.py) — `ExecutionRepo.add_scenario_result`, appelée à CHAQUE scénario
    Behave exécuté, aurait levé `TypeError: int() argument must be... not 'NoneType'` au tout
    premier run réel contre PostgreSQL. Preuve comportementale, pas seulement statique (voir
    `tests/test_tables_avec_id_postgres.py` pour le garde-fou qui empêche la régression)."""
    suffixe = uuid4().hex[:8]
    conn = get_initialized_db()
    try:
        pid = ProjectRepo(conn).create(name=f"Projet scénario {suffixe}")
        mid = ModuleRepo(conn).create(project_id=pid, name="Module scénario")
        cid = CaseRepo(conn).create_manual(
            module_id=mid, title="Cas scénario", test_steps='["agir"]', expected_result="ok")
        case = CaseRepo(conn).get(cid)
        execution_repo = ExecutionRepo(conn)
        eid = execution_repo.create(test_case_id=cid, version_id=case["current_version_id"])

        rid = execution_repo.add_scenario_result(
            execution_id=eid, scenario_name="Scénario nominal",
            execution_status="success", functional_status="conforme")

        assert isinstance(rid, int) and rid > 0
        resultats = execution_repo.list_scenario_results(eid)
        assert [r["id"] for r in resultats] == [rid]
        assert resultats[0]["scenario_name"] == "Scénario nominal"
    finally:
        conn.close()


def test_insert_or_ignore_se_traduit_correctement_en_on_conflict_do_nothing():
    """Seul site du dépôt utilisant `INSERT OR IGNORE` (`RunRepo.create`, liaison
    `test_run_case`) — traduit en `ON CONFLICT DO NOTHING` par `portable_connection._adapter_sql`.
    Preuve que la déduplication marche VRAIMENT sous PostgreSQL, pas seulement que la requête ne
    lève pas d'erreur de syntaxe : un `case_id` en double dans la sélection ne doit produire
    qu'UNE seule ligne de liaison, comme sous SQLite."""
    suffixe = uuid4().hex[:8]
    conn = get_initialized_db()
    try:
        pid = ProjectRepo(conn).create(name=f"Projet run {suffixe}")
        mid = ModuleRepo(conn).create(project_id=pid, name="Module run")
        cid = CaseRepo(conn).create_manual(
            module_id=mid, title="Cas run", test_steps='["agir"]', expected_result="ok")

        run_id = RunRepo(conn).create(
            project_id=pid, name=f"Run {suffixe}", selection_mode="frozen",
            case_ids=[cid, cid, cid])  # le même cas 3 fois : la dédup doit tenir

        liaisons = conn.execute(
            "SELECT case_id FROM test_run_case WHERE run_id=?", (run_id,)).fetchall()
        assert [r["case_id"] for r in liaisons] == [cid]
    finally:
        conn.close()


def test_upsert_on_conflict_do_update_reecrit_la_valeur_existante():
    """`ON CONFLICT(...) DO UPDATE SET col=excluded.col` (`SettingRepo.ecrire`,
    `ProjectAccessRepo`/`ProjectMemberRepo`/`ProjectGroupAccessRepo`.set — 4 sites au total) est
    du SQL standard, identique sous SQLite et PostgreSQL : `_adapter_sql` ne le traduit pas
    spécialement (seuls `?`→`%s` s'appliquent). Preuve que ça marche vraiment, pas seulement que
    la requête ne lève pas d'erreur de syntaxe : une deuxième écriture sur la MÊME clé doit
    REMPLACER la valeur, jamais dupliquer la ligne."""
    suffixe = uuid4().hex[:8]
    conn = get_initialized_db()
    try:
        # `SettingRepo` a un vocabulaire FERMÉ (`CLES_CONNUES`) — une clé arbitraire est refusée
        # avant même d'atteindre le SQL. `reference_url_template` est une clé réelle et neutre.
        cle = "reference_url_template"
        repo = SettingRepo(conn)
        repo.ecrire(cle, f"première valeur {suffixe}", par="qa")
        repo.ecrire(cle, f"valeur écrasée {suffixe}", par="qa")

        lignes = conn.execute(
            "SELECT value FROM app_setting WHERE key=?", (cle,)).fetchall()
        assert [r["value"] for r in lignes] == [f"valeur écrasée {suffixe}"]
    finally:
        conn.close()


def test_postgresql_refuse_un_resultat_dont_le_mode_contredit_la_campagne():
    suffixe = uuid4().hex[:8]
    conn = get_initialized_db()
    try:
        pid = ProjectRepo(conn).create(name=f"Projet mode {suffixe}")
        mid = ModuleRepo(conn).create(project_id=pid, name="Module mode")
        case_id = CaseRepo(conn).create_manual(
            module_id=mid, title="Cas mode", test_steps='["agir"]', expected_result="ok")
        curseur = conn.execute(
            "INSERT INTO test_run (project_id, name, description, refs, selection_mode, mode,"
            " status, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (pid, "Run manuel", "", "", "frozen", "manuelle", "draft",
             "2026-08-28T00:00:00+00:00"),
        )
        run_id = curseur.lastrowid
        with pytest.raises(psycopg.IntegrityError, match="ne concorde pas"):
            conn.execute(
                "INSERT INTO test_result (case_id, run_id, mode, statut_manuel, created_at, created_by)"
                " VALUES (?,?,?,?,?,?)",
                (case_id, run_id, "automatique", "passed", "2026-08-28T00:00:00+00:00", "audit"),
            )
        conn.rollback()
    finally:
        conn.close()
