"""`connectors/_web_helpers.py::elements_interactifs_visibles` (lot 09, C9) — vrai Chromium,
même motif que `test_accname.py` (module exclu de `pytest -q` par défaut, marqueur
`conformance`, lancé par le job `browser-evidence`)."""

from __future__ import annotations

import pytest
from playwright.sync_api import sync_playwright

from testpilot.connectors._web_helpers import elements_interactifs_visibles

pytestmark = pytest.mark.conformance


@pytest.fixture(scope="module")
def page():
    with sync_playwright() as p:
        navigateur = p.chromium.launch(headless=True)
        contexte = navigateur.new_context()
        pg = contexte.new_page()
        yield pg
        contexte.close()
        navigateur.close()


def test_recense_un_bouton_visible_avec_son_role_et_son_nom(page):
    page.set_content('<button aria-label="Se connecter">Connexion</button>')

    elements = elements_interactifs_visibles(page)

    assert len(elements) == 1
    # Le NOM accessible (aria-label) ET le texte affiché, qui diffèrent ici : l'ancien format les fusionnait dans `nom`.
    assert elements[0] == {"role": "button", "nom": "Se connecter", "type": "", "texte": "Connexion"}


def test_falsifiable_le_texte_affiche_est_distingue_du_nom_accessible(page):
    """Mesuré le 2026-10-08 : un bouton « Ajouter » (aria-label « Ajouter Clavier mécanique au panier ») était présenté comme
    un bouton nommé « Ajouter Clavier… » ; l'agent l'a visé par `:has-text('Ajouter Clavier…')`, qui ne trouve rien. La page
    réelle prouve les deux ciblages : le nom accessible trouve le bouton, le texte long non."""
    page.set_content('<button aria-label="Ajouter Clavier mécanique au panier">Ajouter</button>')

    element = elements_interactifs_visibles(page)[0]

    assert element["nom"] == "Ajouter Clavier mécanique au panier" and element["texte"] == "Ajouter"
    assert page.get_by_role("button", name=element["nom"]).count() == 1
    assert page.locator("button", has_text=element["nom"]).count() == 0
    assert page.locator("button", has_text=element["texte"]).count() == 1


def test_un_element_dont_le_texte_est_le_nom_ne_porte_pas_de_champ_texte_en_double(page):
    page.set_content('<button>Valider</button><a href="#">Aide</a>')

    assert all("texte" not in el for el in elements_interactifs_visibles(page))


def test_falsifiable_un_element_masque_est_exclu(page):
    """Sans le filtre `offsetParent !== null` (ou `getClientRects().length`), un champ masqué
    apparaîtrait comme un candidat cliquable — un test généré à partir de lui échouerait toujours
    (élément jamais interactif pour un vrai utilisateur)."""
    page.set_content(
        '<button id="visible">Voir</button>'
        '<button id="cache" style="display:none">Caché</button>')

    elements = elements_interactifs_visibles(page)

    noms = {el["nom"] for el in elements}
    assert "Voir" in noms
    assert "Caché" not in noms


def test_plafonne_a_max_elements(page):
    html = "".join(f'<button>b{i}</button>' for i in range(30))
    page.set_content(html)

    elements = elements_interactifs_visibles(page, max_elements=10)

    assert len(elements) == 10


def test_rend_une_liste_vide_sans_lever_si_la_page_est_fermee(page):
    contexte = page.context.browser.new_context()
    pg = contexte.new_page()
    pg.set_content("<button>x</button>")
    pg.close()

    assert elements_interactifs_visibles(pg) == []

    contexte.close()
