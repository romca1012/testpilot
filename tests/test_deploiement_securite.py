"""Gardes qui empêchent un faux profil de production de démarrer."""

import base64
import hashlib
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api.app import create_app


def _profil_valide(monkeypatch):
    monkeypatch.setattr(config, "PRODUCTION", True)
    monkeypatch.setattr(config, "PUBLIC_URL", "https://testpilot.example.test")
    monkeypatch.setattr(config, "PASSWORD_MIN_LENGTH", 15)  # plancher prod depuis l'audit 2026-09-07
    monkeypatch.setattr(config, "DB_URL", "postgresql+psycopg://u:p@db/testpilot")
    monkeypatch.setattr(config, "COOKIE_SECURE", True)
    monkeypatch.setattr(config, "SESSION_SECRET", "s" * 32)
    monkeypatch.setattr(config, "METRICS_TOKEN", "m" * 32)
    monkeypatch.setattr(config, "SECRET_KEY", "cle-fernet-fournie-par-le-coffre")


def test_production_refuse_sqlite_et_les_secrets_implicites(monkeypatch):
    _profil_valide(monkeypatch)
    monkeypatch.setattr(config, "DB_URL", "")
    monkeypatch.setattr(config, "PUBLIC_URL", "http://incorrect/path")
    monkeypatch.setattr(config, "PASSWORD_MIN_LENGTH", 8)
    monkeypatch.setattr(config, "COOKIE_SECURE", False)
    monkeypatch.setattr(config, "SESSION_SECRET", "court")
    monkeypatch.setattr(config, "METRICS_TOKEN", "court")
    monkeypatch.setattr(config, "SECRET_KEY", "")

    with pytest.raises(RuntimeError, match="configuration de production refusée") as erreur:
        config.validate_production()

    message = str(erreur.value)
    assert "PostgreSQL" in message
    assert "PUBLIC_URL" in message
    assert "PASSWORD_MIN_LENGTH" in message
    assert "COOKIE_SECURE" in message
    assert "SESSION_SECRET" in message
    assert "METRICS_TOKEN" in message
    assert "SECRET_KEY" in message


def test_production_accepte_un_profil_complet(monkeypatch):
    _profil_valide(monkeypatch)
    config.validate_production()


def test_production_refuse_un_mot_de_passe_admin_trop_court(monkeypatch):
    _profil_valide(monkeypatch)
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "trop-court")
    with pytest.raises(RuntimeError, match="ADMIN_PASSWORD"):
        config.validate_production()


def test_production_refuse_une_requete_cross_site_avant_la_base(monkeypatch):
    _profil_valide(monkeypatch)
    monkeypatch.setattr(config, "ADMIN_USERNAME", "")
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "")
    client = TestClient(create_app())
    reponse = client.post(
        "/api/auth/login", json={"username": "x", "password": "y"},
        headers={"Origin": "https://attaquant.example", "Sec-Fetch-Site": "cross-site"},
    )
    assert reponse.status_code == 403
    assert reponse.json()["detail"] == "origine refusée"


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


# ── Le hash CSP du script anti-scintillement de thème (bug réel, 2026-09-15) ────────────────────
#
# `frontend/index.html` porte un <script> écrit en clair (jamais compilé par Vite, donc jamais
# servi depuis `'self'` comme un script de bundle) qui pose la classe de thème AVANT le premier
# rendu — sans lui, la page affiche un flash du mauvais thème. La CSP (`script-src 'self'`, sans
# `'unsafe-inline'`) le bloquait en SILENCE côté navigateur : aucune requête HTTP, donc rien côté
# serveur ne le voyait. Trouvé en production en cliquant « lancer » sur un cas (un rechargement
# complet de page, pas une navigation interne à la SPA, réexécute ce script). Le hash exact du
# script est maintenant listé dans la CSP — ce test empêche les deux de diverger en silence si
# quelqu'un modifie un jour ce script sans recalculer son hash.

def _hash_csp_du_script_inline(chemin_index_html: Path) -> str:
    brut = chemin_index_html.read_bytes()
    match = re.search(rb"<script>(.*?)</script>", brut, re.DOTALL)
    assert match, "aucun <script> inline trouvé dans index.html — ce test doit être mis à jour"
    empreinte = hashlib.sha256(match.group(1)).digest()
    return "sha256-" + base64.b64encode(empreinte).decode()


def test_le_hash_csp_correspond_au_script_de_theme_reel(client_deploiement):
    chemin = Path(__file__).resolve().parent.parent / "frontend" / "index.html"
    if not chemin.exists():
        pytest.skip("frontend/index.html absent sur ce poste")

    attendu = _hash_csp_du_script_inline(chemin)
    reponse = client_deploiement.get("/api/health/live")

    assert attendu in reponse.headers["Content-Security-Policy"], (
        f"le script inline de frontend/index.html a changé sans que son hash CSP ne soit "
        f"recalculé dans app.py — hash attendu : {attendu!r}")


def test_metriques_exigent_le_jeton_configure(client_deploiement):
    assert client_deploiement.get("/metrics").status_code == 404

    reponse = client_deploiement.get(
        "/metrics",
        headers={"Authorization": f"Bearer {config.METRICS_TOKEN}"},
    )
    assert reponse.status_code == 200
    assert "testpilot_http_requests_total" in reponse.text
