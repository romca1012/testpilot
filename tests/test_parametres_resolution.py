"""Lot PT-02 — résoudre une variable et la poser dans le texte d'un test (module pur `parametres/resolution.py`).

Ce que ces tests gardent :
1. un texte sans variable ressort identique, octet pour octet (un projet qui ne règle rien se comporte comme avant) ;
2. une case vide reprend la colonne « Par défaut » (A27) ; le niveau le plus précis l'emporte ;
3. une variable inconnue ou sans valeur n'est jamais remplacée par du vide ni laissée passer : le remplacement est
   « incomplet » et dit laquelle ;
4. « 10 % », `{x}` et `<x>` ne sont jamais pris pour une variable ; une valeur ne peut pas casser le texte du test.
"""

import pytest

from testpilot.parametres import resolution as r

DEFAUT = {"client": "Martin SARL", "ville": "Lyon", "quantite": "1", "remise": "", "commentaire": None}
GROSSE = {"client": "Durand Industrie", "ville": "  ", "quantite": "250"}

FEATURE = """# language: fr
Fonctionnalité: Commande
  Scénario: Passer une commande
    Quand je saisis le client "{{client}}" de "{{ ville }}"
    Et je renseigne la quantité "{{Quantite}}" avec 10 % de remise pour {compte} et <exemple>
    Alors la page affiche le texte "Commande de {{client}}"
"""


def _jouer(jeu=GROSSE, connues=DEFAUT):
    valeurs = r.resoudre([("Par défaut", DEFAUT), ("Grosse commande", jeu)], connues)
    return r.remplacer(FEATURE, valeurs, connues)


# ── 1. Rien à remplacer : rien ne change ──────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("texte", [
    "", "Quand j'applique 10 % de remise et 5 % de TVA", 'Quand je saisis "{valeur}" pour <client>', "Alors { { nom } }",
    "du JSON : {\"a\": {\"b\": 1}}", "# language: fr\nFonctionnalité: X\n",
])
def test_falsifiable_un_texte_sans_variable_ressort_identique(texte):
    rendu = r.remplacer(texte, {"nom": r.Valeur("X", "Par défaut")}, ["nom"])

    assert rendu.texte == texte and rendu.complet and rendu.jouees == {}
    assert r.references(texte) == []


def test_remplacer_none_rend_un_texte_vide():
    assert r.remplacer(None, {}, []).texte == "" and r.references(None) == []


# ── 2. Les niveaux ────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_le_jeu_choisi_l_emporte_et_une_case_vide_reprend_par_defaut():
    valeurs = r.resoudre([("Par défaut", DEFAUT), ("Grosse commande", GROSSE)], DEFAUT)

    assert valeurs["client"] == r.Valeur("Durand Industrie", "Grosse commande")
    assert valeurs["quantite"] == r.Valeur("250", "Grosse commande")
    assert valeurs["ville"] == r.Valeur("Lyon", "Par défaut"), "case vide (espaces) dans le jeu : la valeur de « Par défaut » (A27)"
    assert "remise" not in valeurs and "commentaire" not in valeurs, "vide ou absente partout : sans valeur, jamais une chaîne vide"


def test_falsifiable_sans_jeu_choisi_seul_par_defaut_joue():
    valeurs = r.resoudre([("Par défaut", DEFAUT)], DEFAUT)

    assert {n: v.valeur for n, v in valeurs.items()} == {"client": "Martin SARL", "ville": "Lyon", "quantite": "1"}
    assert {v.origine for v in valeurs.values()} == {"Par défaut"}


def test_un_niveau_de_plus_ne_change_pas_la_regle():
    """La bibliothèque commune (PT-05) se placera devant, la campagne derrière : le plus précis l'emporte toujours."""
    niveaux = [("Bibliothèque commune", {"ville": "Paris", "pays": "France"}), ("Par défaut", DEFAUT), ("Grosse commande", GROSSE)]

    valeurs = r.resoudre(niveaux)

    assert valeurs["pays"] == r.Valeur("France", "Bibliothèque commune")
    assert valeurs["ville"] == r.Valeur("Lyon", "Par défaut")
    assert list(valeurs) == ["ville", "pays", "client", "quantite"], "sans liste de noms : toutes les variables citées, dans l'ordre"
    assert r.resoudre([]) == {} and r.resoudre(niveaux, ["inconnue"]) == {}


# ── 3. Le remplacement ────────────────────────────────────────────────────────────────────────────────────────────────────


def test_chaque_reference_recoit_la_valeur_retenue_et_rien_d_autre_ne_bouge():
    rendu = _jouer()

    assert rendu.complet
    assert rendu.texte == FEATURE.replace("{{client}}", "Durand Industrie").replace("{{ ville }}", "Lyon").replace("{{Quantite}}", "250")
    assert "10 % de remise pour {compte} et <exemple>" in rendu.texte
    assert {n: (v.valeur, v.origine) for n, v in rendu.jouees.items()} == {
        "client": ("Durand Industrie", "Grosse commande"), "ville": ("Lyon", "Par défaut"), "quantite": ("250", "Grosse commande")}
    assert r.references(FEATURE) == ["client", "ville", "quantite"]


@pytest.mark.parametrize("ecrit, nom", [("{{inconnue}}", "inconnue"), ("{{nom client}}", "{{nom client}}"), ("{{}}", "{{}}"),
                                        ("{{Client-2}}", "{{Client-2}}"), ("{{2clients}}", "{{2clients}}")])
def test_falsifiable_une_reference_inconnue_ou_mal_ecrite_rend_le_remplacement_incomplet(ecrit, nom):
    """Jamais laissée passer comme du texte : elle serait saisie telle quelle dans l'application."""
    rendu = r.remplacer(f'Quand je saisis "{ecrit}" puis "{{{{client}}}}"', r.resoudre([("Par défaut", DEFAUT)]), DEFAUT)

    assert not rendu.complet and rendu.inconnues == (nom,) and rendu.sans_valeur == ()
    assert ecrit in rendu.texte and "Martin SARL" in rendu.texte


def test_falsifiable_une_variable_connue_mais_vide_partout_est_sans_valeur_pas_remplacee_par_du_vide():
    rendu = r.remplacer('Quand je saisis la remise "{{remise}}" et "{{remise}}"', r.resoudre([("Par défaut", DEFAUT)]), DEFAUT)

    assert not rendu.complet and rendu.sans_valeur == ("remise",) and rendu.inconnues == ()
    assert rendu.texte.count("{{remise}}") == 2


def test_falsifiable_un_seul_passage_une_valeur_n_est_jamais_relue():
    valeurs = {"a": r.Valeur("{b}", "Par défaut"), "b": r.Valeur("SECRET", "Par défaut")}

    rendu = r.remplacer("{{a}}{{a}}", valeurs, ["a", "b"])

    assert rendu.texte == "{b}{b}" and "SECRET" not in rendu.texte


# ── 4. Noms et valeurs ────────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("saisi, nom", [("client", "client"), ("  Ville ", "ville"), ("quantité", "quantité"),
                                        ("poids_colis", "poids_colis"), ("taux2", "taux2")])
def test_un_nom_de_variable_est_normalise(saisi, nom):
    assert r.valider_nom(saisi) == nom


@pytest.mark.parametrize("saisi", ["", "   ", None, "nom client", "2clients", "_x", "client-2", "a" * 41, "{{client}}", "10%", "é"[:0]])
def test_falsifiable_un_nom_mal_forme_est_refuse(saisi):
    with pytest.raises(r.NomInvalide):
        r.valider_nom(saisi)


@pytest.mark.parametrize("saisie, gardee", [("Martin SARL", "Martin SARL"), ("  12,50 €  ", "12,50 €"), ("", ""), (None, ""),
                                            ("l'île d'Yeu", "l'île d'Yeu"), ("10 %", "10 %"), ("{compte}", "{compte}")])
def test_une_valeur_est_gardee_telle_qu_ecrite(saisie, gardee):
    assert r.valider_valeur(saisie) == gardee


@pytest.mark.parametrize("saisie", ['Société "Alpha"', "a | b", "ligne 1\nligne 2", "retour\r", "{{autre}}", "fin }}", "x" * 501, "\x00"])
def test_falsifiable_une_valeur_qui_casserait_le_texte_du_test_est_refusee(saisie):
    """Un guillemet fermerait le paramètre du step, une barre couperait la cellule, un retour à la ligne couperait l'étape :
    le test jouerait autre chose que ce qui est écrit."""
    with pytest.raises(r.ValeurInvalide):
        r.valider_valeur(saisie)


def test_falsifiable_une_valeur_acceptee_ne_change_ni_le_nombre_de_lignes_ni_les_guillemets_du_test():
    for valeur in ("Martin SARL", "l'île d'Yeu", "12,50 €", "a{b}c", "x < y", "#1", "@client"):
        rendu = r.remplacer(FEATURE, {"client": r.Valeur(r.valider_valeur(valeur), "j")}, ["client", "ville", "quantite"])

        assert rendu.texte.count("\n") == FEATURE.count("\n") and rendu.texte.count('"') == FEATURE.count('"')


# ── Revue du 2026-10-14 : chaque cas a été REPRODUIT avant d'être corrigé ─────────────────────────────────────────────────

_CLIENT = {"client": r.Valeur("Martin SARL", "Par défaut")}


@pytest.mark.parametrize("ecrit", [
    'Quand je saisis "{{client}"', 'Quand je saisis "{{ {{client}} }}"', 'Quand je saisis "{{{{client}}}}"',
    'Quand je saisis "{{client}}}"', 'Quand je saisis "{{{client}}}"', 'Quand je saisis "{{ client }}" puis "{{\nclient}}"',
    "Quand j'ouvre la page {{ sans fin",
])
def test_falsifiable_une_ecriture_ratee_n_est_jamais_jouee_comme_du_texte(ecrit):
    """Ces écritures passaient pour « complètes » : le test se jouait sans la valeur annoncée par le jeu de données."""
    rendu = r.remplacer(ecrit, _CLIENT, ["client"])

    assert not rendu.complet and any("mal écrite ou mal placée" in i for i in rendu.inconnues)


@pytest.mark.parametrize("ligne", [
    "  @{{client}}", "  # commentaire {{client}}", "  Scénario: Commande de {{client}}", "Fonctionnalité: {{client}}",
    '    {{client}} la page affiche le texte "ok"', "  Plan du scénario: {{client}}", "  une description {{client}}",
])
def test_falsifiable_une_variable_hors_d_une_etape_d_un_tableau_ou_d_un_bloc_n_est_pas_remplacee_en_silence(ligne):
    """Sa valeur changerait la STRUCTURE du test : une étiquette, un commentaire, un titre, le mot-clé d'une étape."""
    rendu = r.remplacer(ligne, _CLIENT, ["client"])

    assert not rendu.complet and any("mal écrite ou mal placée" in i for i in rendu.inconnues)


@pytest.mark.parametrize("texte", [
    '    Quand je saisis le client "{{client}}"', "    Et je saisis {{client}}", "    * je saisis {{client}}",
    "    Given I type {{client}}", "      | {{client}} | Lyon |", '      """\n      Bonjour {{client}}\n      """',
    "    Étant donné que le client {{client}} existe", "    Lorsqu'on saisit {{client}}",
])
def test_une_variable_dans_une_etape_un_tableau_ou_un_bloc_de_texte_est_remplacee(texte):
    rendu = r.remplacer(texte, _CLIENT, ["client"])

    assert rendu.complet and "Martin SARL" in rendu.texte and "{{" not in rendu.texte


@pytest.mark.parametrize("valeur", ["Martin\u2028SARL", "a\u2029b", "a\x85b", "\u200b", "a\u200bb", "x\u202ey", "<produit>",
                                    "un <client> ici"])
def test_falsifiable_une_valeur_invisible_ou_a_double_sens_est_refusee(valeur):
    """« \u2028 » coupe une étape (Behave découpe avec `splitlines()`) ; un caractère invisible fait d'une case vide une case qui
    n'hérite pas ; « <produit> » serait remplacé par Behave dans un plan de scénario."""
    with pytest.raises(r.ValeurInvalide):
        r.valider_valeur(valeur)
