"""Décision A21 (porteur, 2026-10-13) — changer l'application visée par un projet retire l'autorisation donnée à l'IA.

« L'IA peut agir sur cette application pendant la génération » est une autorisation donnée POUR UNE application : celle
que le porteur sait être réservée aux tests. Depuis le lot PT-01b, l'adresse se change dans une fenêtre et l'autorisation
se règle dans une autre. Sans cette règle, changer l'adresse laissait l'autorisation suivre le projet vers une application
que personne n'avait désignée comme sûre.

Règle GLOBALE : la même pour tous les connecteurs, sur l'adresse comme sur la base de données.
"""

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import app as app_mod


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return TestClient(app_mod.app)


def _projet_autorise(client, connecteur: str) -> int:
    corps = {"name": f"Projet {connecteur}", "connector_type": connecteur, "base_url": "https://recette.exemple.test",
             "database": "recette" if connecteur == "odoo" else "", "username": "testeur", "password": "secret"}
    pid = client.post("/api/projects", json=corps).json()["id"]
    assert client.patch(f"/api/projects/{pid}", json={"calibration_writes_enabled": True}).json()["calibration_writes_enabled"] is True
    return pid


@pytest.mark.parametrize("connecteur", ["odoo", "web"])
def test_falsifiable_changer_l_adresse_retire_l_autorisation(client, connecteur):
    """Sans la règle, l'autorisation suit le projet vers la nouvelle adresse."""
    pid = _projet_autorise(client, connecteur)

    r = client.patch(f"/api/projects/{pid}", json={"base_url": "https://autre.exemple.test"})

    assert r.status_code == 200
    assert r.json()["base_url"] == "https://autre.exemple.test"
    assert r.json()["calibration_writes_enabled"] is False


def test_falsifiable_changer_la_base_de_donnees_retire_l_autorisation(client):
    """Même serveur, autre base : ce n'est plus la même application."""
    pid = _projet_autorise(client, "odoo")

    r = client.patch(f"/api/projects/{pid}", json={"database": "production"})

    assert r.json()["calibration_writes_enabled"] is False


@pytest.mark.parametrize("corps", [
    {"name": "Renommé"},
    {"connector_version": "17"},
    {"username": "autre.compte"},
    {"browser_locale": "en-GB"},
    {"base_url": "https://recette.exemple.test"},      # la même adresse, renvoyée telle quelle
    {"base_url": "https://RECETTE.exemple.test/"},     # la même, à la casse et à la barre finale près
])
def test_falsifiable_ce_qui_ne_change_pas_l_application_ne_retire_rien(client, corps):
    """Un retrait trop large éteindrait un réglage voulu à chaque enregistrement de la fenêtre du projet."""
    pid = _projet_autorise(client, "odoo")

    r = client.patch(f"/api/projects/{pid}", json=corps)

    assert r.status_code == 200
    assert r.json()["calibration_writes_enabled"] is True


def test_une_autorisation_posee_avec_la_nouvelle_adresse_est_respectee(client):
    """L'ancienne fenêtre montre l'adresse et la case dans le même formulaire : cocher en changeant l'adresse est un choix."""
    pid = _projet_autorise(client, "odoo")

    r = client.patch(f"/api/projects/{pid}", json={"base_url": "https://autre.exemple.test", "calibration_writes_enabled": True})

    assert r.json()["calibration_writes_enabled"] is True


def test_l_autorisation_se_redonne_apres_le_changement(client):
    pid = _projet_autorise(client, "odoo")
    client.patch(f"/api/projects/{pid}", json={"base_url": "https://autre.exemple.test"})

    r = client.patch(f"/api/projects/{pid}", json={"calibration_writes_enabled": True})

    assert r.json()["calibration_writes_enabled"] is True
    assert r.json()["base_url"] == "https://autre.exemple.test"


def test_sans_autorisation_au_depart_rien_ne_change(client):
    pid = client.post("/api/projects", json={"name": "Sans autorisation", "connector_type": "web",
                                             "base_url": "https://recette.exemple.test"}).json()["id"]

    r = client.patch(f"/api/projects/{pid}", json={"base_url": "https://autre.exemple.test"})

    assert r.json()["calibration_writes_enabled"] is False
