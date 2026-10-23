"""Migration 75 (étape 6 du plan unique : IT-4, IT-3d) — d'où une colonne tire ses valeurs dans l'application, et l'empreinte du
texte d'un cas quand ses lignes ont été enregistrées.

Les quatre pièces d'une évolution de schéma (CLAUDE.md §6) : migration SQLite, révision Alembic chaînée sur la tête précédente,
`schema_sa` aligné, et ce test. Additive : vide par défaut, rien ne change pour une variable ou un cas d'avant.
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

from testpilot.store import db, portable_connection, schema_sa
from testpilot.store.db import _migrate_75_donnees_depuis_l_application, get_initialized_db

RACINE = Path(__file__).resolve().parent.parent


def test_une_base_neuve_a_les_deux_colonnes_vides_par_defaut(tmp_path):
    conn = get_initialized_db(tmp_path / "neuve.db")
    variable = {r["name"]: r for r in conn.execute("PRAGMA table_info(test_variable)")}
    cas = {r["name"]: r for r in conn.execute("PRAGMA table_info(test_case)")}
    assert db._SCHEMA_VERSION >= 75
    assert variable["source_application"]["notnull"] == 1 and cas["lignes_ecrites_pour"]["notnull"] == 1
    conn.close()


def test_la_migration_75_est_idempotente_et_garde_les_lignes_d_avant(tmp_path):
    base = sqlite3.connect(str(tmp_path / "vieille.db"))
    base.row_factory = sqlite3.Row
    base.execute("CREATE TABLE test_variable (id INTEGER PRIMARY KEY, project_id INTEGER, nom TEXT)")
    base.execute("CREATE TABLE test_case (id INTEGER PRIMARY KEY, title TEXT)")
    base.execute("INSERT INTO test_variable VALUES (1, 1, 'client')")
    base.execute("INSERT INTO test_case VALUES (7, 'Cas')")

    _migrate_75_donnees_depuis_l_application(base)
    _migrate_75_donnees_depuis_l_application(base)

    assert base.execute("SELECT source_application FROM test_variable").fetchone()[0] == ""
    assert base.execute("SELECT lignes_ecrites_pour FROM test_case").fetchone()[0] == ""
    base.close()


def test_schema_sa_porte_les_colonnes():
    assert not schema_sa.metadata.tables["test_variable"].c.source_application.nullable
    assert not schema_sa.metadata.tables["test_case"].c.lignes_ecrites_pour.nullable
    assert schema_sa.ALIGNED_WITH_SCHEMA_VERSION == db._SCHEMA_VERSION


def test_la_revision_alembic_est_chainee_sur_la_tete_precedente():
    chemin = RACINE / "alembic" / "versions" / "f4c9a2d7e185_donnees_depuis_l_application.py"
    spec = importlib.util.spec_from_file_location("revision_75", chemin)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)

    assert (revision.revision, revision.down_revision) == ("f4c9a2d7e185", "e8a4c2f6b913")
    assert portable_connection.ALEMBIC_HEAD != "f4c9a2d7e185"   # avancée depuis (migration 76, A107)
