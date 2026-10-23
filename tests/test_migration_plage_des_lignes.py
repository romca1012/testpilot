"""Migration 76 (A107, porteur, 2026-10-23) — « de la ligne X à la ligne Y » des lignes propres aux cas, choisi au lancement.

Les quatre pièces d'une évolution de schéma (CLAUDE.md §6) : migration SQLite, révision Alembic chaînée sur la tête précédente,
`schema_sa` aligné, et ce test. Additive : les deux colonnes NULL par défaut, une campagne d'avant n'a pas de plage.
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import pytest

from testpilot.store import db, portable_connection, schema_sa
from testpilot.store.db import _migrate_76_plage_des_lignes, get_initialized_db

RACINE = Path(__file__).resolve().parent.parent


def test_une_base_neuve_a_les_deux_colonnes_nulles_par_defaut(tmp_path):
    conn = get_initialized_db(tmp_path / "neuve.db")
    colonnes = {r["name"]: r for r in conn.execute("PRAGMA table_info(test_run)")}
    assert db._SCHEMA_VERSION >= 76
    assert colonnes["ligne_debut"]["notnull"] == 0 and colonnes["ligne_fin"]["notnull"] == 0
    conn.close()


def test_la_migration_76_est_idempotente_et_garde_les_campagnes_d_avant(tmp_path):
    base = sqlite3.connect(str(tmp_path / "vieille.db"))
    base.row_factory = sqlite3.Row
    base.execute("CREATE TABLE test_run (id INTEGER PRIMARY KEY, name TEXT, lignes_des_cas TEXT NOT NULL DEFAULT 'toutes')")
    base.execute("INSERT INTO test_run (id, name) VALUES (1, 'Nuit')")

    _migrate_76_plage_des_lignes(base)
    _migrate_76_plage_des_lignes(base)

    ligne = base.execute("SELECT ligne_debut, ligne_fin FROM test_run").fetchone()
    assert (ligne[0], ligne[1]) == (None, None)
    with pytest.raises(sqlite3.IntegrityError):
        base.execute("UPDATE test_run SET ligne_debut = 0")
    base.close()


def test_schema_sa_porte_les_colonnes_et_leur_contrainte():
    table = schema_sa.metadata.tables["test_run"]
    assert table.c.ligne_debut.nullable and table.c.ligne_fin.nullable
    assert "ck_test_run_plage_des_lignes" in {c.name for c in table.constraints}
    assert schema_sa.ALIGNED_WITH_SCHEMA_VERSION == db._SCHEMA_VERSION


def test_la_revision_alembic_est_chainee_sur_la_tete_precedente():
    chemin = RACINE / "alembic" / "versions" / "a7d3e9b2c418_plage_des_lignes.py"
    spec = importlib.util.spec_from_file_location("revision_76", chemin)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)

    assert (revision.revision, revision.down_revision) == ("a7d3e9b2c418", "f4c9a2d7e185")
    assert portable_connection.ALEMBIC_HEAD == "a7d3e9b2c418"
