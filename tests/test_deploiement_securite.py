"""Gardes qui empêchent un faux profil de production de démarrer."""

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api.app import create_app


def _profil_valide(monkeypatch):
    monkeypatch.setattr(config, "PRODUCTION", True)
    monkeypatch.setattr(config, "DB_URL", "postgresql+psycopg://u:p@db/testpilot")
    monkeypatch.setattr(config, "COOKIE_SECURE", True)
    monkeypatch.setattr(config, "SESSION_SECRET", "s" * 32)
    monkeypatch.setattr(config, "METRICS_TOKEN", "m" * 32)
    monkeypatch.setattr(config, "SECRET_KEY", "cle-fernet-fournie-par-le-coffre")


def test_production_refuse_sqlite_et_les_secrets_implicites(monkeypatch):
    _profil_valide(monkeypatch)
    monkeypatch.setattr(config, "DB_URL", "")
    monkeypatch.setattr(config, "COOKIE_SECURE", False)
    monkeypatch.setattr(config, "SESSION_SECRET", "court")
    monkeypatch.setattr(config, "METRICS_TOKEN", "court")
    monkeypatch.setattr(config, "SECRET_KEY", "")

    with pytest.raises(RuntimeError, match="configuration de production refusée") as erreur:
        config.validate_production()

    message = str(erreur.value)
    assert "PostgreSQL" in message
    assert "COOKIE_SECURE" in message
    assert "SESSION_SECRET" in message
    assert "METRICS_TOKEN" in message
    assert "SECRET_KEY" in message


def test_production_accepte_un_profil_complet(monkeypatch):
    _profil_valide(monkeypatch)
    config.validate_production()


@pytest.fixture
def client_deploiement(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(config, "DATA_DIR", data)
    monkeypatch.setattr(config, "DB_PATH", data / "testpilot.db")
    monkeypatch.setattr(config, "PRODUCTION", False)
    monkeypatch.setattr(config, "METRICS_TOKEN", "mesures-" + "m" * 32)
    monkeypatch.setattr(config, "ADMIN_USERNAME", "")
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "")
    with TestClient(create_app()) as client:
        yield client


def test_sante_readiness_swagger_et_entetes(client_deploiement):
    live = client_deploiement.get("/api/health/live", headers={"X-Request-ID": "preuve-123"})
    ready = client_deploiement.get("/api/health/ready")
    swagger = client_deploiement.get("/api/docs")

    assert live.status_code == 200
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"
    assert swagger.status_code == 200
    assert client_deploiement.get("/api/openapi.json").status_code == 200
    assert live.headers["X-Request-ID"] == "preuve-123"
    assert live.headers["X-Content-Type-Options"] == "nosniff"
    assert live.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in live.headers["Content-Security-Policy"]


def test_metriques_exigent_le_jeton_configure(client_deploiement):
    assert client_deploiement.get("/metrics").status_code == 404

    reponse = client_deploiement.get(
        "/metrics",
        headers={"Authorization": f"Bearer {config.METRICS_TOKEN}"},
    )
    assert reponse.status_code == 200
    assert "testpilot_http_requests_total" in reponse.text
