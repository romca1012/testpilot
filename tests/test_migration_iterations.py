"""Migration 70 (décision A52, porteur, 2026-10-16) — `test_run.dataset_ids` : les lignes jouées en itérations.

Les quatre pièces d'une évolution de schéma (CLAUDE.md §6) : migration SQLite, révision Alembic chaînée sur la tête précédente,
`schema_sa` aligné, et ce test. Additive : une exécution d'avant garde `dataset_id`, la nouvelle colonne reste vide.
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

from testpilot.store import db, portable_connection, schema_sa
from testpilot.store.db import _migrate_70_iterations, get_initialized_db

RACINE = Path(__file__).resolve().parent.parent


def test_une_base_neuve_a_la_colonne(tmp_path):
    conn = get_initialized_db(tmp_path / "neuve.db")
    colonnes = {r["name"] for r in conn.execute("PRAGMA table_info(test_run)")}
    conn.close()
    assert db._SCHEMA_VERSION >= 70 and "dataset_ids" in colonnes


def test_la_migration_70_est_idempotente_et_ne_change_rien_d_existant(tmp_path):
    base = sqlite3.connect(str(tmp_path / "vieille.db"))
    base.row_factory = sqlite3.Row
    base.execute("CREATE TABLE test_run (id INTEGER PRIMARY KEY, dataset_id INTEGER)")
    base.execute("INSERT INTO test_run VALUES (1, 7)")

    _migrate_70_iterations(base)
    _migrate_70_iterations(base)

    assert dict(base.execute("SELECT dataset_id, dataset_ids FROM test_run").fetchone()) == {"dataset_id": 7, "dataset_ids": ""}
    base.close()


def test_la_revision_alembic_est_chainee_sur_la_tete_precedente():
    chemin = RACINE / "alembic" / "versions" / "a8d3f5c1e264_iterations.py"
    spec = importlib.util.spec_from_file_location("revision_70", chemin)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)

    assert (revision.revision, revision.down_revision) == ("a8d3f5c1e264", "f6c1d8a2e937")
    assert portable_connection.ALEMBIC_HEAD == "a8d3f5c1e264"
    autres = [p.name for p in chemin.parent.glob("*.py")
              if p != chemin and 'down_revision = "f6c1d8a2e937"' in p.read_text(encoding="utf-8")]
    assert autres == []


def test_le_schema_portable_est_aligne():
    assert schema_sa.ALIGNED_WITH_SCHEMA_VERSION == db._SCHEMA_VERSION
    assert "dataset_ids" in schema_sa.metadata.tables["test_run"].c
