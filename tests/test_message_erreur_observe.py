"""Observer un texte affiché plutôt que le deviner (amendement §4.3-bis étendu, 2026-09-16).

⚠️ **Le bug réel qui motive ce chantier.** Un cas généré affirmait qu'un compte verrouillé
affiche « Sorry, this user has been locked out. » — l'application réelle affiche « Epic sadface:
Sorry, this user has been locked out. ». Rien dans le pipeline de génération ne lit jamais le DOM
avant d'écrire une assertion sur un texte affiché : le dry-run (`behave --dry-run`) ne fait que
vérifier que les steps *matchent*, il n'exécute AUCUNE assertion (confirmé par la documentation
officielle de Behave). Playwright Codegen — l'outil officiel équivalent — ne demande jamais ce
texte à l'auteur : il lit l'`innerText` réel au moment de l'enregistrement. `attempt_login`
applique le même principe à l'agent de génération, pour la catégorie de message la plus fréquente
(l'issue d'une tentative de connexion), en réutilisant EXACTEMENT les sélecteurs déjà validés
contre deux applications réelles par `behave_runtime/steps_library/_base_helpers.py::
validation_error_inline`.
"""

from __future__ import annotations

from testpilot.connectors._web_helpers import (
    ConnexionGeneriqueImpossibleError,
    lire_message_erreur_visible,
    tenter_connexion_et_lire_resultat,
)
from testpilot.connectors.generic_web import GenericWebConnector
from testpilot.connectors.odoo import OdooConnector
from testpilot.generation.tools import ToolContext, dispatch
from testpilot.generation.tools import inspect as inspect_tools


class _FakeChamp:
    def __init__(self):
        self.rempli = None
        self.touche_pressee = None

    def fill(self, value, force=False):
        self.rempli = value

    def press(self, key):
        self.touche_pressee = key


class _FakeElement:
    def __init__(self, texte: str, visible: bool = True):
        self._texte = texte
        self._visible = visible

    def is_visible(self):
        return self._visible

    def inner_text(self):
        return self._texte


class _FakeLocatorCollection:
    def __init__(self, elements: list[_FakeElement]):
        self._elements = elements

    def count(self):
        return len(self._elements)

    def nth(self, i):
        return self._elements[i]


class _PageConnexion:
    """Une page à un seul écran (mot de passe + identifiant ensemble), qui affiche un message
    après soumission — combine l'API attendue par `tenter_connexion_generique` (query_selector)
    et par `lire_message_erreur_visible` (locator)."""

    def __init__(self, *, message_apres_soumission: str = "", url_apres: str = "",
                mdp_present: bool = True, identifiant_present: bool = True):
        self.identifiant = _FakeChamp() if identifiant_present else None
        self.mdp = _FakeChamp() if mdp_present else None
        self._message = message_apres_soumission
        self.url = "https://exemple.test/connexion"
        self._url_apres = url_apres or self.url
        self._soumis = False

    def goto(self, _url):
        pass

    def set_default_timeout(self, *_a, **_kw):
        pass

    def query_selector(self, selector):
        if "password" in selector:
            return self.mdp
        if "email" in selector or "text" in selector:
            return self.identifiant
        return None

    def query_selector_all(self, selector):
        if ("email" in selector or "text" in selector) and self.identifiant is not None:
            return [self.identifiant]
        return []

    def wait_for_load_state(self, *_a, **_kw):
        if self.mdp and self.mdp.touche_pressee == "Enter":
            self._soumis = True
            self.url = self._url_apres

    def locator(self, _selector):
        if self._soumis and self._message:
            return _FakeLocatorCollection([_FakeElement(self._message)])
        return _FakeLocatorCollection([])


# ── `lire_message_erreur_visible` — la lecture pure ──────────────────────────────────────────

def test_lire_message_erreur_visible_rend_le_premier_element_visible():
    class _Page:
        def locator(self, _s):
            return _FakeLocatorCollection([
                _FakeElement("caché", visible=False),
                _FakeElement("  Epic sadface: verrouillé  "),
            ])
    assert lire_message_erreur_visible(_Page()) == "Epic sadface: verrouillé"


def test_lire_message_erreur_visible_ignore_un_element_visible_mais_vide():
    """🔴 Bug réel trouvé en vérifiant contre le vrai SauceDemo (2026-09-16) : la bannière
    d'erreur s'y compose de plusieurs éléments `.error`/`[role="alert"]` imbriqués — un conteneur
    vide et le bouton « X » de fermeture, VISIBLES tous les deux mais SANS texte, AVANT le
    `<h3 data-test="error">` qui porte le vrai message. S'arrêter au premier élément visible sans
    regarder son texte rendait une chaîne vide au lieu du message réel."""
    class _Page:
        def locator(self, _s):
            return _FakeLocatorCollection([
                _FakeElement(""),               # conteneur visible, vide (cas réel SauceDemo)
                _FakeElement(""),               # bouton de fermeture, visible, vide
                _FakeElement("Epic sadface: Sorry, this user has been locked out."),
            ])
    assert lire_message_erreur_visible(_Page()) == (
        "Epic sadface: Sorry, this user has been locked out.")


def test_lire_message_erreur_visible_rend_vide_sans_aucun_element():
    class _Page:
        def locator(self, _s):
            return _FakeLocatorCollection([])
    assert lire_message_erreur_visible(_Page()) == ""


def test_lire_message_erreur_visible_ignore_un_element_qui_leve_a_la_lecture():
    class _ElementInstable(_FakeElement):
        def is_visible(self):
            raise Exception("détaché du DOM entre le comptage et la lecture")
    class _Page:
        def locator(self, _s):
            return _FakeLocatorCollection([_ElementInstable("x"), _FakeElement("le vrai message")])
    assert lire_message_erreur_visible(_Page()) == "le vrai message"


# ── `tenter_connexion_et_lire_resultat` — connexion + lecture combinées ──────────────────────

def test_tenter_connexion_et_lire_resultat_rend_le_message_reel():
    page = _PageConnexion(message_apres_soumission="Epic sadface: Sorry, this user has been "
                                                    "locked out.",
                          url_apres="https://exemple.test/")
    resultat = tenter_connexion_et_lire_resultat(page, "locked_out_user", "secret_sauce")
    assert resultat == {
        "submitted": True, "url": "https://exemple.test/",
        "message": "Epic sadface: Sorry, this user has been locked out.", "error": "",
    }


def test_tenter_connexion_et_lire_resultat_sans_formulaire_detecte():
    page = _PageConnexion(mdp_present=False, identifiant_present=False)
    resultat = tenter_connexion_et_lire_resultat(page, "x", "y")
    assert resultat["submitted"] is False
    assert resultat["message"] == ""
    assert "aucun formulaire" in resultat["error"]


def test_tenter_connexion_et_lire_resultat_capture_l_echec_deux_ecrans():
    class _PageSSO:
        url = "https://exemple.test/connexion"
        def query_selector(self, selector):
            if "email" in selector or "text" in selector:
                return _FakeChamp()
            return None
        def query_selector_all(self, selector):
            return [_FakeChamp()] if ("email" in selector or "text" in selector) else []
        def wait_for_load_state(self, *_a, **_kw):
            pass
    resultat = tenter_connexion_et_lire_resultat(_PageSSO(), "alice", "s3cret")
    assert resultat["submitted"] is False
    assert resultat["message"] == ""
    assert resultat["error"]  # le message de ConnexionGeneriqueImpossibleError, tel quel


# ── `GenericWebConnector.attempt_login` — un contexte FRAIS, jamais la session persistante ──

def test_attempt_login_utilise_un_contexte_jetable_jamais_self_page():
    conn = GenericWebConnector("http://localhost:9999")
    page = _PageConnexion(message_apres_soumission="Epic sadface: mauvais mot de passe",
                          url_apres="http://localhost:9999/")
    contextes_ouverts = []

    class _FakeContext:
        def __init__(self):
            self.ferme = False
        def new_page(self):
            return page
        def close(self):
            self.ferme = True

    class _FakeBrowser:
        def new_context(self):
            ctx = _FakeContext()
            contextes_ouverts.append(ctx)
            return ctx

    conn._ensure_page = lambda: None  # ne PAS lancer un vrai Playwright
    conn._browser = _FakeBrowser()
    conn._run_in_browser = lambda fn, *a: fn(*a)  # synchrone pour le test

    resultat = conn.attempt_login("standard_user", "mauvais_mdp")

    assert resultat["message"] == "Epic sadface: mauvais mot de passe"
    assert resultat["submitted"] is True
    assert len(contextes_ouverts) == 1, "un SEUL contexte jetable, jamais self._page"
    assert contextes_ouverts[0].ferme is True, "le contexte jetable est refermé après lecture"


def test_attempt_login_ne_leve_jamais_et_signale_l_erreur():
    conn = GenericWebConnector("http://localhost:9999")
    def _boom(*_a, **_kw):
        raise RuntimeError("navigateur indisponible")
    conn._run_in_browser = _boom
    resultat = conn.attempt_login("x", "y")
    assert resultat["submitted"] is False
    assert "navigateur indisponible" in resultat["error"]


def test_odoo_attempt_login_utilise_aussi_un_contexte_jetable():
    conn = OdooConnector("http://localhost:9999", "db", "admin", "admin")

    class _PageOdoo:
        url = "http://localhost:9999/web/login"
        def wait_for_selector(self, *_a, **_kw):
            pass
        def locator(self, selector):
            if "input[name='login']" in selector or "input[name='password']" in selector:
                return _FakeChampLocator()
            return _FakeLocatorCollection([_FakeElement("Wrong login/password")])
        def wait_for_load_state(self, *_a, **_kw):
            self.url = "http://localhost:9999/web/login"  # échec : reste sur la page de login
        def goto(self, url):
            pass
        def set_default_timeout(self, *_a, **_kw):
            pass

    class _FakeChampLocator:
        def fill(self, *_a, **_kw):
            pass
        def press(self, *_a, **_kw):
            pass

    contextes_ouverts = []

    class _FakeContext:
        def new_page(self):
            return _PageOdoo()
        def close(self):
            contextes_ouverts.append(True)

    class _FakeBrowser:
        def new_context(self):
            return _FakeContext()

    conn._ensure_page = lambda: None
    conn._browser = _FakeBrowser()
    conn._run_in_browser = lambda fn, *a: fn(*a)

    resultat = conn.attempt_login("admin", "mauvais_mdp")

    assert resultat["submitted"] is True
    assert resultat["message"] == "Wrong login/password"
    assert len(contextes_ouverts) == 1


# ── L'outil exposé à l'agent (ReAct) ──────────────────────────────────────────────────────────

class _ConnecteurFactice:
    def __init__(self, resultat):
        self._resultat = resultat
    def attempt_login(self, username, password):
        return self._resultat


def _ctx(connector=None):
    from pathlib import Path
    return ToolContext(module_name="m", generated_dir=Path("."), connector=connector)


def test_tool_attempt_login_rapporte_le_message_observe():
    outcome = inspect_tools.attempt_login(
        _ctx(_ConnecteurFactice({"submitted": True, "url": "https://x/", "error": "",
                                "message": "Epic sadface: Sorry, this user has been locked out."})),
        "locked_out_user", "secret_sauce")
    assert outcome.ok is True
    assert "Epic sadface: Sorry, this user has been locked out." in outcome.observation


def test_tool_attempt_login_sans_message_le_dit_explicitement():
    outcome = inspect_tools.attempt_login(
        _ctx(_ConnecteurFactice({"submitted": True, "url": "https://x/home", "error": "",
                                "message": ""})),
        "standard_user", "secret_sauce")
    assert outcome.ok is True
    assert "aucun message d'erreur visible" in outcome.observation


def test_tool_attempt_login_sans_connecteur():
    outcome = inspect_tools.attempt_login(_ctx(None), "a", "b")
    assert outcome.ok is False


def test_tool_attempt_login_champs_requis():
    outcome = inspect_tools.attempt_login(_ctx(_ConnecteurFactice({})), "", "")
    assert outcome.ok is False


def test_tool_attempt_login_remonte_une_erreur_de_perception():
    outcome = inspect_tools.attempt_login(
        _ctx(_ConnecteurFactice({"submitted": False, "error": "SSO détecté, hors périmètre"})),
        "a", "b")
    assert outcome.ok is False
    assert "SSO détecté" in outcome.observation


def test_dispatch_route_attempt_login():
    outcome = dispatch(
        "attempt_login", {"username": "locked_out_user", "password": "secret_sauce"},
        _ctx(_ConnecteurFactice({"submitted": True, "url": "u", "error": "", "message": "M"})))
    assert outcome.ok is True
    assert "M" in outcome.observation
