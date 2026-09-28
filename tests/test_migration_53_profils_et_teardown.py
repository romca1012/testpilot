"""Migration 53 — profils d'instance et résidus de teardown (lot 06, D6, F6) : deux colonnes,
vides par défaut (comportement inchangé, aucun profil / aucun résidu), idempotente."""

from __future__ import annotations

import sqlite3

from testpilot.store.db import _migrate_53_profils_et_teardown, get_initialized_db


def _base_pre_53(chemin):
    conn = sqlite3.connect(str(chemin))
    conn.row_factory = sqlite3.Row
    conn.executescript(
        "CREATE TABLE project (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL);"
        "CREATE TABLE execution (id INTEGER PRIMARY KEY AUTOINCREMENT, test_case_id INTEGER NOT NULL);"
    )
    conn.execute("INSERT INTO project (id, name) VALUES (1, 'Sapian')")
    conn.execute("INSERT INTO execution (id, test_case_id) VALUES (1, 1)")
    conn.commit()
    return conn


def test_base_neuve_porte_les_deux_colonnes_avec_leur_defaut_vide(tmp_path, monkeypatch):
    from testpilot import config

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    conn = get_initialized_db(tmp_path / "neuve.db")

    colonnes_project = {r["name"] for r in conn.execute("PRAGMA table_info(project)")}
    colonnes_execution = {r["name"] for r in conn.execute("PRAGMA table_info(execution)")}
    assert "profil_instance" in colonnes_project
    assert "residus" in colonnes_execution
    conn.close()


def test_reprise_une_base_pre_53_recoit_les_defauts_vides_sans_perdre_ses_lignes(tmp_path):
    conn = _base_pre_53(tmp_path / "vieille.db")

    _migrate_53_profils_et_teardown(conn)

    projet = conn.execute("SELECT name, profil_instance FROM project WHERE id=1").fetchone()
    assert tuple(projet) == ("Sapian", "")
    execution = conn.execute("SELECT residus FROM execution WHERE id=1").fetchone()
    assert execution["residus"] == ""
    conn.close()


def test_la_migration_est_idempotente(tmp_path):
    conn = _base_pre_53(tmp_path / "vieille.db")

    _migrate_53_profils_et_teardown(conn)
    _migrate_53_profils_et_teardown(conn)

    assert conn.execute("SELECT COUNT(*) FROM project").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM execution").fetchone()[0] == 1
    conn.close()


def test_profil_instance_accepte_n_importe_quel_nom_pas_un_enum_fige(tmp_path):
    """Contrairement à `auth_strategie` (migration 52), aucun `CHECK` : un profil est un fichier
    sur disque, pas une valeur figée en base — un nom inconnu est refusé à la SAISIE (API), jamais
    ici (cf. docstring de `_migrate_53_profils_et_teardown`)."""
    conn = _base_pre_53(tmp_path / "v.db")
    _migrate_53_profils_et_teardown(conn)

    conn.execute("UPDATE project SET profil_instance='sapian' WHERE id=1")
    assert conn.execute("SELECT profil_instance FROM project WHERE id=1").fetchone()[0] == "sapian"
    conn.close()


def test_residus_porte_une_liste_json_de_messages(tmp_path):
    conn = _base_pre_53(tmp_path / "v.db")
    _migrate_53_profils_et_teardown(conn)

    conn.execute("UPDATE execution SET residus=? WHERE id=1",
                ('["res.partner#4821 (max_id dépassé, non enregistré)"]',))
    assert conn.execute("SELECT residus FROM execution WHERE id=1").fetchone()[0] == (
        '["res.partner#4821 (max_id dépassé, non enregistré)"]')
    conn.close()
