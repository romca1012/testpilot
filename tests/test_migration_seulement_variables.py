"""Migration 65 (paramètres de test, lot PT-02b, décision A35) — `test_run.seulement_variables`.

Les quatre pièces d'une évolution de schéma (CLAUDE.md §6) : migration SQLite idempotente, révision Alembic chaînée sur la tête
précédente, `schema_sa` aligné, et ce test. 0 par défaut : une exécution existante joue tous ses tests, comme avant.
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import pytest

from testpilot.store import db, portable_connection, schema_sa
from testpilot.store.db import _migrate_65_seulement_variables, get_initialized_db

RACINE = Path(__file__).resolve().parent.parent


def test_une_base_neuve_porte_la_colonne_a_zero_et_refuse_une_autre_valeur(tmp_path):
    conn = get_initialized_db(tmp_path / "neuve.db")
    colonne = {r["name"]: r for r in conn.execute("PRAGMA table_info(test_run)")}["seulement_variables"]

    assert db._SCHEMA_VERSION >= 65
    assert (colonne["notnull"], colonne["dflt_value"]) == (1, "0")
    conn.execute("INSERT INTO project (name, connector_type, base_url, created_at) VALUES ('P', 'web', 'http://a', 'x')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO test_run (project_id, name, created_at, seulement_variables) VALUES (1, 'R', 'x', 2)")
    conn.close()


def test_falsifiable_reprise_d_une_base_pre_65(tmp_path):
    base = sqlite3.connect(str(tmp_path / "vieille.db"))
    base.row_factory = sqlite3.Row
    base.execute("CREATE TABLE test_run (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
    base.execute("INSERT INTO test_run (id, name) VALUES (1, 'ancienne campagne')")
    base.commit()

    _migrate_65_seulement_variables(base)
    _migrate_65_seulement_variables(base)  # idempotente

    assert base.execute("SELECT seulement_variables FROM test_run WHERE id=1").fetchone()[0] == 0, \
        "une exécution existante joue tous ses tests"
    base.close()


def test_la_revision_alembic_est_chainee_sur_la_tete_precedente():
    chemin = RACINE / "alembic" / "versions" / "b5e1f3c8d429_seulement_variables.py"
    spec = importlib.util.spec_from_file_location("revision_65", chemin)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)

    assert (revision.revision, revision.down_revision) == ("b5e1f3c8d429", "a4d9e2b7c318")
    assert portable_connection.ALEMBIC_HEAD  # la tête courante est vérifiée par le test de la dernière migration
    autres = [p.name for p in chemin.parent.glob("*.py")
              if p != chemin and 'down_revision = "a4d9e2b7c318"' in p.read_text(encoding="utf-8")]
    assert autres == [], "une seule révision descend de a4d9e2b7c318"


def test_le_schema_portable_est_aligne():
    assert schema_sa.ALIGNED_WITH_SCHEMA_VERSION == db._SCHEMA_VERSION
    run = schema_sa.metadata.tables["test_run"]
    assert not run.c["seulement_variables"].nullable and str(run.c["seulement_variables"].server_default.arg) == "0"
    assert "ck_test_run_seulement_variables" in {c.name for c in run.constraints}
