"""Sous-lot B du lot « Enregistrement assisté du chemin de connexion » : le jeton d'accès à
usage unique d'une session en direct (`store/live_session_tokens.py`) et la route qui l'émet
(`POST /api/projects/{id}/live-session`).

Ce sous-lot ne construit PAS encore la session elle-même (navigateur, WebSocket — sous-lot C) :
seulement de quoi l'autoriser à démarrer, avec les mêmes garanties qu'un lien de réinitialisation
de mot de passe — jeton en clair jamais stocké, usage unique garanti même sous concurrence,
réservé à `admin`.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import access
from testpilot.api import app as app_mod
from testpilot.store import live_session_tokens
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import ProjectRepo, UserRepo

# ── Le dépôt, isolé de l'API ──────────────────────────────────────────────────────────────────


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    c = get_initialized_db(tmp_path / "session-live.db")
    yield c
    c.close()


@pytest.fixture
def projet_et_admin(conn):
    """Un projet et un VRAI utilisateur admin (ligne en base) — `created_by_user_id` porte une
    FK NOT NULL vers `user.id` : un id synthétique de test sans ligne réelle la violerait."""
    project_id = ProjectRepo(conn).create(name="Portail", connector_type="web", base_url="https://app.example")
    user_id = UserRepo(conn).create(username="Admin", password_hash=access.hacher_mot_de_passe("mdp"),
                                    role=access.ROLE_ADMIN)
    return project_id, user_id


def test_creer_rend_un_jeton_jamais_stocke_en_clair(conn, projet_et_admin):
    project_id, user_id = projet_et_admin

    jeton, expires_at = live_session_tokens.creer(conn, project_id=project_id, created_by_user_id=user_id)

    assert jeton and expires_at
    ligne = conn.execute("SELECT token_hash FROM live_session_token").fetchone()
    assert ligne["token_hash"] != jeton and jeton not in ligne["token_hash"]


def test_consommer_un_jeton_valide_rend_le_projet_et_l_auteur(conn, projet_et_admin):
    project_id, user_id = projet_et_admin
    jeton, _ = live_session_tokens.creer(conn, project_id=project_id, created_by_user_id=user_id)

    resultat = live_session_tokens.consommer(conn, jeton)

    assert resultat == {"project_id": project_id, "created_by_user_id": user_id}


def test_falsifiable_un_jeton_deja_consomme_est_refuse_la_deuxieme_fois(conn, projet_et_admin):
    """Preuve de l'usage unique : sans le `AND used_at=''` de la mise à jour atomique, cette
    deuxième consommation réussirait — exactement le trou qu'ouvrirait une lecture puis une
    écriture séparées sous deux tentatives concurrentes."""
    project_id, user_id = projet_et_admin
    jeton, _ = live_session_tokens.creer(conn, project_id=project_id, created_by_user_id=user_id)

    premiere = live_session_tokens.consommer(conn, jeton)
    deuxieme = live_session_tokens.consommer(conn, jeton)

    assert premiere is not None
    assert deuxieme is None


def test_falsifiable_un_jeton_expire_est_refuse(conn, projet_et_admin):
    """Sans le `AND expires_at > ?`, un jeton pourtant expiré depuis longtemps serait accepté."""
    project_id, user_id = projet_et_admin
    jeton, _ = live_session_tokens.creer(
        conn, project_id=project_id, created_by_user_id=user_id, duree_vie_secondes=-1)

    assert live_session_tokens.consommer(conn, jeton) is None


def test_un_jeton_invente_est_refuse(conn, projet_et_admin):
    """Une chaîne qui n'a jamais été émise ne correspond au hash d'aucune ligne — refusée, sans
    distinction avec les deux autres cas de refus (aucun indice qui aiderait à deviner)."""
    project_id, user_id = projet_et_admin
    live_session_tokens.creer(conn, project_id=project_id, created_by_user_id=user_id)

    assert live_session_tokens.consommer(conn, "un-jeton-jamais-emis-par-personne") is None


# ── La route : réservée à `admin` ─────────────────────────────────────────────────────────────


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "session-live-api.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return TestClient(app_mod.app)


def _user(username: str, role: str) -> int:
    c = get_initialized_db(config.DB_PATH)
    try:
        return UserRepo(c).create(username=username, password_hash=access.hacher_mot_de_passe("mdp"), role=role)
    finally:
        c.close()


def _se_connecter(client, nom):
    assert client.post("/api/auth/login", json={"username": nom, "password": "mdp"}).status_code == 200


@pytest.fixture
def equipe(client):
    """Un projet créé par un admin, avec un `dev`, un `testeur` et un `lecture_seule` MEMBRES —
    même patron que `test_comptes_projet.py::equipe`, réutilisé ici pour la même raison : prouver
    qu'un rôle insuffisant est refusé, pas seulement que l'admin réussit."""
    _user("Root", access.ROLE_ADMIN)
    ids = {nom: _user(nom, role) for nom, role in (("Dev", access.ROLE_DEV), ("Testeuse", access.ROLE_TESTEUR),
                                                    ("Lecteur", access.ROLE_LECTURE_SEULE))}
    _se_connecter(client, "Root")
    pid = client.post("/api/projects", json={"name": "Portail", "connector_type": "web",
                                             "base_url": "https://app.example"}).json()["id"]
    for nom, role in (("Dev", "dev"), ("Testeuse", "testeur"), ("Lecteur", "lecture_seule")):
        assert client.post(f"/api/projects/{pid}/members", json={"user_id": ids[nom], "role": role}).status_code == 201
    return pid


def test_un_admin_obtient_un_jeton(client, equipe):
    _se_connecter(client, "Root")

    r = client.post(f"/api/projects/{equipe}/live-session")

    assert r.status_code == 201
    corps = r.json()
    assert corps["token"] and corps["expires_at"]


def test_un_dev_obtient_aussi_un_jeton(client, equipe):
    """La consigne du lot réserve explicitement l'accès à `admin`/`dev` — plus permissif que
    `start_exploration`, qui exige `admin` seul dans le code actuel (écart assumé, pas un oubli)."""
    _se_connecter(client, "Dev")

    assert client.post(f"/api/projects/{equipe}/live-session").status_code == 201


@pytest.mark.parametrize("nom,attendu", [("Testeuse", 403), ("Lecteur", 403)])
def test_falsifiable_un_role_sous_dev_est_refuse(client, equipe, nom, attendu):
    """Preuve que la garde mord réellement, pas seulement qu'elle est déclarée dans la route :
    testeur et lecture_seule sont chacun refusés — jamais accès à un navigateur réel sur le
    projet, contrairement à admin et dev."""
    _se_connecter(client, nom)

    assert client.post(f"/api/projects/{equipe}/live-session").status_code == attendu


def test_projet_inconnu_rend_404(client):
    _user("Root", access.ROLE_ADMIN)
    _se_connecter(client, "Root")

    assert client.post("/api/projects/999/live-session").status_code == 404


def test_le_jeton_emis_par_la_route_est_bien_celui_qui_deverrouille_la_session(client, equipe):
    """Bout en bout minimal : le jeton renvoyé par l'API est celui-là même que `consommer()`
    accepte — pas un jeton de façade sans rapport avec ce qui est stocké."""
    _se_connecter(client, "Root")
    jeton = client.post(f"/api/projects/{equipe}/live-session").json()["token"]

    c = get_initialized_db(config.DB_PATH)
    try:
        resultat = live_session_tokens.consommer(c, jeton)
    finally:
        c.close()

    assert resultat is not None and resultat["project_id"] == equipe
