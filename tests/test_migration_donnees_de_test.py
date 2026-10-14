"""Migration 64 (paramètres de test, lot PT-02) — les données de test : `test_variable`, `test_dataset`, `test_dataset_value`,
et les colonnes qui figent ce qui est joué (`test_run.dataset_id`, `test_run.parametres_figes`, `execution.parametres_joues`).

Les quatre pièces d'une évolution de schéma (CLAUDE.md §6) : migration SQLite idempotente, révision Alembic chaînée sur la tête
précédente, `schema_sa` aligné, et ce test. Tout est vide par défaut : rien ne change pour un projet existant.
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import pytest

from testpilot.store import db, portable_connection, schema_sa
from testpilot.store.db import _migrate_64_donnees_de_test, get_initialized_db
from testpilot.store.repositories import ProjectRepo, TestDataRepo

RACINE = Path(__file__).resolve().parent.parent
TABLES = ("test_variable", "test_dataset", "test_dataset_value")


def test_une_base_neuve_porte_les_tables_et_les_colonnes_vides_par_defaut(tmp_path):
    conn = get_initialized_db(tmp_path / "neuve.db")
    pid = ProjectRepo(conn).create(name="P", connector_type="web", base_url="http://app")

    assert db._SCHEMA_VERSION >= 64
    assert TestDataRepo(conn).tableau(pid) == {"variables": [], "jeux": [], "valeurs": {}}
    colonnes_run = {r["name"]: r for r in conn.execute("PRAGMA table_info(test_run)")}
    colonnes_exec = {r["name"]: r for r in conn.execute("PRAGMA table_info(execution)")}
    assert colonnes_run["dataset_id"]["notnull"] == 0 and colonnes_run["parametres_figes"]["dflt_value"] == "''"
    assert colonnes_exec["parametres_joues"]["dflt_value"] == "''"
    conn.close()


def test_falsifiable_supprimer_le_projet_emporte_ses_donnees_de_test(tmp_path):
    conn = get_initialized_db(tmp_path / "neuve.db")
    pid = ProjectRepo(conn).create(name="P", connector_type="web", base_url="http://app")
    depot = TestDataRepo(conn)
    vid = depot.creer_variable(pid, nom="ville")
    depot.poser_valeurs(pid, depot.jeux(pid)[0]["id"], {vid: "Lyon"})

    conn.execute("DELETE FROM project WHERE id=?", (pid,))
    conn.commit()

    for table in TABLES:
        assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table
    conn.close()


def test_falsifiable_l_unicite_d_un_nom_ne_vaut_que_pour_les_vivants(tmp_path):
    """Un nom à la corbeille est réutilisable (leçon de la migration 24) ; deux vivants du même nom sont refusés par la BASE."""
    conn = get_initialized_db(tmp_path / "neuve.db")
    pid = ProjectRepo(conn).create(name="P", connector_type="web", base_url="http://app")
    depot = TestDataRepo(conn)
    premiere = depot.creer_variable(pid, nom="ville")
    depot.supprimer_variable(pid, premiere, par="admin")
    depot.creer_variable(pid, nom="ville")

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE test_variable SET deleted_at='' WHERE id=?", (premiere,))
    conn.rollback()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE test_dataset SET est_defaut=2")
    conn.close()


def test_falsifiable_reprise_d_une_base_pre_64(tmp_path):
    base = sqlite3.connect(str(tmp_path / "vieille.db"))
    base.row_factory = sqlite3.Row
    base.execute("CREATE TABLE project (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
    base.execute("CREATE TABLE test_run (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
    base.execute("CREATE TABLE execution (id INTEGER PRIMARY KEY)")
    base.execute("INSERT INTO test_run (id, name) VALUES (1, 'ancienne campagne')")
    base.execute("INSERT INTO execution (id) VALUES (1)")
    base.commit()

    _migrate_64_donnees_de_test(base)
    _migrate_64_donnees_de_test(base)  # idempotente

    run = base.execute("SELECT dataset_id, parametres_figes FROM test_run WHERE id=1").fetchone()
    assert (run["dataset_id"], run["parametres_figes"]) == (None, ""), "une campagne existante n'a aucune donnée de test"
    assert base.execute("SELECT parametres_joues FROM execution WHERE id=1").fetchone()[0] == ""
    for table in TABLES:
        assert base.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    base.close()


def test_la_revision_alembic_est_chainee_sur_la_tete_precedente():
    chemin = RACINE / "alembic" / "versions" / "a4d9e2b7c318_donnees_de_test.py"
    spec = importlib.util.spec_from_file_location("revision_64", chemin)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)

    assert (revision.revision, revision.down_revision) == ("a4d9e2b7c318", "f3a8d1c6b257")
    autres = [p.name for p in chemin.parent.glob("*.py")
              if p != chemin and 'down_revision = "f3a8d1c6b257"' in p.read_text(encoding="utf-8")]
    assert autres == [], "une seule révision descend de f3a8d1c6b257"


def test_le_schema_portable_est_aligne():
    assert schema_sa.ALIGNED_WITH_SCHEMA_VERSION == db._SCHEMA_VERSION
    tables = schema_sa.metadata.tables
    for nom in ("test_variable", "test_dataset"):
        assert tables[nom].c["project_id"].nullable, "NULL = bibliothèque commune (lot PT-05)"
        assert not tables[nom].c["deleted_at"].nullable and str(tables[nom].c["deleted_at"].server_default.arg) == ""
        assert nom in portable_connection._TABLES_AVEC_ID, "le dépôt lit `.lastrowid` : PostgreSQL doit le rendre"
    assert tables["test_run"].c["dataset_id"].nullable and str(tables["test_run"].c["parametres_figes"].server_default.arg) == ""
    assert str(tables["execution"].c["parametres_joues"].server_default.arg) == ""
    assert {c.name for c in tables["test_dataset_value"].primary_key.columns} == {"dataset_id", "variable_id"}
