"""Migration 49 — `execution.confiance` et `test_run.strict` (lot 05, D5).

Trois gardes : une base NEUVE porte les colonnes et leurs CHECK ; une base d'AVANT le lot (avec des données) les reçoit
sans perte, l'historique valant `nominale` / `0` par défaut ; la migration est idempotente.
"""

from __future__ import annotations

import sqlite3

import pytest

from testpilot.store.db import _migrate_49_confiance_et_strict, get_initialized_db

_SCHEMA_PRE_49 = """
CREATE TABLE execution (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_status TEXT NOT NULL DEFAULT 'not_executed'
);
CREATE TABLE test_run (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL
);
"""


def _base_pre_49(chemin):
    conn = sqlite3.connect(str(chemin))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA_PRE_49)
    conn.execute("INSERT INTO execution (id, execution_status) VALUES (10, 'success')")
    conn.execute("INSERT INTO test_run (id, name) VALUES (1, 'Campagne ancienne')")
    conn.commit()
    return conn


def test_base_neuve_porte_les_deux_colonnes_et_leurs_CHECK(tmp_path, monkeypatch):
    from testpilot import config

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    conn = get_initialized_db(tmp_path / "neuve.db")
    colonnes_execution = {r["name"] for r in conn.execute("PRAGMA table_info(execution)")}
    colonnes_run = {r["name"] for r in conn.execute("PRAGMA table_info(test_run)")}
    assert "confiance" in colonnes_execution and "strict" in colonnes_run
    sql = conn.execute("SELECT sql FROM sqlite_master WHERE name='execution'").fetchone()[0]
    assert "'apres_retry'" in sql
    conn.close()


def test_reprise_une_base_pre_49_recoit_les_colonnes_sans_perdre_ses_donnees(tmp_path):
    """⚠️ LA GARDE : les lignes d'avant le lot restent, valent `nominale` / 0 — et la nouvelle valeur passe ensuite."""
    conn = _base_pre_49(tmp_path / "vieille.db")

    _migrate_49_confiance_et_strict(conn)

    assert conn.execute("SELECT confiance FROM execution WHERE id=10").fetchone()[0] == "nominale"
    assert conn.execute("SELECT strict FROM test_run WHERE id=1").fetchone()[0] == 0
    conn.execute("INSERT INTO execution (id, confiance) VALUES (11, 'auto_resolue')")
    conn.execute("INSERT INTO execution (id, confiance) VALUES (12, 'apres_retry')")
    conn.execute("INSERT INTO test_run (id, name, strict) VALUES (2, 'Stricte', 1)")
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM execution").fetchone()[0] == 3
    conn.close()


def test_les_CHECK_refusent_une_valeur_inconnue(tmp_path):
    conn = _base_pre_49(tmp_path / "vieille.db")
    _migrate_49_confiance_et_strict(conn)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO execution (id, confiance) VALUES (20, 'presque_sur')")
    conn.rollback()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO test_run (id, name, strict) VALUES (3, 'x', 2)")
    conn.close()


def test_la_migration_est_idempotente(tmp_path):
    conn = _base_pre_49(tmp_path / "vieille.db")

    _migrate_49_confiance_et_strict(conn)
    _migrate_49_confiance_et_strict(conn)

    assert conn.execute("SELECT confiance FROM execution WHERE id=10").fetchone()[0] == "nominale"
    conn.close()
