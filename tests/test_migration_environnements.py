"""Migration 69 (lot PT-04a, décisions A48 à A50) — les environnements d'un projet.

Les quatre pièces d'une évolution de schéma (CLAUDE.md §6) : migration SQLite, révision Alembic chaînée sur la tête précédente,
`schema_sa` aligné, et ce test. Additive : l'adresse du projet n'est pas déplacée, rien n'est rempli d'office.
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import pytest

from testpilot.store import db, portable_connection, schema_sa
from testpilot.store.db import _migrate_69_environnements, get_initialized_db

RACINE = Path(__file__).resolve().parent.parent


def test_une_base_neuve_a_la_table_et_les_colonnes(tmp_path):
    conn = get_initialized_db(tmp_path / "neuve.db")
    colonnes = {t: {r["name"] for r in conn.execute(f"PRAGMA table_info({t})")}
                for t in ("project_environment", "project", "test_run", "scheduled_run")}
    conn.close()

    assert db._SCHEMA_VERSION >= 69
    assert {"nom", "base_url", "connector_version", "database", "oracle_base_url", "nature", "deleted_at"} <= colonnes[
        "project_environment"]
    assert "environnement_nom" in colonnes["project"]
    assert {"environment_id", "environnement_fige"} <= colonnes["test_run"]
    assert "environment_ids" in colonnes["scheduled_run"]


def test_falsifiable_la_nature_est_obligatoire_et_fermee(tmp_path):
    conn = get_initialized_db(tmp_path / "neuve.db")
    conn.execute("INSERT INTO project (name, created_at) VALUES ('P', 'x')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO project_environment (project_id, nom, base_url, created_at) VALUES (1, 'A', 'https://a', 'x')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO project_environment (project_id, nom, base_url, nature, created_at)"
                     " VALUES (1, 'A', 'https://a', 'prod', 'x')")
    conn.close()


def test_la_migration_69_est_idempotente_et_ne_deplace_rien(tmp_path):
    base = sqlite3.connect(str(tmp_path / "vieille.db"))
    base.row_factory = sqlite3.Row
    base.execute("CREATE TABLE project (id INTEGER PRIMARY KEY, name TEXT, base_url TEXT)")
    base.execute("CREATE TABLE test_run (id INTEGER PRIMARY KEY, name TEXT)")
    base.execute("CREATE TABLE scheduled_run (id INTEGER PRIMARY KEY, name TEXT)")
    base.execute("INSERT INTO project VALUES (1, 'Ancien', 'https://recette.test')")
    base.execute("INSERT INTO test_run VALUES (1, 'Nuit')")

    _migrate_69_environnements(base)
    _migrate_69_environnements(base)

    assert dict(base.execute("SELECT base_url, environnement_nom FROM project").fetchone()) == {
        "base_url": "https://recette.test", "environnement_nom": ""}
    assert dict(base.execute("SELECT environment_id, environnement_fige FROM test_run").fetchone()) == {
        "environment_id": None, "environnement_fige": ""}
    assert base.execute("SELECT COUNT(*) FROM project_environment").fetchone()[0] == 0
    base.close()


def test_la_revision_alembic_est_chainee_sur_la_tete_precedente():
    chemin = RACINE / "alembic" / "versions" / "f6c1d8a2e937_environnements.py"
    spec = importlib.util.spec_from_file_location("revision_69", chemin)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)

    assert (revision.revision, revision.down_revision) == ("f6c1d8a2e937", "e4b8c2f19a63")
    assert portable_connection.ALEMBIC_HEAD != "e4b8c2f19a63"   # avancée depuis (migration 70, A52)
    autres = [p.name for p in chemin.parent.glob("*.py")
              if p != chemin and 'down_revision = "e4b8c2f19a63"' in p.read_text(encoding="utf-8")]
    assert autres == [], "une seule révision descend de e4b8c2f19a63"


def test_le_schema_portable_est_aligne():
    assert schema_sa.ALIGNED_WITH_SCHEMA_VERSION == db._SCHEMA_VERSION
    table = schema_sa.metadata.tables["project_environment"]
    assert not table.c["nature"].nullable and table.c["nature"].server_default is None
    assert "environnement_fige" in schema_sa.metadata.tables["test_run"].c
    assert "environment_ids" in schema_sa.metadata.tables["scheduled_run"].c
