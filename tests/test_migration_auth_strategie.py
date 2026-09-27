"""Migration 52 — la stratégie de connexion du compte principal d'un projet (lot 07b-2, C2) : trois colonnes,
`formulaire` par défaut (comportement inchangé), idempotente."""

from __future__ import annotations

import sqlite3

import pytest

from testpilot.store.db import _migrate_52_auth_strategie, get_initialized_db


def _base_pre_52(chemin):
    conn = sqlite3.connect(str(chemin))
    conn.row_factory = sqlite3.Row
    conn.executescript("CREATE TABLE project (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL);")
    conn.execute("INSERT INTO project (id, name) VALUES (1, 'Portail ancien')")
    conn.commit()
    return conn


def test_base_neuve_porte_les_trois_colonnes_avec_le_defaut_formulaire(tmp_path, monkeypatch):
    from testpilot import config

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    conn = get_initialized_db(tmp_path / "neuve.db")

    ligne = conn.execute("SELECT auth_strategie, totp_secret, injected_session FROM project").fetchone()

    assert ligne is None  # aucun projet créé — juste vérifier que les colonnes existent
    colonnes = {r["name"] for r in conn.execute("PRAGMA table_info(project)")}
    assert {"auth_strategie", "totp_secret", "injected_session"} <= colonnes
    conn.close()


def test_reprise_une_base_pre_52_recoit_le_defaut_formulaire_sans_perdre_ses_projets(tmp_path):
    conn = _base_pre_52(tmp_path / "vieille.db")

    _migrate_52_auth_strategie(conn)

    ligne = conn.execute("SELECT name, auth_strategie, totp_secret, injected_session FROM project WHERE id=1").fetchone()
    assert tuple(ligne) == ("Portail ancien", "formulaire", "", "")
    conn.close()


def test_la_migration_est_idempotente(tmp_path):
    conn = _base_pre_52(tmp_path / "vieille.db")

    _migrate_52_auth_strategie(conn)
    _migrate_52_auth_strategie(conn)

    assert conn.execute("SELECT COUNT(*) FROM project").fetchone()[0] == 1
    conn.close()


def test_falsifiable_une_valeur_hors_enum_est_refusee_par_la_base(tmp_path):
    conn = _base_pre_52(tmp_path / "v.db")
    _migrate_52_auth_strategie(conn)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE project SET auth_strategie='sso_invente' WHERE id=1")
    conn.close()


@pytest.mark.parametrize("valeur", ["formulaire", "totp", "session_injectee", "aucune"])
def test_les_quatre_valeurs_de_l_enum_sont_acceptees(tmp_path, valeur):
    conn = _base_pre_52(tmp_path / "v.db")
    _migrate_52_auth_strategie(conn)

    conn.execute("UPDATE project SET auth_strategie=? WHERE id=1", (valeur,))
    assert conn.execute("SELECT auth_strategie FROM project WHERE id=1").fetchone()[0] == valeur
    conn.close()
