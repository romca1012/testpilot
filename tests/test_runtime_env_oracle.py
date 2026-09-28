"""Lot 07e (C5, D7) — transmission de l'oracle backend au sous-processus (`project_env`) et refus
de `verifier_connexion` quand l'oracle configuré est INJOIGNABLE (jamais un repli silencieux —
même discipline que le reste de `runtime_env.py`, voir sa docstring de module).
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from testpilot.connectors.oracle_config import ENV_ORACLE
from testpilot.connectors.runtime_env import ConnexionIncomplete, verifier_connexion


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.send_response(404)
        self.end_headers()


@pytest.fixture
def oracle_joignable():
    httpd = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


_PROJET_WEB = {"connector_type": "web", "base_url": "https://exemple.invalid"}


def test_project_env_ne_transmet_rien_sans_oracle_configure():
    from testpilot.connectors.runtime_env import project_env

    env = project_env({**_PROJET_WEB, "oracle_type": ""})
    assert ENV_ORACLE not in env


def test_project_env_transmet_la_configuration_oracle_decodee():
    from testpilot.connectors.runtime_env import project_env

    env = project_env({
        **_PROJET_WEB, "oracle_type": "http", "oracle_base_url": "https://api.interne.invalid",
        "oracle_auth": json.dumps({"type": "bearer", "token": "T"}),
        "oracle_queries": json.dumps([{"name": "q", "method": "GET", "path": "/q"}]),
    })
    assert json.loads(env[ENV_ORACLE]) == {
        "base_url": "https://api.interne.invalid",
        "auth": {"type": "bearer", "token": "T"},
        "queries": [{"name": "q", "method": "GET", "path": "/q"}],
    }


def test_project_env_transmet_l_oracle_meme_pour_un_projet_odoo():
    """L'oracle n'est pas propre au connecteur `web` — un projet Odoo peut aussi recouper contre
    une API tierce (contrairement à la stratégie d'auth, qui ne concerne que le navigateur)."""
    from testpilot.connectors.runtime_env import project_env

    env = project_env({
        "connector_type": "odoo", "base_url": "http://odoo", "database": "d", "username": "u",
        "password": "p", "oracle_type": "http", "oracle_base_url": "https://api.interne.invalid",
    })
    assert ENV_ORACLE in env


def test_verifier_connexion_accepte_un_oracle_joignable(oracle_joignable):
    env = verifier_connexion({**_PROJET_WEB, "oracle_type": "http", "oracle_base_url": oracle_joignable})
    assert json.loads(env[ENV_ORACLE])["base_url"] == oracle_joignable


def test_falsifiable_verifier_connexion_refuse_un_oracle_injoignable():
    with pytest.raises(ConnexionIncomplete, match="injoignable"):
        verifier_connexion({**_PROJET_WEB, "oracle_type": "http",
                            "oracle_base_url": "http://127.0.0.1:1"})


def test_verifier_connexion_sans_oracle_ignore_la_verification_de_joignabilite():
    """Comportement historique inchangé : sans oracle configuré, aucun appel réseau supplémentaire."""
    env = verifier_connexion({**_PROJET_WEB, "oracle_type": ""})
    assert ENV_ORACLE not in env
