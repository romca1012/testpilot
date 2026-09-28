"""Lot 07e (C5, D7) — l'API des réglages d'oracle backend d'un projet : validation à la saisie
(422 en français), et le secret d'authentification jamais relu (write-only, même règle que
`password`/`totp_secret`)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import app as app_mod
from testpilot.store.db import get_initialized_db

_PROJET = {"name": "Portail", "connector_type": "web", "base_url": "https://exemple.invalid"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "a.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return TestClient(app_mod.app)


def _conn(tmp_path=None):
    return get_initialized_db(config.DB_PATH)


def test_creation_sans_oracle_ne_change_rien(client):
    resp = client.post("/api/projects", json=_PROJET)
    assert resp.status_code == 201
    body = resp.json()
    assert body["oracle_type"] == "" and body["oracle_base_url"] == "" and body["has_oracle_auth"] is False
    assert body["oracle_queries"] == []


def test_creation_avec_oracle_http_valide(client):
    corps = {**_PROJET, "oracle_type": "http", "oracle_base_url": "https://api.interne.invalid",
             "oracle_auth": json.dumps({"type": "bearer", "token": "SECRET-JETON"}),
             "oracle_queries": json.dumps([{"name": "tickets_ouverts", "method": "GET", "path": "/t"}])}
    resp = client.post("/api/projects", json=corps)
    assert resp.status_code == 201
    body = resp.json()
    assert body["oracle_type"] == "http"
    assert body["oracle_base_url"] == "https://api.interne.invalid"
    assert body["oracle_queries"] == [{"name": "tickets_ouverts", "method": "GET", "path": "/t"}]
    assert body["has_oracle_auth"] is True


def test_falsifiable_le_secret_d_authentification_n_apparait_jamais_dans_la_reponse(client):
    corps = {**_PROJET, "oracle_type": "http", "oracle_base_url": "https://api.interne.invalid",
             "oracle_auth": json.dumps({"type": "bearer", "token": "SECRET-JETON-UNIQUE"})}
    resp = client.post("/api/projects", json=corps)
    assert "SECRET-JETON-UNIQUE" not in resp.text


def test_falsifiable_oracle_http_sans_adresse_est_refuse_422(client):
    resp = client.post("/api/projects", json={**_PROJET, "oracle_type": "http"})
    assert resp.status_code == 422
    assert "adresse" in resp.json()["detail"]


def test_falsifiable_authentification_illisible_est_refusee_422(client):
    corps = {**_PROJET, "oracle_type": "http", "oracle_base_url": "https://api.interne.invalid",
             "oracle_auth": "pas du json"}
    resp = client.post("/api/projects", json=corps)
    assert resp.status_code == 422


def test_le_secret_est_chiffre_au_repos(client):
    corps = {**_PROJET, "oracle_type": "http", "oracle_base_url": "https://api.interne.invalid",
             "oracle_auth": json.dumps({"type": "bearer", "token": "SECRET-AU-REPOS"})}
    pid = client.post("/api/projects", json=corps).json()["id"]

    conn = _conn()
    brut = conn.execute("SELECT oracle_auth FROM project WHERE id=?", (pid,)).fetchone()[0]
    conn.close()
    assert "SECRET-AU-REPOS" not in brut and brut.startswith("enc:v1:")


def test_patch_modifie_les_reglages_d_oracle(client):
    pid = client.post("/api/projects", json=_PROJET).json()["id"]

    resp = client.patch(f"/api/projects/{pid}", json={
        "oracle_type": "http", "oracle_base_url": "https://api.interne.invalid",
        "oracle_queries": json.dumps([{"name": "q", "method": "GET", "path": "/q"}])})

    assert resp.status_code == 200
    body = resp.json()
    assert body["oracle_type"] == "http"
    assert body["oracle_queries"] == [{"name": "q", "method": "GET", "path": "/q"}]


def test_falsifiable_patch_qui_ne_touche_que_l_authentification_est_valide(client):
    """La rotation d'un jeton seul (sans retoucher type/adresse/requêtes) doit quand même être
    validée — sinon une authentification illisible se glisserait sans le 422 attendu."""
    corps = {**_PROJET, "oracle_type": "http", "oracle_base_url": "https://api.interne.invalid"}
    pid = client.post("/api/projects", json=corps).json()["id"]

    resp = client.patch(f"/api/projects/{pid}", json={"oracle_auth": "pas du json"})

    assert resp.status_code == 422


def test_patch_sans_champ_oracle_ne_touche_pas_a_l_oracle_existant(client):
    """`None` = n'y touche pas — même discipline que les autres champs de connexion (`ProjectPatch`)."""
    corps = {**_PROJET, "oracle_type": "http", "oracle_base_url": "https://api.interne.invalid"}
    pid = client.post("/api/projects", json=corps).json()["id"]

    resp = client.patch(f"/api/projects/{pid}", json={"description": "note"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["oracle_type"] == "http" and body["oracle_base_url"] == "https://api.interne.invalid"
