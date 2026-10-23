"""Étape 7 (A108, A110) — le calculateur des valeurs attendues, module pur.

Ce que ces tests gardent :
1. le calcul est EXACT (`Decimal`) et dit son détail, une ligne par étape ;
2. une fiche ne s'utilise que si elle retrouve EXACTEMENT ses exemples — une fiche fausse est attrapée (falsifiabilité) ;
3. rien n'est deviné : arrondi sans mode, barème sans lecture, élément sans source, constante sans date, nombre ambigu,
   entrée manquante, division par zéro → refus qui dit quoi corriger, jamais un résultat de repli.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from testpilot.parametres import calcul

TOTAL = {
    "nom": "Total commande", "resultat": "total", "unite": "EUR",
    "elements": [
        {"nom": "quantite", "source": "variable {{quantite}}"},
        {"nom": "prix", "source": "variable {{prix}}"},
        {"nom": "taux_remise", "valeur": "10", "source": "spec § 2.3", "verifie_le": "2026-10-23"},
        {"nom": "taux_tva", "valeur": "20", "source": "CGI art. 278", "verifie_le": "2026-10-23"},
    ],
    "etapes": [
        {"resultat": "brut", "operation": "multiplier", "termes": ["quantite", "prix"]},
        {"resultat": "remise", "operation": "pourcentage", "de": "brut", "taux": "taux_remise"},
        {"resultat": "ht", "operation": "soustraire", "termes": ["brut", "remise"]},
        {"resultat": "tva", "operation": "pourcentage", "de": "ht", "taux": "taux_tva"},
        {"resultat": "ttc", "operation": "additionner", "termes": ["ht", "tva"]},
        {"resultat": "total", "operation": "arrondir", "valeur": "ttc", "decimales": 2, "mode": "au_plus_proche"},
    ],
    "exemples": [{"entrees": {"quantite": "3", "prix": "10"}, "attendu": "32,40"}],
}


def _avec(**changements):
    return {**TOTAL, **changements}


def test_un_calcul_exact_avec_son_detail():
    fiche = calcul.valider_fiche(TOTAL)
    r = calcul.calculer(fiche, {"quantite": "3", "prix": "19,99"})

    assert r.resultat == Decimal("64.77")          # 59,97 − 10 % = 53,973 ; + 20 % = 64,7676 → 64,77
    assert r.unite == "EUR"
    assert r.detail[0] == "quantite = 3 (source : variable {{quantite}})"
    assert "taux_tva = 20 (source : CGI art. 278, vérifié le 2026-10-23)" in r.detail
    assert r.detail[-1] == "total = ttc arrondi à 2 décimale(s), au plus proche = 64,77"
    assert calcul.verifier_exemples(fiche) == []


def test_jamais_de_flottant():
    fiche = calcul.valider_fiche({
        "nom": "Somme", "resultat": "s", "elements": [{"nom": "a", "source": "x"}, {"nom": "b", "source": "x"}],
        "etapes": [{"resultat": "s", "operation": "additionner", "termes": ["a", "b"]}],
        "exemples": [{"entrees": {"a": "0,1", "b": "0,2"}, "attendu": "0,3"}]})
    assert calcul.verifier_exemples(fiche) == [], "0,1 + 0,2 vaut 0,3 (un flottant donnerait 0,30000000000000004)"


def test_falsifiable_une_fiche_qui_ne_retrouve_pas_son_exemple_est_attrapee():
    """La spec dit 32,40 ; une fiche qui oublie la remise trouve 36 : l'écart est dit, avec les deux valeurs."""
    sans_remise = _avec(etapes=[e for e in TOTAL["etapes"] if e["resultat"] not in ("remise",)])
    sans_remise["etapes"] = [
        {"resultat": "ht", "operation": "multiplier", "termes": ["quantite", "prix"]},
        {"resultat": "tva", "operation": "pourcentage", "de": "ht", "taux": "taux_tva"},
        {"resultat": "ttc", "operation": "additionner", "termes": ["ht", "tva"]},
        {"resultat": "total", "operation": "arrondir", "valeur": "ttc", "decimales": 2, "mode": "au_plus_proche"},
    ]
    ecarts = calcul.verifier_exemples(calcul.valider_fiche(sans_remise))
    assert ecarts == [calcul.EcartExemple(1, "32,40", "36,00")]


def test_falsifiable_un_centime_d_ecart_suffit():
    fiche = calcul.valider_fiche(_avec(exemples=[{"entrees": {"quantite": "3", "prix": "10"}, "attendu": "32,41"}]))
    assert len(calcul.verifier_exemples(fiche)) == 1


@pytest.mark.parametrize("mode, attendu", [("au_plus_proche", "0.13"), ("au_plus_proche_pair", "0.12"),
                                           ("inferieur", "0.12"), ("superieur", "0.13"), ("tronquer", "0.12")])
def test_le_mode_d_arrondi_est_celui_de_la_fiche(mode, attendu):
    fiche = calcul.valider_fiche({
        "nom": "Arrondi", "resultat": "r", "elements": [{"nom": "a", "source": "x"}],
        "etapes": [{"resultat": "r", "operation": "arrondir", "valeur": "a", "decimales": 2, "mode": mode}],
        "exemples": [{"entrees": {"a": "0,125"}, "attendu": attendu.replace(".", ",")}]})
    assert calcul.calculer(fiche, {"a": "0,125"}).resultat == Decimal(attendu)


def _bareme(mode):
    return calcul.valider_fiche({
        "nom": "Barème", "resultat": "r", "elements": [{"nom": "montant", "source": "x"}],
        "etapes": [{"resultat": "r", "operation": "bareme", "valeur": "montant", "mode": mode, "tranches": [
            {"jusqu_a": "1000", "taux": "0"}, {"jusqu_a": "5000", "taux": "10"}, {"taux": "20"}]}],
        "exemples": [{"entrees": {"montant": "0"}, "attendu": "0"}]})


def test_bareme_progressif_et_par_palier_ne_donnent_pas_le_meme_resultat():
    assert calcul.calculer(_bareme("progressif"), {"montant": "6000"}).resultat == Decimal("600")   # 0 + 400 + 200
    assert calcul.calculer(_bareme("par_palier"), {"montant": "6000"}).resultat == Decimal("1200")  # 6000 × 20 %
    assert calcul.calculer(_bareme("par_palier"), {"montant": "1000"}).resultat == Decimal("0"), "la borne est incluse"


def test_condition_plafond_et_minimum():
    fiche = calcul.valider_fiche({
        "nom": "Frais de port", "resultat": "port", "elements": [
            {"nom": "total", "source": "x"},
            {"nom": "seuil", "valeur": "50", "source": "CGV", "verifie_le": "2026-10-01"},
            {"nom": "forfait", "valeur": "4,90", "source": "CGV", "verifie_le": "2026-10-01"}],
        "etapes": [{"resultat": "port", "operation": "si", "condition": {"gauche": "total", "comparateur": ">=",
                                                                          "droite": "seuil"},
                    "alors": "0", "sinon": "forfait"}],
        "exemples": [{"entrees": {"total": "49,99"}, "attendu": "4,90"}, {"entrees": {"total": "50"}, "attendu": "0"}]})
    assert calcul.verifier_exemples(fiche) == []
    assert "(non)" in calcul.calculer(fiche, {"total": "10"}).detail[-1]


@pytest.mark.parametrize("modification, message", [
    ({"elements": [{"nom": "quantite"}]}, "source manque"),
    ({"elements": [{"nom": "taux", "valeur": "20", "source": "loi"}]}, "date de vérification"),
    ({"exemples": []}, "aucun exemple"),
    ({"resultat": "inconnu"}, "n'est produit par aucune étape"),
    ({"etapes": [{"resultat": "r", "operation": "arrondir", "valeur": "quantite", "decimales": 2}]}, "comment arrondir"),
    ({"etapes": [{"resultat": "r", "operation": "multiplier", "termes": ["quantite", "prix_oublie"]}]},
     "ni un élément ni le résultat"),
    ({"etapes": [{"resultat": "r", "operation": "bareme", "valeur": "quantite",
                  "tranches": [{"taux": "5"}]}]}, "progressif"),
    ({"etapes": [{"resultat": "r", "operation": "racine", "valeur": "quantite"}]}, "inconnue"),
])
def test_rien_n_est_devine(modification, message):
    with pytest.raises(calcul.FicheInvalide, match=message):
        calcul.valider_fiche(_avec(**modification))


def test_un_nombre_ambigu_n_est_jamais_tranche():
    with pytest.raises(calcul.FicheInvalide, match="n'est pas un nombre"):
        calcul.valider_fiche(_avec(exemples=[{"entrees": {"quantite": "1,234.5", "prix": "1"}, "attendu": "1"}]))


def test_une_entree_manquante_ou_une_division_par_zero_ne_donnent_aucun_resultat():
    fiche = calcul.valider_fiche(TOTAL)
    with pytest.raises(calcul.CalculImpossible, match="« prix » manque"):
        calcul.calculer(fiche, {"quantite": "3"})
    division = calcul.valider_fiche({
        "nom": "Moyenne", "resultat": "m", "elements": [{"nom": "a", "source": "x"}, {"nom": "n", "source": "x"}],
        "etapes": [{"resultat": "m", "operation": "diviser", "valeur": "a", "par": "n"}],
        "exemples": [{"entrees": {"a": "10", "n": "0"}, "attendu": "0"}]})
    with pytest.raises(calcul.CalculImpossible, match="division par zéro"):
        calcul.calculer(division, {"a": "10", "n": "0"})
    assert "incalculable" in calcul.verifier_exemples(division)[0].obtenu, "l'exemple n'est jamais tenu pour retrouvé"


def test_les_entrees_attendues_sont_les_elements_sans_valeur_fixe():
    assert calcul.entrees_attendues(calcul.valider_fiche(TOTAL)) == ["quantite", "prix"]
