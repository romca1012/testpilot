"""Accès par projet — surcharge du rôle global (migration 31, 2026-08-10).

Portée validée avec le porteur, après vérification du vrai modèle TestRail : garder le rôle
global comme comportement par défaut, ajouter une surcharge PAR PROJET (accès par défaut du
projet, exceptions par compte) — pas de groupes, pas de droit Administrateur séparé.

Invariants figés ici :

1. Résolution : exception par compte > accès par défaut du projet > rôle global (dans cet ordre).
2. `no_access` rend **404**, jamais 403 — un projet sans accès n'existe pas, il ne se confirme
   jamais par un refus.
3. Un projet en `no_access` pour un compte disparaît de `GET /api/projects` pour LUI seul.
4. Un accès par défaut FORCÉ (ex. lecture seule) s'applique même à un compte Testeur globalement.
5. Gérer l'accès (`/access`, `/access/users`) est réservé à l'Admin — et un Admin y accède
   TOUJOURS, même sur un projet qu'il a lui-même mis en `no_access` (sinon il s'y coincerait).
6. Les routes profondes (cas, section) restent hors de cette garde — limite assumée, pas cachée.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import access
from testpilot.api import app as app_mod
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import ProjectAccessRepo, ProjectRepo, UserRepo

_PROJET = {"name": "Recette", "base_url": "http://x", "database": "db",
          "username": "qa", "password": "p"}


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    c = get_initialized_db(tmp_path / "a.db")
    yield c
    c.close()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "a.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return TestClient(app_mod.app)


def _compte(conn_ou_client, username: str, role: str) -> int:
    c = conn_ou_client if hasattr(conn_ou_client, "execute") else get_initialized_db(config.DB_PATH)
    return UserRepo(c).create(username=username,
                              password_hash=access.hacher_mot_de_passe("mdp"), role=role)


def _connecte(client, username: str):
    r = client.post("/api/auth/login", json={"username": username, "password": "mdp"})
    assert r.status_code == 200, r.text


# ── 1. Résolution (unitaire, sans HTTP) ───────────────────────────────────────

def test_sans_rien_regle_le_role_global_s_applique(conn):
    uid = _compte(conn, "Awa", access.ROLE_TESTEUR)
    pid = ProjectRepo(conn).create(name="P", **{k: v for k, v in _PROJET.items() if k != "name"})
    utilisateur = UserRepo(conn).get(uid)
    assert access.role_effectif_projet(conn, utilisateur, pid) == access.ROLE_TESTEUR


def test_l_acces_par_defaut_du_projet_prime_sur_le_role_global(conn):
    uid = _compte(conn, "Awa", access.ROLE_TESTEUR)
    pid = ProjectRepo(conn).create(name="P", **{k: v for k, v in _PROJET.items() if k != "name"})
    ProjectAccessRepo(conn).set_default_access(pid, access.ROLE_LECTURE_SEULE)
    utilisateur = UserRepo(conn).get(uid)
    assert access.role_effectif_projet(conn, utilisateur, pid) == access.ROLE_LECTURE_SEULE


def test_une_exception_par_compte_prime_sur_l_acces_par_defaut(conn):
    uid = _compte(conn, "Awa", access.ROLE_TESTEUR)
    pid = ProjectRepo(conn).create(name="P", **{k: v for k, v in _PROJET.items() if k != "name"})
    ProjectAccessRepo(conn).set_default_access(pid, access.ACCES_PROJET_REFUSE)
    ProjectAccessRepo(conn).set_override(pid, uid, access.ROLE_DEV)
    utilisateur = UserRepo(conn).get(uid)
    assert access.role_effectif_projet(conn, utilisateur, pid) == access.ROLE_DEV


# ── 2. `no_access` → 404, jamais 403, sur une route project_id-scoped ─────────

def test_no_access_par_defaut_rend_404_sur_le_projet(client):
    _compte(client, "Awa", access.ROLE_ADMIN)
    root_id = _compte(client, "Root", access.ROLE_ADMIN)
    _connecte(client, "Awa")
    pid = client.post("/api/projects", json=_PROJET).json()["id"]
    # Un défaut restrictif reste possible à condition de conserver un Admin explicite.
    assert client.post(
        f"/api/projects/{pid}/access/users", json={"user_id": root_id, "role": "admin"}
    ).status_code == 200
    assert client.patch(
        f"/api/projects/{pid}/access", json={"default_access": access.ACCES_PROJET_REFUSE}
    ).status_code == 200

    # Awa n'a pas d'exception : le défaut no_access s'applique bien à elle.
    r = client.get(f"/api/projects/{pid}/modules")
    assert r.status_code == 404


def test_no_access_en_exception_rend_404_meme_role_global_admin(client):
    """Un `no_access` pointé sur un compte précis doit tenir même si son rôle global est Admin —
    c'est une SURCHARGE, elle doit pouvoir aller dans les deux sens."""
    admin_id = _compte(client, "Root", access.ROLE_ADMIN)
    uid = _compte(client, "Awa", access.ROLE_ADMIN)
    conn = get_initialized_db(config.DB_PATH)
    try:
        pid = ProjectRepo(conn).create(name="P", **{k: v for k, v in _PROJET.items() if k != "name"})
        ProjectAccessRepo(conn).set_override(pid, uid, access.ACCES_PROJET_REFUSE)
    finally:
        conn.close()
    _connecte(client, "Awa")
    assert client.get(f"/api/projects/{pid}/modules").status_code == 404


# ── 3. Disparaît de la liste ───────────────────────────────────────────────────

def test_un_projet_no_access_disparait_de_la_liste_pour_ce_compte(client):
    _compte(client, "Root", access.ROLE_ADMIN)
    _connecte(client, "Root")
    pid_visible = client.post("/api/projects", json={**_PROJET, "name": "Visible"}).json()["id"]
    pid_cache = client.post("/api/projects", json={**_PROJET, "name": "Caché"}).json()["id"]

    _compte(client, "Awa", access.ROLE_TESTEUR)
    conn = get_initialized_db(config.DB_PATH)
    try:
        ProjectAccessRepo(conn).set_override(pid_cache, UserRepo(conn).get_by_username("Awa")["id"],
                                             access.ACCES_PROJET_REFUSE)
    finally:
        conn.close()

    _connecte(client, "Awa")
    ids = {p["id"] for p in client.get("/api/projects").json()}
    assert pid_visible in ids
    assert pid_cache not in ids


def test_un_projet_cache_reste_visible_pour_un_AUTRE_compte(client):
    """Le filtre est PAR COMPTE — cacher un projet à Awa ne doit rien changer pour Léo."""
    _compte(client, "Root", access.ROLE_ADMIN)
    _connecte(client, "Root")
    pid = client.post("/api/projects", json=_PROJET).json()["id"]

    _compte(client, "Awa", access.ROLE_TESTEUR)
    _compte(client, "Leo", access.ROLE_TESTEUR)
    conn = get_initialized_db(config.DB_PATH)
    try:
        ProjectAccessRepo(conn).set_override(pid, UserRepo(conn).get_by_username("Awa")["id"],
                                             access.ACCES_PROJET_REFUSE)
    finally:
        conn.close()

    _connecte(client, "Leo")
    assert pid in {p["id"] for p in client.get("/api/projects").json()}


# ── 4. Un accès par défaut FORCÉ s'applique même à un rôle global plus haut ───

def test_un_projet_force_en_lecture_seule_bloque_meme_un_testeur(client):
    root_id = _compte(client, "Root", access.ROLE_ADMIN)
    _connecte(client, "Root")
    pid = client.post("/api/projects", json=_PROJET).json()["id"]
    # Le défaut Lecture seule ne doit pas rétrograder le dernier Admin du projet.
    assert client.post(
        f"/api/projects/{pid}/access/users", json={"user_id": root_id, "role": "admin"}
    ).status_code == 200
    assert client.patch(
        f"/api/projects/{pid}/access", json={"default_access": access.ROLE_LECTURE_SEULE}
    ).status_code == 200

    _compte(client, "Awa", access.ROLE_TESTEUR)
    _connecte(client, "Awa")
    projet = next(p for p in client.get("/api/projects").json() if p["id"] == pid)
    assert projet["effective_role"] == access.ROLE_LECTURE_SEULE
    r = client.post(f"/api/projects/{pid}/modules", json={"name": "M"})
    assert r.status_code == 403
    assert client.get(f"/api/projects/{pid}/modules").status_code == 200   # lecture, elle, passe


# ── 5. Gérer l'accès — Admin seulement, jamais coincé dehors ─────────────────

def test_un_testeur_ne_peut_pas_gerer_l_acces(client):
    _compte(client, "Root", access.ROLE_ADMIN)
    _connecte(client, "Root")
    pid = client.post("/api/projects", json=_PROJET).json()["id"]

    _compte(client, "Awa", access.ROLE_TESTEUR)
    _connecte(client, "Awa")
    assert client.get(f"/api/projects/{pid}/access").status_code == 403
    assert client.patch(f"/api/projects/{pid}/access",
                        json={"default_access": access.ROLE_TESTEUR}).status_code == 403


def test_un_admin_ne_peut_pas_laisser_le_projet_sans_admin_actif(client):
    """Le garde-fou Lot A : aucun réglage par défaut ne peut retirer le dernier Admin."""
    _compte(client, "Root", access.ROLE_ADMIN)
    _connecte(client, "Root")
    pid = client.post("/api/projects", json=_PROJET).json()["id"]

    r = client.patch(f"/api/projects/{pid}/access",
                     json={"default_access": access.ACCES_PROJET_REFUSE})
    assert r.status_code == 409
    assert r.json()["code"] == "etat_incompatible"

    # L'opération refusée est atomique : Root reste Admin et le défaut reste inchangé.
    assert client.get(f"/api/projects/{pid}/modules").status_code == 200
    assert client.get(f"/api/projects/{pid}/access").json()["default_access"] == ""


def test_ajouter_et_retirer_une_exception_par_compte(client):
    _compte(client, "Root", access.ROLE_ADMIN)
    _connecte(client, "Root")
    pid = client.post("/api/projects", json=_PROJET).json()["id"]
    uid = _compte(client, "Awa", access.ROLE_TESTEUR)

    r = client.post(f"/api/projects/{pid}/access/users", json={"user_id": uid, "role": "dev"})
    assert r.status_code == 200
    overrides = r.json()["overrides"]
    assert len(overrides) == 1
    assert overrides[0]["user_id"] == uid
    assert overrides[0]["role"] == "dev"

    r = client.delete(f"/api/projects/{pid}/access/users/{uid}")
    assert r.status_code == 200
    assert r.json()["overrides"] == []


def test_un_role_inconnu_est_refuse(client):
    _compte(client, "Root", access.ROLE_ADMIN)
    _connecte(client, "Root")
    pid = client.post("/api/projects", json=_PROJET).json()["id"]
    r = client.patch(f"/api/projects/{pid}/access", json={"default_access": "super_admin"})
    assert r.status_code == 422


# ── 6. La migration est rejouable ─────────────────────────────────────────────

def test_la_migration_est_rejouable_sans_planter(tmp_path, monkeypatch):
    from testpilot.store.db import _migrate_31_acces_par_projet

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    conn = get_initialized_db(tmp_path / "rejeu.db")
    try:
        _migrate_31_acces_par_projet(conn)
        _migrate_31_acces_par_projet(conn)
    finally:
        conn.close()
