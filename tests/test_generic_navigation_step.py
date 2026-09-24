"""`steps_library/generic/_generic_steps.py::step_access_home_page` — bug SauceDemo (2026-09-13).

⚠️ Le vrai bug exécuté en conditions réelles sur /dev : `context.page` démarre sur `about:blank`
(`environment.py::playwright_browser`), et RIEN dans toute la bibliothèque `generic/` ne chargeait
jamais l'application — seul `odoo/_odoo_steps.py` savait `page.goto(...)`. L'IA a alors détourné
« j'accède à la section "…" du portail » (fait pour cliquer un onglet d'un portail DÉJÀ chargé) en
lui passant "/" comme s'il s'agissait d'une navigation : capture finale entièrement blanche,
7 cas sur 7 en échec contre SauceDemo alors que l'exploration et la génération avaient réussi.

Ces tests chargent le module de steps directement (même helper que `test_crawl_generique.py` pour
`crawl_domaine.py`) — aucun Playwright réel, `context.page` est un simple espion.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent


def _charger_generic_steps():
    """Importe `_generic_steps.py` avec `_base_helpers` résolvable (layout PLAT réel)."""
    steps_lib = RACINE / "behave_runtime" / "steps_library"
    sys.path.insert(0, str(steps_lib))
    spec = importlib.util.spec_from_file_location(
        "_generic_steps_sous_test", steps_lib / "generic" / "_generic_steps.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _PageEspion:
    def __init__(self):
        self.appels_goto: list[tuple[str, dict]] = []
        # Lot 07a : le step d'entrée lit désormais l'URL courante (pour la connexion automatique) ;
        # la double doit en porter une. Aucun identifiant dans ce contexte : aucune connexion tentée,
        # et les assertions ci-dessous sont inchangées.
        self.url = "about:blank"

    def goto(self, url, **kwargs):
        self.appels_goto.append((url, kwargs))
        self.url = url


class _Contexte:
    def __init__(self, web_url: str = ""):
        self.web_url = web_url
        self.page = _PageEspion()


def test_charge_bien_la_page_d_accueil_via_web_url():
    """Le cœur du correctif : ce step doit être LE point qui quitte `about:blank`."""
    mod = _charger_generic_steps()
    ctx = _Contexte(web_url="https://www.saucedemo.com")

    mod.step_access_home_page(ctx)

    assert ctx.page.appels_goto == [
        ("https://www.saucedemo.com", {"wait_until": "domcontentloaded"})]


def test_refuse_clairement_si_aucune_url_n_est_configuree():
    """Mieux vaut un message actionnable qu'un `page.goto(None)` ou un scénario qui continue à
    l'aveugle sur `about:blank` (exactement le bug SauceDemo, en pire — silencieux).

    ⚠️ `NavigationImpossibleError`, pas `AssertionError` (correctif 2026-09-14, cas C45) : une
    connexion de projet incomplète est un problème d'ENVIRONNEMENT, jamais une preuve que
    l'application se comporte mal — voir `defect_taxonomy._EXCEPTION_TO_CAUSE`."""
    mod = _charger_generic_steps()
    ctx = _Contexte(web_url="")

    with pytest.raises(mod.NavigationImpossibleError, match="URL de l'application introuvable"):
        mod.step_access_home_page(ctx)

    assert ctx.page.appels_goto == []
