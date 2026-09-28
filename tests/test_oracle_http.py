"""Lot 07e (C5, D7) — le client HTTP de l'oracle backend.

Un serveur HTTP LOCAL (`http.server`, aucun réseau externe) sert de double d'une API tierce :
requêtes nommées, authentification, comptage et navigation de champ, et distinction stricte entre
« le serveur répond une erreur » (joignable) et « rien ne répond » (injoignable, `OracleIndisponible`).
"""

from __future__ import annotations

import json
import threading
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from testpilot.connectors.oracle_http import (
    OracleHttp,
    OracleIndisponible,
    RequeteOracleInconnue,
    champ,
    compte_resultats,
)


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence le bruit dans la sortie des tests
        pass

    def _repondre(self, code: int, corps: object) -> None:
        payload = b"" if corps is None else json.dumps(corps).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if payload:
            self.wfile.write(payload)

    def do_GET(self):
        if self.path == "/erreur-serveur":
            self._repondre(500, {"erreur": "boom"})
        elif self.path.startswith("/tickets"):
            self._repondre(200, [{"id": 1, "statut": "ouvert"}, {"id": 2, "statut": "ferme"}])
        elif self.path == "/ticket-unique":
            self._repondre(200, {"id": 1, "statut": "ouvert"})
        elif self.path == "/vide":
            self._repondre(200, None)
        elif self.path == "/protege":
            attendu = "Bearer jeton-secret"
            if self.headers.get("Authorization") != attendu:
                self._repondre(401, {"erreur": "non autorisé"})
            else:
                self._repondre(200, [{"id": 1}])
        else:
            self._repondre(404, {"erreur": "introuvable"})

    def do_POST(self):
        longueur = int(self.headers.get("Content-Length") or 0)
        corps = json.loads(self.rfile.read(longueur) or b"{}")
        self._repondre(201, {"recu": corps})


@pytest.fixture
def serveur():
    httpd = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


# ── verifier_joignable ───────────────────────────────────────────────────────────────────────────


def test_un_serveur_qui_repond_meme_en_erreur_est_joignable(serveur):
    OracleHttp(serveur).verifier_joignable()  # ne lève pas : 404 sur "/" prouve que le serveur existe


def test_falsifiable_un_port_ferme_est_injoignable():
    with pytest.raises(OracleIndisponible):
        OracleHttp("http://127.0.0.1:1").verifier_joignable()


# ── executer (requêtes nommées) ─────────────────────────────────────────────────────────────────


def test_executer_une_requete_get_declaree(serveur):
    oracle = OracleHttp(serveur, queries=[{"name": "tickets", "method": "GET", "path": "/tickets"}])
    reponse = oracle.executer("tickets")
    assert compte_resultats(reponse) == 2


def test_executer_une_requete_post_declaree(serveur):
    oracle = OracleHttp(serveur, queries=[
        {"name": "creer", "method": "POST", "path": "/x", "params": {"nom": "test"}}])
    reponse = oracle.executer("creer")
    assert reponse == {"recu": {"nom": "test"}}


def test_falsifiable_une_requete_non_declaree_est_refusee(serveur):
    oracle = OracleHttp(serveur, queries=[{"name": "tickets", "method": "GET", "path": "/tickets"}])
    with pytest.raises(RequeteOracleInconnue, match="tickets"):
        oracle.executer("autre_chose")


def test_authentification_bearer_est_transmise(serveur):
    oracle = OracleHttp(serveur, auth={"type": "bearer", "token": "jeton-secret"},
                        queries=[{"name": "q", "method": "GET", "path": "/protege"}])
    assert compte_resultats(oracle.executer("q")) == 1


def test_falsifiable_sans_authentification_le_serveur_refuse(serveur):
    """401 : `executer` ne l'avale PAS — l'appelant (`_base_helpers._executer_oracle`) le voit
    remonter, jamais confondu avec « requête inconnue »."""
    oracle = OracleHttp(serveur, queries=[{"name": "q", "method": "GET", "path": "/protege"}])
    with pytest.raises(urllib.error.HTTPError):
        oracle.executer("q")


# ── compte_resultats ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("reponse,attendu", [
    (None, 0),
    ([], 0),
    ([1, 2, 3], 3),
    ({"id": 1}, 1),
])
def test_compte_resultats(reponse, attendu):
    assert compte_resultats(reponse) == attendu


# ── champ (navigation JSON) ──────────────────────────────────────────────────────────────────────


def test_champ_navigue_un_objet_simple():
    assert champ({"statut": "ouvert"}, "statut") == "ouvert"


def test_champ_navigue_une_liste_indexee():
    assert champ([{"nom": "a"}, {"nom": "b"}], "1.nom") == "b"
    assert champ({"resultats": [{"nom": "a"}]}, "resultats[0].nom") == "a"


@pytest.mark.parametrize("reponse,chemin", [
    ({"a": 1}, "b"),
    ({"a": 1}, "a.b"),
    ([1, 2], "5"),
    ({"a": [1]}, "a.b"),
])
def test_falsifiable_un_chemin_absent_ou_incoherent_leve(reponse, chemin):
    with pytest.raises((KeyError, IndexError, TypeError)):
        champ(reponse, chemin)
