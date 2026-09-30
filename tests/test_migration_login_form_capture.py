"""Migration 56 — extension du lot « Enregistrement assisté du chemin de connexion » : la colonne
`login_form_json` porte le descripteur (rôle/nom) du champ identifiant, du champ mot de passe et
du bouton de soumission, capturés par 3 clics guidés — jamais un secret. Vide = jamais capturé,
comportement inchangé (fallback sur `tenter_connexion_generique`)."""

from __future__ import annotations

import sqlite3

from testpilot.store.db import (
    _migrate_55_project_login_recording,
    _migrate_56_login_form_capture,
    get_initialized_db,
)


def _base_pre_56(chemin):
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
    _migrate_55_project_login_recording(conn)
    return conn


def test_base_neuve_porte_la_colonne(tmp_path, monkeypatch):
    from testpilot import config

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    conn = get_initialized_db(tmp_path / "neuve.db")

    colonnes = {r["name"] for r in conn.execute("PRAGMA table_info(project_login_recording)")}

    assert colonnes == {
        "id", "project_id", "steps_json", "recorded_at", "recorded_by_user_id", "login_form_json",
    }
    conn.close()


def test_reprise_une_ligne_existante_recoit_une_valeur_vide_par_defaut(tmp_path):
    conn = _base_pre_56(tmp_path / "vieille.db")
    conn.execute(
        "INSERT INTO project_login_recording (project_id, steps_json, recorded_at,"
        " recorded_by_user_id) VALUES (1, '[]', 'x', 1)")

    _migrate_56_login_form_capture(conn)

    valeur = conn.execute(
        "SELECT login_form_json FROM project_login_recording WHERE project_id=1").fetchone()[0]
    assert valeur == ""
    conn.close()


def test_la_migration_est_idempotente(tmp_path):
    conn = _base_pre_56(tmp_path / "vieille.db")

    _migrate_56_login_form_capture(conn)
    _migrate_56_login_form_capture(conn)  # ne doit pas lever (colonne déjà présente)

    colonnes = {r["name"] for r in conn.execute("PRAGMA table_info(project_login_recording)")}
    assert "login_form_json" in colonnes
    conn.close()


def test_falsifiable_une_valeur_reelle_survit_a_la_migration(tmp_path):
    conn = _base_pre_56(tmp_path / "v.db")
    _migrate_56_login_form_capture(conn)
    descripteur = '{"champ_identifiant": {"role": "textbox", "name": "E-mail"}}'
    conn.execute(
        "INSERT INTO project_login_recording (project_id, steps_json, recorded_at,"
        " recorded_by_user_id, login_form_json) VALUES (1, '[]', 'x', 1, ?)", (descripteur,))

    _migrate_56_login_form_capture(conn)

    valeur = conn.execute(
        "SELECT login_form_json FROM project_login_recording WHERE project_id=1").fetchone()[0]
    assert valeur == descripteur
    conn.close()
