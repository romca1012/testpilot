"""Étape 4, morceau 6 (A81, A82) : une exploration sans limite de pages, qui regroupe les pages sœurs identiques.

Falsifiable dans les deux sens : des fiches produit identiques sont regroupées après 3 exemples (sinon l'exploration
visiterait 5 000 pages) ; mais une seule différence — un champ, un bouton, une destination de lien — ou une famille
hétérogène empêche tout regroupement (sinon la carte aurait un trou silencieux).
"""

from __future__ import annotations

from testpilot.generation.familles_de_pages import Regroupement, adresse_parente, structure


def _fiche(*, bouton="Ajouter au panier", champs=("quantite",), lien="/categorie/chaussures"):
    return {"champs": [{"name": n, "tag": "input", "type": "number"} for n in champs],
            "formulaires": [{"action": "/panier", "method": "post", "champs": len(champs)}],
            "actions": [{"role": "button", "label": bouton}],
            "liens": [{"href": lien, "text": "x"}, {"href": "/", "text": "Accueil"}]}


def test_adresse_parente():
    assert adresse_parente("/produit/sac-noir-12") == "/produit"
    assert adresse_parente("/boutique/homme/sac-noir") == "/boutique/homme"
    assert adresse_parente("/contact") is None, "la racine du site n'est jamais une famille"
    assert adresse_parente("/") is None
    assert adresse_parente("/commande/{id}") is None, "déjà un modèle"


LISTE = 20   # la page catalogue liste 20 fiches


def test_falsifiable_des_fiches_identiques_sont_regroupees_apres_trois_exemples():
    r = Regroupement()
    for nom in ("chaussure-rouge-cuir", "sac-noir-12"):
        r.noter(f"/produit/{nom}", _fiche())
    assert r.a_ignorer("/produit/ceinture-cuir-noire", LISTE) is False, "deux exemples ne suffisent pas"
    r.noter("/produit/ceinture-cuir-noire", _fiche())
    assert r.a_ignorer("/produit/montre-or-18k", LISTE) is True and r.a_ignorer("/produit/bonnet-42", LISTE) is True
    assert r.a_ignorer("/produit/sac-noir-12", LISTE) is False, "un exemple déjà visité n'est jamais « ignoré »"
    assert r.a_ignorer("/categorie/chaussures", LISTE) is False, "une autre famille n'est pas touchée"
    assert r.bilan() == {"/produit/…": {"exemples": ["/produit/chaussure-rouge-cuir", "/produit/sac-noir-12", "/produit/ceinture-cuir-noire"],
                                        "pages_du_meme_modele": 2}}


def test_falsifiable_un_menu_n_est_jamais_une_liste_et_une_rubrique_jamais_un_identifiant():
    """Revue du 2026-10-21 : trois listes vides identiques sous /admin, puis /admin/parametres (un formulaire) — sautée sans
    avoir été vue. Un menu (moins de 10 sœurs liées) ou des noms de rubriques : tout est visité."""
    r = Regroupement()
    for nom in ("utilisateurs", "groupes", "roles"):
        r.noter(f"/admin/{nom}", _fiche())
    assert r.a_ignorer("/admin/parametres", 4) is False, "un menu de 4 entrées n'est pas une liste"
    assert r.a_ignorer("/admin/parametres", LISTE) is False, "des noms de rubriques ne sont pas des identifiants"
    r3 = Regroupement()
    for nom in ("email-templates", "sms-templates", "push-templates"):
        r3.noter(f"/settings/{nom}", _fiche())
    assert r3.a_ignorer("/settings/api-keys", LISTE) is False, "un seul tiret ne fait pas un identifiant (seconde revue)"
    r2 = Regroupement()
    for nom in ("article-1", "article-2", "article-3"):
        r2.noter(f"/blog/{nom}", _fiche())
    assert r2.a_ignorer("/blog/article-4", 9) is False, "9 sœurs liées : pas encore une liste"
    assert r2.a_ignorer("/blog/article-4", 10) is True


def test_falsifiable_une_seule_difference_empeche_le_regroupement():
    for difference in ({"bouton": "Réserver"}, {"champs": ("quantite", "taille")}, {"lien": "/avis/ecrire"}):
        r = Regroupement()
        r.noter("/produit/a-1", _fiche())
        r.noter("/produit/b-2", _fiche())
        r.noter("/produit/c-3", _fiche(**difference))
        r.noter("/produit/d-4", _fiche())
        assert r.a_ignorer("/produit/e-5", LISTE) is False, f"famille hétérogène ({difference}) : tout est visité"
        assert r.bilan() == {}


def test_la_racine_n_est_jamais_regroupee():
    r = Regroupement()
    for page in ("/contact", "/tarifs", "/a-propos", "/equipe"):
        r.noter(page, _fiche())
    assert r.a_ignorer("/connexion", LISTE) is False


def test_le_contenu_affiche_ne_compte_pas_seulement_ce_que_la_page_permet():
    a, b = _fiche(), _fiche()
    a["titre"], b["titre"] = "Chaussure rouge", "Sac noir"
    a["liens"][0]["text"], b["liens"][0]["text"] = "Chaussures", "Sacs"
    assert structure(a, "/produit/a") == structure(b, "/produit/b")
