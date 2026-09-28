"""Migration 57 — l'oracle backend HTTP optionnel d'un projet (lot 07e, C5, D7) : quatre colonnes,
vide par défaut (aucun oracle, comportement inchangé), idempotente."""

from __future__ import annotations

import sqlite3

import pytest

from testpilot.store.db import _migrate_57_oracle, get_initialized_db


def _base_pre_57(chemin):
    conn = sqlite3.connect(str(chemin))
    conn.row_factory = sqlite3.Row
    conn.executescript("CREATE TABLE project (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL);")
    conn.execute("INSERT INTO project (id, name) VALUES (1, 'Portail ancien')")
    conn.commit()
    return conn


def test_base_neuve_porte_les_quatre_colonnes_vides_par_defaut(tmp_path, monkeypatch):
    from testpilot import config

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    conn = get_initialized_db(tmp_path / "neuve.db")

    colonnes = {r["name"] for r in conn.execute("PRAGMA table_info(project)")}
    assert {"oracle_type", "oracle_base_url", "oracle_auth", "oracle_queries"} <= colonnes
    conn.close()


def test_reprise_une_base_pre_57_recoit_les_defauts_sans_perdre_ses_projets(tmp_path):
    conn = _base_pre_57(tmp_path / "vieille.db")

    _migrate_57_oracle(conn)

    ligne = conn.execute(
        "SELECT name, oracle_type, oracle_base_url, oracle_auth, oracle_queries FROM project WHERE id=1").fetchone()
    assert tuple(ligne) == ("Portail ancien", "", "", "", "[]")
    conn.close()


def test_la_migration_est_idempotente(tmp_path):
    conn = _base_pre_57(tmp_path / "vieille.db")

    _migrate_57_oracle(conn)
    _migrate_57_oracle(conn)

    assert conn.execute("SELECT COUNT(*) FROM project").fetchone()[0] == 1
    conn.close()


def test_falsifiable_un_type_hors_enum_est_refuse_par_la_base(tmp_path):
    conn = _base_pre_57(tmp_path / "v.db")
    _migrate_57_oracle(conn)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE project SET oracle_type='sql_invente' WHERE id=1")
    conn.close()


@pytest.mark.parametrize("valeur", ["", "http"])
def test_les_deux_valeurs_de_l_enum_sont_acceptees(tmp_path, valeur):
    conn = _base_pre_57(tmp_path / "v.db")
    _migrate_57_oracle(conn)

    conn.execute("UPDATE project SET oracle_type=? WHERE id=1", (valeur,))
    conn.commit()
    assert conn.execute("SELECT oracle_type FROM project WHERE id=1").fetchone()[0] == valeur
    conn.close()
