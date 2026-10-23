"""Migration 78 (étape 7b, A109) — les parcours d'un cas enregistrés, et le cas d'une session d'enregistrement.

Les quatre pièces d'une évolution de schéma (CLAUDE.md §6) : migration SQLite, révision Alembic chaînée sur la tête précédente,
`schema_sa` aligné, et ce test. Additive : un jeton d'avant n'a pas de cas (enregistrement de la connexion).
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

from testpilot.store import db, portable_connection, schema_sa
from testpilot.store.db import _migrate_78_parcours_enregistres, get_initialized_db

RACINE = Path(__file__).resolve().parent.parent


def test_une_base_neuve_a_la_table_et_la_colonne(tmp_path):
    conn = get_initialized_db(tmp_path / "neuve.db")
    colonnes = {r["name"] for r in conn.execute("PRAGMA table_info(parcours_enregistre)")}
    assert {"project_id", "case_id", "version_id", "actions", "auteur", "created_at"} <= colonnes
    assert "case_id" in {r["name"] for r in conn.execute("PRAGMA table_info(live_session_token)")}
    assert db._SCHEMA_VERSION >= 78
    conn.close()


def test_la_migration_78_est_idempotente_et_garde_les_jetons_d_avant(tmp_path):
    base = sqlite3.connect(str(tmp_path / "vieille.db"))
    base.row_factory = sqlite3.Row
    base.execute("CREATE TABLE live_session_token (id INTEGER PRIMARY KEY, token_hash TEXT)")
    base.execute("INSERT INTO live_session_token VALUES (1, 'h')")

    _migrate_78_parcours_enregistres(base)
    _migrate_78_parcours_enregistres(base)

    assert base.execute("SELECT case_id FROM live_session_token").fetchone()[0] is None
    assert base.execute("SELECT COUNT(*) FROM parcours_enregistre").fetchone()[0] == 0
    base.close()


def test_schema_sa_porte_la_table_et_la_colonne():
    assert "parcours_enregistre" in schema_sa.metadata.tables
    assert schema_sa.metadata.tables["live_session_token"].c.case_id.nullable
    assert schema_sa.ALIGNED_WITH_SCHEMA_VERSION == db._SCHEMA_VERSION


def test_la_revision_alembic_est_chainee_sur_la_tete_precedente():
    chemin = RACINE / "alembic" / "versions" / "c3f7a9d2e481_parcours_enregistres.py"
    spec = importlib.util.spec_from_file_location("revision_78", chemin)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)

    assert (revision.revision, revision.down_revision) == ("c3f7a9d2e481", "b8e2f4a6c193")
    assert portable_connection.ALEMBIC_HEAD == "c3f7a9d2e481"
