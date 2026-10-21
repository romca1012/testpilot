"""Étape 4, morceau 6 (A69 révisée) : une seule carte de l'application, qui dit quel compte voit quoi.

Ce que ces tests gardent :
1. rien ne se perd ni ne s'altère : la vue d'un compte est EXACTEMENT son relevé ;
2. la carte dit qui voit une route, un champ, un bouton, un menu ;
3. « ne voit pas » n'est affirmé que pour un compte exploré en entier — jamais pour un compte en échec, arrêté ou absent.
"""

from __future__ import annotations

import copy

from testpilot.generation import carte_des_comptes as carte_mod


def _champ(name, *, visible=True, options=None):
    c = {"name": name, "identifie_par": "name", "tag": "select" if options else "input", "type": "", "required": False,
         "visible": visible, "role": "textbox", "label": name}
    if options:
        c["options"] = options
    return c


PRINCIPAL = {
    "pages": {
        "/commandes": {"champs": [_champ("client"), _champ("remise"), _champ("etat", options=[["a", "A"], ["b", "B"]])],
                       "actions": [{"role": "button", "label": "Confirmer", "soumet": True, "visible": True}],
                       "liens": [], "formulaires": [], "titre": "Commandes", "url_exemple": "/commandes"},
        "/comptabilite": {"champs": [], "actions": [], "liens": [], "formulaires": [], "titre": "Compta",
                          "url_exemple": "/comptabilite"},
    },
    "transitions": {"/commandes": ["/comptabilite"]},
    "onglets_internes": {},
    "modeles_backoffice": [],
    "menus_visibles": [{"cle": "account.menu_finance", "chemin": "Comptabilité / Factures"},
                       {"cle": "sale.menu_sale_order", "chemin": "Ventes / Commandes"}],
    "absence_fiable": True,
}
LECTEUR = {
    "pages": {
        "/commandes": {"champs": [_champ("client"), _champ("etat", options=[["a", "A"]]), _champ("note", visible=False)],
                       "actions": [{"role": "button", "label": "Confirmer", "soumet": True, "visible": False}],
                       "liens": [], "formulaires": [], "titre": "Commandes", "url_exemple": "/commandes"},
        "/mon-profil": {"champs": [], "actions": [], "liens": [], "formulaires": [], "titre": "Profil",
                        "url_exemple": "/mon-profil"},
    },
    "transitions": {},
    "onglets_internes": {},
    "modeles_backoffice": [],
    "menus_visibles": [{"cle": "sale.menu_sale_order", "chemin": "Ventes / Commande"}],   # traduit autrement : même clé
    "absence_fiable": True,
}


def _carte(**kw):
    return carte_mod.fusionner([("principal", PRINCIPAL), ("Lecteur", LECTEUR)], **kw)


def test_falsifiable_la_vue_d_un_compte_est_exactement_son_releve():
    principal, lecteur = copy.deepcopy(PRINCIPAL), copy.deepcopy(LECTEUR)
    carte = carte_mod.fusionner([("principal", principal), ("Lecteur", lecteur)])
    assert carte_mod.vue_du_compte(carte, "principal") == PRINCIPAL
    assert carte_mod.vue_du_compte(carte, "Lecteur") == LECTEUR
    assert (principal, lecteur) == (PRINCIPAL, LECTEUR), "la fusion ne modifie jamais un relevé"
    vue = carte_mod.vue_du_compte(carte, "Lecteur")
    vue["pages"].clear()
    assert carte_mod.vue_du_compte(carte, "Lecteur") == LECTEUR, "une vue est une copie : la modifier ne touche pas la carte"


def test_un_compte_jamais_explore_n_a_aucune_vue_jamais_celle_d_un_autre():
    assert carte_mod.vue_du_compte(_carte(), "Comptable") is None


def test_falsifiable_la_carte_reunit_toutes_les_routes_et_dit_qui_les_voit():
    carte = _carte()
    assert set(carte["routes"]) == {"/commandes", "/comptabilite", "/mon-profil"}, "toutes les routes, de tous les comptes"
    assert carte["routes"]["/commandes"]["vu_par"] == ["principal", "Lecteur"]
    assert carte["routes"]["/comptabilite"]["vu_par"] == ["principal"]
    assert carte["routes"]["/mon-profil"]["vu_par"] == ["Lecteur"]
    champs = carte["routes"]["/commandes"]["champs"]
    assert champs["remise|name|input"]["vu_par"] == ["principal"], "un champ que Lecteur n'a pas"
    assert champs["note|name|input"] == {"vu_par": ["Lecteur"], "visible_pour": []}, "présent mais caché pour Lecteur"
    assert champs["etat|name|select"]["vu_par"] == ["principal", "Lecteur"]
    assert carte["routes"]["/commandes"]["actions"]["Confirmer"]["visible_pour"] == ["principal"]
    assert carte["menus"]["account.menu_finance"]["vu_par"] == ["principal"]
    assert carte["menus"]["sale.menu_sale_order"]["vu_par"] == ["principal", "Lecteur"], \
        "la clé technique, pas le libellé traduit : deux comptes en deux langues voient le même menu"


def test_falsifiable_les_attributs_propres_a_un_compte_ne_sont_jamais_meles():
    """Liste « état » : deux options pour le principal, une pour Lecteur. Chaque vue garde les SIENNES."""
    carte = _carte()
    options = lambda libelle: next(c["options"] for c in carte_mod.vue_du_compte(carte, libelle)["pages"]["/commandes"]["champs"]  # noqa: E731
                                   if c["name"] == "etat")
    assert options("principal") == [["a", "A"], ["b", "B"]] and options("Lecteur") == [["a", "A"]]


def test_falsifiable_ne_voit_pas_n_est_affirme_que_pour_un_compte_explore_en_entier():
    complet = _carte()
    assert carte_mod.voit(complet, "Lecteur", "/comptabilite") is False
    assert carte_mod.voit(complet, "Lecteur", "/commandes") is True
    assert carte_mod.voit(complet, "Lecteur", "/commandes", champ=_champ("remise")) is False
    assert carte_mod.voit(complet, "Lecteur", "", menu="Comptabilité / Factures") is False
    assert carte_mod.voit(complet, "Lecteur", "", menu="Ventes / Commandes") is True
    assert carte_mod.voit(complet, "Lecteur", "", menu="Sales / Orders") is None, "un chemin inconnu (autre langue) : inconnu"

    arrete = _carte(incomplets=["Lecteur"])
    assert carte_mod.voit(arrete, "Lecteur", "/comptabilite") is None, "arrêté en route : peut-être pas encore atteint"
    assert carte_mod.voit(arrete, "Lecteur", "/commandes") is True, "ce qui a été vu reste vu"
    assert carte_mod.voit(complet, "Comptable", "/commandes") is None, "jamais exploré : inconnu"


def test_falsifiable_des_menus_non_lus_ne_disent_jamais_ne_voit_pas():
    """Mesuré sur le banc (2026-10-21) : la découverte des menus échouait en silence pour un compte non administrateur.
    Un compte dont les menus n'ont pas pu être lus (`menus_visibles` absent) : « on ne sait pas », jamais « ne voit pas »."""
    sans_menus = {k: v for k, v in LECTEUR.items() if k != "menus_visibles"}
    carte = carte_mod.fusionner([("principal", PRINCIPAL), ("Lecteur", sans_menus)])
    assert carte_mod.voit(carte, "Lecteur", "", menu="Comptabilité / Factures") is None
    assert carte_mod.voit(carte, "Lecteur", "/comptabilite") is False, "les pages, elles, ont bien été parcourues"


def test_un_compte_en_echec_n_apparait_dans_aucun_vu_par():
    carte = carte_mod.fusionner([("principal", PRINCIPAL)],
                                en_echec=[{"libelle": "Lecteur", "message": "connexion impossible"}])
    assert all("Lecteur" not in e["vu_par"] for e in carte["routes"].values())
    assert carte["comptes_en_echec"] == [{"libelle": "Lecteur", "message": "connexion impossible"}]
    assert carte_mod.voit(carte, "Lecteur", "/commandes") is None


def test_l_ordre_d_affichage_ne_depend_pas_de_l_ordre_des_releves():
    a = carte_mod.fusionner([("principal", PRINCIPAL), ("Lecteur", LECTEUR)])
    b = carte_mod.fusionner([("Lecteur", LECTEUR), ("principal", PRINCIPAL)])
    assert a["routes"]["/commandes"]["vu_par"] == b["routes"]["/commandes"]["vu_par"] == ["principal", "Lecteur"]


def test_falsifiable_sans_session_reverifiee_ou_page_sautee_par_son_regroupement_jamais_ne_voit_pas():
    """Revue du 2026-10-21 : (1) une session perdue en route, ou un connecteur qui ne sait pas la revérifier (web), ne permet
    jamais « ne voit pas » ; (2) une sœur que le regroupement de CE compte n'a pas visitée n'est pas « absente »."""
    non_fiable = {**LECTEUR, "absence_fiable": False}
    carte = carte_mod.fusionner([("principal", PRINCIPAL), ("Lecteur", non_fiable)])
    assert carte_mod.voit(carte, "Lecteur", "/comptabilite") is None
    assert carte_mod.voit(carte, "Lecteur", "/commandes") is True, "ce qui a été vu reste vu"
    regroupe = {**LECTEUR, "familles": {"/produit/…": {"exemples": ["/produit/a-1"], "pages_du_meme_modele": 40}}}
    carte = carte_mod.fusionner([("principal", PRINCIPAL), ("Lecteur", regroupe)])
    assert carte_mod.voit(carte, "Lecteur", "/produit/z-9") is None
    assert carte_mod.voit(carte, "Lecteur", "/comptabilite") is False, "hors de la famille : l'absence reste un fait"
