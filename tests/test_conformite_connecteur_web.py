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

⚠️ **SauceDemo et the-internet restent COMPLAISANTES** (étape 1.3 du plan de consolidation,
2026-09-15 — audit « Le pari Mabl/Testim ») : markup stable, attribut technique toujours présent,
connexion en une seule page. Une fixture CONTRÔLÉE et VERSIONNÉE dans le dépôt
(`tests/fixtures/torture_app/`) complète le filet avec ce que ces deux applications n'exercent
jamais — identifiants d'éléments régénérés à chaque chargement, un champ atteignable SEULEMENT par
son libellé, une connexion étalée sur DEUX écrans — sans dépendre d'une 3ᵉ application publique
(fiabilité/CGU incertaines) : ce qu'elle mesure ne peut pas changer sous nos pieds.

Lancer en local : `pytest -m conformance -v`
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "behave_runtime" / "steps_library"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from _base_helpers import (  # noqa: E402
    click_button, fill_field, select_field_value, select_product_in_list, validation_error_inline,
)
import crawl_domaine as cd  # noqa: E402

from testpilot.connectors._web_helpers import tenter_connexion_generique  # noqa: E402

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


def test_selection_produit_par_texte_marche_sans_url_odoo(page):
    """`select_product_in_list` ne reconnaissait que des liens produit au format Odoo
    (`/description/`, `/product/`, …) — cas C45, SauceDemo, 2026-09-14 : le lien produit y route
    en JS pur (`href="#"`), donc AUCUN candidat n'aurait jamais pu matcher. Testé sur SauceDemo
    seul (the-internet.herokuapp.com n'a pas de catalogue produit comparable)."""
    app = next(a for a in _APPS if a.nom == "SauceDemo")
    page.goto(app.url_login, wait_until="domcontentloaded")
    fill_field(page, app.champ_identifiant, app.identifiant_valide)
    fill_field(page, app.champ_mot_de_passe, app.mot_de_passe_valide)
    click_button(page, "Login")

    select_product_in_list(page, "Sauce Labs Backpack")

    assert "inventory-item.html" in page.url, (
        f"la sélection du produit n'a pas navigué vers sa fiche (url actuelle : {page.url})")


def test_selection_dans_un_select_sans_name_marche_par_sa_classe_css(page):
    """`select_field_value` ne trouvait un `<select>` que par son attribut `name` — cas C39,
    SauceDemo, 2026-09-14 : le menu de tri du catalogue n'a AUCUN `name` (juste une classe CSS et
    un `data-test`), un filtre d'affichage, pas un champ de formulaire soumis. Testé sur SauceDemo
    seul (the-internet.herokuapp.com n'a pas de tri comparable)."""
    app = next(a for a in _APPS if a.nom == "SauceDemo")
    page.goto(app.url_login, wait_until="domcontentloaded")
    fill_field(page, app.champ_identifiant, app.identifiant_valide)
    fill_field(page, app.champ_mot_de_passe, app.mot_de_passe_valide)
    click_button(page, "Login")

    select_field_value(page, "Name (Z to A)", "product_sort_container")

    noms = page.locator(".inventory_item_name")
    premier = noms.first.inner_text()
    dernier = noms.nth(noms.count() - 1).inner_text()
    assert premier > dernier, (
        f"le tri Z-A n'a pas été appliqué (premier={premier!r}, dernier={dernier!r})")


# ── Fixture « torture » locale (§1.3 du plan de consolidation, 2026-09-15) ──────────────────────
#
# SauceDemo et the-internet sont conçues pour être automatisées : markup stable, un attribut
# technique (name/data-test) toujours présent, connexion en une seule page. Rien ne prouve que la
# cascade tient face à une application plus dure — des identifiants d'éléments qui changent à
# chaque chargement, un champ atteignable SEULEMENT par son libellé, une connexion étalée sur DEUX
# écrans. Plutôt que de dépendre d'une 3ᵉ application publique (fiabilité/CGU incertaines), cette
# fixture est CONTRÔLÉE et VERSIONNÉE dans le dépôt (`tests/fixtures/torture_app/`) : ce qu'elle
# mesure ne peut pas changer sous nos pieds comme une vraie application tierce le pourrait.

_TORTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "torture_app"


def _page_torture(nom: str) -> str:
    return (_TORTURE_DIR / nom).resolve().as_uri()


def test_torture_locate_field_resout_un_champ_sans_le_moindre_identifiant_technique(page):
    """Ni `name`, ni `data-test`, ni `id` stable (régénéré à CHAQUE chargement) : seul le libellé
    visible permet de retrouver ce champ — le palier le plus proche d'un usage humain, jamais
    exercé par SauceDemo/the-internet (les deux posent toujours un attribut technique stable)."""
    page.goto(_page_torture("login1.html"))

    fill_field(page, "Identifiant", "testpilot")
    click_button(page, "Continuer")
    page.wait_for_url(lambda url: "login2.html" in url, timeout=5000)

    assert "login2.html" in page.url


def test_torture_la_connexion_en_deux_ecrans_aboutit(page):
    """La bibliothèque partagée (`locate_field`/`fill_field`/`click_button`) doit fonctionner sur
    CHAQUE écran indépendamment. ⚠️ La détection AUTOMATIQUE d'une connexion à deux écrans (ce que
    `tenter_connexion_generique` ferait toute seule) est une étape À PART du plan de consolidation
    (§3.1), pas encore construite — ce test pilote les deux écrans explicitement, un par un."""
    page.goto(_page_torture("login1.html"))
    fill_field(page, "Identifiant", "testpilot")
    click_button(page, "Continuer")
    page.wait_for_url(lambda url: "login2.html" in url, timeout=5000)

    fill_field(page, "Mot de passe", "secret")
    click_button(page, "Se connecter")
    page.wait_for_url(lambda url: "dashboard.html" in url, timeout=5000)

    assert "dashboard.html" in page.url, (
        f"la connexion en deux écrans n'a pas abouti (url actuelle : {page.url})")


def test_torture_un_select_sans_name_marche_par_sa_classe_css(page):
    page.goto(_page_torture("dashboard.html"))

    select_field_value(page, "Z à A", "tri-catalogue")

    assert page.locator(".tri-catalogue").input_value() == "za"


def test_torture_tenter_connexion_generique_detecte_seule_la_connexion_a_deux_ecrans(page):
    """Étape 3.1 du plan de consolidation : la détection AUTOMATIQUE (pas un pilotage manuel
    écran par écran comme les deux tests ci-dessus) doit franchir les DEUX écrans toute seule,
    en conditions réelles — exactement ce que `GenericWebConnector`/le crawl générique lui
    délèguent."""
    page.goto(_page_torture("login1.html"))

    resultat = tenter_connexion_generique(page, "testpilot", "secret")

    assert resultat is True
    assert "dashboard.html" in page.url, (
        f"la détection à deux écrans n'a pas abouti (url actuelle : {page.url})")


# ── Le crawl capture un champ SANS name (audit « Le pari Mabl/Testim », cas réel 2026-09-15) ────
#
# Défaut RÉEL trouvé en diagnostiquant un cas généré : le tri du catalogue SauceDemo n'a AUCUN
# attribut `name` — la requête DOM du crawl exigeait `[name]`, ce champ lui était donc INVISIBLE,
# absent de l'annuaire. Sans donnée mesurée, l'agent de génération avait inventé un identifiant
# plausible mais faux (« sort-by ») — introuvable à l'exécution, cas classé en Retest.

def test_le_crawl_capture_desormais_un_champ_sans_name_via_son_data_test(page):
    """Preuve directe du défaut corrigé : AVANT ce correctif, `product-sort-container` (le
    sélecteur de tri, sans `name`) n'apparaissait dans AUCUN `champs` mesuré par le crawl."""
    app = next(a for a in _APPS if a.nom == "SauceDemo")
    page.goto(app.url_login, wait_until="domcontentloaded")
    fill_field(page, app.champ_identifiant, app.identifiant_valide)
    fill_field(page, app.champ_mot_de_passe, app.mot_de_passe_valide)
    click_button(page, "Login")
    # ⚠️ `_inspecter_page` prend un INSTANTANÉ du DOM (`page.evaluate`, sans la moindre attente) —
    # le vrai crawl l'appelle toujours juste après un `page.goto(..., wait_until="networkidle")`
    # (voir `crawler()`). Ici, la navigation vient d'un clic de connexion, pas d'un `goto` : sans
    # cette attente, la mesure peut tomber avant que le sélecteur ne soit rendu (flaky vu en CI,
    # runner plus lent que le poste de développement).
    page.wait_for_load_state("networkidle")

    infos = cd._inspecter_page(page)

    tri = next((c for c in infos["champs"] if c["tag"] == "select"), None)
    assert tri is not None, "le sélecteur de tri doit maintenant apparaître dans les champs mesurés"
    assert tri["name"] == "product-sort-container"
    assert tri["identifie_par"] == "data-test"


def test_le_crawl_capture_un_champ_sans_aucun_attribut_technique_via_sa_classe_css(page):
    """Le cas encore plus dur (ni `name`, ni `data-test`) : la fixture torture — la classe CSS
    n'est retenue que parce qu'elle est UNIQUE sur la page (voir `_inspecter_page`)."""
    page.goto(_page_torture("dashboard.html"))

    infos = cd._inspecter_page(page)

    tri = next((c for c in infos["champs"] if c["tag"] == "select"), None)
    assert tri is not None
    assert tri["name"] == "tri-catalogue"
    assert tri["identifie_par"] == "classe"


def test_le_crawl_ne_change_rien_pour_un_champ_deja_nomme(page):
    """Comportement HISTORIQUE inchangé : un champ avec un vrai `name` continue de le porter
    tel quel, jamais une classe ou un libellé à la place."""
    app = next(a for a in _APPS if a.nom == "SauceDemo")
    page.goto(app.url_login, wait_until="domcontentloaded")

    infos = cd._inspecter_page(page)

    identifiant = next(c for c in infos["champs"] if c["name"] == app.champ_identifiant)
    assert identifiant["identifie_par"] == "name"
