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

import _base_helpers  # noqa: E402
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
    # Lot 05 : la ligne du sidecar porte aussi le SCÉNARIO courant — posé ici explicitement, et attendu tel quel.
    monkeypatch.setitem(_base_helpers._ETAT_CONSTAT, "scenario", "Scénario X")
    page = _FaussePage(selecteur_existant=selecteur)

    loc = locate_field(page, "product_sort_container")

    assert loc.count() > 0, f"non trouvé via {attribut}"
    lignes = [json.loads(l) for l in sidecar.read_text(encoding="utf-8").splitlines()]
    assert lignes == [{"ident": "product_sort_container", "tier": tier_attendu, "scenario": "Scénario X"}]


def test_repli_sur_le_libelle_si_aucun_attribut_technique(tmp_path, monkeypatch):
    sidecar = tmp_path / "tiers.jsonl"
    monkeypatch.setenv(SELECTOR_TIER_FILE_ENV, str(sidecar))
    # Lot 05 : la ligne du sidecar porte aussi le SCÉNARIO courant — posé ici explicitement, et attendu tel quel.
    monkeypatch.setitem(_base_helpers._ETAT_CONSTAT, "scenario", "Scénario X")
    page = _FaussePage(via_libelle=True)

    loc = locate_field(page, "Trier par")

    assert loc.count() > 0
    lignes = [json.loads(l) for l in sidecar.read_text(encoding="utf-8").splitlines()]
    assert lignes == [{"ident": "Trier par", "tier": "label", "scenario": "Scénario X"}]


def test_repli_sur_le_placeholder_en_dernier_recours(tmp_path, monkeypatch):
    sidecar = tmp_path / "tiers.jsonl"
    monkeypatch.setenv(SELECTOR_TIER_FILE_ENV, str(sidecar))
    # Lot 05 : la ligne du sidecar porte aussi le SCÉNARIO courant — posé ici explicitement, et attendu tel quel.
    monkeypatch.setitem(_base_helpers._ETAT_CONSTAT, "scenario", "Scénario X")
    page = _FaussePage(via_placeholder=True)

    loc = locate_field(page, "Rechercher")

    assert loc.count() > 0
    lignes = [json.loads(l) for l in sidecar.read_text(encoding="utf-8").splitlines()]
    assert lignes == [{"ident": "Rechercher", "tier": "placeholder", "scenario": "Scénario X"}]


def test_locate_field_ne_consigne_rien_quand_rien_n_est_trouve(tmp_path, monkeypatch):
    sidecar = tmp_path / "tiers.jsonl"
    monkeypatch.setenv(SELECTOR_TIER_FILE_ENV, str(sidecar))
    # Lot 05 : la ligne du sidecar porte aussi le SCÉNARIO courant — posé ici explicitement, et attendu tel quel.
    monkeypatch.setitem(_base_helpers._ETAT_CONSTAT, "scenario", "Scénario X")
    page = _FaussePage()

    locate_field(page, "champ_fantome")

    assert not sidecar.exists()


class _LocatorPlusieursCandidats:
    """Simule `[name="name"]` matchant PLUSIEURS éléments (un champ caché + le vrai titre) — le
    cas RÉEL mesuré en run (Sapian, 2026-09-22) : le formulaire de création d'un ticket Helpdesk
    avait un `[name="name"]` caché en plus du vrai titre, et `.first` prenait le mauvais."""

    def __init__(self, *, avec_visible: bool):
        self._avec_visible = avec_visible

    @property
    def first(self):
        return self

    def count(self):
        return 1 if self._avec_visible else 3  # ":visible" filtre à 1 ; le brut en voit 3

    def wait_for(self, **_kw):
        pass

    def evaluate(self, _script):
        return "input"

    def get_attribute(self, _attr):
        return "text"


class _PageChampAmbigu:
    def __init__(self):
        self.url = "https://exemple.test/ticket"

    def locator(self, selecteur):
        return _LocatorPlusieursCandidats(avec_visible=":visible" in selecteur)

    def get_by_label(self, _texte, exact=False):
        return _LocatorPlusieursCandidats(avec_visible=False)

    def get_by_placeholder(self, _texte, exact=False):
        return _LocatorPlusieursCandidats(avec_visible=False)


def test_locate_field_filtre_par_visibilite_quand_plusieurs_candidats_techniques(tmp_path,
                                                                                 monkeypatch):
    """Le VRAI bug mesuré (Sapian, 2026-09-22) : `[name="name"]` matchait plusieurs éléments sur
    le formulaire de ticket Helpdesk, `.first` prenait un champ CACHÉ (jamais le vrai titre
    visible) — Odoo refusait alors silencieusement la sauvegarde (titre resté vide). Un humain ne
    peut PHYSIQUEMENT PAS remplir un champ qu'il ne voit pas : `locate_field` doit préférer le(s)
    candidat(s) visible(s) dès que le palier technique en trouve plus d'un."""
    page = _PageChampAmbigu()
    loc = locate_field(page, "name")
    assert loc.count() == 1  # le Locator filtré ":visible", pas les 3 candidats bruts


# ── Descente dans un conteneur non éditable (Sapian, 2026-09-23) ─────────────────────────────
#
# Odoo pose le nom technique STABLE d'un champ sur le `<div class="o_field_widget">` qui ENGLOBE
# le vrai contrôle, jamais sur l'`<input>`/`<textarea>` interne (qui, lui, n'a souvent aucun
# `name` et un `id` volatil selon l'ordre de montage de la session — un `id` capturé à la
# génération ne correspond à RIEN à l'exécution, une session différente).

class _ElementInterne:
    def __init__(self, tag):
        self._tag = tag

    def evaluate(self, script, *_a):
        return self._tag if "tagName" in script else ""


class _LocatorInterne:
    """`conteneur.locator("input, select, textarea")` — les contrôles réellement DANS le
    conteneur résolu."""

    def __init__(self, elements, *, filtre_visible=False):
        self._elements = elements
        self._filtre_visible = filtre_visible

    def count(self):
        return len(self._elements)

    @property
    def first(self):
        return self._elements[0] if self._elements else self

    def locator(self, selecteur):
        if selecteur == ":visible" or selecteur.endswith(":visible"):
            return _LocatorInterne(self._elements[:1] if self._elements else [],
                                   filtre_visible=True)
        return self


class _LocatorConteneur:
    def __init__(self, *, tag="div", enfants=(), plusieurs_visibles=False):
        self._tag = tag
        self._enfants = list(enfants)
        self._plusieurs_visibles = plusieurs_visibles

    @property
    def first(self):
        return self

    def count(self):
        return 1

    def wait_for(self, **_kw):
        pass

    def evaluate(self, script, *_a):
        return self._tag if "tagName" in script else ""

    def locator(self, selecteur):
        if "input" in selecteur and "select" in selecteur:
            if self._plusieurs_visibles:
                return _LocatorInterne(self._enfants)
            return _LocatorInterne(self._enfants[:1] if self._enfants else [])
        return _LocatorInterne([])


class _PageChampDansConteneur:
    def __init__(self, conteneur):
        self.url = "https://exemple.test/web#action=1&model=helpdesk.ticket&view_type=form"
        self._conteneur = conteneur

    def locator(self, _selecteur):
        return self._conteneur


def test_locate_field_descend_dans_un_conteneur_non_editable():
    """Le VRAI cas mesuré (Sapian, 2026-09-23, cas 127) : `[name="name"]` résolvait le `<div
    class="o_field_widget">` englobant, jamais la `<textarea>` réelle — `fill_field` échouait sur
    un élément non éditable. `locate_field` doit descendre vers le contrôle réel."""
    conteneur = _LocatorConteneur(tag="div", enfants=[_ElementInterne("textarea")])
    page = _PageChampDansConteneur(conteneur)

    loc = locate_field(page, "name")

    assert loc.count() == 1
    assert loc.first.evaluate("el => el.tagName.toLowerCase()") == "textarea"


def test_locate_field_sans_controle_interne_retombe_sur_le_conteneur():
    """Repli STRICTEMENT inchangé si aucun contrôle éditable n'existe dans le conteneur résolu —
    mieux vaut rendre le conteneur (l'appelant échouera avec un message clair) que rien du tout."""
    conteneur = _LocatorConteneur(tag="div", enfants=[])
    page = _PageChampDansConteneur(conteneur)

    loc = locate_field(page, "name")

    assert loc is conteneur


def test_locate_field_preferre_le_controle_interne_visible_si_plusieurs():
    conteneur = _LocatorConteneur(tag="div", plusieurs_visibles=True,
                                  enfants=[_ElementInterne("input"), _ElementInterne("input")])
    page = _PageChampDansConteneur(conteneur)

    loc = locate_field(page, "team_id")

    assert loc.count() == 1  # le filtre ":visible" a réduit à un seul contrôle


def test_locate_field_ne_descend_jamais_quand_l_element_resolu_est_deja_editable():
    """Garde anti-régression : un `<input>`/`<select>`/`<textarea>` déjà résolu ne doit JAMAIS
    déclencher une recherche d'enfant — comportement inchangé pour l'immense majorité des cas
    (portail générique, formulaires HTML classiques)."""
    page = _FaussePage(selecteur_existant='[name="product_id"]', tag="input")

    loc = locate_field(page, "product_id")

    assert loc.count() == 1


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


# ── 3. Champ RELATIONNEL Odoo (many2one) — bug réel Parc IT, 2026-09-18/22 ─────────────────────
#
# `select_field_value` ne savait gérer QUE select/radio — un `product_id` (rendu comme un
# `<input type="text">` qui ouvre une liste de résultats) levait `ElementIntrouvableError` en
# cherchant un radio qui n'a jamais existé. Vérifié EN DIRECT sur Sapian (2026-09-22) avant ce
# correctif : voir `select_many2one_odoo` pour le détail de l'interaction mesurée.

from _base_helpers import select_many2one_odoo  # noqa: E402


class _ElementM2O:
    def __init__(self):
        self.clicked = False
        self.rempli_directement = None

    def click(self, **_kw):
        self.clicked = True

    def fill(self, value, **_kw):
        # Ne doit JAMAIS être appelé : `.fill()` ne déclenche aucune recherche côté Odoo
        # (mesuré) — seules de vraies frappes (`page.keyboard.type`) le font.
        self.rempli_directement = value


class _LocatorM2O:
    """Locator minimal : `.or_()`, `.first`, `.wait_for()`, `.click()` — assez pour
    `select_many2one_odoo` et `click_first_actionable`."""

    def __init__(self, trouve: bool, on_click=None):
        self._trouve = trouve
        self._on_click = on_click
        self.first = self

    def or_(self, autre):
        return _LocatorM2O(self._trouve or autre._trouve,
                          on_click=self._on_click or autre._on_click)

    def wait_for(self, state="visible", timeout=None):
        if not self._trouve:
            raise PlaywrightTimeout("introuvable")

    def click(self, timeout=None):
        if not self._trouve:
            raise PlaywrightTimeout("introuvable")
        if self._on_click:
            self._on_click()


class _PageM2O:
    """Simule l'ouverture d'Odoo : `.o_dialog` apparaît (ou pas), une carte kanban correspond
    (ou pas) — jamais le menu déroulant compact dans ces tests (non mesuré sur le champ réel)."""

    def __init__(self, *, dialogue_ouvre: bool = True, carte_correspond: bool = True):
        self.url = "https://exemple.test/equipment_order"
        self.keyboard = self
        self.frappes: list[str] = []
        self._dialogue_ouvre = dialogue_ouvre
        self._carte_correspond = carte_correspond
        self.selection: str | None = None

    def type(self, text, delay=None):
        self.frappes.append(text)

    def locator(self, selecteur):
        if selecteur == ".o_dialog":
            return _LocatorM2O(self._dialogue_ouvre)
        if "o-autocomplete" in selecteur or "ui-autocomplete" in selecteur:
            return _LocatorM2O(False)
        if "o_kanban_record" in selecteur:
            trouve = self._dialogue_ouvre and self._carte_correspond
            return _LocatorM2O(trouve, on_click=lambda: setattr(self, "selection", "kanban"))
        return _LocatorM2O(False)


def test_select_many2one_odoo_tape_de_vraies_frappes_jamais_fill():
    page = _PageM2O()
    champ = _ElementM2O()

    select_many2one_odoo(page, champ, "GOOGLE PIXEL 8", field="product_id")

    assert champ.clicked
    assert page.frappes == ["GOOGLE PIXEL 8"]
    assert champ.rempli_directement is None, "`.fill()` ne déclenche aucune recherche côté Odoo"


def test_select_many2one_odoo_clique_la_carte_kanban_correspondante():
    page = _PageM2O()
    champ = _ElementM2O()

    select_many2one_odoo(page, champ, "GOOGLE PIXEL 8", field="product_id")

    assert page.selection == "kanban"


def test_select_many2one_odoo_leve_si_aucune_liste_n_apparait():
    """Ni `.o_dialog` ni le menu déroulant compact ne sont apparus — un champ RÉELLEMENT
    introuvable, pas un défaut de sélecteur maquillé."""
    page = _PageM2O(dialogue_ouvre=False)
    champ = _ElementM2O()

    with pytest.raises(ElementIntrouvableError, match="product_id"):
        select_many2one_odoo(page, champ, "GOOGLE PIXEL 8", field="product_id")


def test_select_many2one_odoo_leve_si_la_boite_s_ouvre_sans_correspondance():
    """La boîte de dialogue apparaît (les droits sont bons, la recherche a tourné), mais AUCUNE
    carte ne correspond à la valeur demandée — un vrai « valeur introuvable », pas une erreur de
    connexion à la boîte elle-même."""
    page = _PageM2O(carte_correspond=False)
    champ = _ElementM2O()

    with pytest.raises(ElementIntrouvableError):
        select_many2one_odoo(page, champ, "PRODUIT INCONNU", field="product_id")


def test_select_field_value_dispatche_vers_le_many2one_pour_un_champ_input(monkeypatch):
    """L'intégration : `select_field_value` doit reconnaître un `<input>` (ni select, ni radio)
    et le router vers `select_many2one_odoo` — c'est CE branchement qui manquait sur le cas réel
    Parc IT (`product_id`), où l'ancien code retombait tout droit sur le message radio/select."""
    import _base_helpers as helpers

    appels = []
    monkeypatch.setattr(helpers, "select_many2one_odoo",
                        lambda page, champ, value, field="": appels.append((value, field)))

    page = _FaussePage(selecteur_existant="[name=\"product_id\"]", tag="input")
    select_field_value(page, "GOOGLE PIXEL 8", "product_id")

    assert appels == [("GOOGLE PIXEL 8", "product_id")]
