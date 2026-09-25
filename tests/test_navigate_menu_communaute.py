"""F17 (banc du lot 04) — `navigate_menu` ouvre la grille des applications sur Enterprise ET sur Community.

`/web#action=menu` est le home menu d'Enterprise ; sur Community (16.0/17.0/18.0) elle est vide et la grille vit dans
`.o_navbar_apps_menu button`. Ces tests fixent l'ORDRE (une attente sur « grille OU commutateur », puis le repli) sur des
doublures ; la preuve sur de vraies instances Community est dans `tests/test_navigation_menu_banc.py` (marqueur `banc`).
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeout

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "behave_runtime" / "steps_library"))
import _base_helpers as H  # noqa: E402

UNION = ".o_app, .o_navbar_apps_menu button"


class _Commutateur:
    def __init__(self, page):
        self._page = page

    @property
    def first(self):
        return self

    def wait_for(self, state=None, timeout=None):
        self._page.journal.append("attend_commutateur")

    def click(self, timeout=None):
        self._page.journal.append("clic_commutateur")
        self._page.clics += 1


class _Page:
    """Enterprise : `.o_app` d'emblée. Community : le commutateur, et `.o_app` seulement après N clics. Sinon : rien."""

    def __init__(self, *, enterprise=False, community=False, clics_necessaires=1):
        self.journal, self.clics, self.urls = [], 0, []
        self._enterprise, self._community, self._necessaires = enterprise, community, clics_necessaires
        self.url = "http://instance.example:8069/web#action=menu"

    def _grille(self):
        return self._enterprise or (self._community and self.clics >= self._necessaires)

    def wait_for_selector(self, selecteur, timeout=None):
        self.journal.append(f"attend[{selecteur}]_{timeout}")
        if selecteur == UNION and (self._enterprise or self._community):
            return
        if selecteur == ".o_app" and self._grille():
            return
        raise PlaywrightTimeout("absent")

    def goto(self, url, **_k):
        self.urls.append(url)
        self.journal.append("goto_racine")

    def locator(self, selecteur):
        if selecteur == ".o_app":
            return types.SimpleNamespace(count=lambda: 1 if self._grille() else 0)
        assert selecteur == ".o_navbar_apps_menu button", "seul le commutateur COMMUNITY déclenche le repli"
        return _Commutateur(self)


def test_enterprise_la_grille_suffit_aucun_clic_aucune_navigation():
    page = _Page(enterprise=True)

    H._ouvrir_grille_applications(page)

    assert page.journal == [f"attend[{UNION}]_15000"], "ancien comportement : la grille suffit, on ne touche à rien"


def test_community_repart_de_la_racine_puis_clique_le_commutateur_jusqu_a_l_ouverture():
    page = _Page(community=True)

    H._ouvrir_grille_applications(page)

    assert page.journal == [f"attend[{UNION}]_15000", "goto_racine", "attend_commutateur", "clic_commutateur",
                            "attend[.o_app]_2500"]
    assert page.urls == ["http://instance.example:8069/web"], "la boîte d'erreur de l'ancienne route recouvre le commutateur"


def test_community_un_clic_donne_trop_tot_n_ouvre_rien_on_reessaie():
    """Mesuré sur 17.0 : le commutateur est visible avant que le client web ait attaché ses gestionnaires."""
    page = _Page(community=True, clics_necessaires=3)

    H._ouvrir_grille_applications(page)

    assert page.journal.count("clic_commutateur") == 3 and page._grille()


def test_un_commutateur_qui_n_ouvre_rien_est_borne_et_ne_leve_jamais():
    page = _Page(community=True, clics_necessaires=99)

    H._ouvrir_grille_applications(page)

    assert page.journal.count("clic_commutateur") == H._ESSAIS_COMMUTATEUR


def test_ni_grille_ni_commutateur_la_marge_historique_de_15_s_puis_on_rend_la_main():
    """Enterprise à froid qui n'a rien rendu, ou instance en panne : une seule attente de 15 s, aucun clic."""
    page = _Page()

    H._ouvrir_grille_applications(page)

    assert page.journal == [f"attend[{UNION}]_15000"]


def test_navigate_menu_appelle_le_helper_apres_le_goto_et_avant_de_chercher_l_application(monkeypatch):
    ordre = []

    class _Loc:
        first = property(lambda self: self)
        click = lambda self, timeout=None: ordre.append("clic_application")  # noqa: E731

    page = types.SimpleNamespace(goto=lambda url, **k: ordre.append("goto"),
                                 get_by_text=lambda texte, exact=True: _Loc(), url="x")
    monkeypatch.setattr(H, "_ouvrir_grille_applications", lambda p: ordre.append("grille"))

    H.navigate_menu(types.SimpleNamespace(page=page, odoo_url="http://x"), "Ventes")

    assert ordre == ["goto", "grille", "clic_application"]


# ── F21 : navigate_menu connecte le NAVIGATEUR quand la page est vide (comme `navigate`) ───────────────────────


def _contexte_menu(url_page):
    ordre = []

    class _Loc:
        first = property(lambda self: self)
        click = lambda self, timeout=None: ordre.append("clic_application")  # noqa: E731

    page = types.SimpleNamespace(url=url_page, goto=lambda url, **k: ordre.append("goto"),
                                 get_by_text=lambda texte, exact=True: _Loc())
    return ordre, types.SimpleNamespace(page=page, odoo_url="http://x")


def test_une_page_vide_est_connectee_AVANT_d_ouvrir_le_menu(monkeypatch):
    """Sans cela, `/web#action=menu` rend la page de CONNEXION : ni grille ni commutateur, 23 s de timeout."""
    ordre, contexte = _contexte_menu("about:blank")
    monkeypatch.setattr(H, "playwright_login", lambda ctx: ordre.append("connexion"))
    monkeypatch.setattr(H, "_ouvrir_grille_applications", lambda p: ordre.append("grille"))

    H.navigate_menu(contexte, "Ventes")

    assert ordre == ["connexion", "goto", "grille", "clic_application"]


def test_une_page_deja_ouverte_n_est_pas_reconnectee(monkeypatch):
    ordre, contexte = _contexte_menu("http://x/web#action=124")
    monkeypatch.setattr(H, "playwright_login", lambda ctx: ordre.append("connexion"))
    monkeypatch.setattr(H, "_ouvrir_grille_applications", lambda p: ordre.append("grille"))

    H.navigate_menu(contexte, "Ventes")

    assert "connexion" not in ordre


def test_navigate_et_navigate_menu_partagent_le_meme_garde(monkeypatch):
    """Deux copies du même geste divergent (incident du 2026-09-18) : une seule fonction pour tout step qui OUVRE une page."""
    appels = []
    monkeypatch.setattr(H, "connecter_le_navigateur_si_page_vide", lambda ctx: appels.append("garde"))
    monkeypatch.setattr(H, "_ouvrir_grille_applications", lambda p: None)
    ordre, contexte = _contexte_menu("about:blank")

    H.navigate(contexte, "/web")
    H.navigate_menu(contexte, "Ventes")

    assert appels == ["garde", "garde"]


def test_le_seul_selecteur_de_repli_est_celui_de_community():
    """Un sélecteur présent aussi sur Enterprise ferait cliquer le repli là où l'ancienne route marche."""
    source = Path(H.__file__).read_text(encoding="utf-8")
    bloc = source[source.index("def _ouvrir_grille_applications"):source.index("def navigate_menu")]

    assert bloc.count("page.locator(") == bloc.count('page.locator(".o_navbar_apps_menu button")') + 1
    assert bloc.count('page.locator(".o_app")') == 1
