"""Migration 66 (paramètres de test, lot PT-02b, A28) — `scheduled_run.dataset_ids`.

Les quatre pièces d'une évolution de schéma (CLAUDE.md §6) : migration SQLite idempotente, révision Alembic chaînée sur la tête
précédente, `schema_sa` aligné, et ce test. Vide par défaut : une planification existante joue comme avant.
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

from testpilot.store import db, portable_connection, schema_sa
from testpilot.store.db import _migrate_66_planification_jeux, get_initialized_db

RACINE = Path(__file__).resolve().parent.parent


def test_une_base_neuve_porte_la_colonne_vide_par_defaut(tmp_path):
    conn = get_initialized_db(tmp_path / "neuve.db")
    colonne = {r["name"]: r for r in conn.execute("PRAGMA table_info(scheduled_run)")}["dataset_ids"]

    assert db._SCHEMA_VERSION >= 66
    assert (colonne["notnull"], colonne["dflt_value"]) == (1, "''")
    conn.close()


def test_falsifiable_reprise_d_une_base_pre_66(tmp_path):
    base = sqlite3.connect(str(tmp_path / "vieille.db"))
    base.row_factory = sqlite3.Row
    base.execute("CREATE TABLE scheduled_run (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
    base.execute("INSERT INTO scheduled_run (id, name) VALUES (1, 'Nocturne')")
    base.commit()

    _migrate_66_planification_jeux(base)
    _migrate_66_planification_jeux(base)  # idempotente

    assert base.execute("SELECT dataset_ids FROM scheduled_run WHERE id=1").fetchone()[0] == "", \
        "une planification existante joue comme avant"
    base.close()


def test_la_revision_alembic_est_chainee_sur_la_tete_precedente():
    chemin = RACINE / "alembic" / "versions" / "c7a2e9d4f610_planification_jeux.py"
    spec = importlib.util.spec_from_file_location("revision_66", chemin)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)

    assert (revision.revision, revision.down_revision) == ("c7a2e9d4f610", "b5e1f3c8d429")
    assert portable_connection.ALEMBIC_HEAD  # la tête courante est vérifiée par le test de la dernière migration
    autres = [p.name for p in chemin.parent.glob("*.py")
              if p != chemin and 'down_revision = "b5e1f3c8d429"' in p.read_text(encoding="utf-8")]
    assert autres == [], "une seule révision descend de b5e1f3c8d429"


def test_le_schema_portable_est_aligne():
    assert schema_sa.ALIGNED_WITH_SCHEMA_VERSION == db._SCHEMA_VERSION
    colonne = schema_sa.metadata.tables["scheduled_run"].c["dataset_ids"]
    assert not colonne.nullable and str(colonne.server_default.arg) == ""
