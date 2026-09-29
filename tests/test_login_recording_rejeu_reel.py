"""Preuve avec un VRAI Chromium (sous-lot D, étape 8) : la séquence enregistrée franchit un écran
de pré-connexion (sélection de pays — le scénario même qui a motivé ce chantier, yros-portail),
puis la détection générique existante (`tenter_connexion_generique`) prend le relais sur le
formulaire ainsi révélé. Marqueur `conformance`, exclu de `pytest -q` par défaut.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from playwright.sync_api import sync_playwright

from testpilot.connectors._web_helpers import (
    SequenceConnexionObsoleteError,
    rejouer_sequence_connexion,
    tenter_connexion_generique,
)

pytestmark = pytest.mark.conformance

_ACCUEIL = b"""<!doctype html><html><body>
<div id="ecran-pays">
  <button id="france">France</button>
</div>
<form id="ecran-connexion" style="display:none">
  <input type="text" id="identifiant" name="identifiant">
  <input type="password" id="motdepasse" name="motdepasse">
  <button type="submit" id="valider">Connexion</button>
</form>
<script>
document.getElementById('france').onclick = function () {
  document.getElementById('ecran-pays').style.display = 'none';
  document.getElementById('ecran-connexion').style.display = 'block';
};
document.getElementById('ecran-connexion').onsubmit = function (e) {
  e.preventDefault();
  window.location.href = '/bienvenue';
};
</script>
</body></html>"""

_BIENVENUE = b"<!doctype html><html><body><h1>Bienvenue, connecte</h1></body></html>"

# Le libellé du bouton a changé, mais reste une SUR-CHAÎNE du nom enregistré (« France » est
# encore présent dans « France métropolitaine ») — le cas précis trouvé en revue verdict-reviewer
# (2026-09-29, vrai Chromium) : sans `exact=True`, `get_by_role` matche par sous-chaîne ET sans
# tenir compte de la casse, cliquant en silence sur un bouton qui n'est PLUS le bon.
_ECRAN_RENOMME = b"""<!doctype html><html><body>
<button id="france">France metropolitaine</button>
</body></html>"""

# Même nom mais casse différente — même défaut par défaut de Playwright, cas distinct de la
# sous-chaîne ci-dessus.
_ECRAN_CASSE_DIFFERENTE = b"""<!doctype html><html><body>
<button id="france">FRANCE</button>
</body></html>"""


class _Application(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path.startswith("/bienvenue"):
            corps = _BIENVENUE
        elif self.path.startswith("/renomme-souschaine"):
            corps = _ECRAN_RENOMME
        elif self.path.startswith("/renomme-casse"):
            corps = _ECRAN_CASSE_DIFFERENTE
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


@pytest.fixture(scope="module")
def page():
    with sync_playwright() as p:
        navigateur = p.chromium.launch(headless=True)
        contexte = navigateur.new_context()
        pg = contexte.new_page()
        yield pg
        contexte.close()
        navigateur.close()


def test_la_sequence_enregistree_franchit_l_ecran_de_pays_puis_la_connexion_aboutit(page, application):
    """Reproduit le scénario même qui motive ce chantier : un écran de sélection de pays
    s'intercale avant le formulaire de connexion — la connexion générique seule (sans la séquence
    enregistrée) ne le franchirait jamais, elle ne cherche qu'un mot de passe/identifiant."""
    page.goto(application)

    rejoue = rejouer_sequence_connexion(page, [{"role": "button", "name": "France"}])
    assert rejoue is True

    soumis = tenter_connexion_generique(page, "alice", "s3cret")
    assert soumis is True
    page.wait_for_load_state("networkidle")
    assert page.url.endswith("/bienvenue")


def test_falsifiable_une_sequence_perimee_leve_sans_tenter_la_connexion(page, application):
    """L'application a changé (le bouton « France » n'existe plus, ex. « FR » à la place) : le
    rejeu doit s'arrêter net avec un message clair, jamais deviner un autre bouton à la place."""
    page.goto(application)

    with pytest.raises(SequenceConnexionObsoleteError, match="Belgique"):
        rejouer_sequence_connexion(page, [{"role": "button", "name": "Belgique"}])


def test_falsifiable_un_libelle_qui_contient_le_nom_enregistre_est_rejete(page, application):
    """Bloquant trouvé en revue verdict-reviewer (2026-09-29, vrai Chromium) : `get_by_role` fait
    par défaut un matching PAR SOUS-CHAÎNE — sans `exact=True`, un bouton renommé « France
    métropolitaine » aurait matché le `name` enregistré « France » et reçu un clic SANS LEVER,
    alors que ce n'est manifestement plus le bon élément. `exact=True` doit rejeter ce cas."""
    page.goto(f"{application}/renomme-souschaine")

    with pytest.raises(SequenceConnexionObsoleteError):
        rejouer_sequence_connexion(page, [{"role": "button", "name": "France"}])


def test_falsifiable_un_libelle_de_casse_differente_est_rejete(page, application):
    """Même défaut de fond, cas distinct : sans `exact=True`, `get_by_role` ignore aussi la
    casse — « FRANCE » aurait matché un `name` enregistré « France »."""
    page.goto(f"{application}/renomme-casse")

    with pytest.raises(SequenceConnexionObsoleteError):
        rejouer_sequence_connexion(page, [{"role": "button", "name": "France"}])
