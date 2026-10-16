"""Décision A43 (porteur, 2026-10-16) — « L'IA peut agir sur cette application pendant la génération » est coché par
défaut, et changer l'application visée ne le décoche plus (la règle A21 du 2026-10-13 est retirée).

TestPilot vise des environnements de test : l'agent doit pouvoir explorer et essayer pour générer et exécuter juste. Ce que
ces tests gardent : (1) un projet NOUVEAU est autorisé d'office, quel que soit le connecteur ; (2) changer l'adresse ou la
base ne touche plus l'autorisation ; (3) une personne qui la décoche est respectée, et ce choix survit à un changement
d'application. La protection de la production n'est pas ici : elle est gardée par ses propres tests.
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


def _projet(client, connecteur: str) -> int:
    corps = {"name": f"Projet {connecteur}", "connector_type": connecteur, "base_url": "https://recette.exemple.test",
             "database": "recette" if connecteur == "odoo" else "", "username": "testeur", "password": "secret"}
    return client.post("/api/projects", json=corps).json()["id"]


@pytest.mark.parametrize("connecteur", ["odoo", "web"])
def test_falsifiable_un_projet_nouveau_est_autorise_d_office(client, connecteur):
    pid = _projet(client, connecteur)

    assert client.get("/api/projects").json()[0]["id"] == pid
    assert client.get("/api/projects").json()[0]["calibration_writes_enabled"] is True


@pytest.mark.parametrize("corps", [{"base_url": "https://autre.exemple.test"}, {"database": "autre"}])
def test_falsifiable_changer_l_application_ne_retire_plus_l_autorisation(client, corps):
    """A21 retirée : avant, l'autorisation se décochait d'office."""
    pid = _projet(client, "odoo")

    r = client.patch(f"/api/projects/{pid}", json=corps)

    assert r.status_code == 200 and r.json()["calibration_writes_enabled"] is True


def test_un_choix_de_decocher_est_respecte_et_survit_au_changement_d_application(client):
    pid = _projet(client, "web")
    assert client.patch(f"/api/projects/{pid}", json={"calibration_writes_enabled": False}).json()[
        "calibration_writes_enabled"] is False

    r = client.patch(f"/api/projects/{pid}", json={"base_url": "https://autre.exemple.test"})

    assert r.json()["calibration_writes_enabled"] is False
