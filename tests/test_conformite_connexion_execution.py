"""Lot 07a (C1) — conformité de la connexion à l'EXÉCUTION contre de VRAIES applications.

Même principe que `test_conformite_connecteur_web.py` : SauceDemo (React) et the-internet
(Sinatra/Ruby) — deux techs sans rapport, pour ne pas corriger « pour SauceDemo sous un nom
générique » — plus la fixture locale « torture » (connexion à DEUX écrans).

Ce qui est vérifié, avec le critère PAR DÉFAUT seul (l'URL a quitté la page de connexion ET plus aucun
champ mot de passe visible), sans aucun sélecteur « connecté » déclaré :
- le step d'entrée de la bibliothèque connecte réellement, sans qu'aucun step de connexion soit écrit ;
- un mauvais mot de passe donne un `PreconditionNonRemplieError` (→ `blocked`), jamais un succès ;
- « j'accède à la page de connexion sans me connecter » laisse la page de connexion intacte.

Exclue de `pytest -q` (marker `conformance`) : réseau sortant + navigateur réel.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from testpilot.execution.behave_result import BehaveFailure
from testpilot.verdict import defect_taxonomy as dt

_STEPS_LIB = Path(__file__).resolve().parent.parent / "behave_runtime" / "steps_library"
_CHEMINS = [str(_STEPS_LIB), str(_STEPS_LIB / "generic"), str(_STEPS_LIB / "web")]
H = generic = web = None  # posés par la fixture ci-dessous


@pytest.fixture(scope="module", autouse=True)
def _steps_isoles():
    """Charge les steps SANS laisser leurs déclarations dans le registre GLOBAL de Behave.

    ⚠️ Un run réel ne charge que `generic/` + UN connecteur ; ce fichier charge `generic/` + `web/`. Sans
    cette isolation, le libellé « je me connecte… » (aussi déclaré côté `odoo/`) resterait enregistré et
    ferait lever `AmbiguousStep` aux tests qui importent les steps Odoo ensuite (mesuré : 26 échecs).
    """
    global H, generic, web
    from behave import step_registry

    avant = {mot_cle: list(liste) for mot_cle, liste in step_registry.registry.steps.items()}
    deja = {nom for nom in ("_generic_steps", "_web_steps") if nom in sys.modules}
    for chemin in _CHEMINS:
        sys.path.insert(0, chemin)
    import _base_helpers as helpers
    import _generic_steps as generic_steps
    import _web_steps as web_steps
    H, generic, web = helpers, generic_steps, web_steps
    yield
    for mot_cle in list(step_registry.registry.steps):
        step_registry.registry.steps[mot_cle][:] = avant.get(mot_cle, [])
    for nom in ("_generic_steps", "_web_steps"):
        if nom not in deja:
            sys.modules.pop(nom, None)
    for chemin in _CHEMINS:
        if chemin in sys.path:
            sys.path.remove(chemin)

pytestmark = pytest.mark.conformance

_TORTURE = Path(__file__).resolve().parent / "fixtures" / "torture_app" / "login1.html"

# (nom, url d'entrée, identifiant, mot de passe valide, fragment d'URL une fois connecté)
_APPS = [
    ("SauceDemo", "https://www.saucedemo.com", "standard_user", "secret_sauce", "inventory"),
    ("the-internet", "https://the-internet.herokuapp.com/login", "tomsmith",
     "SuperSecretPassword!", "secure"),
    ("torture-deux-ecrans", _TORTURE.resolve().as_uri(), "testpilot", "secret", "dashboard.html"),
]
_IDS = [a[0] for a in _APPS]


@pytest.fixture(scope="module")
def navigateur():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture
def page(navigateur):
    p = navigateur.new_page()
    p.set_default_timeout(60000)
    yield p
    p.close()


def _contexte(page, url, user, mdp):
    return types.SimpleNamespace(page=page, web_url=url, web_user=user, web_password=mdp)


@pytest.mark.parametrize("nom, url, user, mdp, fragment", _APPS, ids=_IDS)
def test_le_step_d_entree_connecte_sans_aucun_step_de_connexion_ecrit(page, nom, url, user, mdp, fragment):
    ctx = _contexte(page, url, user, mdp)

    generic.step_access_home_page(ctx)

    assert fragment in page.url, f"{nom} : non connecté après le step d'entrée ({page.url})"
    assert not H._mot_de_passe_visible(page)
    assert ctx._tp_connecte is True
    # Le critère PAR DÉFAUT suffit seul : URL partie ET plus de mot de passe.
    assert H.connexion_reussie(url, page.url, H._mot_de_passe_visible(page))


@pytest.mark.parametrize("nom, url, user, mdp, fragment", _APPS, ids=_IDS)
def test_un_mauvais_mot_de_passe_est_un_prerequis_non_rempli_donc_blocked(page, nom, url, user, mdp, fragment):
    ctx = _contexte(page, url, user, "mauvais-mot-de-passe-xyz")

    with pytest.raises(H.PreconditionNonRemplieError) as err:
        generic.step_access_home_page(ctx)

    assert not isinstance(err.value, AssertionError)
    assert fragment not in page.url, f"{nom} : connecté malgré un mauvais mot de passe !"
    assert url.rstrip("/") in str(err.value) or url in str(err.value)
    echec = BehaveFailure("s", "", "unknown", "", step_type="given",
                          raw=("Traceback (most recent call last):\n"
                               f"_base_helpers.PreconditionNonRemplieError: {err.value}"))
    assert dt.classify_failure(echec) == dt.PRECONDITION_NON_REMPLIE


@pytest.mark.parametrize("nom, url, user, mdp, fragment", _APPS, ids=_IDS)
def test_sans_me_connecter_laisse_la_page_de_connexion_intacte(page, nom, url, user, mdp, fragment):
    ctx = _contexte(page, url, user, mdp)

    generic.step_access_login_page_without_login(ctx)

    assert fragment not in page.url
    assert H._mot_de_passe_visible(page) or "login1.html" in page.url


@pytest.mark.parametrize("nom, url, user, mdp, fragment", _APPS, ids=_IDS)
def test_le_step_explicite_apres_une_deconnexion_reconnecte(page, nom, url, user, mdp, fragment):
    """Milieu de parcours : on charge la page de connexion SANS se connecter, puis le step explicite."""
    ctx = _contexte(page, url, user, mdp)
    generic.step_access_login_page_without_login(ctx)

    web.step_login_web(ctx)

    assert fragment in page.url
    assert not H._mot_de_passe_visible(page)
