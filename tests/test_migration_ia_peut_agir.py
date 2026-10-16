"""Migration 67 (décision A43, porteur, 2026-10-16) — « L'IA peut agir sur cette application » coché par défaut.

Les quatre pièces d'une évolution de schéma (CLAUDE.md §6) : migration SQLite, révision Alembic chaînée sur la tête précédente,
`schema_sa` aligné, et ce test. Les projets existants sont cochés ; un projet neuf l'est d'office.
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

from testpilot.store import db, portable_connection, schema_sa
from testpilot.store.db import _migrate_67_ia_peut_agir_par_defaut, get_initialized_db
from testpilot.store.repositories import ProjectRepo

RACINE = Path(__file__).resolve().parent.parent


def test_une_base_neuve_autorise_d_office(tmp_path):
    conn = get_initialized_db(tmp_path / "neuve.db")
    colonne = {r["name"]: r for r in conn.execute("PRAGMA table_info(project)")}["calibration_writes_enabled"]
    pid = ProjectRepo(conn).create(name="Neuf", connector_type="web", base_url="https://a.test")

    assert db._SCHEMA_VERSION >= 67 and colonne["dflt_value"] == "1"
    assert bool(ProjectRepo(conn).get(pid)["calibration_writes_enabled"]) is True
    assert bool(ProjectRepo(conn).get(ProjectRepo(conn).create(name="Explicite", calibration_writes_enabled=False))[
        "calibration_writes_enabled"]) is False, "un appelant qui le refuse est respecté (banc d'agents)"
    conn.close()


def test_falsifiable_reprise_d_une_base_pre_67_coche_les_projets_existants(tmp_path):
    base = sqlite3.connect(str(tmp_path / "vieille.db"))
    base.row_factory = sqlite3.Row
    base.execute("CREATE TABLE project (id INTEGER PRIMARY KEY, name TEXT, calibration_writes_enabled INTEGER NOT NULL DEFAULT 0)")
    base.execute("INSERT INTO project (id, name, calibration_writes_enabled) VALUES (1, 'Ancien', 0), (2, 'Coché', 1)")
    base.commit()

    _migrate_67_ia_peut_agir_par_defaut(base)
    _migrate_67_ia_peut_agir_par_defaut(base)  # rejouée : sans effet de plus

    assert [r[0] for r in base.execute("SELECT calibration_writes_enabled FROM project ORDER BY id")] == [1, 1]
    base.close()


def test_la_revision_alembic_est_chainee_sur_la_tete_precedente():
    chemin = RACINE / "alembic" / "versions" / "d9e3a1b7c582_ia_peut_agir_par_defaut.py"
    spec = importlib.util.spec_from_file_location("revision_67", chemin)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)

    assert (revision.revision, revision.down_revision) == ("d9e3a1b7c582", "c7a2e9d4f610")
    # La tête a avancé depuis (migration 68, A45) : vérifiée par `test_migration_instance_de_test.py`.
    assert portable_connection.ALEMBIC_HEAD != "c7a2e9d4f610"
    autres = [p.name for p in chemin.parent.glob("*.py")
              if p != chemin and 'down_revision = "c7a2e9d4f610"' in p.read_text(encoding="utf-8")]
    assert autres == [], "une seule révision descend de c7a2e9d4f610"


def test_le_schema_portable_est_aligne():
    assert schema_sa.ALIGNED_WITH_SCHEMA_VERSION == db._SCHEMA_VERSION
    colonne = schema_sa.metadata.tables["project"].c["calibration_writes_enabled"]
    assert not colonne.nullable and str(colonne.server_default.arg) == "1"
