"""Migration 19 — la base accepte le 4ᵉ verdict `donnee_invalide` (§2bis).

⚠️ **Le défaut, trouvé par le RÉEL** (re-rejeu 2026-07-23). Le 4ᵉ verdict était branché partout en
Python, mais les CHECK de la base n'acceptaient pas la valeur → un cas correctement jugé
`donnee_invalide` PLANTAIT à la persistance (`IntegrityError`) et retombait en `technical_error`.
Mes tests de statut exerçaient la DÉRIVATION, jamais la PERSISTANCE (§8.8, encore).

La garde centrale est un test de REPRISE : on fabrique une base à l'ANCIEN schéma (CHECK strict) +
des données avec FK, on la migre, et on vérifie que la nouvelle valeur passe — sur les trois
tables, sans perte de données ni FK cassée. Il ÉCHOUERAIT sur une base non migrée.
"""

from __future__ import annotations

import sqlite3

import pytest

from testpilot.store.db import _migrate_19_verdict_donnee_invalide, get_initialized_db

# Schéma AVANT migration 19 : le CHECK strict, avec les FK entrantes qui rendent la reconstruction
# non triviale (c'est justement ce que la migration doit gérer).
_SCHEMA_PRE_19 = """
CREATE TABLE test_case (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    last_functional_status TEXT CHECK (last_functional_status IN ('conforme', 'non_conforme', 'indetermine', 'not_evaluated'))
);
CREATE TABLE execution (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_case_id INTEGER NOT NULL,
    functional_status TEXT NOT NULL DEFAULT 'not_evaluated'
        CHECK (functional_status IN ('conforme', 'non_conforme', 'indetermine', 'not_evaluated')),
    FOREIGN KEY (test_case_id) REFERENCES test_case(id)
);
CREATE TABLE scenario_result (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id INTEGER NOT NULL,
    scenario_name TEXT NOT NULL,
    functional_status TEXT NOT NULL
        CHECK (functional_status IN ('conforme', 'non_conforme', 'indetermine')),
    FOREIGN KEY (execution_id) REFERENCES execution(id)
);
CREATE INDEX idx_scenario_execution ON scenario_result(execution_id);
"""


def _base_pre_19(path):
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA_PRE_19)
    conn.execute("INSERT INTO test_case (id, title, last_functional_status) VALUES (1, 'Cas', 'conforme')")
    conn.execute("INSERT INTO execution (id, test_case_id, functional_status) VALUES (10, 1, 'non_conforme')")
    conn.execute("INSERT INTO scenario_result (id, execution_id, scenario_name, functional_status)"
                 " VALUES (100, 10, 's', 'conforme')")
    conn.commit()
    return conn


def test_base_neuve_porte_la_valeur_dans_les_trois_CHECK(tmp_path):
    """Une base fraîche (schema.sql à jour) doit enregistrer la valeur dans les CHECK des trois
    tables — sinon une base neuve replanterait comme la base migrée."""
    conn = get_initialized_db(tmp_path / "neuve.db")
    for tbl in ("execution", "scenario_result", "test_case"):
        sql = conn.execute("SELECT sql FROM sqlite_master WHERE name=?", (tbl,)).fetchone()[0]
        assert "donnee_invalide" in sql, f"{tbl} : schema.sql doit inclure la valeur"
    conn.close()


def test_reprise_une_base_pre_19_accepte_ensuite_donnee_invalide(tmp_path):
    """⚠️ LA GARDE. Base à l'ancien schéma → migration → la nouvelle valeur passe sur LES TROIS
    tables. Échouerait (IntegrityError) sans la migration."""
    path = tmp_path / "vieille.db"
    conn = _base_pre_19(path)

    # Avant migration : la valeur est REFUSÉE (preuve que le CHECK mordait vraiment).
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO scenario_result (execution_id, scenario_name, functional_status)"
                     " VALUES (10, 's2', 'donnee_invalide')")
    conn.rollback()

    _migrate_19_verdict_donnee_invalide(conn)

    # Après migration : les trois tables acceptent la valeur.
    conn.execute("INSERT INTO scenario_result (execution_id, scenario_name, functional_status)"
                 " VALUES (10, 's2', 'donnee_invalide')")
    conn.execute("INSERT INTO execution (test_case_id, functional_status) VALUES (1, 'donnee_invalide')")
    conn.execute("UPDATE test_case SET last_functional_status = 'donnee_invalide' WHERE id = 1")
    conn.commit()

    # Données préexistantes préservées, index recréé, aucune FK cassée.
    assert conn.execute("SELECT functional_status FROM scenario_result WHERE id=100").fetchone()[0] == "conforme"
    assert conn.execute("SELECT functional_status FROM execution WHERE id=10").fetchone()[0] == "non_conforme"
    idx = conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_scenario_execution'").fetchone()
    assert idx is not None, "l'index doit être recréé après la reconstruction"
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    conn.close()


def test_migration_19_est_idempotente(tmp_path):
    """Rejouée sur une base déjà migrée, elle ne fait rien (et ne casse rien)."""
    path = tmp_path / "idem.db"
    conn = _base_pre_19(path)
    _migrate_19_verdict_donnee_invalide(conn)
    _migrate_19_verdict_donnee_invalide(conn)  # 2ᵉ passage : no-op
    conn.execute("INSERT INTO scenario_result (execution_id, scenario_name, functional_status)"
                 " VALUES (10, 's3', 'donnee_invalide')")
    conn.commit()
    conn.close()
