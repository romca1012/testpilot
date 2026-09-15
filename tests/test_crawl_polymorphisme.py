"""Étape 1.1 du plan de consolidation (audit « Le pari Mabl/Testim », 2026-09-15) : le crawl
choisit ses paramètres via le CONNECTEUR du projet, plus par un `if connector_type == "odoo"` en
dur dans `exploration_service.py::_crawl`.

⚠️ **Le défaut que ça ferme.** `connectors/factory.py` s'était déjà donné pour mission de
centraliser ce choix (« un seul endroit à faire évoluer le jour où un troisième connecteur
arrive ») et l'avait fait pour la génération et la réparation (2026-09-11) — mais pas pour le
crawl, resté couplé. Ces tests vérifient les 4 méthodes de crawl connecteur par connecteur, PUIS
prouvent que `exploration_service.py` n'a plus besoin d'être modifié pour un 3ᵉ type.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from urllib.parse import urlparse

from testpilot.connectors.base import Connector
from testpilot.connectors.generic_web import GenericWebConnector
from testpilot.connectors.odoo import OdooConnector

RACINE = Path(__file__).resolve().parent.parent


def _charger_crawl_domaine():
    """Même helper que `test_crawl_generique.py` : importe le script sans le lancer."""
    sys.path.insert(0, str(RACINE / "behave_runtime" / "steps_library"))
    spec = importlib.util.spec_from_file_location(
        "_crawl_domaine_sous_test_polymorphisme", RACINE / "scripts" / "crawl_domaine.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Page:
    def __init__(self, url):
        self.url = url


def _odoo() -> OdooConnector:
    return OdooConnector(url="http://x", database="d", user="u", password="p")


# ── Défauts génériques de `Connector` (mesurés sur SauceDemo) ───────────────────

def test_le_defaut_generique_part_de_la_page_courante():
    """Jamais une racine en dur : sur une appli dont "/" EST le formulaire de connexion (ex.
    SauceDemo), y retourner après coup perdrait la session tout juste établie (bug réel,
    2026-09-11)."""
    conn = GenericWebConnector(url="http://app.local")
    assert conn.crawl_roots(_Page("http://app.local/dashboard")) == ["/dashboard"]


def test_le_defaut_generique_n_exclut_que_les_assets():
    conn = GenericWebConnector(url="http://app.local")
    motif = conn.crawl_exclusion_pattern()
    assert motif.search("/assets/logo.png")
    assert not motif.search("/web/login"), "rien de spécifique à un ERP dans le défaut générique"


def test_le_defaut_generique_suit_les_ancres_hash():
    assert GenericWebConnector(url="http://app.local").crawl_follow_hash_anchors() is True


# ── Overrides d'OdooConnector — comportement HISTORIQUE strictement inchangé ────

def test_odoo_garde_ses_racines_historiques_quelle_que_soit_la_page():
    assert _odoo().crawl_roots(_Page("http://x/n-importe-quoi")) == ["/my/home", "/myservices"]


def test_odoo_exclut_le_back_office_le_generique_ne_l_exclut_pas():
    assert _odoo().crawl_exclusion_pattern().search("/web/login")
    assert not GenericWebConnector(url="http://x").crawl_exclusion_pattern().search("/web/login")


def test_odoo_n_suit_jamais_les_ancres_hash():
    assert _odoo().crawl_follow_hash_anchors() is False


def test_odoo_et_le_script_de_crawl_partagent_les_memes_racines_et_exclusions():
    """Les constantes sont DUPLIQUÉES (`scripts/crawl_domaine.py` est un script AUTONOME,
    utilisable en CLI sans le moindre projet ni connecteur) — rien dans le code ne tient cet
    accord, ce test si (même patron que `test_les_deux_noms_de_variable_denv_concordent`)."""
    cd = _charger_crawl_domaine()
    conn = _odoo()
    assert conn.crawl_roots(_Page("http://x/peu-importe")) == cd.RACINES
    assert conn.crawl_exclusion_pattern().pattern == cd._HORS_PERIMETRE.pattern


# ── Les crochets de (re)connexion ────────────────────────────────────────────

def test_generic_relogin_hook_delegue_a_la_detection_partagee(monkeypatch):
    import testpilot.connectors.generic_web as gw
    appels = []
    monkeypatch.setattr(gw, "tenter_connexion_generique",
                        lambda page, user, password: appels.append((page, user, password)))

    class _PageConnexion:
        def goto(self, url, **_k):
            pass

        def wait_for_load_state(self, *_a, **_k):
            pass

    conn = GenericWebConnector(url="http://app.local", user="bob", password="secret")
    ctx = types.SimpleNamespace(page=_PageConnexion())
    conn.crawl_relogin_hook()(ctx)

    assert appels == [(ctx.page, "bob", "secret")]


def test_odoo_relogin_hook_pose_le_contexte_puis_delegue_a_playwright_login(monkeypatch):
    sys.path.insert(0, str(RACINE / "behave_runtime" / "steps_library"))
    import _base_helpers as H
    appels = []
    monkeypatch.setattr(H, "playwright_login", lambda ctx: appels.append(dict(vars(ctx))))

    ctx = types.SimpleNamespace(page=object())
    _odoo().crawl_relogin_hook()(ctx)

    assert appels[0]["odoo_url"] == "http://x"
    assert appels[0]["odoo_db"] == "d"
    assert appels[0]["odoo_user"] == "u"
    assert appels[0]["odoo_password"] == "p"


# ── La preuve architecturale : `exploration_service.py` ne connaît plus AUCUN connecteur ────

class _FakePage:
    """Reprend le patron de `test_crawl_generique.py::_FakePage` — un site tient dans un dict
    chemin → liens sortants."""

    def __init__(self, pages: dict[str, list[str]]):
        self.url = ""
        self._pages = pages

    def goto(self, url, **_kwargs):
        self.url = url

    def wait_for_load_state(self, *_args, **_kwargs):
        pass

    def evaluate(self, _script):
        chemin = urlparse(self.url).path or "/"
        liens = [{"href": h, "text": "", "role": None, "id": ""}
                for h in self._pages.get(chemin, [])]
        return {"champs": [], "actions": [], "formulaires": [], "titre": "", "liens": liens}


class _FakeBrowser:
    def __init__(self, page):
        self._page = page

    def new_page(self):
        return self._page

    def close(self):
        pass


class _FakePlaywrightContext:
    def __init__(self, browser):
        self.chromium = types.SimpleNamespace(launch=lambda: browser)

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class _ConnecteurFactice(Connector):
    """Un 3ᵉ connecteur, jamais vu par `exploration_service.py` — la preuve que le couplage est
    parti : ce fichier n'a reçu AUCUNE modification pour que ce test passe."""

    def __init__(self):
        self.connecte: list[bool] = []

    def connect(self):
        ...

    def disconnect(self):
        ...

    def get_schema(self, model):
        raise NotImplementedError

    def search(self, model, filters, limit=0):
        raise NotImplementedError

    def read(self, model, ids, fields):
        raise NotImplementedError

    def inspect_form(self, page_url):
        raise NotImplementedError

    def discover_route(self, path_pattern, sample_id=None):
        raise NotImplementedError

    def create(self, model, vals):
        raise NotImplementedError

    def delete(self, model, ids):
        raise NotImplementedError

    def crawl_roots(self, page):
        return ["/accueil-factice"]

    def crawl_relogin_hook(self):
        def _login(ctx):
            self.connecte.append(True)
            ctx.page.goto("http://factice.local/accueil-factice")
        return _login


def test_exploration_service_ne_branche_plus_sur_connector_type(monkeypatch):
    import testpilot.api.services.exploration_service as es

    connecteur = _ConnecteurFactice()
    monkeypatch.setattr("testpilot.connectors.factory.build_connector",
                        lambda *_a, **_k: connecteur)

    page = _FakePage({"/accueil-factice": ["/autre-page"], "/autre-page": []})
    fake_pw = _FakePlaywrightContext(_FakeBrowser(page))
    monkeypatch.setattr("playwright.sync_api.sync_playwright", lambda: fake_pw)

    resultat = es._crawl(
        {"base_url": "http://factice.local", "database": "", "username": "", "password": "",
         "connector_type": "un-type-que-personne-ne-connait", "nom": "Test"},
        max_pages=10)

    assert connecteur.connecte == [True], "le premier login doit passer par le connecteur"
    assert set(resultat["pages"]) == {"/accueil-factice", "/autre-page"}
