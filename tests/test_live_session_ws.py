"""La route WebSocket d'une session en direct (sous-lot C, étapes 4-7) — preuve avec un VRAI
Chromium (CDP réel, relais vidéo réel) contre une application locale, aucun mock sur le pilotage
du navigateur.

Marqueur `conformance` : exécuté par le job « browser-evidence », exclu de `pytest -q` par défaut.
"""

from __future__ import annotations

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from starlette.testclient import TestClient

from testpilot import config
from testpilot.api import access
from testpilot.api import app as app_mod
from testpilot.api.routes import live_session as live_session_route
from testpilot.guardrails import concurrency
from testpilot.store import project_login_recordings
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import UserRepo

pytestmark = pytest.mark.conformance

_PAGE = b"""<!doctype html><html><body>
<button id="pays" aria-label="France">France</button>
<div id="apres" style="display:none">
  <label for="pwd">Mot de passe</label>
  <input type="password" id="pwd">
</div>
<script>
document.getElementById('pays').onclick = function () {
  document.getElementById('apres').style.display = 'block';
};
</script>
</body></html>"""


class _Application(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(_PAGE)))
        self.end_headers()
        self.wfile.write(_PAGE)


@pytest.fixture(scope="module")
def application():
    serveur = ThreadingHTTPServer(("127.0.0.1", 0), _Application)
    fil = threading.Thread(target=serveur.serve_forever, daemon=True)
    fil.start()
    yield f"http://127.0.0.1:{serveur.server_address[1]}"
    serveur.shutdown()


@pytest.fixture(autouse=True)
def _file_fraiche():
    """Chaque test part d'une file de concurrence neuve — sinon un test qui laisserait une place
    prise fausserait le suivant (même précaution que `test_concurrency.py`)."""
    concurrency.reset_default_queue_for_tests()
    yield
    concurrency.reset_default_queue_for_tests()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "live-session-ws.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return TestClient(app_mod.app)


def _admin_et_projet(client, application: str) -> int:
    conn = get_initialized_db(config.DB_PATH)
    try:
        UserRepo(conn).create(username="Root", password_hash=access.hacher_mot_de_passe("mdp"),
                              role=access.ROLE_ADMIN)
    finally:
        conn.close()
    assert client.post("/api/auth/login", json={"username": "Root", "password": "mdp"}).status_code == 200
    pid = client.post("/api/projects", json={
        "name": "Portail", "connector_type": "web", "base_url": application,
    }).json()["id"]
    return pid


def _jeton(client, project_id: int) -> str:
    return client.post(f"/api/projects/{project_id}/live-session").json()["token"]


def _recevoir_jusqua(ws, predicat, max_messages: int = 200) -> dict:
    """Lit les messages un par un jusqu'à en trouver un qui satisfait `predicat` — le flux porte
    surtout des images (une par frame de screencast), les messages qui nous intéressent sont
    entremêlés dedans."""
    for _ in range(max_messages):
        message = ws.receive_json()
        if predicat(message):
            return message
    raise AssertionError(f"aucun message satisfaisant après {max_messages} messages")


# ── Jeton : refusé AVANT toute ouverture ──────────────────────────────────────────────────────

def test_falsifiable_un_jeton_invente_est_refuse_avant_l_ouverture(client, application):
    project_id = _admin_et_projet(client, application)

    with pytest.raises(Exception):
        with client.websocket_connect(
                f"/api/projects/{project_id}/live-session/ws?token=jamais-emis") as ws:
            ws.receive_json()

    # Rien n'a été admis dans la file : le refus a lieu avant même `websocket.accept()`.
    assert concurrency.get_queue().status().running == 0


def test_falsifiable_un_jeton_deja_consomme_est_refuse_une_deuxieme_fois(client, application):
    project_id = _admin_et_projet(client, application)
    jeton = _jeton(client, project_id)

    with client.websocket_connect(f"/api/projects/{project_id}/live-session/ws?token={jeton}") as ws:
        _recevoir_jusqua(ws, lambda m: m.get("type") == "image")
        ws.send_json({"type": "annuler"})

    with pytest.raises(Exception):
        with client.websocket_connect(f"/api/projects/{project_id}/live-session/ws?token={jeton}") as ws2:
            ws2.receive_json()


# ── Ouverture réelle : relais vidéo, capture, confirmation ───────────────────────────────────

def test_la_session_recoit_des_images_du_vrai_navigateur(client, application):
    project_id = _admin_et_projet(client, application)
    jeton = _jeton(client, project_id)

    with client.websocket_connect(f"/api/projects/{project_id}/live-session/ws?token={jeton}") as ws:
        image = _recevoir_jusqua(ws, lambda m: m.get("type") == "image")
        assert image["data"]  # JPEG encodé en base64, non vide
        ws.send_json({"type": "annuler"})


def test_un_clic_reel_capture_le_role_et_le_nom_de_l_element(client, application):
    project_id = _admin_et_projet(client, application)
    jeton = _jeton(client, project_id)

    with client.websocket_connect(f"/api/projects/{project_id}/live-session/ws?token={jeton}") as ws:
        _recevoir_jusqua(ws, lambda m: m.get("type") == "image")
        ws.send_json({"type": "clic", "x": 30, "y": 12})
        etape = _recevoir_jusqua(ws, lambda m: m.get("type") == "etape_capturee")
        assert etape["role"] == "button" and etape["name"] == "France"
        ws.send_json({"type": "annuler"})


def test_le_champ_mot_de_passe_visible_arrete_la_capture(client, application):
    project_id = _admin_et_projet(client, application)
    jeton = _jeton(client, project_id)

    with client.websocket_connect(f"/api/projects/{project_id}/live-session/ws?token={jeton}") as ws:
        _recevoir_jusqua(ws, lambda m: m.get("type") == "image")
        ws.send_json({"type": "clic", "x": 30, "y": 12})  # révèle le champ mot de passe
        arret = _recevoir_jusqua(
            ws, lambda m: m.get("type") in ("etape_capturee", "capture_arretee"))
        # Le clic qui révèle le mot de passe EST capturé (il fait partie du chemin) ; l'arrêt
        # suit juste après.
        if arret["type"] == "etape_capturee":
            arret = _recevoir_jusqua(ws, lambda m: m.get("type") == "capture_arretee")
        assert arret["raison"] == "mot_de_passe_visible"
        ws.send_json({"type": "annuler"})


def test_confirmer_ecrit_la_sequence_et_annuler_n_ecrit_rien(client, application):
    project_id = _admin_et_projet(client, application)

    jeton_annule = _jeton(client, project_id)
    with client.websocket_connect(f"/api/projects/{project_id}/live-session/ws?token={jeton_annule}") as ws:
        _recevoir_jusqua(ws, lambda m: m.get("type") == "image")
        ws.send_json({"type": "clic", "x": 30, "y": 12})
        _recevoir_jusqua(ws, lambda m: m.get("type") == "etape_capturee")
        ws.send_json({"type": "annuler"})

    conn = get_initialized_db(config.DB_PATH)
    try:
        assert project_login_recordings.lire(conn, project_id) is None
    finally:
        conn.close()

    jeton_confirme = _jeton(client, project_id)
    with client.websocket_connect(f"/api/projects/{project_id}/live-session/ws?token={jeton_confirme}") as ws:
        _recevoir_jusqua(ws, lambda m: m.get("type") == "image")
        ws.send_json({"type": "clic", "x": 30, "y": 12})
        _recevoir_jusqua(ws, lambda m: m.get("type") == "etape_capturee")
        ws.send_json({"type": "confirmer"})
        confirme = _recevoir_jusqua(ws, lambda m: m.get("type") == "confirme")
        assert confirme["etapes"] == 1

    conn = get_initialized_db(config.DB_PATH)
    try:
        sequence = project_login_recordings.lire(conn, project_id)
    finally:
        conn.close()
    assert sequence == [{"role": "button", "name": "France"}]


def test_recommencer_vide_la_liste_en_memoire_avant_confirmation(client, application):
    project_id = _admin_et_projet(client, application)
    jeton = _jeton(client, project_id)

    with client.websocket_connect(f"/api/projects/{project_id}/live-session/ws?token={jeton}") as ws:
        _recevoir_jusqua(ws, lambda m: m.get("type") == "image")
        ws.send_json({"type": "clic", "x": 30, "y": 12})
        _recevoir_jusqua(ws, lambda m: m.get("type") == "etape_capturee")
        ws.send_json({"type": "recommencer"})
        ws.send_json({"type": "confirmer"})
        confirme = _recevoir_jusqua(ws, lambda m: m.get("type") == "confirme")
        assert confirme["etapes"] == 0

    conn = get_initialized_db(config.DB_PATH)
    try:
        assert project_login_recordings.lire(conn, project_id) == []
    finally:
        conn.close()


def test_falsifiable_un_clic_juste_avant_confirmer_n_est_pas_perdu(client, application):
    """Reproduit exactement le bloquant trouvé en revue verdict-reviewer (2026-09-29) : sans
    l'attente sur `attendre_clics_traites`, envoyer `confirmer` juste après `clic`, SANS attendre
    l'accusé `etape_capturee` intermédiaire, perdait le clic en silence (`{"etapes": 0}` persisté
    alors qu'un clic réel venait d'être envoyé) — reproduit à 100% avant le correctif."""
    project_id = _admin_et_projet(client, application)
    jeton = _jeton(client, project_id)

    with client.websocket_connect(f"/api/projects/{project_id}/live-session/ws?token={jeton}") as ws:
        _recevoir_jusqua(ws, lambda m: m.get("type") == "image")
        ws.send_json({"type": "clic", "x": 30, "y": 12})
        ws.send_json({"type": "confirmer"})  # AUCUNE attente de l'accusé entre les deux
        confirme = _recevoir_jusqua(ws, lambda m: m.get("type") == "confirme")
        assert confirme["etapes"] == 1, "le clic envoyé juste avant confirmer a été perdu"

    conn = get_initialized_db(config.DB_PATH)
    try:
        assert project_login_recordings.lire(conn, project_id) == [{"role": "button", "name": "France"}]
    finally:
        conn.close()


def test_falsifiable_un_clic_juste_avant_recommencer_ne_ressuscite_pas(client, application):
    """Même bloquant, sens inverse : un clic envoyé juste avant `recommencer` (sans attendre son
    accusé) ne doit PAS réapparaître dans la séquence après le vidage — avant le correctif, le
    clic pouvait être traité APRÈS `reinitialiser_etapes()` et survivre à la réinitialisation.

    Le court délai avant `confirmer` est nécessaire pour que ce test morde réellement : envoyé
    immédiatement, `confirmer` lit `service.etapes` quasiment aussi vite que `recommencer` l'a
    vidée, sans laisser au clic (CDP + calcul AccName, quelques dizaines de ms) le temps d'être
    traité — le test « réussirait » alors pour la mauvaise raison (le clic n'a simplement pas eu
    le temps d'atterrir), avec ou sans le correctif. Vérifié en revue verdict-reviewer
    (2026-09-29) : SANS ce délai le test passe même sur le code d'AVANT correctif (faux positif) ;
    AVEC ce délai il échoue de façon fiable (3/3) sur l'ancien code et passe sur le code corrigé."""
    project_id = _admin_et_projet(client, application)
    jeton = _jeton(client, project_id)

    with client.websocket_connect(f"/api/projects/{project_id}/live-session/ws?token={jeton}") as ws:
        _recevoir_jusqua(ws, lambda m: m.get("type") == "image")
        ws.send_json({"type": "clic", "x": 30, "y": 12})
        ws.send_json({"type": "recommencer"})  # AUCUNE attente de l'accusé entre les deux
        time.sleep(0.15)  # laisse une vraie chance au clic de finir son traitement en premier
        ws.send_json({"type": "confirmer"})
        confirme = _recevoir_jusqua(ws, lambda m: m.get("type") == "confirme")
        assert confirme["etapes"] == 0, "le clic envoyé juste avant recommencer a ressuscité"

    conn = get_initialized_db(config.DB_PATH)
    try:
        assert project_login_recordings.lire(conn, project_id) == []
    finally:
        conn.close()


# ── Fermeture garantie (étape 7) — falsifiable, coupure brutale ──────────────────────────────

def test_falsifiable_une_coupure_brutale_libere_le_navigateur_et_la_place_de_la_file(client, application):
    """Preuve exigée par l'étape 7 : simule une coupure SANS déconnexion propre (fermeture brute
    du transport, pas `annuler`/`confirmer`) et vérifie qu'aucune ressource ne reste ouverte
    derrière — le navigateur (thread fermé) ET la place dans la file de concurrence partagée."""
    project_id = _admin_et_projet(client, application)
    jeton = _jeton(client, project_id)

    with client.websocket_connect(f"/api/projects/{project_id}/live-session/ws?token={jeton}") as ws:
        _recevoir_jusqua(ws, lambda m: m.get("type") == "image")
        assert concurrency.get_queue().status().running == 1
        # Coupure brutale : ferme le transport sous-jacent sans envoyer `annuler`/`confirmer` —
        # le serveur reçoit un WebSocketDisconnect, pas un message applicatif.
        ws.close()

    fin = time.monotonic() + 10
    while time.monotonic() < fin and concurrency.get_queue().status().running != 0:
        time.sleep(0.05)

    assert concurrency.get_queue().status().running == 0, (
        "la place de la file de concurrence n'a jamais été libérée après la coupure brutale")


# ── Timeout à deux niveaux ─────────────────────────────────────────────────────────────────

def test_falsifiable_l_inactivite_ferme_la_session_avec_avertissement_prealable(
        client, application, monkeypatch):
    # Marges généreuses par rapport au démarrage réel du navigateur (~1-2 s, mesuré sur les tests
    # précédents) : un délai trop court ferait expirer l'inactivité PENDANT le démarrage, avant
    # même que la première image n'arrive — flaky par construction, pas un bug du code testé.
    monkeypatch.setattr(live_session_route, "DUREE_INACTIVITE_SECONDES", 4)
    monkeypatch.setattr(live_session_route, "DUREE_AVERTISSEMENT_AVANT_INACTIVITE_SECONDES", 2)
    monkeypatch.setattr(live_session_route, "DUREE_ABSOLUE_SECONDES", 60)
    project_id = _admin_et_projet(client, application)
    jeton = _jeton(client, project_id)

    with client.websocket_connect(f"/api/projects/{project_id}/live-session/ws?token={jeton}") as ws:
        _recevoir_jusqua(ws, lambda m: m.get("type") == "image")
        # Aucun clic envoyé : le compteur d'inactivité n'est jamais repoussé.
        avertissement = _recevoir_jusqua(ws, lambda m: m.get("type") == "avertissement_inactivite")
        assert avertissement["secondes_restantes"] == 2
        fermeture = _recevoir_jusqua(ws, lambda m: m.get("type") == "fermeture")
        assert fermeture["raison"] == "inactivite"


def test_falsifiable_une_activite_continue_n_empeche_pas_le_plafond_absolu(
        client, application, monkeypatch):
    """Le deuxième scénario exigé par l'addendum timeout : une activité continue (un clic bien
    avant chaque échéance d'inactivité) ne doit PAS empêcher la fermeture par le plafond absolu,
    filet de sécurité indépendant de l'activité."""
    monkeypatch.setattr(live_session_route, "DUREE_INACTIVITE_SECONDES", 15)
    monkeypatch.setattr(live_session_route, "DUREE_AVERTISSEMENT_AVANT_INACTIVITE_SECONDES", 5)
    # Marge par rapport au démarrage réel du navigateur (~1-2 s, mesuré) : un plafond absolu trop
    # court expirerait PENDANT le démarrage, avant que la première image n'arrive.
    monkeypatch.setattr(live_session_route, "DUREE_ABSOLUE_SECONDES", 3)
    project_id = _admin_et_projet(client, application)
    jeton = _jeton(client, project_id)

    with client.websocket_connect(f"/api/projects/{project_id}/live-session/ws?token={jeton}") as ws:
        _recevoir_jusqua(ws, lambda m: m.get("type") == "image")
        fin = time.monotonic() + 5
        fermeture = None
        while time.monotonic() < fin and fermeture is None:
            ws.send_json({"type": "clic", "x": 200, "y": 200})  # zone vide, jamais interactif
            for _ in range(50):
                message = ws.receive_json()
                if message.get("type") == "fermeture":
                    fermeture = message
                    break
                if message.get("type") == "image":
                    continue
            time.sleep(0.05)

        assert fermeture is not None, "la session ne s'est jamais fermée malgré une activité continue"
        assert fermeture["raison"] == "plafond_absolu"
