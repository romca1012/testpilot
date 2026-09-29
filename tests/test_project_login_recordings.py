"""`store/project_login_recordings.py` — sous-lot C : la séquence de connexion confirmée, une
seule active par projet, jamais un historique."""

from __future__ import annotations

import pytest

from testpilot import config
from testpilot.store import project_login_recordings as repo
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import ProjectRepo, UserRepo
from testpilot.api import access


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    c = get_initialized_db(tmp_path / "recordings.db")
    yield c
    c.close()


@pytest.fixture
def projet_et_admin(conn):
    project_id = ProjectRepo(conn).create(name="Portail", connector_type="web", base_url="https://app.example")
    user_id = UserRepo(conn).create(username="Admin", password_hash=access.hacher_mot_de_passe("mdp"),
                                    role=access.ROLE_ADMIN)
    return project_id, user_id


def test_lire_rend_none_quand_rien_n_a_jamais_ete_confirme(conn, projet_et_admin):
    project_id, _ = projet_et_admin

    assert repo.lire(conn, project_id) is None


def test_enregistrer_puis_lire_rend_la_meme_sequence(conn, projet_et_admin):
    project_id, user_id = projet_et_admin
    etapes = [{"role": "combobox", "name": "Pays"}, {"role": "button", "name": "Continuer"}]

    repo.enregistrer(conn, project_id=project_id, etapes=etapes, recorded_by_user_id=user_id)

    assert repo.lire(conn, project_id) == etapes


def test_une_nouvelle_confirmation_remplace_la_precedente_sans_historique(conn, projet_et_admin):
    """Preuve qu'il n'y a jamais deux lignes pour le même projet : une deuxième confirmation
    écrase la première, elle ne s'y ajoute pas."""
    project_id, user_id = projet_et_admin
    repo.enregistrer(conn, project_id=project_id, etapes=[{"role": "button", "name": "Ancien"}],
                     recorded_by_user_id=user_id)

    repo.enregistrer(conn, project_id=project_id, etapes=[{"role": "button", "name": "Nouveau"}],
                     recorded_by_user_id=user_id)

    assert repo.lire(conn, project_id) == [{"role": "button", "name": "Nouveau"}]
    assert conn.execute("SELECT COUNT(*) FROM project_login_recording").fetchone()[0] == 1


def test_falsifiable_une_sequence_d_un_autre_projet_n_est_ni_lue_ni_ecrasee(conn, projet_et_admin):
    project_id, user_id = projet_et_admin
    autre = ProjectRepo(conn).create(name="Autre", connector_type="web", base_url="https://b.example")
    repo.enregistrer(conn, project_id=project_id, etapes=[{"role": "button", "name": "A"}],
                     recorded_by_user_id=user_id)

    assert repo.lire(conn, autre) is None
    repo.enregistrer(conn, project_id=autre, etapes=[{"role": "button", "name": "B"}],
                     recorded_by_user_id=user_id)

    assert repo.lire(conn, project_id) == [{"role": "button", "name": "A"}]
    assert repo.lire(conn, autre) == [{"role": "button", "name": "B"}]


def test_supprimer_retire_la_sequence_et_rend_false_si_rien_n_existait(conn, projet_et_admin):
    project_id, user_id = projet_et_admin

    assert repo.supprimer(conn, project_id) is False

    repo.enregistrer(conn, project_id=project_id, etapes=[{"role": "button", "name": "A"}],
                     recorded_by_user_id=user_id)
    assert repo.supprimer(conn, project_id) is True
    assert repo.lire(conn, project_id) is None
