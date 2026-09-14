"""`select_field_value` ne trouvait un `<select>` que par son attribut `name` — bug réel cas C39
(SauceDemo, 2026-09-14) : le menu de tri du catalogue (`<select class="product_sort_container"
data-test="product-sort-container">`) n'a AUCUN attribut `name` — ce n'est pas un champ de
formulaire soumis, juste un filtre d'affichage. Le step échouait TOUJOURS ; la capture montrait
pourtant le tri déjà par défaut sur A-Z (SauceDemo), donnant l'illusion trompeuse d'un « tri qui
ne fonctionne pas » alors que le tri n'avait jamais été DÉCLENCHÉ.

L'agent avait pourtant correctement nommé le contrôle : `product_sort_container` est très
exactement sa classe CSS. `select_field_value` tente désormais, dans l'ordre : `name`, `data-test`,
`data-testid`, puis la classe CSS littérale (seulement si `field` est un identifiant CSS valide —
un libellé humain avec espaces ne doit jamais produire un sélecteur invalide).

Preuve dynamique contre le vrai SauceDemo : `tests/test_conformite_connecteur_web.py`. Ces tests-ci
verrouillent la LOGIQUE du repli (jamais un site réel dans une suite pytest).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "behave_runtime" / "steps_library"))

from _base_helpers import ElementIntrouvableError, select_field_value  # noqa: E402


class _FauxOption:
    def __init__(self, value, texte):
        self.value, self.texte = value, texte


class _FauxSelect:
    def __init__(self, options):
        self._options = options
        self.valeur_choisie = None

    def evaluate(self, _script):
        return [[o.value, o.texte] for o in self._options]

    def select_option(self, value):
        self.valeur_choisie = value

    def wait_for(self, **_kw):
        pass  # existe déjà : rien à attendre dans ce faux


class _FauxLocatorUnique:
    """Un seul élément — celui qui existe VRAIMENT selon le test (name, data-test, ou classe)."""

    def __init__(self, element=None):
        self._element = element
        self.first = element if element is not None else self

    def count(self):
        return 1 if self._element is not None else 0

    def wait_for(self, **_kw):
        if self._element is None:
            from playwright.sync_api import TimeoutError as PlaywrightTimeout
            raise PlaywrightTimeout("introuvable")


class _FauxLocatorVide(_FauxLocatorUnique):
    def __init__(self):
        super().__init__(element=None)


class _FaussePage:
    """Un seul `<select>` réel, exposé UNIQUEMENT via l'attribut choisi par le test — les autres
    sélecteurs CSS ne trouvent rien, comme sur la vraie page SauceDemo."""

    def __init__(self, select, *, via: str):
        self._select = select
        self._via = via  # "name" | "data-test" | "data-testid" | "classe"
        self.url = "https://exemple.test/catalogue"

    def get_by_label(self, _texte, exact=False):
        return _FauxLocatorVide()  # aucun <label> ici : resolve_field_name rend `ident` tel quel

    def locator(self, selecteur: str):
        cible = {
            "name": "select[name='product_sort_container']",
            "data-test": "select[data-test='product_sort_container']",
            "data-testid": "select[data-testid='product_sort_container']",
            "classe": "select.product_sort_container",
        }[self._via]
        if selecteur == cible:
            return _FauxLocatorUnique(self._select)
        if selecteur.startswith("input[type='radio']"):
            return _FauxLocatorVide()
        if "," in selecteur:  # le sélecteur combiné du `wait_for`
            return _FauxLocatorUnique(self._select) if cible in selecteur else _FauxLocatorVide()
        return _FauxLocatorVide()


@pytest.mark.parametrize("via", ["name", "data-test", "data-testid", "classe"])
def test_le_select_est_trouve_quel_que_soit_l_attribut_qui_le_porte(via):
    """Le cas C39 : SEULE la classe CSS existe sur le vrai SauceDemo — mais `name`/`data-test`/
    `data-testid` doivent continuer à marcher pour les applis qui, elles, les posent."""
    select = _FauxSelect([_FauxOption("az", "Name (A to Z)"), _FauxOption("za", "Name (Z to A)")])
    page = _FaussePage(select, via=via)

    select_field_value(page, "Name (A to Z)", "product_sort_container")

    assert select.valeur_choisie == "az"


def test_un_identifiant_avec_espaces_n_essaie_jamais_la_classe_css():
    """Un libellé humain (« Trier par nom », espaces compris) ne doit jamais produire
    `select.Trier par nom` — un sélecteur CSS invalide, qui échouerait pour une MAUVAISE raison."""
    select = _FauxSelect([_FauxOption("az", "Name (A to Z)")])
    page = _FaussePage(select, via="classe")
    page._via = "classe"

    with pytest.raises(ElementIntrouvableError):
        select_field_value(page, "Name (A to Z)", "Trier par nom")
