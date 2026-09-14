"""Suite de conformité multi-application (2026-09-14).

⚠️ **Pourquoi cette suite existe.** Trois bugs réels trouvés cette session (`fill_field` : la
valeur écrite en JS brut n'atteignait jamais l'état interne de SauceDemo ; navigation absente :
le navigateur restait sur `about:blank` toute la durée du scénario ; `validation_error_inline` :
ne reconnaissait que Odoo) avaient un point commun — **rien ne rejouait un scénario réel contre
une VRAIE application, autre qu'Odoo, avant qu'un cas généré n'y tombe en production.** Chacun
aurait été détecté ICI, avant tout client.

Directive explicite du porteur (2026-09-14) : « on ne cherche pas à faire en sorte que ça marche
uniquement [sur SauceDemo] » — cette suite rejoue donc les MÊMES vérifications contre DEUX
applications réelles, publiques, aux DOM différents : SauceDemo (React) et
the-internet.herokuapp.com (Sinatra/Ruby, aucun rapport technique avec SauceDemo). Une correction
qui ne passe que sur l'une des deux n'est pas générique — elle est encore spécifique à une appli,
sous un nom générique (précisément le bug de `validation_error_inline`).

Ce qui est exercé, à dessein : le socle minimal qu'AUCUNE campagne générée ne peut éviter —
naviguer, remplir un champ, cliquer un bouton, reconnaître une erreur de validation. Directement
sur la bibliothèque partagée (`_base_helpers.py`), pas via un run Behave complet : plus rapide,
et ça isole précisément CE qui doit être générique (le comportement des fonctions, pas
l'assemblage d'un run).

⚠️ **EXCLUE de `pytest -q` par défaut** (marker `conformance`, voir `pyproject.toml`) : réseau
sortant vers des sites tiers + navigateur Playwright réel, deux besoins que le job CI `pytest -q`
n'a pas (`ci.yml` n'installe aucun navigateur). Lancée par `.github/workflows/conformance.yml` —
à chaque changement de `behave_runtime/steps_library/`, et chaque nuit en tâche de fond contre la
dérive de ces applications tierces (une mise à jour de SauceDemo peut changer son DOM sans que
rien dans ce dépôt ne bouge).

Lancer en local : `pytest -m conformance -v`
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "behave_runtime" / "steps_library"))

from _base_helpers import click_button, fill_field, validation_error_inline  # noqa: E402

pytestmark = pytest.mark.conformance


@dataclass(frozen=True)
class _AppConforme:
    """Une application PUBLIQUE, faite pour l'automatisation de tests — identifiants publiés sur
    la page elle-même (SauceDemo, the-internet), jamais un compte personnel de qui que ce soit."""

    nom: str
    url_login: str
    champ_identifiant: str
    champ_mot_de_passe: str
    identifiant_valide: str
    mot_de_passe_valide: str
    fragment_url_connecte: str


# Deux applications RÉELLES, deux technos sans rapport (React vs Sinatra/Ruby) — le seul moyen de
# distinguer « corrigé pour de vrai » de « corrigé pour SauceDemo, sous un nom générique ».
_APPS = [
    _AppConforme(
        nom="SauceDemo", url_login="https://www.saucedemo.com",
        champ_identifiant="user-name", champ_mot_de_passe="password",
        identifiant_valide="standard_user", mot_de_passe_valide="secret_sauce",
        fragment_url_connecte="inventory",
    ),
    _AppConforme(
        nom="the-internet", url_login="https://the-internet.herokuapp.com/login",
        champ_identifiant="username", champ_mot_de_passe="password",
        identifiant_valide="tomsmith", mot_de_passe_valide="SuperSecretPassword!",
        fragment_url_connecte="secure",
    ),
]

_IDS = [app.nom for app in _APPS]


@pytest.fixture(scope="module")
def navigateur():
    """Un seul navigateur pour toute la suite (recommandation Playwright : plusieurs pages sur UN
    navigateur, pas un process Chromium par test) — chaque test reçoit sa propre page, isolée."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture
def page(navigateur):
    p = navigateur.new_page()
    yield p
    p.close()


@pytest.mark.parametrize("app", _APPS, ids=_IDS)
def test_navigation_initiale_atteint_bien_la_page_visee(page, app):
    """Le socle absolu, sans lequel tout le reste tourne dans le vide (bug de navigation,
    SauceDemo, 2026-09-11 : le navigateur restait sur `about:blank` toute la durée du scénario)."""
    page.goto(app.url_login, wait_until="domcontentloaded")

    assert page.url != "about:blank"
    assert page.locator("input").count() > 0, f"{app.nom} : aucun champ visible après navigation"


@pytest.mark.parametrize("app", _APPS, ids=_IDS)
def test_remplir_puis_cliquer_connecte_reellement(page, app):
    """`fill_field` + `click_button` doivent réellement connecter — pas seulement écrire une
    valeur dans le DOM sans que l'application le voie (bug `fill_field`, SauceDemo, 2026-09-11 :
    `el.value = X` en JS brut, jamais vu par l'état interne React de SauceDemo)."""
    page.goto(app.url_login, wait_until="domcontentloaded")

    fill_field(page, app.champ_identifiant, app.identifiant_valide)
    fill_field(page, app.champ_mot_de_passe, app.mot_de_passe_valide)
    click_button(page, "Login")

    assert app.fragment_url_connecte in page.url, (
        f"{app.nom} : la connexion n'a pas abouti — fill_field/click_button ne fonctionnent "
        f"pas réellement contre cette application (url actuelle : {page.url})")


@pytest.mark.parametrize("app", _APPS, ids=_IDS)
def test_soumission_vide_affiche_une_erreur_reconnue(page, app):
    """`validation_error_inline` doit reconnaître le refus de CHAQUE application — pas seulement
    celle où le bug a été trouvé (cas C37, SauceDemo, 2026-09-14 : ne reconnaissait que la classe
    CSS `o_has_error` d'Odoo, jamais le `role="alert"` de SauceDemo NI le `.flash.error` — sans
    aucun `role` — de the-internet)."""
    page.goto(app.url_login, wait_until="domcontentloaded")

    click_button(page, "Login")   # champs vides : refus attendu

    validation_error_inline(page)   # lève AssertionError si aucune erreur n'est reconnue
