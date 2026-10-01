"""Migration 58 — F26(b) : `test_case_version.depend_dun_autre_cas_du_groupe` (CHECK 0/1) et
`etat_a_creer_par_ce_cas`, vides/faux par défaut (comportement inchangé), idempotente."""

from __future__ import annotations

import sqlite3

import pytest

from testpilot.store.db import _migrate_58_dependance_inter_cas, get_initialized_db


def _base_pre_58(chemin):
    conn = sqlite3.connect(str(chemin))
    conn.row_factory = sqlite3.Row
    conn.executescript(
        "CREATE TABLE test_case (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL);"
        "CREATE TABLE test_case_version (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "test_case_id INTEGER NOT NULL, title TEXT NOT NULL DEFAULT '');"
    )
    conn.execute("INSERT INTO test_case (id, title) VALUES (1, 'Cas ancien')")
    conn.execute("INSERT INTO test_case_version (id, test_case_id, title) VALUES (1, 1, 'v1')")
    conn.commit()
    return conn


def test_base_neuve_porte_les_deux_colonnes_par_defaut(tmp_path, monkeypatch):
    from testpilot import config

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    conn = get_initialized_db(tmp_path / "neuve.db")

    colonnes = {r["name"] for r in conn.execute("PRAGMA table_info(test_case_version)")}
    assert {"depend_dun_autre_cas_du_groupe", "etat_a_creer_par_ce_cas"} <= colonnes
    conn.close()


def test_reprise_une_base_pre_58_recoit_les_defauts_sans_perdre_ses_versions(tmp_path):
    conn = _base_pre_58(tmp_path / "vieille.db")

    _migrate_58_dependance_inter_cas(conn)

    ligne = conn.execute(
        "SELECT title, depend_dun_autre_cas_du_groupe, etat_a_creer_par_ce_cas "
        "FROM test_case_version WHERE id=1").fetchone()
    assert tuple(ligne) == ("v1", 0, "")
    conn.close()


def test_la_migration_est_idempotente(tmp_path):
    conn = _base_pre_58(tmp_path / "vieille.db")

    _migrate_58_dependance_inter_cas(conn)
    _migrate_58_dependance_inter_cas(conn)

    assert conn.execute("SELECT COUNT(*) FROM test_case_version").fetchone()[0] == 1
    conn.close()


def test_falsifiable_une_valeur_hors_0_1_est_refusee_par_la_base(tmp_path):
    conn = _base_pre_58(tmp_path / "v.db")
    _migrate_58_dependance_inter_cas(conn)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE test_case_version SET depend_dun_autre_cas_du_groupe=2 WHERE id=1")
    conn.close()


@pytest.mark.parametrize("valeur", [0, 1])
def test_les_deux_valeurs_valides_sont_acceptees(tmp_path, valeur):
    conn = _base_pre_58(tmp_path / "v.db")
    _migrate_58_dependance_inter_cas(conn)

    conn.execute("UPDATE test_case_version SET depend_dun_autre_cas_du_groupe=? WHERE id=1",
                (valeur,))
    conn.commit()
    assert conn.execute(
        "SELECT depend_dun_autre_cas_du_groupe FROM test_case_version WHERE id=1"
    ).fetchone()[0] == valeur
    conn.close()
