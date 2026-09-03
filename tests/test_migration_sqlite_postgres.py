"""Preuve opt-in de la migration réelle des données SQLite vers PostgreSQL."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import psycopg
import pytest

from scripts.migrate_sqlite_to_postgres import migrer
from testpilot.api import access
from testpilot.store import schema_sa
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, ModuleRepo, ProjectRepo, UserRepo


URL = os.getenv("TESTPILOT_TEST_POSTGRES_URL", "")
pytestmark = pytest.mark.skipif(not URL, reason="PostgreSQL de test non configuré")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_migration_complete_preserve_source_et_verifie_les_donnees(tmp_path):
    source = tmp_path / "source.db"
    sqlite = get_initialized_db(source)
    try:
        pid = ProjectRepo(sqlite).create(
            name="Migration réelle", connector_type="odoo", connector_version="19")
        mid = ModuleRepo(sqlite).create(project_id=pid, name="Ventes")
        cid = CaseRepo(sqlite).create_manual(
            module_id=mid, title="Créer un devis", test_steps='["ouvrir", "valider"]',
            expected_result="Le devis est créé")
        uid = UserRepo(sqlite).create(
            username="migration-admin",
            password_hash=access.hacher_mot_de_passe("mot-de-passe-migration"),
            role=access.ROLE_ADMIN,
        )
    finally:
        sqlite.close()

    empreinte_avant = _sha256(source)

    # Cette base est explicitement jetable (variable TESTPILOT_TEST_POSTGRES_URL de la CI).
    dsn = URL.replace("postgresql+psycopg://", "postgresql://", 1)
    noms = ", ".join(f'"{table.name}"' for table in reversed(schema_sa.metadata.sorted_tables))
    with psycopg.connect(dsn) as pg:
        pg.execute(f"TRUNCATE TABLE {noms} RESTART IDENTITY CASCADE")

    rapport = migrer(source, URL, tmp_path / "snapshots")

    assert _sha256(source) == empreinte_avant
    assert rapport["tables"]["project"]["lignes"] == 1
    assert rapport["tables"]["test_case"]["lignes"] == 1
    assert rapport["tables"]["user"]["lignes"] == 1

    with psycopg.connect(dsn) as pg:
        projet = pg.execute(
            "SELECT name, connector_version FROM project WHERE id=%s", (pid,)).fetchone()
        cas = pg.execute("SELECT title FROM test_case WHERE id=%s", (cid,)).fetchone()
        utilisateur = pg.execute("SELECT username FROM \"user\" WHERE id=%s", (uid,)).fetchone()
    assert projet == ("Migration réelle", "19")
    assert cas == ("Créer un devis",)
    assert utilisateur == ("migration-admin",)
