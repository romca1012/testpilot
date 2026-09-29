"""Migration 54 — le jeton d'accès à usage unique d'une session en direct (sous-lot B du lot
« Enregistrement assisté du chemin de connexion ») : table neuve, idempotente, FK vers projet et
utilisateur."""

from __future__ import annotations

import sqlite3

import pytest

from testpilot.store.db import _migrate_54_live_session_token, get_initialized_db


def _base_pre_54(chemin):
    conn = sqlite3.connect(str(chemin))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(
        "CREATE TABLE project (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL);"
        "CREATE TABLE user (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL);"
    )
    conn.execute("INSERT INTO project (id, name) VALUES (1, 'Portail')")
    conn.execute("INSERT INTO user (id, username) VALUES (1, 'Admin')")
    conn.commit()
    return conn


def test_base_neuve_porte_la_table_du_jeton(tmp_path, monkeypatch):
    from testpilot import config

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    conn = get_initialized_db(tmp_path / "neuve.db")

    colonnes = {r["name"] for r in conn.execute("PRAGMA table_info(live_session_token)")}

    assert colonnes == {"id", "project_id", "created_by_user_id", "token_hash", "created_at",
                        "expires_at", "used_at"}
    conn.close()


def test_reprise_la_table_est_vide_et_le_reste_ne_bouge_pas(tmp_path):
    conn = _base_pre_54(tmp_path / "vieille.db")

    _migrate_54_live_session_token(conn)

    assert conn.execute("SELECT COUNT(*) FROM live_session_token").fetchone()[0] == 0
    assert conn.execute("SELECT name FROM project WHERE id=1").fetchone()[0] == "Portail"
    conn.close()


def test_la_migration_est_idempotente(tmp_path):
    conn = _base_pre_54(tmp_path / "vieille.db")

    _migrate_54_live_session_token(conn)
    conn.execute(
        "INSERT INTO live_session_token (project_id, created_by_user_id, token_hash, created_at,"
        " expires_at) VALUES (1, 1, 'h', 'x', 'y')")
    _migrate_54_live_session_token(conn)

    assert conn.execute("SELECT COUNT(*) FROM live_session_token").fetchone()[0] == 1
    conn.close()


def test_falsifiable_un_jeton_ne_survit_pas_a_son_projet(tmp_path):
    conn = _base_pre_54(tmp_path / "v.db")
    _migrate_54_live_session_token(conn)
    conn.execute(
        "INSERT INTO live_session_token (project_id, created_by_user_id, token_hash, created_at,"
        " expires_at) VALUES (1, 1, 'h', 'x', 'y')")

    conn.execute("DELETE FROM project WHERE id=1")

    assert conn.execute("SELECT COUNT(*) FROM live_session_token").fetchone()[0] == 0
    conn.close()


def test_falsifiable_un_jeton_ne_pointe_pas_vers_un_projet_ou_un_utilisateur_absent(tmp_path):
    conn = _base_pre_54(tmp_path / "v.db")
    _migrate_54_live_session_token(conn)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO live_session_token (project_id, created_by_user_id, token_hash,"
            " created_at, expires_at) VALUES (999, 1, 'h', 'x', 'y')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO live_session_token (project_id, created_by_user_id, token_hash,"
            " created_at, expires_at) VALUES (1, 999, 'h', 'x', 'y')")
    conn.close()


def test_falsifiable_deux_jetons_ne_partagent_jamais_le_meme_hash(tmp_path):
    conn = _base_pre_54(tmp_path / "v.db")
    _migrate_54_live_session_token(conn)
    conn.execute(
        "INSERT INTO live_session_token (project_id, created_by_user_id, token_hash, created_at,"
        " expires_at) VALUES (1, 1, 'meme-hash', 'x', 'y')")

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO live_session_token (project_id, created_by_user_id, token_hash,"
            " created_at, expires_at) VALUES (1, 1, 'meme-hash', 'x', 'y')")
    conn.close()
