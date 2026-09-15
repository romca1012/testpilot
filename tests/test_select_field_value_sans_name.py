"""`locate_field` — la résolution UNIFIÉE d'un champ, remplaçant les cascades ad hoc dispersées
(bug réel cas C39, SauceDemo, 2026-09-14 : `select_field_value` ne trouvait un `<select>` que par
son attribut `name`). Étape 1 du plan de généricité demandé par le porteur (recherche du
2026-09-14, doc officielle Playwright/Testing Library) : une cascade UNIQUE, appliquée d'abord à
`select_field_value` — le premier appelant migré.

Le menu de tri du catalogue SauceDemo n'a AUCUN attribut `name` — ce n'est pas un champ de
formulaire soumis, juste un filtre d'affichage (`<select class="product_sort_container"
data-test="product-sort-container">`). `locate_field` tente, dans l'ordre : `name`, `data-test`,
`data-testid`, la classe CSS littérale (seulement si syntaxiquement valide), puis le libellé et
le placeholder — chaque repli étant TRACÉ (0007/§5), jamais silencieux.

Preuve dynamique contre le vrai SauceDemo : `tests/test_conformite_connecteur_web.py`. Ces tests-ci
verrouillent la LOGIQUE de la cascade et de l'attente (jamais un site réel dans une suite pytest).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "behave_runtime" / "steps_library"))

from _base_helpers import (  # noqa: E402
    ElementIntrouvableError, SELECTOR_TIER_FILE_ENV, locate_field, select_field_value,
)


class _FauxElement:
    """Ce que `.first` rend sur un élément trouvé — assez pour `evaluate()` (tag ET options,
    cette dernière lue par `select_option_strict`) ET `wait_for()` (paliers libellé/placeholder
    de `locate_field`)."""

    def __init__(self, tag="select", options=(("az", "Name (A to Z)"), ("za", "Name (Z to A)"))):
        self.tag = tag
        self.options = options
        self.valeur_choisie = None

    def evaluate(self, script):
        if "tagName" in script:
            return self.tag
        if "options" in script:  # `select_option_strict._options_of`
            return [list(o) for o in self.options]
        return None

    def wait_for(self, **_kw):
        pass

    def select_option(self, value):
        self.valeur_choisie = value


class _FauxLocator:
    def __init__(self, trouve: bool, element: _FauxElement | None = None):
        self._trouve = trouve
        self.first = element if (trouve and element is not None) else self

    def count(self):
        return 1 if self._trouve else 0

    def wait_for(self, **_kw):
        if not self._trouve:
            raise PlaywrightTimeout("introuvable")

    def evaluate(self, _script):
        # `.first` retombe ici quand rien n'a été trouvé (voir __init__) : jamais appelé en
        # pratique côté production (toujours gardé par un `count() > 0`), présent pour la sûreté.
        return None


class _FaussePage:
    """Simule SauceDemo : EXACTEMENT un sélecteur technique (ou un libellé/placeholder) existe —
    les autres ne trouvent rien, comme sur la vraie page."""

    def __init__(self, *, selecteur_existant: str = "", via_libelle=False, via_placeholder=False,
                 tag="select"):
        self._selecteur_existant = selecteur_existant
        self._via_libelle = via_libelle
        self._via_placeholder = via_placeholder
        self.url = "https://exemple.test/catalogue"
        self._element = _FauxElement(tag=tag)

    def locator(self, selecteur):
        trouve = bool(self._selecteur_existant) and self._selecteur_existant in selecteur
        return _FauxLocator(trouve, element=self._element if trouve else None)

    def get_by_label(self, _texte, exact=False):
        return _FauxLocator(self._via_libelle, element=self._element)

    def get_by_placeholder(self, _texte, exact=False):
        return _FauxLocator(self._via_placeholder, element=self._element)


# ── 1. `locate_field` — la cascade, isolée ─────────────────────────────────────

@pytest.mark.parametrize("attribut,selecteur,tier_attendu", [
    ("name", "[name=\"product_sort_container\"]", "name"),
    ("data-test", "[data-test=\"product_sort_container\"]", "data_test"),
    ("data-testid", "[data-testid=\"product_sort_container\"]", "data_testid"),
    ("classe CSS", ".product_sort_container", "css_class"),
])
def test_locate_field_trouve_par_chaque_attribut_technique(
        tmp_path, monkeypatch, attribut, selecteur, tier_attendu):
    """Le cas C39 : SEULE la classe CSS existe sur le vrai SauceDemo — mais `name`/`data-test`/
    `data-testid` doivent continuer à marcher pour les applis qui, elles, les posent.

    Consigne aussi le PALIER qui a résolu (§1.2, mémoire de dérive) — y compris `name`, le cas
    silencieux : sans lui, la toute première dérive d'un champ jusque-là stable n'aurait rien à
    quoi se comparer."""
    sidecar = tmp_path / "tiers.jsonl"
    monkeypatch.setenv(SELECTOR_TIER_FILE_ENV, str(sidecar))
    page = _FaussePage(selecteur_existant=selecteur)

    loc = locate_field(page, "product_sort_container")

    assert loc.count() > 0, f"non trouvé via {attribut}"
    lignes = [json.loads(l) for l in sidecar.read_text(encoding="utf-8").splitlines()]
    assert lignes == [{"ident": "product_sort_container", "tier": tier_attendu}]


def test_repli_sur_le_libelle_si_aucun_attribut_technique(tmp_path, monkeypatch):
    sidecar = tmp_path / "tiers.jsonl"
    monkeypatch.setenv(SELECTOR_TIER_FILE_ENV, str(sidecar))
    page = _FaussePage(via_libelle=True)

    loc = locate_field(page, "Trier par")

    assert loc.count() > 0
    lignes = [json.loads(l) for l in sidecar.read_text(encoding="utf-8").splitlines()]
    assert lignes == [{"ident": "Trier par", "tier": "label"}]


def test_repli_sur_le_placeholder_en_dernier_recours(tmp_path, monkeypatch):
    sidecar = tmp_path / "tiers.jsonl"
    monkeypatch.setenv(SELECTOR_TIER_FILE_ENV, str(sidecar))
    page = _FaussePage(via_placeholder=True)

    loc = locate_field(page, "Rechercher")

    assert loc.count() > 0
    lignes = [json.loads(l) for l in sidecar.read_text(encoding="utf-8").splitlines()]
    assert lignes == [{"ident": "Rechercher", "tier": "placeholder"}]


def test_locate_field_ne_consigne_rien_quand_rien_n_est_trouve(tmp_path, monkeypatch):
    sidecar = tmp_path / "tiers.jsonl"
    monkeypatch.setenv(SELECTOR_TIER_FILE_ENV, str(sidecar))
    page = _FaussePage()

    locate_field(page, "champ_fantome")

    assert not sidecar.exists()


def test_rien_trouve_nulle_part_rend_un_locator_vide_pas_une_exception():
    """`locate_field` ne lève JAMAIS — à l'appelant de décider comment échouer (même contrat que
    `resolve_field_name`, qui rendait `ident` inchangé plutôt que de lever)."""
    page = _FaussePage()

    loc = locate_field(page, "champ_fantome")

    assert loc.count() == 0


def test_un_identifiant_avec_espaces_n_essaie_jamais_la_classe_css():
    """Un libellé humain (« Trier par nom », espaces compris) ne doit jamais produire
    `.Trier par nom` — un sélecteur CSS invalide, qui échouerait pour une MAUVAISE raison."""
    page = _FaussePage(selecteur_existant=".Trier par nom")  # n'existe QUE sous cette forme invalide

    loc = locate_field(page, "Trier par nom")

    assert loc.count() == 0  # jamais tenté comme classe : correctement introuvable


# ── 2. `select_field_value` — le premier appelant migré ────────────────────────

def test_select_field_value_trouve_un_select_SANS_name_via_sa_classe():
    """Reproduit le cas C39 réel : un `<select>` identifié UNIQUEMENT par sa classe CSS."""
    page = _FaussePage(selecteur_existant=".product_sort_container", tag="select")

    select_field_value(page, "za", "product_sort_container")

    assert page._element.valeur_choisie == "za"


def test_select_field_value_sans_select_ni_radio_leve_element_introuvable():
    page = _FaussePage()  # rien n'existe

    with pytest.raises(ElementIntrouvableError, match="introuvable"):
        select_field_value(page, "za", "champ_fantome")
