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
from testpilot.store.repositories import CaseRepo, ModuleRepo, ProjectRepo, UserRepo, VersionRepo

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
