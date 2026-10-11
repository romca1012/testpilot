"""Migration 61 (lot VH-07, décision D26) — `project.bac_a_sable_reset`, l'adresse de remise à zéro du bac à sable.

Les quatre pièces d'une évolution de schéma (CLAUDE.md §6) : migration SQLite idempotente, révision Alembic chaînée sur la tête
précédente, `schema_sa` aligné, et ce test. Vide par défaut : sans déclaration du porteur, aucun essai pendant la génération.
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

from testpilot.store import db, portable_connection, schema_sa
from testpilot.store.db import _migrate_61_bac_a_sable_reset, get_initialized_db
from testpilot.store.repositories import ProjectRepo

RACINE = Path(__file__).resolve().parent.parent


def test_une_base_neuve_porte_la_colonne_vide_par_defaut(tmp_path):
    conn = get_initialized_db(tmp_path / "neuve.db")
    pid = ProjectRepo(conn).create(name="P", connector_type="web", base_url="http://app")

    assert db._SCHEMA_VERSION >= 61
    assert ProjectRepo(conn).get(pid)["bac_a_sable_reset"] == "", "jamais posée implicitement"
    ProjectRepo(conn).set_bac_a_sable_reset(pid, "  http://app/reset ")
    assert ProjectRepo(conn).get(pid)["bac_a_sable_reset"] == "http://app/reset"
    conn.close()


def test_falsifiable_reprise_d_une_base_pre_61(tmp_path):
    base = sqlite3.connect(str(tmp_path / "vieille.db"))
    base.row_factory = sqlite3.Row
    base.execute("CREATE TABLE project (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
    base.execute("INSERT INTO project (id, name) VALUES (1, 'ancien')")
    base.commit()
    assert "bac_a_sable_reset" not in {r["name"] for r in base.execute("PRAGMA table_info(project)")}

    _migrate_61_bac_a_sable_reset(base)
    _migrate_61_bac_a_sable_reset(base)  # idempotente

    assert base.execute("SELECT bac_a_sable_reset FROM project WHERE id=1").fetchone()[0] == "", \
        "un projet existant ne devient pas bac à sable"
    base.close()


def test_la_revision_alembic_est_chainee_sur_la_tete_precedente():
    chemin = RACINE / "alembic" / "versions" / "d1a7b3c5e924_bac_a_sable_reset.py"
    spec = importlib.util.spec_from_file_location("revision_61", chemin)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)

    assert (revision.revision, revision.down_revision) == ("d1a7b3c5e924", "c9f4a2d6e813")
    assert portable_connection.ALEMBIC_HEAD == "d1a7b3c5e924"
    autres_tetes = [p.name for p in chemin.parent.glob("*.py")
                    if p != chemin and 'down_revision = "c9f4a2d6e813"' in p.read_text(encoding="utf-8")]
    assert autres_tetes == [], "une seule révision descend de c9f4a2d6e813"


def test_le_schema_portable_est_aligne():
    colonne = schema_sa.metadata.tables["project"].c["bac_a_sable_reset"]

    assert schema_sa.ALIGNED_WITH_SCHEMA_VERSION == db._SCHEMA_VERSION
    assert not colonne.nullable and str(colonne.server_default.arg) == ""
