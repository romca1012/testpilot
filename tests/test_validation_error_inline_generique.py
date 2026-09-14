"""`validation_error_inline` ne reconnaissait QUE Odoo — bug réel SauceDemo C37 (2026-09-14).

⚠️ **Le vrai bug, confirmé en conditions réelles contre https://www.saucedemo.com.** Le step
générique « une erreur de validation est affichée dans le formulaire » (`generic/_generic_steps.py`)
délègue à `validation_error_inline`, qui ne vérifiait que `s_website_form_field.o_has_error` — une
classe CSS du website builder Odoo. SauceDemo affiche pourtant l'erreur attendue au bon endroit
(« Epic sadface: Username is required »), mais en `<h3 data-test="error" role="alert">` — jamais vu
par ce contrôle. Le cas C37 (formulaire de connexion vide, refus attendu ET obtenu) passait en
`failed`, accusant l'application d'un défaut qui était en réalité le nôtre.

Ces tests figent la LOGIQUE de reconnaissance (jamais un site réel dans une suite pytest — trop
lent, trop fragile) : `role="alert"` d'abord (signal WAI-ARIA standard, utile à toute application
accessible), le motif Odoo ensuite en repli — préservé, jamais supprimé.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "behave_runtime" / "steps_library"))

from _base_helpers import validation_error_inline


class _FauxElement:
    def __init__(self, visible: bool):
        self._visible = visible

    def is_visible(self):
        return self._visible


class _FauxLocatorAlertes:
    """`page.locator('[role="alert"]')` — une liste d'éléments, visibles ou non, dans l'ordre où
    Playwright les rendrait (le `.nth(i)` de `validation_error_inline` en dépend)."""

    def __init__(self, visibilites: tuple[bool, ...]):
        self._visibilites = visibilites

    def count(self):
        return len(self._visibilites)

    def nth(self, i):
        return _FauxElement(self._visibilites[i])


class _FauxLocatorOdoo:
    def __init__(self, visible: bool):
        self.first = _FauxElement(visible)


class _FaussePage:
    def __init__(self, *, alertes: tuple[bool, ...] = (), odoo_visible: bool = False):
        self._alertes = alertes
        self._odoo_visible = odoo_visible

    def locator(self, selector):
        if selector == '[role="alert"]':
            return _FauxLocatorAlertes(self._alertes)
        if "s_website_form_field" in selector:
            return _FauxLocatorOdoo(self._odoo_visible)
        raise AssertionError(f"sélecteur inattendu : {selector}")


def test_un_role_alert_visible_est_reconnu_meme_sans_aucune_classe_odoo():
    """Le cas SauceDemo C37, reproduit : aucune classe Odoo nulle part, un `role=alert` visible."""
    page = _FaussePage(alertes=(True,))
    validation_error_inline(page)   # ne doit PAS lever


def test_le_motif_odoo_reste_reconnu_en_repli():
    """Le comportement d'AVANT ce correctif ne doit pas régresser sur Odoo."""
    page = _FaussePage(alertes=(), odoo_visible=True)
    validation_error_inline(page)   # ne doit PAS lever


def test_un_role_alert_present_mais_invisible_ne_suffit_pas():
    """Un `role=alert` dans le DOM mais caché (ex. un gabarit de toast jamais affiché) ne doit
    pas faire passer un formulaire qui n'a RIEN montré."""
    page = _FaussePage(alertes=(False,), odoo_visible=False)
    with pytest.raises(AssertionError, match="Aucune erreur de validation visible"):
        validation_error_inline(page)


def test_le_premier_alert_invisible_n_empeche_pas_de_voir_le_second():
    page = _FaussePage(alertes=(False, True))
    validation_error_inline(page)   # ne doit PAS lever


def test_aucune_erreur_nulle_part_leve_toujours():
    page = _FaussePage(alertes=(), odoo_visible=False)
    with pytest.raises(AssertionError, match="Aucune erreur de validation visible"):
        validation_error_inline(page)
