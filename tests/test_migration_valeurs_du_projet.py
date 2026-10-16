"""Migration 62 (paramètres de test, lot PT-03) — `project.format_nombre` (la monnaie du projet, prévue d'abord, a été retirée
avant tout envoi : A38, porteur, 2026-10-15).

Les quatre pièces d'une évolution de schéma (CLAUDE.md §6) : migration SQLite idempotente, révision Alembic chaînée sur la tête
précédente, `schema_sa` aligné, et ce test. Vide par défaut : sans déclaration, rien ne change pour un projet existant.
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import pytest

from testpilot.store import db, schema_sa
from testpilot.store.db import _migrate_62_valeurs_du_projet, get_initialized_db
from testpilot.store.repositories import ProjectRepo

RACINE = Path(__file__).resolve().parent.parent
COLONNES = ("format_nombre",)


def test_une_base_neuve_porte_les_colonnes_vides_par_defaut(tmp_path):
    conn = get_initialized_db(tmp_path / "neuve.db")
    pid = ProjectRepo(conn).create(name="P", connector_type="web", base_url="http://app")

    assert db._SCHEMA_VERSION >= 62
    projet = ProjectRepo(conn).get(pid)
    assert projet["format_nombre"] == "", "jamais posée implicitement"
    assert "devise" not in projet, "aucune monnaie du projet (A38)"
    # Décision A44 (2026-10-16) : la colonne reste, inutilisée — plus rien ne l'écrit.
    ProjectRepo(conn).update_connection(pid, format_nombre="espace_virgule", base_url="http://autre")
    assert ProjectRepo(conn).get(pid)["format_nombre"] == ""
    conn.close()


def test_falsifiable_l_ecriture_des_nombres_est_une_enumeration_fermee(tmp_path):
    """La base refuse elle-même une écriture inconnue, sur une base neuve comme sur une base reprise."""
    neuve = get_initialized_db(tmp_path / "neuve.db")
    pid = ProjectRepo(neuve).create(name="P", connector_type="web", base_url="http://app")
    with pytest.raises(sqlite3.IntegrityError):
        neuve.execute("UPDATE project SET format_nombre='tiret' WHERE id=?", (pid,))
    neuve.close()

    reprise = sqlite3.connect(str(tmp_path / "vieille.db"))
    reprise.row_factory = sqlite3.Row
    reprise.execute("CREATE TABLE project (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
    reprise.execute("INSERT INTO project (id, name) VALUES (1, 'ancien')")
    _migrate_62_valeurs_du_projet(reprise)
    with pytest.raises(sqlite3.IntegrityError):
        reprise.execute("UPDATE project SET format_nombre='virgule' WHERE id=1")
    reprise.execute("UPDATE project SET format_nombre='point_virgule' WHERE id=1")
    reprise.close()


def test_falsifiable_reprise_d_une_base_pre_62(tmp_path):
    base = sqlite3.connect(str(tmp_path / "vieille.db"))
    base.row_factory = sqlite3.Row
    base.execute("CREATE TABLE project (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
    base.execute("INSERT INTO project (id, name) VALUES (1, 'ancien')")
    base.commit()
    assert not set(COLONNES) & {r["name"] for r in base.execute("PRAGMA table_info(project)")}

    _migrate_62_valeurs_du_projet(base)
    _migrate_62_valeurs_du_projet(base)  # idempotente

    assert base.execute("SELECT format_nombre FROM project WHERE id=1").fetchone()[0] == "", "un projet existant ne déclare rien"
    assert "devise" not in {r["name"] for r in base.execute("PRAGMA table_info(project)")}, "aucune colonne de monnaie (A38)"
    base.close()


def test_la_revision_alembic_est_chainee_sur_la_tete_precedente():
    chemin = RACINE / "alembic" / "versions" / "e7c2f4a9b136_valeurs_du_projet.py"
    spec = importlib.util.spec_from_file_location("revision_62", chemin)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)

    assert (revision.revision, revision.down_revision) == ("e7c2f4a9b136", "d1a7b3c5e924")
    contraintes = {c.name: str(c.sqltext) for c in schema_sa.metadata.tables["project"].constraints
                   if getattr(c, "sqltext", None) is not None}
    assert revision._CONTRAINTE == contraintes["ck_project_format_nombre"], "PostgreSQL et le modèle portable disent la même liste"
    autres = [p.name for p in chemin.parent.glob("*.py")
              if p != chemin and 'down_revision = "d1a7b3c5e924"' in p.read_text(encoding="utf-8")]
    assert autres == [], "une seule révision descend de d1a7b3c5e924"


def test_le_schema_portable_est_aligne():
    assert schema_sa.ALIGNED_WITH_SCHEMA_VERSION == db._SCHEMA_VERSION
    for nom in COLONNES:
        colonne = schema_sa.metadata.tables["project"].c[nom]
        assert not colonne.nullable and str(colonne.server_default.arg) == ""
    contraintes = {c.name: str(c.sqltext) for c in schema_sa.metadata.tables["project"].constraints if getattr(c, "sqltext", None) is not None}
    for cle in ("espace_virgule", "virgule_point", "point_virgule"):   # les valeurs que la migration 62 admettait
        assert f"'{cle}'" in contraintes["ck_project_format_nombre"]
    assert contraintes["ck_project_format_nombre"].count("'") == 2 * 4
