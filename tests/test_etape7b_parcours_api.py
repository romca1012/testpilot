"""Étape 7b (A109) : qui peut enregistrer le parcours d'un cas, et l'historique gardé (jamais écrasé)."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from testpilot import config
from testpilot.api import access
from testpilot.api import app as app_mod
from testpilot.parametres import parcours
from testpilot.store import live_session_tokens
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, ModuleRepo, ParcoursRepo, UserRepo


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "parcours-api.db")
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
def cas(client):
    _user("Root", access.ROLE_ADMIN)
    ids = {nom: _user(nom, role) for nom, role in (("Dev", access.ROLE_DEV), ("Testeuse", access.ROLE_TESTEUR),
                                                    ("Lecteur", access.ROLE_LECTURE_SEULE))}
    _se_connecter(client, "Root")
    pid = client.post("/api/projects", json={"name": "Boutique", "connector_type": "web",
                                             "base_url": "https://app.example"}).json()["id"]
    for nom, role in (("Dev", "dev"), ("Testeuse", "testeur"), ("Lecteur", "lecture_seule")):
        assert client.post(f"/api/projects/{pid}/members", json={"user_id": ids[nom], "role": role}).status_code == 201
    c = get_initialized_db(config.DB_PATH)
    try:
        return CaseRepo(c).create(title="Commande", module_id=ModuleRepo(c).create(project_id=pid, name="Ventes"))
    finally:
        c.close()


@pytest.mark.parametrize("nom", ["Root", "Dev", "Testeuse"])
def test_testeur_developpeur_et_administrateur_peuvent_enregistrer(client, cas, nom):
    _se_connecter(client, nom)

    r = client.post(f"/api/cases/{cas}/parcours/session")

    assert r.status_code == 201
    c = get_initialized_db(config.DB_PATH)
    try:
        assert live_session_tokens.consommer(c, r.json()["token"])["case_id"] == cas
    finally:
        c.close()


def test_falsifiable_la_lecture_seule_ne_peut_pas_enregistrer_mais_lit_le_mode_operatoire(client, cas):
    _se_connecter(client, "Lecteur")

    assert client.post(f"/api/cases/{cas}/parcours/session").status_code == 403
    assert client.get(f"/api/cases/{cas}/parcours").status_code == 200


def test_un_nouveau_parcours_s_ajoute_a_l_historique(client, cas):
    c = get_initialized_db(config.DB_PATH)
    try:
        pid = CaseRepo(c).get(cas)["project_id"]
        depot = ParcoursRepo(c)
        premier = depot.enregistrer(project_id=pid, case_id=cas, auteur="Root", actions=parcours.normaliser(
            [{"action": "clic", "role": "button", "nom": "Nouveau"}]))
        second = depot.enregistrer(project_id=pid, case_id=cas, auteur="Dev", actions=parcours.normaliser(
            [{"action": "clic", "role": "link", "nom": "Commandes"}]))
        depot.rattacher_version(premier, 42)
    finally:
        c.close()
    _se_connecter(client, "Lecteur")

    lus = client.get(f"/api/cases/{cas}/parcours").json()["parcours"]

    assert [p["id"] for p in lus] == [second, premier]
    assert lus[0]["mode_operatoire"] == ["1. Cliquer sur « Commandes » (lien)"]
    assert lus[1]["version_id"] == 42


def test_cas_inconnu_rend_404(client, cas):
    _se_connecter(client, "Root")

    assert client.get("/api/cases/99999/parcours").status_code in (403, 404)
    assert client.post("/api/cases/99999/parcours/session").status_code in (403, 404)
