"""`_odoo_steps.py` déléguait à un doublon local de la connexion Playwright — jamais corrigé
quand `_base_helpers.playwright_login` l'a été (commit `3ceee7c`, formulaire replié derrière un
SSO, 2026-09-17). Mesuré en RUN RÉEL (résultat #1, staging Sapian, 2026-09-18) : le step
d'exécution « je me connecte avec mes identifiants utilisateur » attendait
`input[name='login']` en `state="attached"` (jamais `"visible"`) — sur le formulaire replié, le
`fill(force=True)` s'exécutait en pure perte et Playwright expirait en attendant la navigation
post-login (`Timeout 15000ms exceeded`). Le CRAWL, lui, avait déjà le correctif — deux gestes
identiques, un seul corrigé.

Ces tests prouvent la délégation, pas le comportement Playwright réel (déjà couvert par les
tests de `_base_helpers.playwright_login` lui-même).
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
_STEPS_LIB = RACINE / "behave_runtime" / "steps_library"


def _charger_odoo_steps():
    sys.path.insert(0, str(_STEPS_LIB))
    sys.path.insert(0, str(_STEPS_LIB / "odoo"))
    import _odoo_steps as steps
    return steps


def test_step_login_portal_delegue_a_playwright_login_corrige(monkeypatch):
    steps = _charger_odoo_steps()
    import _base_helpers as H

    appels = []
    monkeypatch.setattr(H, "playwright_login", lambda ctx: appels.append(ctx))
    monkeypatch.setattr(steps, "playwright_login", H.playwright_login)

    class _Page:
        url = "about:blank"

        def goto(self, url, **_k):
            self.url = url

    ctx = types.SimpleNamespace(page=_Page(), odoo_url="http://x")
    steps.step_login_portal(ctx)

    assert appels == [ctx], "le step doit déléguer à la fonction déjà corrigée, pas la recopier"


def test_step_navigate_url_delegue_aussi_si_page_vierge(monkeypatch):
    """Même geste que le crawl (`crawl_roots`) : sur une page vierge, se connecter D'ABORD."""
    steps = _charger_odoo_steps()
    import _base_helpers as H

    appels = []
    monkeypatch.setattr(H, "playwright_login", lambda ctx: appels.append(ctx))
    monkeypatch.setattr(steps, "playwright_login", H.playwright_login)

    class _Page:
        url = "about:blank"

        def goto(self, url, **_k):
            self.url = url

    ctx = types.SimpleNamespace(page=_Page(), odoo_url="http://x")
    steps.step_navigate_url(ctx, "/myservices")

    assert appels == [ctx]


def test_step_navigate_url_ne_relogue_pas_si_deja_sur_une_page():
    steps = _charger_odoo_steps()

    class _Page:
        url = "http://x/myservices"

        def goto(self, url, **_k):
            self.url = url

    appels = []
    steps.playwright_login = lambda ctx: appels.append(ctx)  # type: ignore[attr-defined]
    ctx = types.SimpleNamespace(page=_Page(), odoo_url="http://x")

    steps.step_navigate_url(ctx, "/autre")

    assert appels == [], "une session déjà établie ne doit jamais être re-authentifiée"


def test_aucun_doublon_local_de_playwright_login_ne_subsiste():
    """Garde anti-régression : la fonction locale `_playwright_login` ne doit jamais réapparaître
    — c'est exactement la duplication qui a laissé ce bug non corrigé une fois."""
    steps = _charger_odoo_steps()
    assert not hasattr(steps, "_playwright_login")


# ── Navigation menu : le back-office, jamais la racine du portail ─────────────────────────────
#
# Bug RÉEL mesuré en run (staging Sapian, 2026-09-18) : une fois le login corrigé, le step
# « je navigue vers le menu Odoo "Parc IT / Générer des équipements" » atterrissait sur le
# PORTAIL applicatif custom (`context.odoo_url`, sa page d'accueil), où « Parc IT » n'apparaît
# jamais — seulement dans le sélecteur d'applications back-office (`/web#action=menu`, vérifié en
# direct : icône « Parc IT » bien présente). Le clic sur un texte absent expirait après 8 s.

class _Clickable:
    def __init__(self, journal, texte):
        self._journal = journal
        self._texte = texte

    @property
    def first(self):
        return self

    def click(self, timeout=None):
        self._journal.append(self._texte)


class _FakePageMenu:
    def __init__(self):
        self.urls_visitees = []
        # Session navigateur DÉJÀ ouverte : ces tests portent sur le découpage du chemin de menu. Depuis F21,
        # `navigate_menu` connecte d'abord une page vide (`about:blank`) — cas testé à part, dans
        # `test_navigate_menu_communaute.py` ; les assertions ci-dessous sont inchangées.
        self.url = "https://sapian.example.com/web#cids=1"

    def goto(self, url, **_k):
        self.urls_visitees.append(url)
        self.url = url

    def wait_for_selector(self, *_a, **_kw):
        pass  # grille d'applications déjà "rendue" dans ce fake — rien à attendre.

    def get_by_text(self, texte, exact=True):
        return _Clickable(self.clics, texte)


def test_navigate_menu_part_du_selecteur_d_applications_back_office():
    steps = _charger_odoo_steps()
    page = _FakePageMenu()
    page.clics = []
    ctx = types.SimpleNamespace(page=page, odoo_url="https://sapian.example.com")

    steps.step_navigate_menu(ctx, "Parc IT > Générer des équipements")

    assert page.urls_visitees == ["https://sapian.example.com/web#action=menu"], (
        "jamais la racine du portail — Parc IT n'y vit pas")
    assert page.clics == ["Parc IT", "Générer des équipements"]


def test_navigate_menu_tolere_un_slash_final_sur_odoo_url():
    steps = _charger_odoo_steps()
    page = _FakePageMenu()
    page.clics = []
    ctx = types.SimpleNamespace(page=page, odoo_url="https://sapian.example.com/")

    steps.step_navigate_menu(ctx, "Parc IT")

    assert page.urls_visitees == ["https://sapian.example.com/web#action=menu"]


def test_navigate_menu_accepte_le_separateur_slash():
    """Bug RÉEL, mesuré en run (résultat #3, staging Sapian, 2026-09-18) : aucune convention de
    séparateur n'est documentée nulle part dans le prompt de génération — l'IA a écrit
    `"Parc IT / Générer des équipements"` avec `/`, alors que le step ne coupait que sur `>`.
    Sans séparateur reconnu, toute la chaîne partait comme un seul texte à chercher, qui n'existe
    nulle part — d'où le `Timeout 8000ms exceeded` observé. `/` doit être accepté au même titre
    que `>`, sans qu'aucun cas existant n'ait besoin d'être régénéré."""
    steps = _charger_odoo_steps()
    page = _FakePageMenu()
    page.clics = []
    ctx = types.SimpleNamespace(page=page, odoo_url="https://sapian.example.com")

    steps.step_navigate_menu(ctx, "Parc IT / Générer des équipements")

    assert page.clics == ["Parc IT", "Générer des équipements"], (
        "la chaîne entière ne doit plus jamais partir comme un seul texte à chercher")


def test_navigate_menu_ignore_les_segments_vides():
    """Un séparateur en tête, en fin, ou doublé ne doit jamais produire une recherche sur un
    texte vide (qui matcherait n'importe quel élément et casserait la navigation)."""
    steps = _charger_odoo_steps()
    page = _FakePageMenu()
    page.clics = []
    ctx = types.SimpleNamespace(page=page, odoo_url="https://sapian.example.com")

    steps.step_navigate_menu(ctx, "/Parc IT//Équipements/")

    assert page.clics == ["Parc IT", "Équipements"]


def test_navigation_helper_et_step_restent_identiques_apres_divergence_mesuree(monkeypatch):
    """18/09/2026 : le helper visitait le portail avec un chemin non découpé, le step non."""
    steps = _charger_odoo_steps()
    import _base_helpers as helpers

    assert steps.navigate_menu is helpers.navigate_menu
    calls = []
    monkeypatch.setattr(steps, "navigate_menu", lambda context, path: calls.append((context, path)))
    context = object()
    steps.step_navigate_menu(context, "Parc IT / Équipements")
    assert calls == [(context, "Parc IT / Équipements")]


def test_langue_des_libelles_mesures_conservee_sans_traduction_devinee():
    steps = _charger_odoo_steps()
    import _base_helpers as helpers

    for navigate in (helpers.navigate_menu, steps.step_navigate_menu):
        page = _FakePageMenu()
        page.clics = []
        context = types.SimpleNamespace(page=page, odoo_url="https://odoo.example/")
        navigate(context, "/Parc IT//Générer des équipements > Equipment/")
        assert page.urls_visitees == ["https://odoo.example/web#action=menu"]
        assert page.clics == ["Parc IT", "Générer des équipements", "Equipment"]
