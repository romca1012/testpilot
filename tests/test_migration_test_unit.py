"""Migration 63 (paramètres de test, lot PT-03) — table `test_unit`, les unités ajoutées par un projet.

Les quatre pièces d'une évolution de schéma (CLAUDE.md §6) : migration SQLite idempotente, révision Alembic chaînée sur la tête
précédente, `schema_sa` aligné, et ce test. Table nouvelle : rien ne change pour un projet existant.
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import pytest

from testpilot.store import db, portable_connection, schema_sa
from testpilot.store.db import _migrate_63_test_unit, get_initialized_db
from testpilot.store.repositories import DuplicateName, ProjectRepo, TestUnitRepo

RACINE = Path(__file__).resolve().parent.parent


def test_une_base_neuve_porte_la_table_et_le_depot_y_range_les_unites(tmp_path):
    conn = get_initialized_db(tmp_path / "neuve.db")
    pid = ProjectRepo(conn).create(name="P", connector_type="web", base_url="http://app")
    depot = TestUnitRepo(conn)

    assert db._SCHEMA_VERSION >= 63 and depot.liste(pid) == []
    uid = depot.creer(pid, nom="palette", ecritures=["palettes", "palette", "palettes", ""])
    assert depot.liste(pid) == [{"id": uid, "nom": "palette", "ecritures": ["palettes"]}]
    with pytest.raises(DuplicateName):
        depot.creer(pid, nom="carton", ecritures=["palettes"])
    assert depot.modifier(pid, uid, nom="palette", ecritures=["Palettes"]) and depot.lire(pid, uid)["ecritures"] == ["Palettes"]
    assert not depot.modifier(pid + 1, uid, nom="x", ecritures=[])
    conn.close()


def test_falsifiable_supprimer_le_projet_emporte_ses_unites(tmp_path):
    conn = get_initialized_db(tmp_path / "neuve.db")
    conn.execute("PRAGMA foreign_keys = ON")
    pid = ProjectRepo(conn).create(name="P", connector_type="web", base_url="http://app")
    TestUnitRepo(conn).creer(pid, nom="palette", ecritures=[])

    conn.execute("DELETE FROM project WHERE id=?", (pid,))
    conn.commit()

    assert conn.execute("SELECT COUNT(*) FROM test_unit").fetchone()[0] == 0
    conn.close()


def test_falsifiable_reprise_d_une_base_pre_63(tmp_path):
    base = sqlite3.connect(str(tmp_path / "vieille.db"))
    base.row_factory = sqlite3.Row
    base.execute("CREATE TABLE project (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
    base.execute("INSERT INTO project (id, name) VALUES (1, 'ancien')")
    base.commit()

    _migrate_63_test_unit(base)
    _migrate_63_test_unit(base)  # idempotente

    colonnes = {r["name"]: r for r in base.execute("PRAGMA table_info(test_unit)")}
    assert set(colonnes) == {"id", "project_id", "nom", "ecritures", "created_at"}
    assert colonnes["project_id"]["notnull"] == 0, "NULL = bibliothèque commune (lot PT-05)"
    assert base.execute("SELECT COUNT(*) FROM test_unit").fetchone()[0] == 0, "un projet existant ne déclare aucune unité"
    base.close()


def test_la_revision_alembic_est_chainee_sur_la_tete_precedente():
    chemin = RACINE / "alembic" / "versions" / "f3a8d1c6b257_test_unit.py"
    spec = importlib.util.spec_from_file_location("revision_63", chemin)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)

    assert (revision.revision, revision.down_revision) == ("f3a8d1c6b257", "e7c2f4a9b136")
    autres = [p.name for p in chemin.parent.glob("*.py")
              if p != chemin and 'down_revision = "e7c2f4a9b136"' in p.read_text(encoding="utf-8")]
    assert autres == [], "une seule révision descend de e7c2f4a9b136"


def test_le_schema_portable_est_aligne():
    table = schema_sa.metadata.tables["test_unit"]

    assert schema_sa.ALIGNED_WITH_SCHEMA_VERSION == db._SCHEMA_VERSION
    assert table.c["project_id"].nullable and not table.c["nom"].nullable
    assert str(table.c["ecritures"].server_default.arg) == "[]"
    assert "test_unit" in portable_connection._TABLES_AVEC_ID, "le dépôt lit `.lastrowid` : PostgreSQL doit le rendre"
