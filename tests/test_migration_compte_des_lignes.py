"""Migration 74 (décisions A90-A92, porteur, 2026-10-21) — le compte avec lequel une ligne de données du cas est jouée.

Les quatre pièces d'une évolution de schéma (CLAUDE.md §6) : migration SQLite, révision Alembic chaînée sur la tête précédente,
`schema_sa` aligné, et ce test. Additive : toute ligne d'avant reprend « Joué en tant que » du cas (`compte_choisi` = 0).
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import pytest

from testpilot.store import db, portable_connection, schema_sa
from testpilot.store.db import _migrate_74_compte_des_lignes, get_initialized_db

RACINE = Path(__file__).resolve().parent.parent


def test_une_base_neuve_a_les_colonnes_et_refuse_une_valeur_hors_0_1(tmp_path):
    conn = get_initialized_db(tmp_path / "neuve.db")
    colonnes = {r["name"]: r for r in conn.execute("PRAGMA table_info(case_data_row)")}
    assert db._SCHEMA_VERSION >= 74 and colonnes["compte_choisi"]["notnull"] == 1 and colonnes["compte_id"]["notnull"] == 0
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO case_data_row (case_id, nom, rang, created_at, compte_choisi) VALUES (1, '', 1, 'x', 2)")
    conn.close()


def test_la_migration_74_est_idempotente_et_garde_les_lignes_d_avant(tmp_path):
    base = sqlite3.connect(str(tmp_path / "vieille.db"))
    base.row_factory = sqlite3.Row
    base.execute("CREATE TABLE case_data_row (id INTEGER PRIMARY KEY, case_id INTEGER, nom TEXT, rang INTEGER, created_at TEXT)")
    base.execute("INSERT INTO case_data_row VALUES (1, 7, 'Mineur', 1, 'x')")

    _migrate_74_compte_des_lignes(base)
    _migrate_74_compte_des_lignes(base)

    assert dict(base.execute("SELECT nom, compte_choisi, compte_id FROM case_data_row").fetchone()) == {
        "nom": "Mineur", "compte_choisi": 0, "compte_id": None}, "une ligne d'avant reprend le compte du cas"
    base.close()


def test_schema_sa_porte_les_colonnes():
    table = schema_sa.metadata.tables["case_data_row"]
    assert not table.c.compte_choisi.nullable and table.c.compte_id.nullable
    assert schema_sa.ALIGNED_WITH_SCHEMA_VERSION == db._SCHEMA_VERSION


def test_la_revision_alembic_est_chainee_sur_la_tete_precedente():
    chemin = RACINE / "alembic" / "versions" / "e8a4c2f6b913_compte_des_lignes.py"
    spec = importlib.util.spec_from_file_location("revision_74", chemin)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)

    assert (revision.revision, revision.down_revision) == ("e8a4c2f6b913", "d7e3b9a1c642")
    assert portable_connection.ALEMBIC_HEAD == "e8a4c2f6b913"
