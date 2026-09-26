"""Migration 51 — les comptes secondaires d'un projet (lot 07b-1, D8) : table neuve, idempotente, compte principal intact."""

from __future__ import annotations

import sqlite3

import pytest

from testpilot.store.db import _migrate_51_project_account, get_initialized_db


def _base_pre_51(chemin):
    conn = sqlite3.connect(str(chemin))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript("CREATE TABLE project (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,"
                       " username TEXT NOT NULL DEFAULT '', password TEXT NOT NULL DEFAULT '');")
    conn.execute("INSERT INTO project (id, name, username, password) VALUES (1, 'Portail ancien', 'admin', 'enc:v1:xxx')")
    conn.commit()
    return conn


def test_base_neuve_porte_la_table_des_comptes(tmp_path, monkeypatch):
    from testpilot import config

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    conn = get_initialized_db(tmp_path / "neuve.db")

    colonnes = {r["name"] for r in conn.execute("PRAGMA table_info(project_account)")}

    assert colonnes == {"id", "project_id", "label", "username", "password", "business_role", "created_at"}
    conn.close()


def test_reprise_le_compte_principal_du_projet_reste_intact_et_la_table_est_vide(tmp_path):
    """Précision 1 de D8 : le compte déjà configuré EST le principal — rien n'est copié, déplacé ni perdu."""
    conn = _base_pre_51(tmp_path / "vieille.db")

    _migrate_51_project_account(conn)

    assert tuple(conn.execute("SELECT name, username, password FROM project WHERE id=1").fetchone()) == (
        "Portail ancien", "admin", "enc:v1:xxx")
    assert conn.execute("SELECT COUNT(*) FROM project_account").fetchone()[0] == 0
    conn.close()


def test_la_migration_est_idempotente(tmp_path):
    conn = _base_pre_51(tmp_path / "vieille.db")

    _migrate_51_project_account(conn)
    conn.execute("INSERT INTO project_account (project_id, label, username, created_at) VALUES (1, 'A', 'u', 'x')")
    _migrate_51_project_account(conn)

    assert conn.execute("SELECT COUNT(*) FROM project_account").fetchone()[0] == 1
    conn.close()


def test_falsifiable_deux_comptes_de_meme_libelle_sur_un_projet_sont_refuses_par_la_base(tmp_path):
    conn = _base_pre_51(tmp_path / "v.db")
    _migrate_51_project_account(conn)
    conn.execute("INSERT INTO project_account (project_id, label, username, created_at) VALUES (1, 'A', 'u', 'x')")

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO project_account (project_id, label, username, created_at) VALUES (1, 'A', 'v', 'x')")
    conn.close()


def test_falsifiable_un_compte_ne_survit_pas_a_son_projet_ni_ne_pointe_vers_un_projet_absent(tmp_path):
    conn = _base_pre_51(tmp_path / "v.db")
    _migrate_51_project_account(conn)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO project_account (project_id, label, username, created_at) VALUES (999, 'A', 'u', 'x')")
    conn.execute("INSERT INTO project_account (project_id, label, username, created_at) VALUES (1, 'A', 'u', 'x')")
    conn.execute("DELETE FROM project WHERE id=1")
    assert conn.execute("SELECT COUNT(*) FROM project_account").fetchone()[0] == 0
    conn.close()
