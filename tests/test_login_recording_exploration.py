"""`exploration_service.start_exploration` transmet la séquence de connexion confirmée (sous-lot
C) au connecteur qui va crawler — sous-lot D, étape 8. Lue UNE fois ici (conn disponible), jamais
par le connecteur lui-même (`GenericWebConnector` ne dépend d'aucune connexion DB)."""

from __future__ import annotations

import pytest

from testpilot import config
from testpilot.api.services import exploration_service
from testpilot.store import project_login_recordings
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import ProjectRepo, UserRepo
from testpilot.api import access


@pytest.fixture(autouse=True)
def _sans_job_en_cours():
    exploration_service._JOBS.clear()
    yield
    exploration_service._JOBS.clear()


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    c = get_initialized_db(tmp_path / "exploration-sequence.db")
    yield c
    c.close()


@pytest.fixture
def projet_et_admin(conn):
    project_id = ProjectRepo(conn).create(name="Portail", connector_type="web", base_url="https://app.example")
    user_id = UserRepo(conn).create(username="Admin", password_hash=access.hacher_mot_de_passe("mdp"),
                                    role=access.ROLE_ADMIN)
    return project_id, user_id


def test_sans_sequence_enregistree_la_connexion_porte_une_liste_vide(conn, projet_et_admin):
    project_id, _ = projet_et_admin

    _, params = exploration_service.start_exploration(conn, project_id)

    assert params["connexion"]["sequence_connexion"] == []


def test_avec_une_sequence_confirmee_elle_est_transmise_telle_quelle(conn, projet_et_admin):
    project_id, user_id = projet_et_admin
    etapes = [{"role": "combobox", "name": "Pays"}, {"role": "button", "name": "Continuer"}]
    project_login_recordings.enregistrer(conn, project_id=project_id, etapes=etapes,
                                         recorded_by_user_id=user_id)

    _, params = exploration_service.start_exploration(conn, project_id)

    assert params["connexion"]["sequence_connexion"] == etapes
