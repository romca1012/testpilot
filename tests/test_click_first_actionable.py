"""Piste (b) — la fragilité de rendu : `click_first_actionable` ancre l'attente sur l'ÉLÉMENT
qui devient actionnable, jamais sur `count()` (lecture DOM instantanée) ni sur `networkidle`.

Contexte mesuré : exec 30 a timeouté sur `get_by_role("tab", name="Ordinateurs")` alors que
`/myservices` était la BONNE page (sonde du 2026-07-19 : l'onglet y est, `role=tab`, cliquable).
Cause plausible : l'onglet est construit en JS, et un garde `count() > 0` instantané le rate
avant que Playwright ait pu attendre. Le primitif supprime ce garde.

Comme le reste des tests de steps (cf. `test_select_option_stricte`), on n'ouvre AUCUN navigateur :
on injecte un faux `page`/`locator`. Ce qu'on verrouille, c'est le CONTRAT du primitif.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "behave_runtime" / "steps_library"))

import _base_helpers as H  # noqa: E402
from playwright.sync_api import TimeoutError as PlaywrightTimeout  # noqa: E402


class FauxLocator:
    """Un locator qui note ce qu'on lui demande. `count()` renvoie 0 — l'élément n'est PAS là au
    moment du check instantané (c'est exactement la course que le primitif ne doit plus perdre) ;
    seul `click()` décide, en simulant l'auto-attente d'actionnabilité de Playwright."""

    def __init__(self, page, selector, click_leve):
        self.page = page
        self.selector = selector
        self._click_leve = click_leve

    @property
    def first(self):
        return self

    def count(self):
        return 0

    def click(self, timeout=None):
        self.page.clicks.append((self.selector, timeout))
        leve = self._click_leve(self.selector) if callable(self._click_leve) else self._click_leve
        if leve:
            raise PlaywrightTimeout(f"Locator.click: Timeout {timeout}ms exceeded")


class FauxPage:
    def __init__(self, url, click_leve):
        self.url = url
        self.clicks = []
        self._click_leve = click_leve

    def locator(self, selector):
        return FauxLocator(self, selector, self._click_leve)


def test_clique_meme_quand_l_element_apparait_en_retard():
    """Élément rendu en retard : `count()` vaut 0 au check, mais le clic RÉUSSIT (Playwright a
    auto-attendu). Le primitif ne doit PAS se laisser arrêter par `count()` — c'est la régression
    exacte de l'ancien `assert link.count() > 0` qui échouait avant tout attente."""
    page = FauxPage("http://odoo/myservices", click_leve=False)

    H.click_first_actionable(
        page, ["[role='tab']:has-text('Ordinateurs')"], quoi="Onglet 'Ordinateurs'")

    assert len(page.clicks) == 1, "doit avoir CLIQUÉ, sans s'arrêter à count()==0"
    _, timeout = page.clicks[0]
    assert timeout and timeout > 0, "l'attente d'actionnabilité passée au clic doit être bornée > 0"


def test_essaie_les_candidats_dans_l_ordre_jusqu_au_premier_actionnable():
    """Un candidat non actionnable (timeout) n'arrête pas : on passe au suivant, dans l'ordre."""
    page = FauxPage("http://odoo/myservices", click_leve=lambda sel: "mauvais" in sel)

    H.click_first_actionable(
        page,
        ["a.mauvais:has-text('Ordinateurs')", "[role='tab']:has-text('Ordinateurs')"],
        quoi="Onglet 'Ordinateurs'")

    assert [s for s, _ in page.clicks] == [
        "a.mauvais:has-text('Ordinateurs')", "[role='tab']:has-text('Ordinateurs')"]


def test_element_durablement_absent_echoue_vite_borne_et_nomme_la_cible_et_l_url():
    """Élément absent partout : échec RAPIDE (chaque candidat borné), non silencieux, avec un
    message qui nomme la CIBLE et l'URL — pour que le diagnostic porte la vraie cause (§0002),
    pas un « introuvable » trompeur."""
    page = FauxPage("http://odoo/my/home", click_leve=True)  # tout timeout

    with pytest.raises(AssertionError) as exc:
        H.click_first_actionable(
            page,
            ["[role='tab']:has-text('Ordinateurs')", "a:has-text('Ordinateurs')"],
            quoi="Onglet 'Ordinateurs'", timeout=6000)

    msg = str(exc.value)
    assert "Onglet 'Ordinateurs'" in msg, "le message doit nommer la CIBLE"
    assert "http://odoo/my/home" in msg, "le message doit nommer l'URL"
    # Borné : tous les candidats tentés, chacun avec un timeout fini (jamais une attente infinie).
    assert len(page.clicks) == 2
    assert all(0 < t <= 6000 for _, t in page.clicks)
