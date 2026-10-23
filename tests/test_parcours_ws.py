"""Étape 7b (A109) : l'enregistrement du parcours d'un cas — preuve avec un VRAI Chromium contre une application locale.

Marqueur `conformance` : exécuté par le job « browser-evidence », exclu de `pytest -q` par défaut.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from starlette.testclient import TestClient

from testpilot import config
from testpilot.api import access
from testpilot.api import app as app_mod
from testpilot.guardrails import concurrency
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, ModuleRepo, ParcoursRepo, UserRepo

pytestmark = pytest.mark.conformance

# Positions fixes : les coordonnées d'un geste désignent l'élément sans dépendre de la mise en page par défaut.
_PAGE = b"""<!doctype html><html><head><style>
body { margin: 0; font: 14px sans-serif; } .p { position: absolute; left: 10px; width: 200px; height: 30px; }
</style></head><body>
<button class="p" style="top:10px" onclick="document.getElementById('total').textContent='30 EUR'">Nouveau</button>
<label class="p" style="top:60px" for="q">Quantite</label>
<input class="p" style="top:100px" id="q" name="quantite">
<select class="p" style="top:150px" name="client" aria-label="Client"><option>Azure</option><option>Gemini</option></select>
<input class="p" style="top:200px" type="password" name="secret" aria-label="Code">
<div class="p" style="top:250px" id="total">0 EUR</div>
<input class="p" style="top:300px" type="text" name="mdp_visible" autocomplete="current-password" aria-label="Mot de passe">
<div class="p" style="top:350px">sans identifiant</div>
<button class="p" style="top:400px" name="action_view_invoice"><span>3</span> Factures</button>
<button class="p" style="top:450px"><span>2</span> Avoirs</button>
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
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{serveur.server_address[1]}"
    serveur.shutdown()


@pytest.fixture(autouse=True)
def _file_fraiche():
    concurrency.reset_default_queue_for_tests()
    yield
    concurrency.reset_default_queue_for_tests()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "parcours-ws.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return TestClient(app_mod.app)


def _cas(client, application: str, role: str = access.ROLE_TESTEUR) -> int:
    conn = get_initialized_db(config.DB_PATH)
    try:
        UserRepo(conn).create(username="Root", password_hash=access.hacher_mot_de_passe("mdp"), role=access.ROLE_ADMIN)
    finally:
        conn.close()
    assert client.post("/api/auth/login", json={"username": "Root", "password": "mdp"}).status_code == 200
    pid = client.post("/api/projects", json={"name": "Boutique", "connector_type": "web", "base_url": application}).json()["id"]
    conn = get_initialized_db(config.DB_PATH)
    try:
        return CaseRepo(conn).create(title="Commande", module_id=ModuleRepo(conn).create(project_id=pid, name="Ventes"))
    finally:
        conn.close()


def _recevoir_jusqua(ws, predicat, max_messages: int = 300) -> dict:
    for _ in range(max_messages):
        message = ws.receive_json()
        if predicat(message):
            return message
    raise AssertionError(f"aucun message satisfaisant après {max_messages} messages")


def _type(nom):
    return lambda m: m.get("type") == nom


def test_un_parcours_reel_est_enregistre_sans_le_mot_de_passe(client, application):
    case_id = _cas(client, application)
    jeton = client.post(f"/api/cases/{case_id}/parcours/session").json()["token"]

    with client.websocket_connect(f"/api/cases/{case_id}/parcours/ws?token={jeton}") as ws:
        _recevoir_jusqua(ws, _type("image"))
        ws.send_json({"type": "clic", "x": 50, "y": 25})                       # Nouveau
        clic = _recevoir_jusqua(ws, _type("action_capturee"))
        assert (clic["action"], clic["role"], clic["nom"]) == ("clic", "button", "Nouveau")

        ws.send_json({"type": "clic", "x": 50, "y": 115})                      # désigne Quantite
        champ = _recevoir_jusqua(ws, _type("champ_designe"))
        assert champ["nom"] == "Quantite" and champ["secret"] is False
        ws.send_json({"type": "saisie", "valeur": "3"})
        saisie = _recevoir_jusqua(ws, _type("action_capturee"))
        assert (saisie["champ"], saisie["valeur"]) == ("quantite", "3")

        ws.send_json({"type": "clic", "x": 50, "y": 165})                      # désigne la liste Client
        liste = _recevoir_jusqua(ws, _type("champ_designe"))
        assert liste["options"] == ["Azure", "Gemini"]
        ws.send_json({"type": "choix", "valeur": "Gemini"})
        choix = _recevoir_jusqua(ws, _type("action_capturee"))
        assert (choix["champ"], choix["valeur"]) == ("client", "Gemini")

        ws.send_json({"type": "clic", "x": 50, "y": 215})                      # désigne le champ secret
        assert _recevoir_jusqua(ws, _type("champ_designe"))["secret"] is True
        ws.send_json({"type": "saisie", "valeur": "S3cret!"})
        assert _recevoir_jusqua(ws, _type("clic_non_enregistre"))["raison"] == "mot_de_passe"

        # Un mot de passe AFFICHÉ en clair (bouton « voir ») reste un mot de passe : jamais gardé.
        ws.send_json({"type": "clic", "x": 50, "y": 315})
        _recevoir_jusqua(ws, _type("champ_designe"))
        ws.send_json({"type": "saisie", "valeur": "S3cret!"})
        assert _recevoir_jusqua(ws, _type("clic_non_enregistre"))["raison"] == "mot_de_passe"

        # « C'est ici que je vérifie » sur un montant : sa désignation technique, JAMAIS ce qu'il affiche (A39).
        ws.send_json({"type": "verifier", "x": 50, "y": 265})
        verif = _recevoir_jusqua(ws, _type("action_capturee"))
        assert verif["action"] == "verifier" and verif["nom"] == "total"
        assert "EUR" not in repr(verif)

        # Un élément sans aucune désignation technique : refusé, jamais désigné par son texte.
        ws.send_json({"type": "verifier", "x": 50, "y": 365})
        assert _recevoir_jusqua(ws, _type("clic_non_enregistre"))["raison"] == "element_sans_designation"

        # Un bouton dont le nom vient de ce qu'il affiche (« 3 Factures ») : son nom technique, jamais son texte.
        ws.send_json({"type": "verifier", "x": 50, "y": 415})
        bouton = _recevoir_jusqua(ws, _type("action_capturee"))
        assert bouton["nom"] == "action_view_invoice" and "Factures" not in repr(bouton)
        ws.send_json({"type": "verifier", "x": 50, "y": 465})                  # sans nom technique : refusé
        assert _recevoir_jusqua(ws, _type("clic_non_enregistre"))["raison"] == "element_sans_designation"

        ws.send_json({"type": "confirmer"})
        confirme = _recevoir_jusqua(ws, _type("confirme"))
        assert confirme["actions"] == 5

    conn = get_initialized_db(config.DB_PATH)
    try:
        enregistre = ParcoursRepo(conn).dernier(case_id)
    finally:
        conn.close()
    assert [a["action"] for a in enregistre["actions"]] == ["clic", "saisie", "choix", "verifier", "verifier"]
    assert "S3cret" not in repr(enregistre) and "30 EUR" not in repr(enregistre)
    assert enregistre["auteur"] == "Root"

    lu = client.get(f"/api/cases/{case_id}/parcours").json()["parcours"][0]
    assert lu["mode_operatoire"][0] == "1. Cliquer sur « Nouveau » (bouton)"


def test_falsifiable_un_jeton_de_parcours_n_ouvre_ni_un_autre_cas_ni_la_connexion_du_projet(client, application):
    case_id = _cas(client, application)
    conn = get_initialized_db(config.DB_PATH)
    try:
        cas = CaseRepo(conn).get(case_id)
        autre = CaseRepo(conn).create(title="Autre", module_id=cas["module_id"])
    finally:
        conn.close()

    jeton = client.post(f"/api/cases/{case_id}/parcours/session").json()["token"]
    with pytest.raises(Exception):
        with client.websocket_connect(f"/api/cases/{autre}/parcours/ws?token={jeton}") as ws:
            ws.receive_json()

    jeton = client.post(f"/api/cases/{case_id}/parcours/session").json()["token"]
    with pytest.raises(Exception):
        with client.websocket_connect(f"/api/projects/{cas['project_id']}/live-session/ws?token={jeton}") as ws:
            ws.receive_json()

    jeton_projet = client.post(f"/api/projects/{cas['project_id']}/live-session").json()["token"]
    with pytest.raises(Exception):
        with client.websocket_connect(f"/api/cases/{case_id}/parcours/ws?token={jeton_projet}") as ws:
            ws.receive_json()
    assert concurrency.get_queue().status().running == 0


def test_rien_n_est_garde_sans_confirmer(client, application):
    case_id = _cas(client, application)
    jeton = client.post(f"/api/cases/{case_id}/parcours/session").json()["token"]

    with client.websocket_connect(f"/api/cases/{case_id}/parcours/ws?token={jeton}") as ws:
        _recevoir_jusqua(ws, _type("image"))
        ws.send_json({"type": "clic", "x": 50, "y": 25})
        _recevoir_jusqua(ws, _type("action_capturee"))
        ws.send_json({"type": "retirer", "rang": 0})
        assert _recevoir_jusqua(ws, _type("action_retiree"))["rang"] == 0
        ws.send_json({"type": "confirmer"})                      # parcours vide : refusé, la session reste ouverte
        assert _recevoir_jusqua(ws, _type("erreur"))["detail"] == "parcours_invalide"
        ws.send_json({"type": "annuler"})

    assert client.get(f"/api/cases/{case_id}/parcours").json()["parcours"] == []


def test_falsifiable_une_connexion_a_la_main_n_entre_pas_dans_le_parcours(client, application, monkeypatch):
    """Revue du 2026-10-23 : connexion automatique en échec → rien n'est capturé avant « Je suis connecté »."""
    from testpilot.connectors import factory

    class _Connecteur:
        def crawl_relogin_hook(self):
            def _echoue(ctx):
                raise RuntimeError("SSO")
            return _echoue

    monkeypatch.setattr(factory, "build_connector", lambda connexion: _Connecteur())
    case_id = _cas(client, application)
    jeton = client.post(f"/api/cases/{case_id}/parcours/session").json()["token"]

    with client.websocket_connect(f"/api/cases/{case_id}/parcours/ws?token={jeton}") as ws:
        assert _recevoir_jusqua(ws, _type("connexion_auto"))["ok"] is False
        ws.send_json({"type": "clic", "x": 50, "y": 115})                      # « identifiant » saisi à la main
        _recevoir_jusqua(ws, _type("champ_designe"))
        ws.send_json({"type": "saisie", "valeur": "jdupont@client.fr"})
        ws.send_json({"type": "clic", "x": 50, "y": 25})
        ws.send_json({"type": "commencer"})
        _recevoir_jusqua(ws, _type("capture_commencee"))
        ws.send_json({"type": "clic", "x": 50, "y": 25})
        clic = _recevoir_jusqua(ws, _type("action_capturee"))
        assert clic["rang"] == 0
        ws.send_json({"type": "retirer", "rang": "zéro"})                      # mal formé : la session tient
        assert _recevoir_jusqua(ws, _type("erreur"))["detail"] == "rang_invalide"
        ws.send_json({"type": "confirmer"})
        assert _recevoir_jusqua(ws, _type("confirme"))["actions"] == 1

    lu = client.get(f"/api/cases/{case_id}/parcours").json()["parcours"][0]
    assert "jdupont" not in repr(lu)
