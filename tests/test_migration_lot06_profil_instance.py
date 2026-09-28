"""Lot 06 (D6, F6) — `scripts/migration_lot06_profil_instance.py` : dry-run par défaut, application
explicite, idempotence, et cas AMBIGU laissé de côté."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, ModuleRepo, ProjectRepo, VersionRepo

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "migration_lot06_profil_instance.py"
spec = importlib.util.spec_from_file_location("migration_lot06_profil_instance", _SCRIPT)
migration = importlib.util.module_from_spec(spec)
sys.modules["migration_lot06_profil_instance"] = migration
spec.loader.exec_module(migration)


@pytest.fixture
def conn(tmp_path, monkeypatch):
    from testpilot import config

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    c = get_initialized_db(tmp_path / "m.db")
    yield c
    c.close()


def _cas(conn, *, project_name: str, steps_content: str = "", feature_content: str = "") -> int:
    pid = ProjectRepo(conn).create(name=project_name)
    mid = ModuleRepo(conn).create(project_id=pid, name="M")
    cid = CaseRepo(conn).create(title="Cas", module_id=mid, feature_slug="cas")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="",
                                   feature_content=feature_content, steps_content=steps_content)
    CaseRepo(conn).set_current_version(cid, vid)
    return pid


def test_detecte_un_projet_sapian_volet_odoo(conn):
    _cas(conn, project_name="Portail Sapian",
        steps_content="odoo.env['res.users'].browse(1).write({'employee_front_role_ids': [(3, 1)]})")

    candidats = migration._projets_a_migrer(conn)

    assert len(candidats) == 1
    assert candidats[0]["profils_suggeres"] == {"sapian"}


def test_detecte_un_projet_sapian_volet_generique_par_le_libelle_du_step(conn):
    _cas(conn, project_name="Portail Sapian",
        feature_content='Alors je force le nom du ticket à "Test"')

    candidats = migration._projets_a_migrer(conn)

    assert candidats[0]["profils_suggeres"] == {"sapian"}


def test_detecte_un_projet_demo_saucedemo(conn):
    _cas(conn, project_name="Démo",
        feature_content='Quand je clique sur le bouton "Ajouter" avec accessoires')

    candidats = migration._projets_a_migrer(conn)

    assert candidats[0]["profils_suggeres"] == {"demo_saucedemo"}


def test_falsifiable_un_projet_sans_marqueur_n_est_pas_candidat(conn):
    _cas(conn, project_name="Ordinaire", steps_content="context.page.click('button')")

    assert migration._projets_a_migrer(conn) == []


def test_falsifiable_un_projet_deja_dote_d_un_profil_n_est_jamais_recalcule(conn):
    pid = _cas(conn, project_name="Déjà réglé",
              steps_content="employee_front_role_ids")
    ProjectRepo(conn).update_connection(pid, profil_instance="sapian")

    assert migration._projets_a_migrer(conn) == []


def test_main_dry_run_par_defaut_n_ecrit_rien(conn, tmp_path, capsys):
    pid = _cas(conn, project_name="Portail Sapian", steps_content="employee_front_role_ids")
    conn.close()
    chemin_db = tmp_path / "m.db"

    import subprocess
    resultat = subprocess.run(
        [sys.executable, str(_SCRIPT), "--db", str(chemin_db)],
        capture_output=True, text=True, check=True)

    assert "Dry-run" in resultat.stdout
    import sqlite3
    verif = sqlite3.connect(str(chemin_db))
    assert verif.execute("SELECT profil_instance FROM project WHERE id=?", (pid,)).fetchone()[0] == ""
    verif.close()


def test_main_applique_reellement_avec_l_option(conn, tmp_path):
    pid = _cas(conn, project_name="Portail Sapian", steps_content="employee_front_role_ids")
    conn.close()
    chemin_db = tmp_path / "m.db"

    import subprocess
    subprocess.run([sys.executable, str(_SCRIPT), "--db", str(chemin_db), "--appliquer"],
                   capture_output=True, text=True, check=True)

    import sqlite3
    verif = sqlite3.connect(str(chemin_db))
    assert verif.execute("SELECT profil_instance FROM project WHERE id=?", (pid,)).fetchone()[0] == "sapian"
    verif.close()


def test_falsifiable_idempotent_un_second_passage_n_ecrase_rien(conn, tmp_path):
    """Relancer avec --appliquer une SECONDE fois (ex. le porteur a changé le profil à la main
    entre-temps) ne doit RIEN écraser."""
    pid = _cas(conn, project_name="Portail Sapian", steps_content="employee_front_role_ids")
    conn.close()
    chemin_db = tmp_path / "m.db"

    import subprocess
    subprocess.run([sys.executable, str(_SCRIPT), "--db", str(chemin_db), "--appliquer"],
                   capture_output=True, text=True, check=True)
    import sqlite3
    verif = sqlite3.connect(str(chemin_db))
    verif.execute("UPDATE project SET profil_instance='autre_profil' WHERE id=?", (pid,))
    verif.commit()
    verif.close()

    subprocess.run([sys.executable, str(_SCRIPT), "--db", str(chemin_db), "--appliquer"],
                   capture_output=True, text=True, check=True)

    verif = sqlite3.connect(str(chemin_db))
    assert verif.execute("SELECT profil_instance FROM project WHERE id=?", (pid,)).fetchone()[0] == "autre_profil"
    verif.close()


def test_falsifiable_un_projet_ambigu_n_est_jamais_applique_automatiquement(conn, tmp_path):
    pid = _cas(conn, project_name="Mixte",
              steps_content="employee_front_role_ids",
              feature_content='Quand je clique sur le bouton "X" avec accessoires')
    conn.close()
    chemin_db = tmp_path / "m.db"

    import subprocess
    resultat = subprocess.run([sys.executable, str(_SCRIPT), "--db", str(chemin_db), "--appliquer"],
                              capture_output=True, text=True, check=True)

    assert "AMBIGU" in resultat.stdout
    import sqlite3
    verif = sqlite3.connect(str(chemin_db))
    assert verif.execute("SELECT profil_instance FROM project WHERE id=?", (pid,)).fetchone()[0] == ""
    verif.close()
