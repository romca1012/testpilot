"""Migration 55 — la séquence de connexion confirmée d'un projet (sous-lot C du lot
« Enregistrement assisté du chemin de connexion ») : table neuve, idempotente, une seule séquence
active par projet (UNIQUE), FK vers projet et utilisateur."""

from __future__ import annotations

import sqlite3

import pytest

from testpilot.store.db import _migrate_55_project_login_recording, get_initialized_db


def _base_pre_55(chemin):
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


def test_base_neuve_porte_la_table_de_la_sequence(tmp_path, monkeypatch):
    from testpilot import config

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    conn = get_initialized_db(tmp_path / "neuve.db")

    colonnes = {r["name"] for r in conn.execute("PRAGMA table_info(project_login_recording)")}

    # `login_form_json` (migration 56) s'ajoute forcément ici : `get_initialized_db` applique
    # TOUTES les migrations jusqu'à `_SCHEMA_VERSION` courante, jamais seulement la 55.
    assert colonnes == {
        "id", "project_id", "steps_json", "recorded_at", "recorded_by_user_id", "login_form_json",
    }
    conn.close()


def test_reprise_la_table_est_vide_et_le_reste_ne_bouge_pas(tmp_path):
    conn = _base_pre_55(tmp_path / "vieille.db")

    _migrate_55_project_login_recording(conn)

    assert conn.execute("SELECT COUNT(*) FROM project_login_recording").fetchone()[0] == 0
    assert conn.execute("SELECT name FROM project WHERE id=1").fetchone()[0] == "Portail"
    conn.close()


def test_la_migration_est_idempotente(tmp_path):
    conn = _base_pre_55(tmp_path / "vieille.db")

    _migrate_55_project_login_recording(conn)
    conn.execute(
        "INSERT INTO project_login_recording (project_id, steps_json, recorded_at,"
        " recorded_by_user_id) VALUES (1, '[]', 'x', 1)")
    _migrate_55_project_login_recording(conn)

    assert conn.execute("SELECT COUNT(*) FROM project_login_recording").fetchone()[0] == 1
    conn.close()


def test_falsifiable_une_seule_sequence_active_par_projet(tmp_path):
    conn = _base_pre_55(tmp_path / "v.db")
    _migrate_55_project_login_recording(conn)
    conn.execute(
        "INSERT INTO project_login_recording (project_id, steps_json, recorded_at,"
        " recorded_by_user_id) VALUES (1, '[]', 'x', 1)")

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO project_login_recording (project_id, steps_json, recorded_at,"
            " recorded_by_user_id) VALUES (1, '[]', 'y', 1)")
    conn.close()


def test_falsifiable_une_sequence_ne_survit_pas_a_son_projet(tmp_path):
    conn = _base_pre_55(tmp_path / "v.db")
    _migrate_55_project_login_recording(conn)
    conn.execute(
        "INSERT INTO project_login_recording (project_id, steps_json, recorded_at,"
        " recorded_by_user_id) VALUES (1, '[]', 'x', 1)")

    conn.execute("DELETE FROM project WHERE id=1")

    assert conn.execute("SELECT COUNT(*) FROM project_login_recording").fetchone()[0] == 0
    conn.close()


def test_falsifiable_une_sequence_ne_pointe_pas_vers_un_projet_ou_un_utilisateur_absent(tmp_path):
    conn = _base_pre_55(tmp_path / "v.db")
    _migrate_55_project_login_recording(conn)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO project_login_recording (project_id, steps_json, recorded_at,"
            " recorded_by_user_id) VALUES (999, '[]', 'x', 1)")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO project_login_recording (project_id, steps_json, recorded_at,"
            " recorded_by_user_id) VALUES (1, '[]', 'x', 999)")
    conn.close()
