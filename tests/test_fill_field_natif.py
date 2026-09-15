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
    """Un `<input type="text">` — `.fill()` réussit ou lève, selon le scénario testé.

    ⚠️ **Porte aussi la lecture de la valeur retenue** (étape 2.1 du plan de consolidation,
    2026-09-15) : `fill_field` et `_verifier_valeur_retenue` opèrent tous deux sur l'ÉLÉMENT déjà
    résolu par `locate_field`, plus jamais sur une reconstruction `[name=...]` côté page — cet
    élément factice doit donc savoir répondre aux TROIS scripts distincts qu'on lui envoie
    (tagName, repli JS d'écriture, lecture de la valeur retenue), reconnus par un marqueur propre
    à chacun plutôt que par leur ordre d'appel."""

    def __init__(self, *, leve_fill: bool = False, valeur_retenue: str | None = None):
        self._leve_fill = leve_fill
        self.valeur_remplie: str | None = None
        self.scripts_evalues: list[str] = []
        self._valeur_retenue = valeur_retenue

    def evaluate(self, script, *args):
        self.scripts_evalues.append(script)
        if "tagName" in script:
            return "input"
        if "dispatchEvent" in script:
            return None  # le repli JS de fill_field lui-même : une écriture, rien à en tirer
        if ".type" in script:
            return "text"
        return self._valeur_retenue  # lecture de la valeur retenue (_verifier_valeur_retenue)

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
        return 1  # `locate_field` : le champ existe par son attribut `name`, tel quel

    def wait_for(self, **kw):
        pass


class _FaussePage:
    def __init__(self, element):
        self._element = element

    def locator(self, _selector):
        return _FauxLocatorChamp(self._element)

    def wait_for_selector(self, *_a, **_kw):
        pass


def _repli_js_a_ete_utilise(element: _FauxElement) -> bool:
    return any("dispatchEvent" in s for s in element.scripts_evalues)


def test_fill_natif_est_utilise_en_premier_et_reussit():
    element = _FauxElement(valeur_retenue="standard_user")
    page = _FaussePage(element)

    fill_field(page, "user-name", "standard_user")

    assert element.valeur_remplie == "standard_user", ".fill() doit recevoir la valeur telle quelle"
    assert not _repli_js_a_ete_utilise(element), \
        "le repli JS ne doit JAMAIS servir quand .fill() réussit"


def test_le_repli_js_ne_sert_QUE_si_fill_native_leve():
    element = _FauxElement(leve_fill=True, valeur_retenue="standard_user")
    page = _FaussePage(element)

    fill_field(page, "user-name", "standard_user")  # ne doit pas lever malgré l'échec de .fill()

    assert element.valeur_remplie is None, ".fill() a échoué : il n'a rien pu écrire"
    assert _repli_js_a_ete_utilise(element), "le repli JS (widgets Odoo) doit rester disponible"


def test_le_repli_js_agit_sur_l_element_deja_resolu_jamais_un_selecteur_reconstruit():
    """Le cœur de l'étape 2.1 : le repli JS ne doit plus reconstruire `[name=...]` côté page — il
    reçoit l'élément déjà résolu par `locate_field`, ce qui le rend valable même pour un champ
    résolu par data-test/data-testid/classe CSS/libellé, sans attribut `name` du tout."""
    element = _FauxElement(leve_fill=True, valeur_retenue="standard_user")
    page = _FaussePage(element)

    fill_field(page, "user-name", "standard_user")

    scripts = [s for s in element.scripts_evalues if "dispatchEvent" in s]
    assert scripts, "le repli JS doit avoir tourné"
    assert "querySelector" not in scripts[0], (
        "le repli ne doit plus reconstruire un sélecteur — il agit sur l'élément déjà résolu")


def test_la_valeur_transmise_a_fill_n_est_jamais_echappee():
    """⚠️ `.fill()` est un appel Playwright, pas du JS interpolé — lui passer la version ÉCHAPPÉE
    (pensée pour le repli JS) écrirait des antislashs/apostrophes littéraux dans le champ."""
    element = _FauxElement(valeur_retenue="l'entrepôt d'Alice")
    page = _FaussePage(element)

    fill_field(page, "nom", "l'entrepôt d'Alice")

    assert element.valeur_remplie == "l'entrepôt d'Alice"


def test_la_valeur_transmise_au_repli_js_n_est_jamais_echappee_non_plus():
    """Depuis l'étape 2.1, le repli JS reçoit la valeur BRUTE en argument Playwright (comme
    `.fill()`), plus une version pré-échappée interpolée dans le script — l'échappement manuel
    (`safe = value.replace(...)`) n'a donc plus de raison d'exister."""
    element = _FauxElement(leve_fill=True, valeur_retenue="l'entrepôt d'Alice")
    page = _FaussePage(element)

    fill_field(page, "nom", "l'entrepôt d'Alice")

    assert element.valeur_remplie is None  # .fill() a levé : rien écrit par ce chemin
    # Aucune trace de l'échappement manuel (`\\'`) dans les scripts envoyés à l'élément.
    assert not any("\\'" in s for s in element.scripts_evalues)
