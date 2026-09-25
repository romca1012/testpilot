"""F17 — preuve sur de VRAIES instances Odoo Community (16.0, 17.0, 18.0) du banc de mesure.

Lancer : `scripts/banc_init.sh <version>` puis `pytest -m banc tests/test_navigation_menu_banc.py -v`. Ignoré si le banc
ne répond pas. Trois preuves, dont la FALSIFIABILITÉ :
1. la cause est toujours là : `/web#action=menu` ne rend AUCUNE grille d'applications sur Community ;
2. `navigate_menu` atteint la liste des devis ;
3. avec l'ancien comportement (attendre la grille sur cette route, sans repli), la même navigation ÉCHOUE.
"""

from __future__ import annotations

import os
import sys
import types
import urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "behave_runtime" / "steps_library"))
import _base_helpers as H  # noqa: E402

pytestmark = pytest.mark.banc

BANC = os.environ.get("BANC_URL", "http://127.0.0.1:18069")


def _banc_repond() -> bool:
    try:
        urllib.request.urlopen(BANC + "/web/login", timeout=5)
        return True
    except Exception:
        # En CI (`BANC_REQUIS=1`), un banc absent est un ÉCHEC : un skip passerait pour une preuve qu'on n'a pas faite.
        if os.environ.get("BANC_REQUIS") == "1":
            pytest.fail(f"BANC_REQUIS=1 mais le banc ne répond pas sur {BANC}")
        return False


@pytest.fixture(scope="module")
def _navigateur():
    """UN navigateur pour tout le module (deux `sync_playwright()` imbriqués sont refusés par Playwright)."""
    if not _banc_repond():
        pytest.skip(f"le banc ne répond pas sur {BANC} (scripts/banc_init.sh)")
    with sync_playwright() as pw:
        navigateur = pw.chromium.launch(headless=True)
        yield navigateur
        navigateur.close()


@pytest.fixture(scope="module")
def page(_navigateur):
    p = _navigateur.new_context(viewport={"width": 1400, "height": 900}).new_page()
    p.goto(BANC + "/web/login")
    p.fill("input[name=login]", "admin")
    p.fill("input[name=password]", "admin")
    p.press("input[name=password]", "Enter")
    p.wait_for_timeout(5000)
    return p


@pytest.fixture
def navigateur_neuf(_navigateur):
    """Une page VIERGE (`about:blank`, contexte neuf, aucune session) — comme le début d'un scénario Behave."""
    contexte = _navigateur.new_context(viewport={"width": 1400, "height": 900})
    yield contexte.new_page()
    contexte.close()


@pytest.fixture
def contexte(page):
    return types.SimpleNamespace(page=page, odoo_url=BANC)


def test_la_route_historique_ne_rend_aucune_grille_sur_community(page):
    page.goto(BANC + "/web#action=menu", wait_until="domcontentloaded")
    page.wait_for_timeout(5000)

    assert page.locator(".o_app").count() == 0, (
        "si cette route rend maintenant la grille, F17 n'existe plus sur cette version : revoir le repli")


def test_navigate_menu_atteint_la_liste_des_devis(contexte):
    H.navigate_menu(contexte, "Ventes / Commandes / Devis")

    contexte.page.locator(".o_list_view").first.wait_for(state="visible", timeout=20000)


def test_navigate_menu_sans_connexion_prealable_du_navigateur_atteint_la_liste(navigateur_neuf):
    """F21 : un cas généré n'écrit pas toujours « je me connecte » — le step doit connecter lui-même la page vide."""
    contexte = types.SimpleNamespace(page=navigateur_neuf, odoo_url=BANC, odoo_db="banc",
                                     odoo_user="admin", odoo_password="admin")
    assert navigateur_neuf.url == "about:blank"

    H.navigate_menu(contexte, "Ventes / Commandes / Devis")

    navigateur_neuf.locator(".o_list_view").first.wait_for(state="visible", timeout=20000)


def test_sans_le_garde_de_connexion_la_meme_navigation_echoue(navigateur_neuf, monkeypatch):
    monkeypatch.setattr(H, "connecter_le_navigateur_si_page_vide", lambda ctx: None)  # l'ancien navigate_menu
    monkeypatch.setattr(H, "_repli_adaptatif", lambda *a, **k: None)
    contexte = types.SimpleNamespace(page=navigateur_neuf, odoo_url=BANC, odoo_db="banc",
                                     odoo_user="admin", odoo_password="admin")

    with pytest.raises(PlaywrightTimeout):
        H.navigate_menu(contexte, "Ventes / Commandes / Devis")


def test_avec_l_ancien_comportement_la_meme_navigation_echoue(contexte, monkeypatch):
    def ancien(page, *_a, **_k):  # exactement l'attente d'avant F17 : la grille sur cette route, rien d'autre
        try:
            page.wait_for_selector(".o_app", timeout=15000)
        except PlaywrightTimeout:
            pass

    monkeypatch.setattr(H, "_ouvrir_grille_applications", ancien)
    monkeypatch.setattr(H, "_repli_adaptatif", lambda *a, **k: None)  # jamais de LLM dans ce test

    with pytest.raises(PlaywrightTimeout):
        H.navigate_menu(contexte, "Ventes / Commandes / Devis")
