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
    assert elements[0] == {"role": "button", "nom": "Se connecter", "type": ""}


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
