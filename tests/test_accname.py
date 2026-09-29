"""Sous-lot A du lot « Enregistrement assisté du chemin de connexion » (2026-09-29).

Deux algorithmes prouvés séparément, comme documenté dans `src/testpilot/generation/accname.py` :

1. Le calcul du nom accessible (AccName) — cas repris du dépôt officiel du groupe de travail W3C
   (`web-platform-tests/wpt`, dossier `accname/name/`, fichiers `comp_labelledby.html`,
   `comp_name_from_content.html`, `comp_host_language_label.html` — lus le 2026-09-29 via leur
   contenu brut sur GitHub, PAS travaillés de mémoire). Chaque cas gardé ici porte en commentaire
   le fichier source et le libellé du test WPT dont il vient.
   Cas écartés, documentés plutôt que passés sous silence : les tests portant sur le contenu
   généré par CSS (`::before`/`::after`, compteurs, `content: attr()`), le rendu bidirectionnel
   (RTL) et `text-transform` — aucun rapport avec un chemin de connexion, et une reproduction
   fidèle exigerait de réimplémenter un moteur de disposition CSS dans le calcul, hors de portée
   de ce lot. L'étape 2C (« embedded control ») est également écartée (voir le module).
2. La remontée d'arbre (point cliqué → élément interactif) — propre à ce projet, AUCUN jeu de
   tests officiel externe ne la couvre (les cas WPT partent toujours d'un élément déjà identifié,
   jamais d'un point). Les cas ci-dessous sont donc la SEULE preuve qui existera pour cette partie
   du code — volontairement nombreux, au-delà du plancher initialement posé.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import sync_playwright

from testpilot.generation import accname

# Vrai Chromium, aucune application distante — même motif que `test_contexte_navigateur_reel.py`
# (`pytestmark` au niveau du module) : exclu de `pytest -q` par défaut (aucun navigateur installé
# sur ce job), exécuté par le job « browser-evidence » qui en installe un.
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


def _centre(page, selecteur: str) -> tuple[float, float]:
    boite = page.locator(selecteur).bounding_box()
    assert boite is not None, f"« {selecteur} » introuvable ou non rendu"
    return boite["x"] + boite["width"] / 2, boite["y"] + boite["height"] / 2


def _nom_via_clic(page, html: str, selecteur: str):
    """Point central de `selecteur` — c'est le passage obligé de CHAQUE cas ci-dessous : jamais un
    `ElementHandle` passé directement, toujours des coordonnées obtenues sur un élément réellement
    rendu, exactement comme un vrai clic humain relayé par le futur mécanisme CDP."""
    page.set_content(html)
    x, y = _centre(page, selecteur)
    return accname.calculer(page, x, y)


# ══ 1. AccName — cas officiels WPT (web-platform-tests/wpt, accname/name/) ══════════════════════
# Les rôles/éléments non interactifs des fichiers source (`role="group"`, `<h2>`...) sont adaptés
# vers un rôle interactif équivalent (`button`/`a href`) : `calculer()` ne calcule un nom que pour
# une cible cliquable, jamais pour un rôle structurel — la relation de nommage testée (labelledby,
# aria-label, contenu) est, elle, inchangée.

def test_wpt_labelledby_simple_reference(page):
    # comp_labelledby.html — « Nav with multiple span references » (réduit à 1 ref).
    html = '<a href="#" aria-labelledby="h">x</a><h2 id="h">first heading</h2>'
    assert _nom_via_clic(page, html, "a")["name"] == "first heading"


def test_wpt_labelledby_plusieurs_references_jointes_par_un_espace(page):
    # comp_labelledby.html — « Nav with multiple span references ».
    html = ('<button aria-labelledby="s1 s2 s3">x</button>'
            '<span id="s1">verify</span><span id="s2">spaces</span><span id="s3">between</span>')
    assert _nom_via_clic(page, html, "button")["name"] == "verify spaces between"


def test_wpt_labelledby_prime_sur_aria_label(page):
    # comp_labelledby.html — « Button with aria-labelledby precedence ».
    html = '<button aria-label="ignoré" aria-labelledby="n1">x</button><span id="n1">vrai label</span>'
    assert _nom_via_clic(page, html, "button")["name"] == "vrai label"


def test_wpt_aria_label_seul(page):
    # comp_label.html.
    html = '<button aria-label="Se connecter">Connexion</button>'
    assert _nom_via_clic(page, html, "button")["name"] == "Se connecter"


def test_wpt_host_label_for_associe(page):
    # comp_host_language_label.html — « Label-For Association Tests » (checkbox).
    html = '<label for="cb">case à cocher</label><input id="cb" type="checkbox">'
    assert _nom_via_clic(page, html, "#cb")["name"] == "case à cocher"


def test_wpt_host_label_englobant(page):
    # comp_host_language_label.html — « Encapsulated Label Tests ».
    html = '<label><input type="checkbox">case à cocher</label>'
    assert _nom_via_clic(page, html, "input")["name"] == "case à cocher"


def test_wpt_host_plusieurs_labels_for_joints(page):
    # comp_host_language_label.html — « Multiple Labels ».
    html = ('<label for="tf">label 1</label><label for="tf">label 2</label>'
            '<input id="tf" type="text">')
    assert _nom_via_clic(page, html, "#tf")["name"] == "label 1 label 2"


def test_wpt_host_input_image_alt(page):
    # comp_host_language_label.html — « Input Elements with Built-in Labels ».
    html = '<input type="image" alt="valider le paiement">'
    assert _nom_via_clic(page, html, "input")["name"] == "valider le paiement"


def test_wpt_name_from_content_bouton(page):
    # comp_name_from_content.html — « Simple Native Elements ».
    assert _nom_via_clic(page, "<button>label</button>", "button")["name"] == "label"


def test_wpt_name_from_content_lien(page):
    assert _nom_via_clic(page, '<a href="#">label</a>', "a")["name"] == "label"


def test_wpt_name_from_content_role_explicite_sur_span(page):
    # comp_name_from_content.html — « ARIA Roles (Inline) ».
    assert _nom_via_clic(page, '<span role="button">label</span>', "span")["name"] == "label"


def test_wpt_name_from_content_plusieurs_enfants_joints_par_un_espace(page):
    # comp_name_from_content.html — « Multiple Children ».
    html = "<button><span>one</span> <span>two</span> <span>three</span></button>"
    assert _nom_via_clic(page, html, "button")["name"] == "one two three"


def test_wpt_name_from_content_image_imbriquee_dans_un_lien(page):
    # comp_name_from_content.html — « Nested Elements with Image » (adapté).
    html = '<a href="#">link2 <img alt="image"> link3</a>'
    assert _nom_via_clic(page, html, "a")["name"] == "link2 image link3"


def test_wpt_name_from_content_aria_label_ignore_le_contenu_imbrique(page):
    # comp_name_from_content.html — « Heading with Nested Link (aria-label) » (adapté sur <a>).
    html = '<a href="#" aria-label="libellé du lien">texte ignoré <img alt="alt ignoré"> ignoré</a>'
    assert _nom_via_clic(page, html, "a")["name"] == "libellé du lien"


def test_wpt_name_from_content_labelledby_sur_image_imbriquee_ignore_le_texte(page):
    # comp_name_from_content.html — « Heading with Nested Link (aria-labelledby) » (adapté).
    html = ('<a href="#" aria-labelledby="img1">ignoré <img id="img1" alt="image"> ignoré</a>')
    assert _nom_via_clic(page, html, "a")["name"] == "image"


# ── Repli placeholder / title, et absences ───────────────────────────────────────────────────────

def test_placeholder_utilise_si_aucune_autre_etiquette(page):
    html = '<input type="text" placeholder="votre email">'
    assert _nom_via_clic(page, html, "input")["name"] == "votre email"


def test_placeholder_ignore_si_un_label_existe(page):
    html = '<label for="e2">Email</label><input id="e2" type="text" placeholder="ignoré">'
    assert _nom_via_clic(page, html, "#e2")["name"] == "Email"


def test_title_en_tout_dernier_recours(page):
    html = '<button title="dernier recours" style="font-size:0"></button>'
    assert _nom_via_clic(page, html, "button")["name"] == "dernier recours"


def test_element_sans_nom_du_tout_rend_une_chaine_vide_jamais_une_exception(page):
    html = '<button style="width:40px;height:40px"></button>'
    resultat = _nom_via_clic(page, html, "button")
    assert resultat["name"] == ""
    assert resultat["role"] == "button"


def test_descendant_masque_ne_contribue_rien_au_nom_depuis_le_contenu(page):
    html = '<button>Visible <span style="display:none">Caché</span> texte</button>'
    assert _nom_via_clic(page, html, "button")["name"] == "Visible texte"


def test_labelledby_garde_le_texte_d_un_noeud_reference_meme_masque(page):
    """L'exception EXPLICITE de l'étape 2A (« not part of an aria-labelledby traversal ») : un
    nœud masqué directement référencé par aria-labelledby garde son texte — contrairement au
    descendant masqué du test précédent, jamais référencé, lui. Falsifié en local en inversant
    `viaReference` sur ce seul chemin (`nomDepuisRefs`) : le nom retombe alors à la chaîne vide."""
    html = ('<button aria-labelledby="ref">x</button>'
            '<span id="ref" style="display:none">nom caché</span>')
    assert _nom_via_clic(page, html, "button")["name"] == "nom caché"


# ══ 2. Ambiguïté — falsifiabilité (le garde-fou doit RÉELLEMENT mordre) ═════════════════════════

def test_falsifiable_deux_boutons_meme_role_et_meme_nom_leve_ElementIntrouvableError(page):
    html = "<button>Valider</button><button>Valider</button>"
    page.set_content(html)
    x, y = _centre(page, "button >> nth=0")
    with pytest.raises(accname.ElementIntrouvableError, match="ambigu"):
        accname.calculer(page, x, y)


def test_falsifiable_deux_boutons_meme_role_mais_nom_different_ne_leve_rien(page):
    """Preuve négative : le garde-fou ne mord QUE sur une vraie ambiguïté — deux boutons de rôle
    identique mais de nom distinct doivent réussir normalement, jamais être pris pour ambigus."""
    html = "<button>Valider</button><button>Annuler</button>"
    resultat = _nom_via_clic(page, html, "button >> nth=0")
    assert resultat["name"] == "Valider"


# ══ 3. Remontée d'arbre — AUCUN jeu de tests officiel externe : cas généreux, propres au projet ══

def test_clic_sur_une_icone_a_l_interieur_d_un_bouton_resout_le_bouton_porteur_du_role(page):
    html = '<button aria-label="Fermer"><svg width="16" height="16"><circle r="8"/></svg></button>'
    page.set_content(html)
    # Le point cliqué : le SVG lui-même (l'icône), jamais le bouton directement.
    boite = page.locator("svg").bounding_box()
    x, y = boite["x"] + boite["width"] / 2, boite["y"] + boite["height"] / 2
    resultat = accname.calculer(page, x, y)
    assert resultat == {"role": "button", "name": "Fermer"}


def test_clic_sur_le_texte_a_l_interieur_d_un_lien_resout_le_lien(page):
    html = '<a href="#" aria-label="Mot de passe oublié"><span>Mot de passe oublié ?</span></a>'
    page.set_content(html)
    boite = page.locator("span").bounding_box()
    x, y = boite["x"] + boite["width"] / 2, boite["y"] + boite["height"] / 2
    resultat = accname.calculer(page, x, y)
    assert resultat == {"role": "link", "name": "Mot de passe oublié"}


def test_clic_sur_une_zone_vide_d_un_role_button_sans_enfant_semantique(page):
    """Un `role="button"` posé sur un `<div>` sans texte ni enfant sémantique (juste une image de
    fond CSS, motif fréquent pour un bouton icône) : le rôle se résout, le nom est vide — jamais
    un `None` (qui signifierait « pas de rôle interactif du tout », un cas bien différent)."""
    html = '<div role="button" style="width:48px;height:48px;background:gray"></div>'
    assert _nom_via_clic(page, html, "div") == {"role": "button", "name": ""}


def test_clic_qui_ne_touche_aucun_role_interactif_rend_une_absence_propre_jamais_une_exception(page):
    html = '<p style="width:400px;height:200px">du texte de navigation, rien de cliquable ici</p>'
    page.set_content(html)
    x, y = _centre(page, "p")
    assert accname.calculer(page, x, y) is None


def test_clic_sur_un_conteneur_purement_visuel_remonte_jusqu_a_un_ancetre_interactif_plus_haut(page):
    """Une icône dans un `<span>` de mise en page, lui-même dans un bouton : la remontée doit
    dépasser le `<span>` (rôle structurel, aucun rôle exploitable) pour trouver le bouton."""
    html = ('<button aria-label="Envoyer"><span class="icone-wrapper">'
            '<svg width="20" height="20"><rect width="20" height="20"/></svg></span></button>')
    page.set_content(html)
    boite = page.locator("svg").bounding_box()
    x, y = boite["x"] + boite["width"] / 2, boite["y"] + boite["height"] / 2
    assert accname.calculer(page, x, y) == {"role": "button", "name": "Envoyer"}


# ══ 4. Bugs mesurés en revue verdict-reviewer (2026-09-29, vrai Chromium) ═══════════════════════

def test_label_masque_ne_contribue_rien_au_nom(page):
    """Un `<label for>` masqué fuyait son texte dans le nom calculé — l'exception 2A n'exempte QUE
    le nœud directement référencé par aria-labelledby, jamais un `<label for>`."""
    html = ('<label for="cb" style="display:none">Ancien libellé caché</label>'
            '<input id="cb" type="checkbox">')
    assert _nom_via_clic(page, html, "#cb") == {"role": "checkbox", "name": ""}


def _point_shadow(page, selecteur: str = "button") -> tuple[float, float]:
    boite = page.evaluate(
        """(selecteur) => {
            const b = document.getElementById('host').shadowRoot.querySelector(selecteur);
            const r = b.getBoundingClientRect();
            return {x: r.x + r.width / 2, y: r.y + r.height / 2};
        }""", selecteur)
    return boite["x"], boite["y"]


def test_clic_sur_un_bouton_a_l_interieur_d_un_shadow_dom_ouvert_est_resolu(page):
    """Sans perçage du shadow DOM, `document.elementFromPoint` rend seulement l'hôte (`<div
    id="host">`), jamais le bouton interne — le clic était traité comme un clic égaré (`None`)
    alors qu'une vraie cible interactive, nommée, avait été cliquée."""
    html = ("<div id=\"host\"></div>"
            "<script>document.getElementById('host').attachShadow({mode:'open'})"
            ".innerHTML = '<button aria-label=\"Valider\">x</button>';</script>")
    page.set_content(html)
    x, y = _point_shadow(page)
    assert accname.calculer(page, x, y) == {"role": "button", "name": "Valider"}


def test_clic_a_l_interieur_d_un_shadow_dom_ne_remonte_pas_sur_un_ancetre_hors_shadow(page):
    """Sans perçage, ce clic remontait silencieusement sur le bouton EXTÉRIEUR (« Annuler ») — un
    résultat plausible mais FAUX : le clic réel touche le bouton INTÉRIEUR (« Valider »), la
    remontée d'arbre sautait par-dessus la frontière du shadow DOM sans jamais s'en apercevoir."""
    html = ("<button aria-label=\"Annuler\"><div id=\"host\"></div></button>"
            "<script>document.getElementById('host').attachShadow({mode:'open'})"
            ".innerHTML = '<button aria-label=\"Valider\">x</button>';</script>")
    page.set_content(html)
    x, y = _point_shadow(page)
    assert accname.calculer(page, x, y) == {"role": "button", "name": "Valider"}


def test_falsifiable_aria_labelledby_resout_un_id_a_l_interieur_du_meme_shadow_dom(page):
    """`document.getElementById` ne traverse jamais un shadow root (scope d'id isolé, propre à la
    plateforme) : un `aria-labelledby` valide À L'INTÉRIEUR d'un shadow DOM échouait silencieusement
    et le calcul retombait sur l'étape suivante (ici le contenu du bouton, « x ») — un nom plausible
    mais FAUX, pas une absence détectable. Bug mesuré en revue verdict-reviewer, 2026-09-29, avec un
    vrai Chromium."""
    html = ("<div id=\"host\"></div>"
            "<script>document.getElementById('host').attachShadow({mode:'open'})"
            ".innerHTML = '<button aria-labelledby=\"lbl\">x</button>"
            "<span id=\"lbl\">Valider commande</span>';</script>")
    page.set_content(html)
    x, y = _point_shadow(page)
    assert accname.calculer(page, x, y) == {"role": "button", "name": "Valider commande"}


def test_falsifiable_label_for_resout_un_id_a_l_interieur_du_meme_shadow_dom(page):
    """Même défaut de scope que ci-dessus pour `<label for>` : `document.querySelectorAll` ne
    trouve jamais un id interne à un shadow DOM — le nom retombait silencieusement VIDE plutôt que
    de trouver le `<label>` associé, pourtant bel et bien présent dans le même shadow root."""
    html = ("<div id=\"host\"></div>"
            "<script>document.getElementById('host').attachShadow({mode:'open'})"
            ".innerHTML = '<label for=\"cb\">Se souvenir de moi</label>"
            "<input id=\"cb\" type=\"checkbox\">';</script>")
    page.set_content(html)
    x, y = _point_shadow(page, "#cb")
    assert accname.calculer(page, x, y) == {"role": "checkbox", "name": "Se souvenir de moi"}


def test_falsifiable_ambiguite_detectee_a_travers_un_shadow_dom(page):
    """Le décompte d'homonymes doit percer le shadow DOM lui aussi — sinon un doublon caché dans un
    composant serait invisible à `querySelectorAll('*')` et l'ambiguïté passerait inaperçue (faux
    négatif — le pire cas ici : une capture silencieusement retrouvée sur la mauvaise cible)."""
    html = ("<button id=\"leger\">Valider</button><div id=\"host\"></div>"
            "<script>document.getElementById('host').attachShadow({mode:'open'})"
            ".innerHTML = '<button>Valider</button>';</script>")
    page.set_content(html)
    # `page.locator` perce lui-même le shadow DOM ouvert (comportement Playwright standard) — un
    # sélecteur `#leger` cible sans ambiguïté le bouton du DOM léger, celui réellement cliqué ici.
    x, y = _centre(page, "#leger")
    with pytest.raises(accname.ElementIntrouvableError, match="ambigu"):
        accname.calculer(page, x, y)
