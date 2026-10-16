"""Migration 68 (décision A45, porteur, 2026-10-16) — `project.instance_de_test`, et la migration 67 amendée.

Les quatre pièces d'une évolution de schéma (CLAUDE.md §6) : migration SQLite, révision Alembic chaînée sur la tête précédente,
`schema_sa` aligné, et ce test. La colonne est éteinte par défaut : rien ne déclare un projet instance de test à sa place.
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

from testpilot.store import db, portable_connection, schema_sa
from testpilot.store.db import _migrate_67_ia_peut_agir_par_defaut, _migrate_68_instance_de_test, get_initialized_db
from testpilot.store.repositories import ProjectRepo

RACINE = Path(__file__).resolve().parent.parent


def test_une_base_neuve_ne_declare_aucun_projet_instance_de_test(tmp_path):
    conn = get_initialized_db(tmp_path / "neuve.db")
    pid = ProjectRepo(conn).create(name="Neuf", connector_type="odoo", base_url="https://odoo.test")

    assert db._SCHEMA_VERSION >= 68
    assert bool(ProjectRepo(conn).get(pid)["instance_de_test"]) is False
    ProjectRepo(conn).set_instance_de_test(pid, True)
    assert bool(ProjectRepo(conn).get(pid)["instance_de_test"]) is True
    ProjectRepo(conn).set_instance_de_test(pid, False)
    assert bool(ProjectRepo(conn).get(pid)["instance_de_test"]) is False
    conn.close()


def test_la_migration_68_est_idempotente_et_n_allume_rien(tmp_path):
    base = sqlite3.connect(str(tmp_path / "vieille.db"))
    base.row_factory = sqlite3.Row
    base.execute("CREATE TABLE project (id INTEGER PRIMARY KEY, name TEXT)")
    base.execute("INSERT INTO project (id, name) VALUES (1, 'Ancien')")

    _migrate_68_instance_de_test(base)
    _migrate_68_instance_de_test(base)

    assert [r[0] for r in base.execute("SELECT instance_de_test FROM project")] == [0]
    base.close()


def test_falsifiable_la_migration_67_ne_recoche_pas_un_refus_delibere(tmp_path):
    """Revue d'A43 : un projet web qui avait déclaré une remise à zéro ET laissé la case décochée a refusé l'autorisation
    en connaissance de cause. Les autres projets décochés (jamais réglés) sont cochés."""
    base = sqlite3.connect(str(tmp_path / "vieille.db"))
    base.row_factory = sqlite3.Row
    base.execute("CREATE TABLE project (id INTEGER PRIMARY KEY, calibration_writes_enabled INTEGER NOT NULL DEFAULT 0,"
                 " bac_a_sable_reset TEXT NOT NULL DEFAULT '')")
    base.execute("INSERT INTO project VALUES (1, 0, ''), (2, 0, 'https://a.test/reset'), (3, 1, 'https://b.test/reset')")

    _migrate_67_ia_peut_agir_par_defaut(base)

    assert [r[0] for r in base.execute("SELECT calibration_writes_enabled FROM project ORDER BY id")] == [1, 0, 1]
    base.close()


def test_la_revision_alembic_est_chainee_sur_la_tete_precedente():
    chemin = RACINE / "alembic" / "versions" / "e4b8c2f19a63_project_instance_de_test.py"
    spec = importlib.util.spec_from_file_location("revision_68", chemin)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)

    assert (revision.revision, revision.down_revision) == ("e4b8c2f19a63", "d9e3a1b7c582")
    # La tête a avancé depuis (migration 69, PT-04a) : vérifiée par `test_migration_environnements.py`.
    assert portable_connection.ALEMBIC_HEAD != "d9e3a1b7c582"
    autres = [p.name for p in chemin.parent.glob("*.py")
              if p != chemin and 'down_revision = "d9e3a1b7c582"' in p.read_text(encoding="utf-8")]
    assert autres == [], "une seule révision descend de d9e3a1b7c582"
    ia_peut_agir = (RACINE / "alembic" / "versions" / "d9e3a1b7c582_ia_peut_agir_par_defaut.py").read_text(encoding="utf-8")
    assert "bac_a_sable_reset = ''" in ia_peut_agir, "la révision PostgreSQL d'A43 épargne aussi le refus délibéré"


def test_le_schema_portable_est_aligne():
    assert schema_sa.ALIGNED_WITH_SCHEMA_VERSION == db._SCHEMA_VERSION
    colonne = schema_sa.metadata.tables["project"].c["instance_de_test"]
    assert not colonne.nullable and str(colonne.server_default.arg) == "0"
