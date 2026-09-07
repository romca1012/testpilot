from pathlib import Path

import pytest

from scripts import preflight, verify_deployment
from testpilot import config


def test_preflight_verifie_base_et_repertoire(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PRODUCTION", False)
    monkeypatch.setattr(config, "DB_URL", "")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "testpilot.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "GENERATED_DIR", tmp_path / "generated")
    resultat = preflight.verifier()
    assert resultat["database"] == "ok"
    assert resultat["data_directory"] == "ok"
    assert resultat["behave_runtime"] == "ok"
    assert resultat["generated_directory"] == "ok"
    assert not list(Path(config.DATA_DIR).glob(".preflight-*"))


def test_preflight_refuse_image_sans_harnais(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PRODUCTION", False)
    monkeypatch.setattr(config, "BEHAVE_RUNTIME_DIR", tmp_path)
    with pytest.raises(RuntimeError, match="harnais Behave incomplet"):
        preflight.verifier()


def test_smoke_refuse_http_hors_controle_local():
    with pytest.raises(RuntimeError, match="HTTPS"):
        verify_deployment.verifier("http://testpilot.example")


def test_smoke_verifie_les_routes_sans_authentification(monkeypatch):
    reponses = {
        "/": (200, {"X-Content-Type-Options": "nosniff"}, b"html"),
        "/api/health/live": (200, {"X-Content-Type-Options": "nosniff"}, b'{}'),
        "/api/health/ready": (
            200, {"X-Content-Type-Options": "nosniff"}, b'{"status":"ready"}'),
        "/api/openapi.json": (401, {"X-Content-Type-Options": "nosniff"}, b'{}'),
        "/metrics": (404, {"X-Content-Type-Options": "nosniff"}, b'{}'),
    }
    monkeypatch.setattr(
        verify_deployment, "_get", lambda url: reponses[url.removeprefix("https://tp.test")])
    resultat = verify_deployment.verifier("https://tp.test")
    assert resultat["/api/health/ready"] == 200
