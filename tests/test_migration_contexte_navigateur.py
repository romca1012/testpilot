"""Migration 50 — le contexte navigateur figé d'un projet (lot 07c) : trois colonnes, vides par défaut, idempotente."""

from __future__ import annotations

import sqlite3

from testpilot.store.db import _migrate_50_contexte_navigateur, get_initialized_db


def _base_pre_50(chemin):
    conn = sqlite3.connect(str(chemin))
    conn.row_factory = sqlite3.Row
    conn.executescript("CREATE TABLE project (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL);")
    conn.execute("INSERT INTO project (id, name) VALUES (1, 'Portail ancien')")
    conn.commit()
    return conn


def test_base_neuve_porte_les_trois_colonnes(tmp_path, monkeypatch):
    from testpilot import config

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    conn = get_initialized_db(tmp_path / "neuve.db")

    colonnes = {r["name"] for r in conn.execute("PRAGMA table_info(project)")}

    assert {"browser_locale", "browser_timezone", "browser_viewport"} <= colonnes
    conn.close()


def test_reprise_une_base_pre_50_recoit_les_colonnes_vides_sans_perdre_ses_projets(tmp_path):
    """Les projets existants n'ont rien à renseigner : vide = le défaut, leur ligne est intacte."""
    conn = _base_pre_50(tmp_path / "vieille.db")

    _migrate_50_contexte_navigateur(conn)

    ligne = conn.execute("SELECT name, browser_locale, browser_timezone, browser_viewport FROM project WHERE id=1").fetchone()
    assert tuple(ligne) == ("Portail ancien", "", "", "")
    conn.close()


def test_la_migration_est_idempotente(tmp_path):
    conn = _base_pre_50(tmp_path / "vieille.db")

    _migrate_50_contexte_navigateur(conn)
    _migrate_50_contexte_navigateur(conn)

    assert conn.execute("SELECT COUNT(*) FROM project").fetchone()[0] == 1
    conn.close()
