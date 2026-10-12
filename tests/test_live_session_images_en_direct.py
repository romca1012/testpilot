"""Session en direct : l'image du navigateur distant suit un clic SANS attendre la commande suivante.

Mesuré le 2026-10-12 (/dev, portail d'intégration Odoo, puis reproduit ici) : les images produites par un clic ne partaient
qu'au clic suivant — l'écran affichait toujours l'état d'avant, le formulaire ouvert par le clic n'apparaissait pas. La boucle
du fil navigateur attendait la commande suivante sur une file Python ; l'API synchrone de Playwright ne distribue un
événement (`Page.screencastFrame`) que pendant un de ses propres appels.

Vrai Chromium, page locale. Marqueur `conformance` : exécuté par le job « browser-evidence », exclu de `pytest -q`.
"""

from __future__ import annotations

import base64
import io
import queue
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from PIL import Image

from testpilot.api.services.live_session_service import SessionLive
from testpilot.guardrails import concurrency

pytestmark = pytest.mark.conformance

# Le clic sur « Ouvrir » fait apparaître un bloc rouge APRÈS un délai : l'image qui le montre ne peut pas être produite pendant
# le traitement du clic lui-même. Elle ne peut arriver que si le fil navigateur relève les événements entre deux commandes.
_RETARD_MS = 800
_PAGE = f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Images en direct</title>
<style>body{{margin:0;background:#fff}} button{{position:absolute;left:100px;top:100px;width:200px;height:60px}}
#bloc{{position:absolute;left:400px;top:300px;width:300px;height:200px;background:#e00000;display:none}}</style></head>
<body><button type="button"
  onclick="setTimeout(function(){{document.getElementById('bloc').style.display='block'}}, {_RETARD_MS})">Ouvrir</button>
<div id="bloc"></div></body></html>""".encode()


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
    yield f"http://127.0.0.1:{serveur.server_address[1]}/"
    serveur.shutdown()


@pytest.fixture
def session(application):
    concurrency.reset_default_queue_for_tests()
    s = SessionLive(project={"id": 0, "base_url": application, "connector_type": "web"}, queue_label="images-en-direct")
    s.demarrer()
    assert s.pret.wait(30), "la session n'a jamais été prête"
    yield s
    s.demander_fermeture()
    s.attendre_fermeture(15)
    concurrency.reset_default_queue_for_tests()


def _montre_le_bloc_rouge(donnee_b64: str) -> bool:
    """Le pixel au centre du bloc est-il rouge ? Lu sur l'image réellement envoyée à l'écran."""
    image = Image.open(io.BytesIO(base64.b64decode(donnee_b64))).convert("RGB")
    largeur, hauteur = image.size
    rouge, vert, bleu = image.getpixel((int(550 / 1440 * largeur), int(400 / 900 * hauteur)))
    return rouge > 180 and vert < 80 and bleu < 80


def _messages_pendant(session: SessionLive, secondes: float) -> list[dict]:
    """Tout ce que la session émet pendant `secondes`, SANS lui envoyer la moindre commande."""
    recus, fin = [], time.monotonic() + secondes
    while time.monotonic() < fin:
        try:
            recus.append(session.sortantes.get(timeout=0.05))
        except queue.Empty:
            continue
    return recus


def test_falsifiable_l_image_suit_le_clic_sans_attendre_la_commande_suivante(session):
    """Sans relève des événements entre deux commandes, aucune image du bloc rouge n'arrive : elle restait en attente
    jusqu'au clic suivant (ce test échoue alors, sans jamais bloquer)."""
    initiales = _messages_pendant(session, 1.0)
    assert any(m["type"] == "image" for m in initiales), "aucune image initiale"
    assert not any(m["type"] == "image" and _montre_le_bloc_rouge(m["data"]) for m in initiales)

    session.soumettre_clic({"type": "clic", "x": 200, "y": 130})   # le bouton « Ouvrir »
    apres_le_clic = _messages_pendant(session, _RETARD_MS / 1000 + 3.0)

    assert any(m["type"] == "etape_capturee" and m.get("name") == "Ouvrir" for m in apres_le_clic), "clic non pris en compte"
    assert any(m["type"] == "image" and _montre_le_bloc_rouge(m["data"]) for m in apres_le_clic), (
        "aucune image ne montre le résultat du clic : l'écran serait resté sur l'état d'avant")


def test_un_clic_soumis_pendant_la_releve_des_evenements_est_traite(session):
    """La relève par tranches ne fait perdre aucun clic : trois clics soumis coup sur coup sont tous traités."""
    _messages_pendant(session, 0.5)

    for _ in range(3):
        session.soumettre_clic({"type": "clic", "x": 200, "y": 130})

    assert session.attendre_clics_traites(timeout=10) is True
    recus = _messages_pendant(session, 0.5)
    assert sum(1 for m in recus if m["type"] == "etape_capturee") == 3
