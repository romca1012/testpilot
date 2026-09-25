"""Lot 07c (C3) — PREUVE dans un vrai navigateur : le contexte figé est réellement appliqué, et son absence ne l'est pas.

Marqueur `conformance` (vrai Chromium, aucune application distante — une page `about:blank`) ; exécuté par le job « browser-evidence »
de chaque PR. Les réglages choisis sont volontairement ÉLOIGNÉS des défauts et de ceux d'une machine française : sans le contexte
figé, `navigator.language`, le fuseau et la fenêtre seraient ceux de l'hôte — c'est ce que le test de contrôle (falsifiabilité) exige.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from testpilot.connectors import contexte_navigateur as cn

pytestmark = pytest.mark.conformance

RACINE = Path(__file__).resolve().parents[1]

_LECTURE = """() => ({
  langue: navigator.language,
  fuseau: Intl.DateTimeFormat().resolvedOptions().timeZone,
  largeur: window.innerWidth, hauteur: window.innerHeight,
  date: new Date(Date.UTC(2026, 6, 4, 23, 30)).toLocaleString(undefined, {dateStyle: 'full', timeStyle: 'short'}),
})"""

REGLAGES = {"browser_locale": "ja-JP", "browser_timezone": "Asia/Tokyo", "browser_viewport": "1111x777"}


@pytest.fixture(scope="module")
def navigateur():
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        yield b
        b.close()


def _lire(navigateur, **options):
    contexte = navigateur.new_context(**options)
    try:
        page = contexte.new_page()
        page.goto("about:blank")
        return page.evaluate(_LECTURE)
    finally:
        contexte.close()


def _harnais():
    sys.path.insert(0, str(RACINE))
    from behave_runtime import environment
    return environment


def test_le_contexte_du_projet_est_reellement_applique_par_le_harnais(navigateur, monkeypatch):
    from testpilot.connectors.runtime_env import project_env

    for cle, valeur in project_env({"connector_type": "web", "base_url": "https://a.example", **REGLAGES}).items():
        monkeypatch.setenv(cle, valeur)

    lu = _lire(navigateur, **_harnais().contexte_navigateur_fige())

    assert lu["langue"] == "ja-JP"
    assert lu["fuseau"] == "Asia/Tokyo"
    assert (lu["largeur"], lu["hauteur"]) == (1111, 777)
    # 23:30 UTC le 4 juillet est le 5 juillet à 08:30 à Tokyo, et s'écrit à la japonaise : la date affichée change VRAIMENT.
    assert "2026年7月5日" in lu["date"] and "8:30" in lu["date"]


def test_l_exploration_et_l_execution_voient_la_meme_page(navigateur, monkeypatch):
    """Le MÊME contexte des deux côtés : ce que l'agent voit à l'exploration est ce que le test verra à l'exécution."""
    from testpilot.connectors.runtime_env import project_env

    projet = {"connector_type": "web", "base_url": "https://a.example", **REGLAGES}
    for cle, valeur in project_env(projet).items():
        monkeypatch.setenv(cle, valeur)

    execution = _lire(navigateur, **_harnais().contexte_navigateur_fige())
    exploration = _lire(navigateur, **cn.depuis_projet(projet).kwargs())

    assert exploration == execution


def test_falsifiable_sans_contexte_fige_le_navigateur_prend_le_contexte_de_l_hote(navigateur, monkeypatch):
    """Le contrôle : un `new_context()` nu (l'ancien comportement) ne donne PAS le contexte du projet."""
    from testpilot.connectors.runtime_env import project_env

    for cle, valeur in project_env({"connector_type": "web", "base_url": "https://a.example", **REGLAGES}).items():
        monkeypatch.setenv(cle, valeur)

    nu = _lire(navigateur)
    fige = _lire(navigateur, **_harnais().contexte_navigateur_fige())

    assert nu["langue"] != fige["langue"] and nu["fuseau"] != fige["fuseau"]
    assert (nu["largeur"], nu["hauteur"]) != (fige["largeur"], fige["hauteur"])


def test_les_defauts_donnent_fr_paris_1440x900_quelle_que_soit_la_machine(navigateur, monkeypatch):
    for cle in (cn.ENV_LOCALE, cn.ENV_TIMEZONE, cn.ENV_VIEWPORT):
        monkeypatch.delenv(cle, raising=False)

    lu = _lire(navigateur, **_harnais().contexte_navigateur_fige())

    assert (lu["langue"], lu["fuseau"], lu["largeur"], lu["hauteur"]) == ("fr-FR", "Europe/Paris", 1440, 900)
