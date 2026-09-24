"""Calibration en ÉCRITURE pendant la génération — migration 45 (2026-09-16).

⚠️ **Pourquoi ce chantier.** `attempt_login` (2026-09-16, premier chantier) ne couvre que les
messages liés à une connexion — jamais un message de CONFIRMATION affiché après la création d'un
enregistrement (« Ticket #4521 créé »), parce qu'observer ce message suppose de créer une vraie
donnée. Analyse (doc Playwright « create + register cleanup », pratiques de synthetic monitoring
« policy-driven, jamais universellement automatique ») : la bonne réponse n'est pas de rendre
l'écriture universellement sûre, mais de la rendre **décidée explicitement par le porteur du
projet**, et bornée à un connecteur qui sait aussi ANNULER ce qu'il crée (Odoo, RPC `delete`) —
jamais le connecteur générique, qui n'a aucune garantie de suppression et refuse explicitement.

Éteinte par défaut sur tout projet (`project.calibration_writes_enabled`, migration 45).
"""

from __future__ import annotations

import pytest

from testpilot import config
from testpilot.connectors._web_helpers import (
    lire_message_confirmation_visible,
    soumettre_formulaire_et_lire_resultat,
)
from testpilot.connectors.generic_web import GenericWebConnector
from testpilot.connectors.odoo import OdooConnector, _extraire_id_depuis_url
from testpilot.generation.tools import ToolContext, dispatch
from testpilot.generation.tools import inspect as inspect_tools
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import ProjectRepo


class _FakeChamp:
    def __init__(self):
        self.rempli = None

    def fill(self, value, force=False):
        self.rempli = value


class _FakeElement:
    def __init__(self, texte: str, visible: bool = True):
        self._texte = texte
        self._visible = visible

    def is_visible(self):
        return self._visible

    def inner_text(self):
        return self._texte


class _FakeLocatorCollection:
    def __init__(self, elements):
        self._elements = elements

    def count(self):
        return len(self._elements)

    def nth(self, i):
        return self._elements[i]


class _FakeBoutonSoumission:
    def __init__(self):
        self.clique = False

    def click(self):
        self.clique = True

    def get_attribute(self, name):
        return 'submit' if name == 'type' else None


class _PageFormulaire:
    """Un formulaire avec deux champs (`name`/`description`), un bouton de soumission, et un
    message de confirmation qui n'apparaît qu'APRÈS le clic — combine l'API attendue par
    `extract_form`/`_detect_submission` (query_selector) et par `lire_message_confirmation_visible`
    (locator)."""

    def __init__(self, *, message_apres: str = "", url_apres: str = ""):
        self.champs = {"name": _FakeChamp(), "description": _FakeChamp()}
        self.bouton = _FakeBoutonSoumission()
        self._message = message_apres
        self.url = "https://exemple.test/formulaire"
        self._url_apres = url_apres or self.url

    def goto(self, _url):
        pass

    def set_default_timeout(self, *_a, **_kw):
        pass

    def query_selector(self, selector):
        for nom, champ in self.champs.items():
            if f"[name='{nom}']" == selector:
                return champ
        if selector == "form":
            return _FormFactice()
        if "submit" in selector or "btn-primary" in selector:
            return self.bouton
        return None

    def query_selector_all(self, _selector):
        return []

    def wait_for_load_state(self, *_a, **_kw):
        if self.bouton.clique:
            self.url = self._url_apres

    def locator(self, _selector):
        if self.bouton.clique and self._message:
            return _FakeLocatorCollection([_FakeElement(self._message)])
        return _FakeLocatorCollection([])


class _FormFactice:
    def get_attribute(self, _name):
        return "/soumettre"


# ── `lire_message_confirmation_visible` — élargi au succès, contrairement à la version erreur ──

def test_lire_message_confirmation_visible_capture_un_succes():
    class _Page:
        def locator(self, _s):
            return _FakeLocatorCollection([_FakeElement("Ticket #4521 créé avec succès.")])
    assert lire_message_confirmation_visible(_Page()) == "Ticket #4521 créé avec succès."


# ── `soumettre_formulaire_et_lire_resultat` — remplir + soumettre + lire, rien de plus ─────────

def test_soumettre_formulaire_et_lire_resultat_rend_le_message_reel():
    page = _PageFormulaire(message_apres="Ticket #4521 créé avec succès.",
                           url_apres="https://exemple.test/ticket/4521")
    resultat = soumettre_formulaire_et_lire_resultat(
        page, {"name": "Panne imprimante", "description": "Ne s'allume plus"})
    assert resultat == {
        "submitted": True, "url": "https://exemple.test/ticket/4521",
        "message": "Ticket #4521 créé avec succès.", "error": "",
    }
    assert page.champs["name"].rempli == "Panne imprimante"


def test_soumettre_formulaire_et_lire_resultat_sans_champ_trouve():
    page = _PageFormulaire()
    resultat = soumettre_formulaire_et_lire_resultat(page, {"champ_inexistant": "x"})
    assert resultat["submitted"] is False
    assert "aucun des champs" in resultat["error"]


def test_soumettre_formulaire_et_lire_resultat_sans_declencheur():
    class _PageSansBouton(_PageFormulaire):
        def query_selector(self, selector):
            if "submit" in selector or "btn-primary" in selector:
                return None
            return super().query_selector(selector)
    resultat = soumettre_formulaire_et_lire_resultat(_PageSansBouton(), {"name": "x"})
    assert resultat["submitted"] is False
    assert "aucun déclencheur" in resultat["error"]


# ── `_extraire_id_depuis_url` — deux conventions Odoo ────────────────────────────────────────

@pytest.mark.parametrize("url,attendu", [
    ("https://exemple.test/odoo/helpdesk-tickets/4521", 4521),
    ("https://exemple.test/web#id=4521&model=helpdesk.ticket&view_type=form", 4521),
    ("https://exemple.test/web#id=4521&model=helpdesk.ticket", 4521),
    ("https://exemple.test/my/home", None),
    ("https://exemple.test/odoo/helpdesk-tickets/new", None),
])
def test_extraire_id_depuis_url(url, attendu):
    assert _extraire_id_depuis_url(url) == attendu


# ── `GenericWebConnector.attempt_form_submission` — refus explicite, jamais un essai risqué ───

def test_generic_web_refuse_la_calibration_en_ecriture():
    conn = GenericWebConnector("http://localhost:9999")
    with pytest.raises(NotImplementedError):
        conn.attempt_form_submission("/nouveau-ticket", {"name": "x"})


# ── `OdooConnector.attempt_form_submission` — le cycle complet, avec nettoyage RPC ─────────────

class _FakeContexteNavigateur:
    def __init__(self, page):
        self._page = page
        self.ferme = False

    def new_page(self):
        return self._page

    def close(self):
        self.ferme = True


class _FakeSessionPrincipale:
    def storage_state(self):
        return {"cookies": [], "origins": []}


class _FakePagePrincipale:
    context = _FakeSessionPrincipale()


def test_odoo_attempt_form_submission_nettoie_via_rpc():
    conn = OdooConnector("http://localhost:9999", "db", "admin", "admin")
    page = _PageFormulaire(message_apres="Ticket #4521 créé avec succès.",
                           url_apres="http://localhost:9999/odoo/helpdesk-tickets/4521")
    contextes = []

    class _FakeBrowser:
        def new_context(self, storage_state=None):
            assert storage_state == {"cookies": [], "origins": []}, (
                "la session AUTHENTIFIÉE doit être copiée, contrairement à attempt_login")
            ctx = _FakeContexteNavigateur(page)
            contextes.append(ctx)
            return ctx

    supprimes = []
    conn._ensure_page = lambda: _FakePagePrincipale()
    conn._browser = _FakeBrowser()
    conn._run_in_browser = lambda fn, *a: fn(*a)
    conn.delete = lambda model, ids: supprimes.append((model, ids)) or True

    resultat = conn.attempt_form_submission(
        "/nouveau-ticket", {"name": "Panne imprimante"}, model="helpdesk.ticket")

    assert resultat["message"] == "Ticket #4521 créé avec succès."
    assert resultat["cleaned_up"] is True
    assert supprimes == [("helpdesk.ticket", [4521])]
    assert contextes[0].ferme is True


def test_odoo_attempt_form_submission_sans_modele_ne_nettoie_pas():
    conn = OdooConnector("http://localhost:9999", "db", "admin", "admin")
    page = _PageFormulaire(message_apres="Créé.", url_apres="http://localhost:9999/x/1")
    conn._ensure_page = lambda: _FakePagePrincipale()
    conn._browser = type("B", (), {"new_context": lambda self, storage_state=None:
                                   _FakeContexteNavigateur(page)})()
    conn._run_in_browser = lambda fn, *a: fn(*a)
    conn.delete = lambda *a, **kw: (_ for _ in ()).throw(AssertionError("ne doit jamais être appelé"))

    resultat = conn.attempt_form_submission("/nouveau-ticket", {"name": "x"})  # pas de model

    assert resultat["cleaned_up"] is False


def test_odoo_attempt_form_submission_id_non_reconnu_ne_nettoie_pas():
    conn = OdooConnector("http://localhost:9999", "db", "admin", "admin")
    page = _PageFormulaire(message_apres="Créé.", url_apres="http://localhost:9999/my/home")
    conn._ensure_page = lambda: _FakePagePrincipale()
    conn._browser = type("B", (), {"new_context": lambda self, storage_state=None:
                                   _FakeContexteNavigateur(page)})()
    conn._run_in_browser = lambda fn, *a: fn(*a)
    conn.delete = lambda *a, **kw: (_ for _ in ()).throw(AssertionError("ne doit jamais être appelé"))

    resultat = conn.attempt_form_submission("/nouveau-ticket", {"name": "x"}, model="helpdesk.ticket")

    assert resultat["cleaned_up"] is False, "aucun id reconnu dans l'URL → pas de suppression à l'aveugle"


def test_odoo_attempt_form_submission_signale_un_echec_de_nettoyage_sans_lever():
    conn = OdooConnector("http://localhost:9999", "db", "admin", "admin")
    page = _PageFormulaire(message_apres="Créé.", url_apres="http://localhost:9999/odoo/x/4521")
    conn._ensure_page = lambda: _FakePagePrincipale()
    conn._browser = type("B", (), {"new_context": lambda self, storage_state=None:
                                   _FakeContexteNavigateur(page)})()
    conn._run_in_browser = lambda fn, *a: fn(*a)
    def _echoue(*_a, **_kw):
        raise RuntimeError("record locked")
    conn.delete = _echoue

    resultat = conn.attempt_form_submission("/nouveau-ticket", {"name": "x"}, model="helpdesk.ticket")

    assert resultat["message"] == "Créé."
    assert resultat["cleaned_up"] is False


def test_odoo_attempt_form_submission_ne_leve_jamais():
    conn = OdooConnector("http://localhost:9999", "db", "admin", "admin")
    conn._run_in_browser = lambda fn, *a: (_ for _ in ()).throw(RuntimeError("navigateur mort"))
    resultat = conn.attempt_form_submission("/x", {"name": "y"})
    assert resultat["submitted"] is False
    assert "navigateur mort" in resultat["error"]


# ── L'outil exposé à l'agent — gardé par le réglage du PROJET ──────────────────────────────────

class _ConnecteurFactice:
    def __init__(self, resultat=None, leve=None):
        self._resultat = resultat
        self._leve = leve
    def attempt_form_submission(self, page_url, field_values, model=""):
        if self._leve:
            raise self._leve
        return self._resultat


def _ctx(connector=None, calibration_writes_enabled=False):
    from pathlib import Path
    return ToolContext(module_name="m", generated_dir=Path("."), connector=connector,
                       calibration_writes_enabled=calibration_writes_enabled)


def test_tool_attempt_form_submission_refuse_si_desactive():
    outcome = inspect_tools.attempt_form_submission(
        _ctx(_ConnecteurFactice({}), calibration_writes_enabled=False),
        "/x", {"name": "y"})
    assert outcome.ok is False
    assert "désactivée" in outcome.observation


def test_tool_attempt_form_submission_rapporte_le_message_et_le_nettoyage():
    outcome = inspect_tools.attempt_form_submission(
        _ctx(_ConnecteurFactice({"submitted": True, "url": "u", "error": "",
                                "message": "Ticket #4521 créé.", "cleaned_up": True}),
            calibration_writes_enabled=True),
        "/nouveau-ticket", {"name": "x"}, "helpdesk.ticket")
    assert outcome.ok is True
    assert "Ticket #4521 créé." in outcome.observation
    assert "nettoyée automatiquement" in outcome.observation


def test_tool_attempt_form_submission_enregistre_le_message_pour_smoke_check():
    """§F8 (2026-09-23) : un message réellement observé doit alimenter `verified_fields`, sous le
    préfixe `MESSAGE_SOURCE_PREFIX` — sans ça, `smoke_check.check_messages_observes` ne peut
    jamais disculper un texte de message pourtant vu pendant la génération."""
    from testpilot.generation.smoke_check import MESSAGE_SOURCE_PREFIX

    outcome = inspect_tools.attempt_form_submission(
        _ctx(_ConnecteurFactice({"submitted": True, "url": "u", "error": "",
                                "message": "Le code client doit contenir exactement 7 chiffres.",
                                "cleaned_up": True}),
            calibration_writes_enabled=True),
        "/mutation", {"code_client1": "123"})

    cle = f"{MESSAGE_SOURCE_PREFIX}attempt_form_submission:/mutation"
    assert outcome.verified_fields.get(cle) == [
        "Le code client doit contenir exactement 7 chiffres."]


def test_tool_attempt_form_submission_dit_quand_le_nettoyage_a_echoue():
    outcome = inspect_tools.attempt_form_submission(
        _ctx(_ConnecteurFactice({"submitted": True, "url": "u", "error": "",
                                "message": "Créé.", "cleaned_up": False}),
            calibration_writes_enabled=True),
        "/x", {"name": "y"})
    assert outcome.ok is True
    assert "PAS nettoyée" in outcome.observation


def test_tool_attempt_form_submission_connecteur_incapable():
    outcome = inspect_tools.attempt_form_submission(
        _ctx(_ConnecteurFactice(leve=NotImplementedError("aucune API de modèle")),
            calibration_writes_enabled=True),
        "/x", {"name": "y"})
    assert outcome.ok is False
    assert "aucune API de modèle" in outcome.observation


def test_dispatch_route_attempt_form_submission():
    outcome = dispatch(
        "attempt_form_submission",
        {"page_url": "/x", "field_values": {"name": "y"}, "model": "helpdesk.ticket"},
        _ctx(_ConnecteurFactice({"submitted": True, "url": "u", "error": "", "message": "M",
                                "cleaned_up": True}), calibration_writes_enabled=True))
    assert outcome.ok is True
    assert "M" in outcome.observation


# ── Le réglage du PROJET — éteint par défaut, décidé explicitement ─────────────────────────────

@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    c = get_initialized_db(tmp_path / "a.db")
    yield c
    c.close()


def test_calibration_writes_enabled_est_eteint_par_defaut(conn):
    pid = ProjectRepo(conn).create(name="P")
    assert ProjectRepo(conn).get(pid)["calibration_writes_enabled"] in (0, False)


def test_set_calibration_writes_enabled(conn):
    pid = ProjectRepo(conn).create(name="P")
    ProjectRepo(conn).set_calibration_writes_enabled(pid, True)
    assert bool(ProjectRepo(conn).get(pid)["calibration_writes_enabled"]) is True
    ProjectRepo(conn).set_calibration_writes_enabled(pid, False)
    assert bool(ProjectRepo(conn).get(pid)["calibration_writes_enabled"]) is False
