"""Migration 72 (décisions A57 et A58, porteur, 2026-10-19) — les lignes propres à un cas, et le choix « toutes » ou
« premiere » d'une exécution.

Les quatre pièces d'une évolution de schéma (CLAUDE.md §6) : migration SQLite, révision Alembic chaînée sur la tête précédente,
`schema_sa` aligné (contrainte CHECK comprise), et ce test. Additive : une exécution d'avant joue « toutes » les lignes, et un
cas d'avant n'en a aucune.
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import pytest

from testpilot.store import db, portable_connection, schema_sa
from testpilot.store.db import _migrate_72_lignes_du_cas, get_initialized_db

RACINE = Path(__file__).resolve().parent.parent


def test_une_base_neuve_a_les_tables_et_la_colonne(tmp_path):
    conn = get_initialized_db(tmp_path / "neuve.db")
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    colonnes = {r["name"] for r in conn.execute("PRAGMA table_info(test_run)")}
    conn.close()
    assert db._SCHEMA_VERSION >= 72 and {"case_data_row", "case_data_value"} <= tables and "lignes_des_cas" in colonnes


def test_falsifiable_la_colonne_refuse_une_valeur_inconnue(tmp_path):
    conn = get_initialized_db(tmp_path / "neuve.db")
    conn.execute("PRAGMA foreign_keys=OFF")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO test_run (project_id, name, selection_mode, mode, status, created_at, lignes_des_cas)"
                     " VALUES (1, 'r', 'frozen', 'automatique', 'draft', 'x', 'trois')")
    conn.close()


def test_la_migration_72_est_idempotente_et_ne_change_rien_d_existant(tmp_path):
    base = sqlite3.connect(str(tmp_path / "vieille.db"))
    base.row_factory = sqlite3.Row
    base.execute("CREATE TABLE test_run (id INTEGER PRIMARY KEY, name TEXT)")
    base.execute("INSERT INTO test_run VALUES (1, 'Nuit')")

    _migrate_72_lignes_du_cas(base)
    _migrate_72_lignes_du_cas(base)

    assert dict(base.execute("SELECT name, lignes_des_cas FROM test_run").fetchone()) == {"name": "Nuit", "lignes_des_cas": "toutes"}
    base.close()


def test_la_revision_alembic_est_chainee_sur_la_tete_precedente():
    chemin = RACINE / "alembic" / "versions" / "c5f2a8e4d917_lignes_du_cas.py"
    spec = importlib.util.spec_from_file_location("revision_72", chemin)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)

    assert (revision.revision, revision.down_revision) == ("c5f2a8e4d917", "b3e7c9d1f405")
    assert portable_connection.ALEMBIC_HEAD != "b3e7c9d1f405"   # avancée depuis (migration 73, A70)
    autres = [p.name for p in chemin.parent.glob("*.py")
              if p != chemin and 'down_revision = "b3e7c9d1f405"' in p.read_text(encoding="utf-8")]
    assert autres == []


def test_le_schema_portable_est_aligne():
    assert schema_sa.ALIGNED_WITH_SCHEMA_VERSION == db._SCHEMA_VERSION
    assert {"case_data_row", "case_data_value"} <= set(schema_sa.metadata.tables)
    contraintes = {c.name for c in schema_sa.metadata.tables["test_run"].constraints}
    assert "ck_test_run_lignes_des_cas" in contraintes
    assert "case_data_row" in portable_connection._TABLES_AVEC_ID
