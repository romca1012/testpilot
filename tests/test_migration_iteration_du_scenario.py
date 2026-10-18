"""Migration 71 (décision A52, porteur, 2026-10-16) — `scenario_result.iterations` : le résultat de chaque itération.

Les quatre pièces d'une évolution de schéma (CLAUDE.md §6) : migration SQLite, révision Alembic chaînée sur la tête précédente,
`schema_sa` aligné, et ce test. Additive : un résultat d'avant couvre toutes les itérations (vide).
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

from testpilot.store import db, portable_connection, schema_sa
from testpilot.store.db import _migrate_71_iteration_du_scenario, get_initialized_db
from testpilot.store.repositories import ExecutionRepo

RACINE = Path(__file__).resolve().parent.parent


def test_une_base_neuve_a_la_colonne_et_l_enregistre(tmp_path):
    conn = get_initialized_db(tmp_path / "neuve.db")
    colonnes = {r["name"] for r in conn.execute("PRAGMA table_info(scenario_result)")}
    conn.execute("PRAGMA foreign_keys=OFF")   # seule la colonne est éprouvée ici, pas l'exécution qui la porte
    rid = ExecutionRepo(conn).add_scenario_result(execution_id=1, scenario_name="S -- @2.1 B", execution_status="success",
                                                  functional_status="conforme", iterations="1,3")
    lue = conn.execute("SELECT iterations FROM scenario_result WHERE id=?", (rid,)).fetchone()[0]
    conn.close()
    assert db._SCHEMA_VERSION >= 71 and "iterations" in colonnes and lue == "1,3"


def test_la_migration_71_est_idempotente_et_ne_change_rien_d_existant(tmp_path):
    base = sqlite3.connect(str(tmp_path / "vieille.db"))
    base.row_factory = sqlite3.Row
    base.execute("CREATE TABLE scenario_result (id INTEGER PRIMARY KEY, scenario_name TEXT)")
    base.execute("INSERT INTO scenario_result VALUES (1, 'S')")

    _migrate_71_iteration_du_scenario(base)
    _migrate_71_iteration_du_scenario(base)

    assert dict(base.execute("SELECT scenario_name, iterations FROM scenario_result").fetchone()) == {
        "scenario_name": "S", "iterations": ""}
    base.close()


def test_la_revision_alembic_est_chainee_sur_la_tete_precedente():
    chemin = RACINE / "alembic" / "versions" / "b3e7c9d1f405_iteration_du_scenario.py"
    spec = importlib.util.spec_from_file_location("revision_71", chemin)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)

    assert (revision.revision, revision.down_revision) == ("b3e7c9d1f405", "a8d3f5c1e264")
    assert portable_connection.ALEMBIC_HEAD == "b3e7c9d1f405"
    autres = [p.name for p in chemin.parent.glob("*.py")
              if p != chemin and 'down_revision = "a8d3f5c1e264"' in p.read_text(encoding="utf-8")]
    assert autres == []


def test_le_schema_portable_est_aligne():
    assert schema_sa.ALIGNED_WITH_SCHEMA_VERSION == db._SCHEMA_VERSION
    assert "iterations" in schema_sa.metadata.tables["scenario_result"].c
