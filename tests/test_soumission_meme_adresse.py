"""Un formulaire envoyé puis une page rendue de nouveau À LA MÊME ADRESSE n'est pas « un refus du navigateur » (2026-10-07).

Défaut trouvé par le premier essai réel du banc d'agents : un test de connexion négative (mauvais mot de passe) sortait
`indetermine` / `donnee_refusee` (« L'APPLICATION N'EST PAS EN CAUSE : c'est le jeu de données du test qui est irrecevable »)
alors que l'application refusait correctement. Après le clic, le serveur renvoyait la page de connexion (même chemin) avec un
message d'erreur ET un champ mot de passe vide et obligatoire ; `click_button` ne regardait que le CHEMIN d'URL, concluait
« rien n'a changé » et prenait le champ vide de la NOUVELLE page pour la preuve que le navigateur avait bloqué l'envoi.

Les deux sens sont prouvés avec un vrai Chromium sur un petit serveur local :
- soumission suivie d'une nouvelle page à la même adresse → AUCUNE accusation (nouveau comportement) ;
- vrai blocage par le navigateur (`required` vide, sans `novalidate`) → l'accusation reste levée (aucune régression).

Exclue de `pytest -q` (marker `conformance`).
"""

from __future__ import annotations

import http.server
import sys
import threading
from contextlib import contextmanager
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

_STEPS_LIB = Path(__file__).resolve().parent.parent / "behave_runtime" / "steps_library"
sys.path.insert(0, str(_STEPS_LIB))
import _base_helpers as h  # noqa: E402

pytestmark = pytest.mark.conformance

_RENDU_SERVEUR = b"""<!doctype html><html><body><h1>Connexion</h1>
<p role="alert">Identifiant ou mot de passe incorrect.</p>
<form method="post" action="/connexion" novalidate>
<label for="mdp">Mot de passe</label><input id="mdp" name="mdp" type="password" required>
<button type="submit">Se connecter</button></form></body></html>"""

_FORMULAIRE_NAVIGATEUR = b"""<!doctype html><html><body><h1>Inscription</h1>
<form method="post" action="/inscription">
<label for="nom">Nom</label><input id="nom" name="nom" type="text" required>
<button type="submit">Envoyer</button></form></body></html>"""


class _Serveur(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_a):
        pass

    def _repondre(self, corps: bytes):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(corps)

    def do_GET(self):  # noqa: N802
        self._repondre(_FORMULAIRE_NAVIGATEUR if self.path.startswith("/inscription") else
                       _RENDU_SERVEUR.replace(b"<p role=\"alert\">Identifiant ou mot de passe incorrect.</p>", b""))

    def do_POST(self):  # noqa: N802
        self._lire = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self._repondre(_RENDU_SERVEUR)  # 200 À LA MÊME ADRESSE : le serveur renvoie la page avec une erreur


@contextmanager
def _serveur():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Serveur)
    fil = threading.Thread(target=srv.serve_forever, daemon=True)
    fil.start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}"
    finally:
        srv.shutdown()
        srv.server_close()
        fil.join(timeout=5)


@pytest.fixture(scope="module")
def page():
    with sync_playwright() as pw:
        navigateur = pw.chromium.launch(headless=True)
        p = navigateur.new_context().new_page()
        yield p
        navigateur.close()


def test_une_page_rendue_de_nouveau_a_la_meme_adresse_n_est_pas_un_refus_du_navigateur(page):
    """Falsifiable : avant, `DonneeRefuseeError` « mot_de_passe » — le champ vide d'une NOUVELLE page."""
    with _serveur() as base:
        page.goto(f"{base}/connexion")
        page.get_by_label("Mot de passe").fill("mauvais")

        h.click_button(page, "Se connecter")  # ne doit pas lever

        assert page.url.endswith("/connexion"), "même adresse avant et après"
        assert "incorrect" in page.content(), "c'est bien le rendu du serveur"


def test_un_vrai_blocage_du_navigateur_reste_signale(page):
    """Sens inverse : `required` vide sans `novalidate` — le navigateur refuse d'envoyer ; l'accusation du jeu de données reste."""
    with _serveur() as base:
        page.goto(f"{base}/inscription")

        with pytest.raises(h.DonneeRefuseeError):
            h.click_button(page, "Envoyer")


def test_le_marqueur_distingue_un_document_remplace_d_un_document_conserve(page):
    with _serveur() as base:
        page.goto(f"{base}/inscription")
        jeton = h._poser_marqueur_document(page)

        assert h._document_remplace(page, jeton) is False
        page.goto(f"{base}/inscription")  # même adresse, NOUVEAU document
        assert h._document_remplace(page, jeton) is True


def test_sans_jeton_ou_page_illisible_le_controle_s_execute_comme_avant(page):
    assert h._document_remplace(page, None) is False

    class _Illisible:
        def evaluate(self, *_a):
            raise RuntimeError("Execution context was destroyed")

    assert h._poser_marqueur_document(_Illisible()) is None
    assert h._document_remplace(_Illisible(), "x") is False
