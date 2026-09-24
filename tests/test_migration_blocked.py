"""Migration 48 — l'axe exécution accepte `blocked` (lot 02, D1).

Même garde que `test_migration_donnee_invalide.py` (migration 19), pour la même raison : une valeur
branchée dans toute la couche Python mais refusée par les CHECK de la base fait PLANTER la persistance
d'un cas correctement jugé — qui retombe alors en `technical_error`, le statut qu'on veut justement
ne plus produire.

La garde centrale est un test de REPRISE : une base à l'ANCIEN schéma (CHECK strict) avec des données
et des FK est migrée ; la nouvelle valeur passe ensuite sur les TROIS tables, sans perte de données.
Il ÉCHOUERAIT (`IntegrityError`) sur une base non migrée.
"""

from __future__ import annotations

import sqlite3

import pytest

from testpilot.store.db import _migrate_48_execution_blocked, get_initialized_db

# Schéma AVANT la migration 48 : CHECK strict, FK entrantes, index — tout ce que la reconstruction
# d'une table SQLite doit préserver.
_SCHEMA_PRE_48 = """
CREATE TABLE test_case (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    last_execution_status TEXT CHECK (last_execution_status IN ('success', 'technical_error', 'not_executed'))
);
CREATE TABLE execution (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_case_id INTEGER NOT NULL,
    execution_status TEXT NOT NULL DEFAULT 'not_executed'
        CHECK (execution_status IN ('success', 'technical_error', 'not_executed')),
    FOREIGN KEY (test_case_id) REFERENCES test_case(id)
);
CREATE TABLE scenario_result (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id INTEGER NOT NULL,
    scenario_name TEXT NOT NULL,
    execution_status TEXT NOT NULL
        CHECK (execution_status IN ('success', 'technical_error')),
    FOREIGN KEY (execution_id) REFERENCES execution(id)
);
CREATE INDEX idx_scenario_execution ON scenario_result(execution_id);
"""


def _base_pre_48(chemin):
    conn = sqlite3.connect(str(chemin))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA_PRE_48)
    conn.execute("INSERT INTO test_case (id, title, last_execution_status) VALUES (1, 'Cas', 'success')")
    conn.execute("INSERT INTO execution (id, test_case_id, execution_status) VALUES (10, 1, 'technical_error')")
    conn.execute("INSERT INTO scenario_result (id, execution_id, scenario_name, execution_status)"
                 " VALUES (100, 10, 's', 'success')")
    conn.commit()
    return conn


def test_base_neuve_porte_la_valeur_dans_les_trois_CHECK(tmp_path, monkeypatch):
    from testpilot import config

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    conn = get_initialized_db(tmp_path / "neuve.db")
    for table in ("execution", "scenario_result", "test_case"):
        sql = conn.execute("SELECT sql FROM sqlite_master WHERE name=?", (table,)).fetchone()[0]
        assert "'blocked'" in sql, f"{table} : schema.sql doit inclure la valeur"
    conn.close()


def test_reprise_une_base_pre_48_accepte_ensuite_blocked(tmp_path):
    """⚠️ LA GARDE. Avant migration `blocked` est REFUSÉ (le CHECK mord vraiment) ; après, les trois
    tables l'acceptent, les données préexistantes et l'index sont préservés."""
    conn = _base_pre_48(tmp_path / "vieille.db")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO scenario_result (execution_id, scenario_name, execution_status)"
                     " VALUES (10, 's2', 'blocked')")
    conn.rollback()

    _migrate_48_execution_blocked(conn)

    conn.execute("INSERT INTO scenario_result (execution_id, scenario_name, execution_status)"
                 " VALUES (10, 's2', 'blocked')")
    conn.execute("INSERT INTO execution (test_case_id, execution_status) VALUES (1, 'blocked')")
    conn.execute("UPDATE test_case SET last_execution_status = 'blocked' WHERE id = 1")
    conn.commit()

    assert conn.execute("SELECT execution_status FROM scenario_result WHERE id=100").fetchone()[0] == "success"
    assert conn.execute("SELECT execution_status FROM execution WHERE id=10").fetchone()[0] == "technical_error"
    index = conn.execute("SELECT name FROM sqlite_master WHERE type='index' "
                         "AND name='idx_scenario_execution'").fetchone()
    assert index is not None, "l'index doit être recréé après la reconstruction"
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    conn.close()


def test_les_anciennes_valeurs_restent_valides_et_les_inconnues_refusees(tmp_path):
    conn = _base_pre_48(tmp_path / "vieille2.db")
    _migrate_48_execution_blocked(conn)

    for valeur in ("success", "technical_error", "not_executed"):
        conn.execute("INSERT INTO execution (test_case_id, execution_status) VALUES (1, ?)", (valeur,))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO execution (test_case_id, execution_status) VALUES (1, 'bidon')")
    conn.rollback()
    conn.close()


def test_migration_48_est_idempotente(tmp_path):
    conn = _base_pre_48(tmp_path / "idem.db")
    _migrate_48_execution_blocked(conn)
    _migrate_48_execution_blocked(conn)  # 2ᵉ passage : no-op

    conn.execute("INSERT INTO scenario_result (execution_id, scenario_name, execution_status)"
                 " VALUES (10, 's3', 'blocked')")
    conn.commit()
    conn.close()


def test_la_migration_ne_touche_pas_une_table_dont_la_liste_est_inconnue(tmp_path):
    """Liste non reconnue → sautée, jamais cassée en silence."""
    conn = sqlite3.connect(str(tmp_path / "inconnue.db"))
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE execution (id INTEGER PRIMARY KEY, "
                 "execution_status TEXT CHECK (execution_status IN ('a', 'b')))")
    conn.commit()

    _migrate_48_execution_blocked(conn)

    sql = conn.execute("SELECT sql FROM sqlite_master WHERE name='execution'").fetchone()[0]
    assert "'blocked'" not in sql and "'a', 'b'" in sql
    conn.close()


def _base_pre_48_tables_renommees(chemin):
    """Une VRAIE base : chaque table a été reconstruite par `ALTER TABLE … RENAME` (comme le fait la
    migration 19), donc SQLite l'écrit `CREATE TABLE "execution"` — avec guillemets."""
    conn = sqlite3.connect(str(chemin))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA_PRE_48)
    conn.execute("INSERT INTO test_case (id, title, last_execution_status) VALUES (1, 'Cas', 'success')")
    conn.execute("INSERT INTO execution (id, test_case_id, execution_status) VALUES (10, 1, 'technical_error')")
    conn.execute("INSERT INTO scenario_result (id, execution_id, scenario_name, execution_status)"
                 " VALUES (100, 10, 's', 'success')")
    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")
    for table in ("scenario_result", "execution", "test_case"):
        sql = conn.execute("SELECT sql FROM sqlite_master WHERE name=?", (table,)).fetchone()[0]
        # Même procédé que la migration 19 : on renomme la NOUVELLE table sur l'ancien nom (renommer
        # l'ancienne réécrirait les FK des autres tables vers le nom temporaire).
        conn.execute(sql.replace(f"CREATE TABLE {table}", f"CREATE TABLE {table}__nouvelle", 1))
        conn.execute(f"INSERT INTO {table}__nouvelle SELECT * FROM {table}")
        conn.execute(f"DROP TABLE {table}")
        conn.execute(f"ALTER TABLE {table}__nouvelle RENAME TO {table}")
    conn.commit()
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def test_reprise_sur_une_base_dont_les_tables_sont_entre_guillemets(tmp_path):
    """⚠️ Le défaut mesuré le 2026-09-24 en rejouant sur la COPIE d'une vraie base (user_version 47) :
    `table "execution" already exists`. Les bases neuves des autres tests ne le voyaient pas."""
    conn = _base_pre_48_tables_renommees(tmp_path / "reelle.db")
    for table in ("execution", "scenario_result", "test_case"):
        sql = conn.execute("SELECT sql FROM sqlite_master WHERE name=?", (table,)).fetchone()[0]
        assert f'CREATE TABLE "{table}"' in sql, "le scénario doit reproduire les guillemets de SQLite"

    _migrate_48_execution_blocked(conn)

    conn.execute("INSERT INTO scenario_result (execution_id, scenario_name, execution_status)"
                 " VALUES (10, 's2', 'blocked')")
    conn.execute("INSERT INTO execution (test_case_id, execution_status) VALUES (1, 'blocked')")
    conn.execute("UPDATE test_case SET last_execution_status = 'blocked' WHERE id = 1")
    conn.commit()
    assert conn.execute("SELECT execution_status FROM scenario_result WHERE id=100").fetchone()[0] == "success"
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    conn.close()


def test_une_violation_de_cle_etrangere_preexistante_ne_bloque_pas_la_migration(tmp_path):
    """Mesuré le 2026-09-24 sur la copie d'une vraie base : `project_member` pointait vers un
    utilisateur supprimé. La migration ne doit réagir qu'aux violations qu'ELLE introduirait — sinon un
    défaut ancien et sans rapport ferait échouer le démarrage."""
    conn = _base_pre_48(tmp_path / "orpheline.db")
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("INSERT INTO execution (id, test_case_id, execution_status) VALUES (99, 4242, 'success')")
    conn.commit()
    assert conn.execute("PRAGMA foreign_key_check").fetchall(), "la base de départ a bien une violation"

    _migrate_48_execution_blocked(conn)  # ne lève pas

    conn.execute("INSERT INTO execution (test_case_id, execution_status) VALUES (1, 'blocked')")
    conn.commit()
    assert conn.execute("SELECT count(*) FROM execution WHERE id=99").fetchone()[0] == 1, (
        "la ligne orpheline est conservée telle quelle, jamais supprimée en silence")
    conn.close()
