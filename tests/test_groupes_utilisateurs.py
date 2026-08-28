from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import access
from testpilot.api import app as app_mod
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import (
    ProjectAccessRepo,
    ProjectGroupAccessRepo,
    ProjectRepo,
    UserGroupRepo,
    UserRepo,
)


def _user(username: str) -> int:
    conn = get_initialized_db(config.DB_PATH)
    try:
        return UserRepo(conn).create(
            username=username,
            password_hash=access.hacher_mot_de_passe("motdepasse"),
            role=access.ROLE_TESTEUR,
        )
    finally:
        conn.close()


def test_cycle_de_vie_groupe_utilisateurs(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "groups.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    client = TestClient(app_mod.app)
    awa = _user("awa")
    leo = _user("leo")

    created = client.post("/api/admin/users/groups", json={
        "name": "Équipe recette", "user_ids": [awa, leo],
    })
    assert created.status_code == 200, created.text
    group = created.json()
    assert group["member_count"] == 2
    assert {m["username"] for m in group["members"]} == {"awa", "leo"}

    updated = client.put(f"/api/admin/users/groups/{group['id']}", json={
        "name": "Recette Sénégal", "user_ids": [awa],
    })
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Recette Sénégal"
    assert [m["username"] for m in updated.json()["members"]] == ["awa"]

    assert client.delete(f"/api/admin/users/groups/{group['id']}").status_code == 204
    assert client.get("/api/admin/users/groups").json() == []


def test_un_groupe_refuse_un_utilisateur_inconnu(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "groups-invalid.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    client = TestClient(app_mod.app)
    response = client.post("/api/admin/users/groups", json={
        "name": "Fantômes", "user_ids": [999],
    })
    assert response.status_code == 422


def test_acces_groupe_se_cumule_et_exception_individuelle_prime(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "group-access.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    conn = get_initialized_db(config.DB_PATH)
    try:
        users = UserRepo(conn)
        uid = users.create(username="membre", password_hash="x", role=access.ROLE_LECTURE_SEULE)
        pid = ProjectRepo(conn).create(name="Projet groupe")
        g1 = UserGroupRepo(conn).create("Testeurs", [uid])
        g2 = UserGroupRepo(conn).create("Développeurs", [uid])
        groupes = ProjectGroupAccessRepo(conn)
        groupes.set(pid, g1, access.ROLE_TESTEUR)
        groupes.set(pid, g2, access.ROLE_DEV)
        user = users.get(uid)

        assert access.role_effectif_projet(conn, user, pid) == access.ROLE_DEV

        # Comme TestRail : l'exception explicite du compte passe avant ses groupes.
        ProjectAccessRepo(conn).set_override(pid, uid, access.ROLE_LECTURE_SEULE)
        assert access.role_effectif_projet(conn, user, pid) == access.ROLE_LECTURE_SEULE
    finally:
        conn.close()
