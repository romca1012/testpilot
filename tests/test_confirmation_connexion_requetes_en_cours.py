"""Régression « yros » (2026-10-06) : l'exploration est revenue à 3 routes d'avant connexion.

Cause mesurée : à l'envoi, le formulaire est remplacé par un état de chargement (le champ mot de
passe disparaît tout de suite) alors que la réponse du proxy d'authentification n'arrive que ~8 s
plus tard. `_attendre_confirmation_post_connexion` concluait « connexion obtenue » dès la
disparition du champ et le crawl partait non authentifié.

Ces tests sont FALSIFIABLES : sur l'ancien code (confirmation = URL changée OU champ disparu),
`test_yros_*` échoue car l'attente sort au premier tour, avec la requête encore en cours.

Le test `conformance` rejoue le scénario dans un VRAI navigateur contre un serveur HTTP local lent.
"""

from __future__ import annotations

import http.server
import threading
import time

import pytest

from testpilot.connectors._web_helpers import (
    _attendre_confirmation_post_connexion,
    _SuiviRequetes,
    remplir_et_soumettre_formulaire_connexion,
    tenter_connexion_generique,
)


class _Requete:
    def __init__(self, resource_type: str = "fetch"):
        self.resource_type = resource_type


class _PageYros:
    """Page factice : le POST démarre au clic, le champ mot de passe disparaît IMMÉDIATEMENT,
    la requête finit au tour `fin_requete`, l'URL change au tour `changement_url`.
    Chaque `wait_for_timeout` = un tour (100 ms simulées)."""

    def __init__(self, *, fin_requete: int = 80, changement_url: int = 85,
                 type_requete: str = "fetch"):
        self.url = "https://portail.test/login"
        self.tour = 0
        self.fin_requete = fin_requete
        self.changement_url = changement_url
        self.type_requete = type_requete
        self.ecouteurs: dict[str, list] = {}
        self.requete = _Requete(type_requete)
        self.envoye = False
        self.retires: list[str] = []

    # --- API Playwright minimale ---
    def on(self, evenement, rappel):
        self.ecouteurs.setdefault(evenement, []).append(rappel)

    def remove_listener(self, evenement, rappel):
        self.retires.append(evenement)
        self.ecouteurs[evenement].remove(rappel)

    def query_selector(self, selector):
        if "password" in selector:
            return None if self.envoye else object()
        return None

    def wait_for_timeout(self, _ms):
        self.tour += 1
        if self.tour == self.fin_requete:
            for rappel in list(self.ecouteurs.get("requestfinished", [])):
                rappel(self.requete)
        if self.tour == self.changement_url:
            self.url = "https://portail.test/accueil"

    def wait_for_load_state(self, *_a, **_kw):
        pass  # Playwright : `networkidle` rend la main aussitôt sur une SPA déjà « calme ».

    def soumettre(self):
        self.envoye = True
        for rappel in list(self.ecouteurs.get("request", [])):
            rappel(self.requete)


def test_yros_attend_la_fin_de_la_requete_meme_si_le_champ_a_disparu():
    page = _PageYros()
    with _SuiviRequetes(page) as suivi:
        page.soumettre()
        _attendre_confirmation_post_connexion(page, "https://portail.test/login", suivi)
    # Falsifiable : l'ancien code rendait la main dès le tour 0 (champ disparu).
    assert page.tour >= page.fin_requete, "sorti alors que la requête d'authentification courait"
    assert suivi.en_cours == 0


def test_requete_qui_ne_finit_jamais_reste_bornee():
    page = _PageYros(fin_requete=10**9, changement_url=10**9)
    with _SuiviRequetes(page) as suivi:
        page.soumettre()
        _attendre_confirmation_post_connexion(page, "https://portail.test/login", suivi)
    assert page.tour == 150  # borne haute : 15 s, jamais un blocage indéfini


def test_les_ressources_statiques_ne_retardent_pas_la_confirmation():
    page = _PageYros(fin_requete=10**9, type_requete="image")
    with _SuiviRequetes(page) as suivi:
        page.soumettre()
        _attendre_confirmation_post_connexion(page, "https://portail.test/login", suivi)
    assert page.tour <= 15  # 1 s de calme exigée, jamais la borne de 15 s (150 tours)


def test_page_sans_ecouteurs_garde_le_comportement_historique():
    class _PageNue:
        url = "https://x.test/login"
        tours = 0

        def query_selector(self, _s):
            return None  # champ déjà disparu

        def wait_for_timeout(self, _ms):
            self.tours += 1

    page = _PageNue()
    with _SuiviRequetes(page) as suivi:
        assert suivi.actif is False
        _attendre_confirmation_post_connexion(page, page.url, suivi)
    assert page.tours == 0


def test_les_ecouteurs_sont_retires_apres_usage():
    page = _PageYros(fin_requete=1, changement_url=2)
    with _SuiviRequetes(page) as suivi:
        page.soumettre()
        _attendre_confirmation_post_connexion(page, "https://portail.test/login", suivi)
    assert sorted(page.retires) == ["request", "requestfailed", "requestfinished"]


def test_connexion_generique_une_page_attend_la_requete():
    class _Champ:
        def __init__(self, page=None, soumet=False):
            self._page, self._soumet = page, soumet

        def fill(self, *_a, **_kw):
            pass

        def press(self, _k):
            if self._soumet:
                self._page.soumettre()

    class _PageGenerique(_PageYros):
        def __init__(self):
            super().__init__()
            self.mdp = _Champ(self, soumet=True)
            self.id = _Champ()

        def query_selector(self, selector):
            if "password" in selector:
                return None if self.envoye else self.mdp
            if "email" in selector or "text" in selector:
                return self.id
            return None

    page = _PageGenerique()
    assert tenter_connexion_generique(page, "u", "p") is True
    assert page.tour >= page.fin_requete


def test_formulaire_enregistre_attend_la_requete():
    class _Loc:
        def __init__(self, page, soumet):
            self._page, self._soumet = page, soumet

        def fill(self, *_a, **_kw):
            pass

        def click(self, **_kw):
            if self._soumet:
                self._page.soumettre()

    class _PageForm(_PageYros):
        def get_by_role(self, role, name=None, exact=False):
            return _Loc(self, soumet=(role == "button"))

    page = _PageForm()
    form = {"champ_identifiant": {"role": "textbox", "name": "Adresse email"},
            "champ_mdp": {"role": "textbox", "name": "Mot de passe"},
            "bouton_soumission": {"role": "button", "name": "Se connecter"}}
    remplir_et_soumettre_formulaire_connexion(page, form, "u", "p")
    assert page.tour >= page.fin_requete


# ── Vrai navigateur : formulaire qui disparaît à l'envoi, POST lent, redirection tardive ──────

_PAGE_LOGIN = b"""<!doctype html><html><body>
<div id="app"><form id="f"><label>Adresse email <input type="text" name="u" aria-label="Adresse email"></label>
<label>Mot de passe <input type="password" name="p" aria-label="Mot de passe"></label>
<button type="submit">Se connecter</button></form></div>
<script>
document.getElementById('f').addEventListener('submit', async (e) => {
  e.preventDefault();
  document.getElementById('app').innerHTML = '<p>Chargement...</p>';
  await new Promise(r => setTimeout(r, 400));  // le POST ne part qu'apres l'etat de chargement
  await fetch('/auth', {method: 'POST'});
  location.href = '/accueil';
});
</script></body></html>"""


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_a):
        pass

    def do_GET(self):  # noqa: N802
        corps = _PAGE_LOGIN if self.path == "/" else b"<html><body>accueil</body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(corps)

    def do_POST(self):  # noqa: N802
        time.sleep(2.5)  # proxy d'authentification lent (yros : ~8 s)
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ok")


@pytest.mark.conformance
def test_navigateur_reel_formulaire_qui_disparait_pendant_un_post_lent():
    sync_api = pytest.importorskip("playwright.sync_api")
    serveur = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{serveur.server_address[1]}/"
    try:
        with sync_api.sync_playwright() as pw:
            nav = pw.chromium.launch()
            try:
                page = nav.new_page()
                page.goto(base)
                form = {"champ_identifiant": {"role": "textbox", "name": "Adresse email"},
                        "champ_mdp": {"role": "textbox", "name": "Mot de passe"},
                        "bouton_soumission": {"role": "button", "name": "Se connecter"}}
                debut = time.time()
                remplir_et_soumettre_formulaire_connexion(page, form, "u", "p")
                assert page.url.endswith("/accueil"), (
                    f"rendu la main avant la fin de l'authentification : {page.url}")
                assert time.time() - debut >= 2.0
            finally:
                nav.close()
    finally:
        serveur.shutdown()


def test_requete_qui_demarre_apres_la_disparition_du_champ_est_attendue():
    """Chronologie yros : le champ disparaît à l'envoi, le POST n'est émis que quelques tours après."""
    page = _PageYros(fin_requete=60, changement_url=65)
    emission = page.wait_for_timeout

    def wait(ms):
        emission(ms)
        if page.tour == 4:  # la requête démarre 400 ms après l'envoi
            for rappel in list(page.ecouteurs.get("request", [])):
                rappel(page.requete)

    page.wait_for_timeout = wait
    with _SuiviRequetes(page) as suivi:
        page.envoye = True  # champ déjà disparu, aucune requête encore émise
        _attendre_confirmation_post_connexion(page, "https://portail.test/login", suivi)
    assert page.tour >= page.fin_requete
