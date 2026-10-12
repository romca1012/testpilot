"""`_web_helpers.attendre_page_rendue` et son emploi avant toute lecture du formulaire de connexion.

Cas réel (OrangeHRM, démo publique, 2026-10-06) : le runtime ouvre la page en `domcontentloaded` puis tente la
connexion aussitôt. Une application à rendu côté client n'a alors RIEN rendu (0 champ, 0 élément interactif) : la
détection concluait « pas de formulaire », ne soumettait rien, et les 4 cas du banc finissaient `blocked` — alors
que la même connexion aboutit dès qu'on attend l'affichage du formulaire (mesuré : ~0,5 s plus tard).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from playwright.sync_api import Error as PlaywrightError

from testpilot.connectors import _web_helpers as wh

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "behave_runtime" / "steps_library"))
import _base_helpers as bh  # noqa: E402

_INTERACTIF = wh._SELECTEUR_ELEMENT_INTERACTIF


class _Page:
    """`rendu_apres` sondages du sélecteur interactif ne trouvent rien, puis un élément apparaît."""

    def __init__(self, rendu_apres: int, url="https://app.test/login", erreurs: int = 0, texte_apres: int | None = None):
        self.url = url
        self._rendu_apres = rendu_apres
        self._erreurs = erreurs
        self._texte_apres = texte_apres   # None : la page n'affiche jamais de texte ; n : du texte après n sondages
        self.requetes: list[str] = []
        self.attentes = 0

    def evaluate(self, _script):
        return self._texte_apres is not None and self.requetes.count(_INTERACTIF) > self._texte_apres

    def query_selector(self, selecteur):
        self.requetes.append(selecteur)
        if selecteur == _INTERACTIF:
            if self._erreurs > 0:
                self._erreurs -= 1
                raise PlaywrightError("Unable to adopt element handle from a different document")
            sondages = self.requetes.count(_INTERACTIF)
            return object() if sondages > self._rendu_apres else None
        return None

    def query_selector_all(self, _selecteur):
        return []

    def wait_for_timeout(self, _ms):
        self.attentes += 1


def test_une_page_deja_rendue_ne_coute_aucune_attente():
    page = _Page(rendu_apres=0)

    assert wh.attendre_page_rendue(page) is True
    assert page.attentes == 0


def test_une_page_au_rendu_tardif_est_attendue_puis_reconnue():
    page = _Page(rendu_apres=5)

    assert wh.attendre_page_rendue(page) is True
    assert page.attentes == 5  # a patienté exactement le temps du rendu, pas plus


def test_falsifiable_une_page_qui_ne_rend_jamais_rien_est_attendue_de_facon_bornee_sans_lever():
    page = _Page(rendu_apres=10**9)

    assert wh.attendre_page_rendue(page) is False
    assert page.attentes == wh._ITERATIONS_ATTENTE_RENDU  # 8 s au plus, jamais un blocage


def test_falsifiable_une_page_de_texte_sans_element_interactif_ne_coute_pas_la_borne_longue():
    """Mesuré le 2026-10-12 : chaque scénario dont la page d'entrée n'a ni champ, ni bouton, ni lien attendait 8 s.
    Une page qui affiche du texte est rendue : seul le délai de grâce est dû."""
    page = _Page(rendu_apres=10**9, texte_apres=0)

    assert wh.attendre_page_rendue(page) is False
    assert page.attentes == wh._ITERATIONS_GRACE_AVEC_TEXTE
    assert page.attentes < wh._ITERATIONS_ATTENTE_RENDU


def test_falsifiable_la_grace_ne_s_applique_pas_a_une_page_encore_vide():
    """Le cas d'origine (OrangeHRM : 0 champ, 0 élément interactif, 0 texte) : tant que la page est VIDE, on attend
    bien au-delà du délai de grâce, et le formulaire tardif est reconnu."""
    tardif = wh._ITERATIONS_GRACE_AVEC_TEXTE * 3
    page = _Page(rendu_apres=tardif)

    assert wh.attendre_page_rendue(page) is True
    assert page.attentes == tardif


def test_un_ecran_d_attente_bref_puis_le_formulaire_est_reconnu_dans_le_delai_de_grace():
    """Un texte provisoire (« Chargement… ») puis le formulaire, moins d'une seconde après : reconnu."""
    page = _Page(rendu_apres=wh._ITERATIONS_GRACE_AVEC_TEXTE - 2, texte_apres=0)

    assert wh.attendre_page_rendue(page) is True


def test_une_page_vide_puis_du_texte_n_a_que_la_grace_a_partir_du_texte():
    """Vide pendant 20 sondages, puis du texte sans élément interactif : la grâce se compte à partir du texte."""
    page = _Page(rendu_apres=10**9, texte_apres=20)

    assert wh.attendre_page_rendue(page) is False
    assert page.attentes == 20 + wh._ITERATIONS_GRACE_AVEC_TEXTE


def test_une_erreur_de_navigation_pendant_le_sondage_vaut_pas_encore_rendu():
    page = _Page(rendu_apres=0, erreurs=3)

    assert wh.attendre_page_rendue(page) is True
    assert page.attentes == 3


def test_aucune_attente_sur_about_blank():
    page = _Page(rendu_apres=10**9, url="about:blank")

    assert wh.attendre_page_rendue(page) is False
    assert page.requetes == []  # rien sondé, rien attendu : il n'y a aucune page à rendre
    assert page.attentes == 0


def test_la_connexion_generique_attend_le_rendu_AVANT_de_chercher_le_formulaire():
    """Le cœur du bug : avant ce correctif, le champ mot de passe était cherché sur une page encore vide."""
    page = _Page(rendu_apres=10**9)

    assert wh.tenter_connexion_generique(page, "Admin", "x") is False

    premiere_lecture_du_formulaire = page.requetes.index("input[type='password']")
    assert premiere_lecture_du_formulaire >= wh._ITERATIONS_ATTENTE_RENDU  # après les sondages d'attente
    assert set(page.requetes[:premiere_lecture_du_formulaire]) == {_INTERACTIF}


def test_sans_identifiants_aucune_attente_n_est_imposee_a_une_application_publique():
    """Application sans connexion (identifiants vides) : on ne ralentit pas son démarrage de 8 s pour rien."""
    page = _Page(rendu_apres=10**9)

    assert wh.tenter_connexion_generique(page, "", "") is False
    assert page.requetes == []
    assert page.attentes == 0


def test_la_connexion_du_runtime_attend_le_rendu_avant_de_lire_la_page(monkeypatch):
    """Même garde côté runtime : `connexion_web_utilisateur` lisait le schéma de la page avant qu'elle n'existe."""
    ordre: list[str] = []
    monkeypatch.setattr(bh, "attendre_page_rendue", lambda page: ordre.append("attente"))
    monkeypatch.setattr(bh, "_schema_de_connexion", lambda page: ordre.append("lecture") or "inconnu")
    monkeypatch.setattr(bh, "_mot_de_passe_visible", lambda page: False)
    import types
    contexte = types.SimpleNamespace(page=_Page(rendu_apres=0), web_user="", web_password="")

    bh.connexion_web_utilisateur(contexte)

    assert ordre == ["attente", "lecture"]
