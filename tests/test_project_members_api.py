from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import access
from testpilot.api import app as app_mod
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import AccessAuditRepo, ProjectAccessRepo, UserRepo


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "members-api.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return TestClient(app_mod.app)


def _user(username: str, role: str = access.ROLE_TESTEUR) -> int:
    conn = get_initialized_db(config.DB_PATH)
    try:
        return UserRepo(conn).create(
            username=username,
            password_hash=access.hacher_mot_de_passe("mdp"),
            role=role,
        )
    finally:
        conn.close()


def _project(client: TestClient) -> int:
    return client.post("/api/projects", json={"name": "P"}).json()["id"]


def test_cycle_de_vie_explicite_d_un_membre(client):
    uid = _user("Awa")
    pid = _project(client)

    created = client.post(f"/api/projects/{pid}/members", json={"user_id": uid, "role": "dev"})
    assert created.status_code == 201
    assert {k: created.json()[k] for k in ("user_id", "role", "status")} == {
        "user_id": uid, "role": "dev", "status": "active"}

    suspended = client.patch(f"/api/projects/{pid}/members/{uid}",
                             json={"status": "suspended"})
    assert suspended.status_code == 200
    assert suspended.json()["status"] == "suspended"

    reactivated = client.patch(f"/api/projects/{pid}/members/{uid}",
                               json={"role": "testeur", "status": "active"})
    assert reactivated.json()["role"] == "testeur"
    assert reactivated.json()["status"] == "active"

    removed = client.delete(f"/api/projects/{pid}/members/{uid}")
    assert removed.status_code == 200
    assert removed.json()["status"] == "removed"


def test_chaque_mutation_reste_alignee_avec_l_ancien_modele(client):
    uid = _user("Awa")
    pid = _project(client)
    client.post(f"/api/projects/{pid}/members", json={"user_id": uid, "role": "dev"})

    conn = get_initialized_db(config.DB_PATH)
    try:
        assert ProjectAccessRepo(conn).override_for_user(pid, uid) == "dev"
    finally:
        conn.close()

    client.patch(f"/api/projects/{pid}/members/{uid}", json={"status": "suspended"})
    conn = get_initialized_db(config.DB_PATH)
    try:
        assert ProjectAccessRepo(conn).override_for_user(pid, uid) == access.ACCES_PROJET_REFUSE
    finally:
        conn.close()


def test_un_non_admin_ne_peut_pas_gerer_les_membres(client):
    admin_id = _user("Root", access.ROLE_ADMIN)
    uid = _user("Awa")
    client.post("/api/auth/login", json={"username": "Root", "password": "mdp"})
    pid = _project(client)
    client.post("/api/auth/login", json={"username": "Awa", "password": "mdp"})

    assert client.get(f"/api/projects/{pid}/members").status_code == 403
    assert client.post(f"/api/projects/{pid}/members",
                       json={"user_id": admin_id, "role": "admin"}).status_code == 403


def test_role_et_statut_inconnus_sont_refuses(client):
    uid = _user("Awa")
    pid = _project(client)
    assert client.post(f"/api/projects/{pid}/members",
                       json={"user_id": uid, "role": "super_admin"}).status_code == 422
    assert client.patch(f"/api/projects/{pid}/members/{uid}",
                        json={"status": "removed"}).status_code == 422


def test_le_dernier_admin_du_projet_ne_peut_pas_etre_suspendu_ou_retire(client):
    root_id = _user("Root", access.ROLE_ADMIN)
    client.post("/api/auth/login", json={"username": "Root", "password": "mdp"})
    pid = _project(client)

    suspended = client.patch(
        f"/api/projects/{pid}/members/{root_id}", json={"status": "suspended"})
    assert suspended.status_code == 409
    assert suspended.json()["code"] == "etat_incompatible"
    assert "dernier Admin actif" in suspended.json()["detail"]

    removed = client.delete(f"/api/projects/{pid}/members/{root_id}")
    assert removed.status_code == 409


def test_un_admin_peut_partir_si_un_autre_admin_actif_reste(client):
    root_id = _user("Root", access.ROLE_ADMIN)
    second_id = _user("Second", access.ROLE_ADMIN)
    client.post("/api/auth/login", json={"username": "Root", "password": "mdp"})
    pid = _project(client)

    result = client.patch(
        f"/api/projects/{pid}/members/{root_id}", json={"status": "suspended"})
    assert result.status_code == 200
    assert result.json()["status"] == "suspended"

    # Le second Admin est bien celui qui conserve la capacité d'administration du projet.
    members = client.get(f"/api/projects/{pid}/members").json()
    assert any(m["user_id"] == second_id and m["role"] == "admin"
               and m["status"] == "active" for m in members)


def test_l_ancienne_route_ne_contourne_pas_la_protection_du_dernier_admin(client):
    root_id = _user("Root", access.ROLE_ADMIN)
    client.post("/api/auth/login", json={"username": "Root", "password": "mdp"})
    pid = _project(client)

    result = client.post(
        f"/api/projects/{pid}/access/users",
        json={"user_id": root_id, "role": access.ACCES_PROJET_REFUSE},
    )
    assert result.status_code == 409


def test_les_autorisations_et_refus_sont_audites(client):
    root_id = _user("Root", access.ROLE_ADMIN)
    awa_id = _user("Awa")
    client.post("/api/auth/login", json={"username": "Root", "password": "mdp"})
    pid = _project(client)

    assert client.patch(
        f"/api/projects/{pid}/members/{root_id}",
        json={"status": "suspended"},
    ).status_code == 409
    assert client.post(
        f"/api/projects/{pid}/members", json={"user_id": awa_id, "role": "dev"}
    ).status_code == 201

    conn = get_initialized_db(config.DB_PATH)
    try:
        audit = AccessAuditRepo(conn).list_for_project(pid)
    finally:
        conn.close()
    assert any(e["action"] == "MEMBER_SUSPENDED" and e["result"] == "denied"
               and e["actor_user_id"] == root_id for e in audit)
    assert any(e["action"] == "MEMBER_ADDED" and e["result"] == "allowed"
               and e["target_user_id"] == awa_id for e in audit)


def test_la_suspension_revoque_immediatement_une_session_deja_ouverte(client):
    _user("Root", access.ROLE_ADMIN)
    awa_id = _user("Awa", access.ROLE_TESTEUR)
    client.post("/api/auth/login", json={"username": "Root", "password": "mdp"})
    pid = _project(client)
    assert client.get(f"/api/projects/{pid}/modules").status_code == 200

    client.post("/api/auth/login", json={"username": "Awa", "password": "mdp"})
    assert client.get(f"/api/projects/{pid}/modules").status_code == 200

    # Un second client Admin suspend Awa pendant que son cookie reste valable.
    admin = TestClient(app_mod.app)
    admin.post("/api/auth/login", json={"username": "Root", "password": "mdp"})
    assert admin.patch(
        f"/api/projects/{pid}/members/{awa_id}", json={"status": "suspended"}
    ).status_code == 200
    assert client.get(f"/api/projects/{pid}/modules").status_code == 404


def test_un_id_de_projet_inconnu_ne_revele_aucun_membre(client):
    _user("Root", access.ROLE_ADMIN)
    client.post("/api/auth/login", json={"username": "Root", "password": "mdp"})
    assert client.get("/api/projects/999999/members").status_code == 404


def test_un_admin_choisit_les_projets_a_la_creation_du_compte(client):
    _user("Root", access.ROLE_ADMIN)
    client.post("/api/auth/login", json={"username": "Root", "password": "mdp"})
    p1 = client.post("/api/projects", json={"name": "Projet autorisé"}).json()["id"]
    p2 = client.post("/api/projects", json={"name": "Projet masqué"}).json()["id"]

    created = client.post("/api/admin/users", json={
        "username": "Aminata", "password": "motdepasse", "role": "testeur",
        "projects": [{"project_id": p1, "role": "dev"}],
    })
    assert created.status_code == 200
    user_id = created.json()["id"]

    accesses = client.get(f"/api/admin/users/{user_id}/projects")
    assert accesses.status_code == 200
    by_project = {p["project_id"]: p for p in accesses.json()}
    assert by_project[p1]["has_access"] is True
    assert by_project[p1]["role"] == "dev"
    assert by_project[p2]["has_access"] is False


def test_les_projets_d_un_compte_peuvent_etre_modifies_depuis_sa_fiche(client):
    _user("Root", access.ROLE_ADMIN)
    client.post("/api/auth/login", json={"username": "Root", "password": "mdp"})
    pid = client.post("/api/projects", json={"name": "Portail"}).json()["id"]
    user_id = client.post("/api/admin/users", json={
        "username": "Awa", "password": "motdepasse", "role": "testeur", "projects": [],
    }).json()["id"]

    updated = client.put(f"/api/admin/users/{user_id}/projects", json={
        "projects": [{"project_id": pid, "role": "lecture_seule"}],
    })
    assert updated.status_code == 200
    assert updated.json()[0]["has_access"] is True
    assert updated.json()[0]["role"] == "lecture_seule"
