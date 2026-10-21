"""Migration 73 (décision A70, porteur, 2026-10-20) — le compte avec lequel une version du cas est jouée.

Les quatre pièces d'une évolution de schéma (CLAUDE.md §6) : migration SQLite, révision Alembic chaînée sur la tête précédente,
`schema_sa` aligné, et ce test. Additive : toute version d'avant est jouée avec le compte principal (NULL).
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

from testpilot.store import db, portable_connection, schema_sa
from testpilot.store.db import _migrate_73_compte_du_cas, get_initialized_db

RACINE = Path(__file__).resolve().parent.parent


def test_une_base_neuve_a_la_colonne_vide_par_defaut(tmp_path):
    conn = get_initialized_db(tmp_path / "neuve.db")
    colonnes = {r["name"]: r for r in conn.execute("PRAGMA table_info(test_case_version)")}
    conn.close()
    assert db._SCHEMA_VERSION >= 73 and "compte_id" in colonnes and colonnes["compte_id"]["notnull"] == 0


def test_la_migration_73_est_idempotente_et_ne_change_rien_d_existant(tmp_path):
    base = sqlite3.connect(str(tmp_path / "vieille.db"))
    base.row_factory = sqlite3.Row
    base.execute("CREATE TABLE test_case_version (id INTEGER PRIMARY KEY, title TEXT)")
    base.execute("INSERT INTO test_case_version VALUES (1, 'Accès')")

    _migrate_73_compte_du_cas(base)
    _migrate_73_compte_du_cas(base)

    assert dict(base.execute("SELECT title, compte_id FROM test_case_version").fetchone()) == {"title": "Accès",
                                                                                                "compte_id": None}
    base.close()


def test_schema_sa_porte_la_colonne():
    assert "compte_id" in schema_sa.metadata.tables["test_case_version"].c
    assert schema_sa.metadata.tables["test_case_version"].c.compte_id.nullable


def test_la_revision_alembic_est_chainee_sur_la_tete_precedente():
    chemin = RACINE / "alembic" / "versions" / "d7e3b9a1c642_compte_du_cas.py"
    spec = importlib.util.spec_from_file_location("revision_73", chemin)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)

    assert (revision.revision, revision.down_revision) == ("d7e3b9a1c642", "c5f2a8e4d917")
    assert portable_connection.ALEMBIC_HEAD == "d7e3b9a1c642"
