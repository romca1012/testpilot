"""`_web_helpers._confirmation_post_connexion_obtenue` / `_attendre_confirmation_post_connexion` face à une
redirection qui CHANGE DE DOCUMENT pendant le sondage.

Cas réel (OrangeHRM, démo publique, 2026-10-06) : juste après l'envoi du formulaire de connexion, la page
redirige vers le tableau de bord ; `page.query_selector` lève alors « Unable to adopt element handle from a
different document ». La fonction d'attente promettait de ne JAMAIS lever (`_attendre_confirmation_post_connexion`) :
l'exploration entière échouait pourtant sur cette erreur, et OrangeHRM n'était exploré que sur sa page de connexion.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Error as PlaywrightError

from testpilot.connectors import _web_helpers as wh

_ERREUR = "Page.query_selector: Unable to adopt element handle from a different document"


class _PageEnRedirection:
    """URL inchangée ; `query_selector` lève `erreurs` fois (document en cours de remplacement), puis rend
    `apres` (le champ mot de passe a disparu : la connexion a abouti)."""

    def __init__(self, erreurs: int, apres=None):
        self.url = "https://app.test/login"
        self._restantes = erreurs
        self._apres = apres
        self.sondages = 0

    def query_selector(self, _selecteur):
        self.sondages += 1
        if self._restantes > 0:
            self._restantes -= 1
            raise PlaywrightError(_ERREUR)
        return self._apres

    def wait_for_timeout(self, _ms):
        pass


def test_une_navigation_en_cours_n_est_pas_une_erreur_c_est_pas_encore_confirme():
    page = _PageEnRedirection(erreurs=1)

    assert wh._confirmation_post_connexion_obtenue(page, "https://app.test/login") is False


def test_l_attente_survit_au_changement_de_document_puis_confirme_quand_la_page_se_stabilise():
    page = _PageEnRedirection(erreurs=3)  # trois sondages tombent pendant la redirection, le quatrième réussit

    wh._attendre_confirmation_post_connexion(page, "https://app.test/login")  # ne lève pas

    assert page.sondages == 4  # a continué de sonder, puis s'est arrêtée dès la confirmation


def test_falsifiable_une_erreur_n_est_jamais_prise_pour_une_connexion_reussie():
    """Garde contre le faux succès : si la page reste en erreur, la boucle va jusqu'à sa borne et rend la main
    SANS certitude — jamais `True` sur la seule foi d'une exception."""
    page = _PageEnRedirection(erreurs=10_000)

    wh._attendre_confirmation_post_connexion(page, "https://app.test/login")

    assert page.sondages == wh._ITERATIONS_ATTENTE_POST_CONNEXION  # bornée, sans lever
    assert wh._confirmation_post_connexion_obtenue(page, "https://app.test/login") is False


def test_un_changement_d_url_confirme_sans_meme_toucher_au_dom():
    page = _PageEnRedirection(erreurs=10_000)  # le DOM serait inutilisable…
    page.url = "https://app.test/dashboard"      # …mais l'URL a changé : signe suffisant

    assert wh._confirmation_post_connexion_obtenue(page, "https://app.test/login") is True
    assert page.sondages == 0


def test_la_disparition_du_champ_mot_de_passe_confirme_toujours():
    page = _PageEnRedirection(erreurs=0, apres=None)

    assert wh._confirmation_post_connexion_obtenue(page, "https://app.test/login") is True


def test_un_champ_mot_de_passe_encore_present_n_est_pas_une_confirmation():
    page = _PageEnRedirection(erreurs=0, apres=object())

    assert wh._confirmation_post_connexion_obtenue(page, "https://app.test/login") is False


def test_une_erreur_qui_n_est_pas_playwright_n_est_pas_avalee():
    """Seule l'erreur de NAVIGATION de Playwright est tolérée : un vrai bug du code (ici une `ValueError`) doit
    continuer de remonter plutôt que d'être masqué en « pas encore confirmé »."""
    class _PageCassee:
        url = "https://app.test/login"

        def query_selector(self, _s):
            raise ValueError("bug du code appelant")

    with pytest.raises(ValueError):
        wh._confirmation_post_connexion_obtenue(_PageCassee(), "https://app.test/login")
