"""Preuve de bout en bout (étape 10 de la consigne, sous-lot E) : une VRAIE session en direct
(sous-lot C) capture un clic réel sur un écran de pré-connexion, confirme, écrit en base — puis
une VRAIE exploration (`exploration_service`, sous-lot D) relancée sur ce même projet franchit cet
écran AUTOMATIQUEMENT, sans qu'un humain ne reclique nulle part cette fois, et atteint des pages
qui n'existent QUE derrière lui.

Ce test échoue si UN SEUL maillon de la chaîne est cassé (capture, écriture, lecture, rejeu,
crawl) — pas seulement si chaque brique testée séparément (sous-lots A à D, chacune déjà couverte
par ses propres tests) semble correcte isolément. Le test de contrôle ci-dessous (même application,
mais sans jamais enregistrer de séquence) prouve que l'écran bloque RÉELLEMENT l'exploration en
l'absence de la fonctionnalité — sans lui, le test positif ne prouverait rien (il pourrait
« réussir » même si le rejeu ne faisait jamais rien).

Marqueur `conformance` : vrai Chromium de bout en bout (CDP réel, crawl réel), exclu de
`pytest -q` par défaut, exécuté par le job « browser-evidence ».
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from starlette.testclient import TestClient

from testpilot import config
from testpilot.api import access
from testpilot.api import app as app_mod
from testpilot.api.services import exploration_service
from testpilot.generation import domain_model
from testpilot.guardrails import concurrency
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import UserRepo

pytestmark = pytest.mark.conformance

# Reproduit le scénario même qui motive ce chantier (YROS/Sapian, CONTINUITE §0) : un écran de
# sélection de pays s'intercale, par une VRAIE navigation serveur (pas un simple display:none côté
# client) — sans quoi `tenter_connexion_generique` trouverait le champ mot de passe caché dans le
# DOM et le remplirait quand même via `force=True`, et le test de contrôle ne prouverait rien.
_ACCUEIL = b"""<!doctype html><html><body>
<button id="france" aria-label="France">France</button>
<script>
document.getElementById('france').onclick = function () {
  window.location.href = '/connexion';
};
</script>
</body></html>"""

_CONNEXION = b"""<!doctype html><html><body>
<form id="ecran-connexion">
  <input type="text" id="identifiant" name="identifiant">
  <input type="password" id="motdepasse" name="motdepasse">
  <button type="submit" id="valider">Connexion</button>
</form>
<script>
document.getElementById('ecran-connexion').onsubmit = function (e) {
  e.preventDefault();
  window.location.href = '/espace-client';
};
</script>
</body></html>"""

_ESPACE_CLIENT = b"""<!doctype html><html><body>
<h1>Espace client</h1>
<a href="/espace-client/profil">Profil</a>
</body></html>"""

_PROFIL = b"<!doctype html><html><body><h1>Profil</h1></body></html>"


class _Application(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path.startswith("/espace-client/profil"):
            corps = _PROFIL
        elif self.path.startswith("/espace-client"):
            corps = _ESPACE_CLIENT
        elif self.path.startswith("/connexion"):
            corps = _CONNEXION
        else:
            corps = _ACCUEIL
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)


@pytest.fixture(scope="module")
def application():
    serveur = ThreadingHTTPServer(("127.0.0.1", 0), _Application)
    fil = threading.Thread(target=serveur.serve_forever, daemon=True)
    fil.start()
    yield f"http://127.0.0.1:{serveur.server_address[1]}"
    serveur.shutdown()


@pytest.fixture(autouse=True)
def _file_fraiche():
    """Même précaution que `test_live_session_ws.py` : une file de concurrence neuve par test."""
    concurrency.reset_default_queue_for_tests()
    yield
    concurrency.reset_default_queue_for_tests()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "e2e-live-session.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    # `domain_model.DOMAIN_DIR` est résolu à l'import depuis `config.DATA_DIR` (constante de
    # module) — le monkeypatch ci-dessus ne le change pas rétroactivement (garde-fou
    # `tests/conftest.py::_garde_donnees_reelles`, qui ferait échouer ce test s'il écrivait dans
    # le vrai `data/domain/` du poste).
    monkeypatch.setattr(domain_model, "DOMAIN_DIR", tmp_path / "domain")
    return TestClient(app_mod.app)


def _admin_et_projet(client, application: str, nom: str) -> int:
    conn = get_initialized_db(config.DB_PATH)
    try:
        if UserRepo(conn).get_by_username("Root") is None:
            UserRepo(conn).create(username="Root", password_hash=access.hacher_mot_de_passe("mdp"),
                                  role=access.ROLE_ADMIN)
    finally:
        conn.close()
    assert client.post("/api/auth/login", json={"username": "Root", "password": "mdp"}).status_code == 200
    r = client.post("/api/projects", json={
        "name": nom, "connector_type": "web", "base_url": application,
        "username": "alice", "password": "s3cret",
    })
    assert r.status_code < 300, r.text
    return r.json()["id"]


def _recevoir_jusqua(ws, predicat, max_messages: int = 200) -> dict:
    for _ in range(max_messages):
        message = ws.receive_json()
        if predicat(message):
            return message
    raise AssertionError(f"aucun message satisfaisant après {max_messages} messages")


def _capturer_et_confirmer(client, project_id: int) -> None:
    """Session en direct RÉELLE (sous-lot C, vrai CDP) : un vrai clic sur le bouton « France »,
    confirmé — jamais une séquence écrite à la main dans le test."""
    jeton = client.post(f"/api/projects/{project_id}/live-session").json()["token"]
    with client.websocket_connect(f"/api/projects/{project_id}/live-session/ws?token={jeton}") as ws:
        _recevoir_jusqua(ws, lambda m: m.get("type") == "image")
        ws.send_json({"type": "clic", "x": 30, "y": 12})
        etape = _recevoir_jusqua(ws, lambda m: m.get("type") == "etape_capturee")
        assert etape["role"] == "button" and etape["name"] == "France"
        ws.send_json({"type": "confirmer"})
        confirme = _recevoir_jusqua(ws, lambda m: m.get("type") == "confirme")
        assert confirme["etapes"] == 1


def _explorer(client, project_id: int) -> dict | None:
    """Exploration RÉELLE (crawl Playwright complet, sous-lot D branché dessus par
    `exploration_service.start_exploration`), appelée en synchrone — la preuve de bout en bout n'a
    rien à gagner à réintroduire le thread de fond que `run_exploration` porte en production."""
    conn = get_initialized_db(config.DB_PATH)
    try:
        job_id, params = exploration_service.start_exploration(conn, project_id)
    finally:
        conn.close()
    exploration_service.run_exploration(
        job_id, project_id=project_id, connexion=params["connexion"], max_pages=20)
    job = exploration_service.get_job(job_id)
    assert job is not None
    if job["status"] != "done":
        return None
    return domain_model.charger_par_projet_id(project_id)


def test_bout_en_bout_capture_confirmation_puis_exploration_automatique(client, application):
    """Le test exigé par l'étape 10 : capture réelle → confirmation réelle → exploration réelle
    qui franchit l'obstacle SEULE, sans qu'un humain ne reclique nulle part cette fois-ci."""
    project_id = _admin_et_projet(client, application, "Portail bout-en-bout")

    _capturer_et_confirmer(client, project_id)

    modele = _explorer(client, project_id)
    assert modele is not None, "l'exploration a échoué alors qu'une séquence était enregistrée"
    routes = set(modele["pages"])
    assert "/espace-client" in routes, (
        "l'exploration n'a jamais dépassé l'écran de pré-connexion malgré la séquence enregistrée "
        f"— routes atteintes : {sorted(routes)}")
    assert "/espace-client/profil" in routes, (
        "l'exploration a atteint /espace-client mais pas au-delà — le crawl lui-même n'a pas "
        f"vraiment continué après la connexion — routes atteintes : {sorted(routes)}")


def test_falsifiable_sans_sequence_enregistree_l_exploration_reste_bloquee(client, application):
    """Contrôle exigé par l'étape 10 (« ce test doit échouer si un seul maillon est cassé ») : le
    MÊME projet, la MÊME application, mais SANS jamais passer par la session en direct. Si
    l'exploration atteignait quand même /espace-client, le test positif ci-dessus ne prouverait
    rien de plus que « /espace-client est toujours accessible » — l'écran doit réellement bloquer
    en l'absence de la fonctionnalité pour que le test positif ait un sens."""
    project_id = _admin_et_projet(client, application, "Portail sans enregistrement")

    modele = _explorer(client, project_id)
    routes = set(modele["pages"]) if modele else set()
    assert "/espace-client" not in routes, (
        "l'exploration a franchi l'écran de pré-connexion SANS aucune séquence enregistrée — "
        "l'application de test ne bloque rien, ce test de contrôle ne prouve donc rien "
        f"(routes atteintes : {sorted(routes)})")
