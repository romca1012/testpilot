"""`fill_field` doit préférer `.fill()` NATIF Playwright — bug SauceDemo réel (2026-09-14).

⚠️ **Le vrai bug, mesuré en conditions réelles contre https://www.saucedemo.com.** `fill_field`
écrivait la valeur d'un champ texte en JS brut (`el.value = ...` + `dispatchEvent()` synthétique).
Playwright relit alors bien la valeur dans le DOM — mais SauceDemo, comme beaucoup d'applications
modernes qui gardent leur PROPRE état interne au lieu de relire le DOM à la soumission, ne voyait
JAMAIS ce changement : un clic « Login » avec `user-name` visiblement rempli à `standard_user`
produisait pourtant "Username is required", comme si le champ était vide. `.fill()` (qui simule
une vraie saisie au niveau du navigateur, un événement FIABLE — contrairement à un `dispatchEvent`
synthétique) résolvait le problème, vérifié en rejouant le scénario réel avant/après.

Ces tests figent la LOGIQUE de préférence (jamais un site réel dans une suite pytest — trop lent,
trop fragile) : `.fill()` d'abord, le JS brut seulement en repli si `.fill()` lève — préservé pour
les widgets Odoo qui l'exigeaient à l'origine, jamais supprimé.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "behave_runtime" / "steps_library"))

from _base_helpers import fill_field


class _FauxElement:
    """Un `<input type="text">` — `.fill()` réussit ou lève, selon le scénario testé."""

    def __init__(self, *, leve_fill: bool = False):
        self._leve_fill = leve_fill
        self.valeur_remplie: str | None = None

    def evaluate(self, script):
        # `fill_field` ne lit que tagName puis .type sur cet élément — un input texte simple.
        return "input" if "tagName" in script else "text"

    def wait_for(self, **kw):
        pass  # `locate_field` : le champ existe déjà (`.first` pointe directement dessus)

    def fill(self, value):
        if self._leve_fill:
            raise RuntimeError("widget qui refuse .fill() (simulation)")
        self.valeur_remplie = value


class _FauxLocatorChamp:
    def __init__(self, element):
        self.first = element

    def count(self):
        return 1  # `resolve_field_name` : le champ existe par son attribut `name`, tel quel

    def wait_for(self, **kw):
        pass


class _FaussePage:
    def __init__(self, element, *, valeur_retenue: str):
        self._element = element
        self._valeur_retenue = valeur_retenue
        self.scripts_evalues: list[str] = []

    def locator(self, _selector):
        return _FauxLocatorChamp(self._element)

    def wait_for_selector(self, *_a, **_kw):
        pass

    def evaluate(self, script, *args):
        self.scripts_evalues.append(script)
        if args:
            # `_verifier_valeur_retenue(page, name, ecrit)` relit CE que le champ a gardé.
            return self._valeur_retenue
        return None  # le repli JS de fill_field lui-même : une écriture, rien à rendre


def _repli_js_a_ete_utilise(page: _FaussePage) -> bool:
    return any("el.value =" in s for s in page.scripts_evalues)


def test_fill_natif_est_utilise_en_premier_et_reussit():
    element = _FauxElement()
    page = _FaussePage(element, valeur_retenue="standard_user")

    fill_field(page, "user-name", "standard_user")

    assert element.valeur_remplie == "standard_user", ".fill() doit recevoir la valeur telle quelle"
    assert not _repli_js_a_ete_utilise(page), "le repli JS ne doit JAMAIS servir quand .fill() réussit"


def test_le_repli_js_ne_sert_QUE_si_fill_native_leve():
    element = _FauxElement(leve_fill=True)
    page = _FaussePage(element, valeur_retenue="standard_user")

    fill_field(page, "user-name", "standard_user")  # ne doit pas lever malgré l'échec de .fill()

    assert element.valeur_remplie is None, ".fill() a échoué : il n'a rien pu écrire"
    assert _repli_js_a_ete_utilise(page), "le repli JS (widgets Odoo) doit rester disponible"


def test_la_valeur_transmise_a_fill_n_est_jamais_echappee():
    """⚠️ `.fill()` est un appel Playwright, pas du JS interpolé — lui passer la version ÉCHAPPÉE
    (pensée pour le repli JS) écrirait des antislashs/apostrophes littéraux dans le champ."""
    element = _FauxElement()
    page = _FaussePage(element, valeur_retenue="l'entrepôt d'Alice")

    fill_field(page, "nom", "l'entrepôt d'Alice")

    assert element.valeur_remplie == "l'entrepôt d'Alice"
