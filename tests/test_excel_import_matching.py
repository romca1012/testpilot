"""Détection feuille/entête/colonnes et extraction de lignes (`excel_import.py`) — pas de base de
données ici, uniquement la logique pure de matching, testée sur un classeur « propre » (même
structure que le cahier de test réel ayant motivé ce lot : 2 lignes de titre, entête en ligne 3,
feuilles annexes) et sur des variantes délibérément « sales » (colonnes mélangées, entêtes en
anglais, pas de ligne de titre, colonne Priorité absente) — le porteur a été explicite : « je
n'aurai pas toujours des excels propres à charger »."""

from __future__ import annotations

import io

import openpyxl
import pytest

from testpilot.api.services import excel_import as ei


def _classeur(feuilles: dict[str, list[list]]) -> bytes:
    """Construit un classeur `.xlsx` en mémoire à partir de `{nom_feuille: [[cellules...], ...]}`
    — fixture synthétique, jamais le fichier personnel du porteur (hors dépôt)."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for nom, lignes in feuilles.items():
        ws = wb.create_sheet(nom)
        for ligne in lignes:
            ws.append(ligne)
    tampon = io.BytesIO()
    wb.save(tampon)
    return tampon.getvalue()


_ENTETE_FR = ["Test Case ID", "Description", "Étapes du Test", "Résultat Attendu", "User Story",
             "Priorité", "Statut", "Testeur", "Date", "Type", "Commentaires"]

_LIGNES_PROPRES = [
    ["CAHIER DE TEST YROS PORTAL"],
    ["Projet: PayorFront | Date: 28/09/2026"],
    _ENTETE_FR,
    ["TC-AUTH-001", "Connexion puis déconnexion", "1. Ouvrir /login\n2. Se connecter\n3. Se déconnecter",
     "Retour sur /login, déconnecté.", "AUTH - Connexion et session", "P1 - Critique", "Passed",
     "Cypress (auto)", "25/09/2026", "Fonctionnel", "cypress/e2e/auth.cy.js"],
    ["TC-AUTH-002", "Annulation de la déconnexion", "1. Cliquer Déconnexion\n2. Annuler",
     "Reste connecté.", "AUTH - Connexion et session", "P3 - Mineur", "Passed", "Cypress (auto)",
     "25/09/2026", "Fonctionnel", "cypress/e2e/auth2.cy.js"],
    # Priorité, statut ET type hors table de correspondance : doit être signalé, jamais deviné
    # en silence (même principe pour les trois).
    ["TC-AUTH-003", "Cas avec priorité inconnue", "1. Faire une étape", "Un résultat.",
     "AUTH - Divers", "Haute-ish", "En Cours", "", "", "Nominal", ""],
    # Ligne incomplète (pas de résultat attendu) : ignorée par défaut, mais visible.
    ["TC-AUTH-004", "Cas incomplet", "1. Faire une étape", "", "AUTH - Divers", "", "", "", "", "", ""],
]


def _classeur_cahier_reel() -> bytes:
    return _classeur({
        "Test Cases": _LIGNES_PROPRES,
        "Dashboard": [["TABLEAU DE BORD"], ["Données calculées automatiquement"]],
        "Guide": [["GUIDE D'UTILISATION"], [None, "Test Case ID", "Identifiant unique"]],
    })


def test_detecte_la_bonne_feuille_et_la_bonne_ligne_entete_malgre_les_feuilles_annexes():
    wb = ei.lire_classeur(_classeur_cahier_reel())
    entetes = ei.detecter_feuille_et_entete(wb)
    assert entetes.feuille == "Test Cases"
    assert entetes.index_ligne_entete == 3  # 2 lignes de titre au-dessus, comme le cahier réel


def test_mappe_les_onze_colonnes_francaises_correctement():
    wb = ei.lire_classeur(_classeur_cahier_reel())
    entetes = ei.detecter_feuille_et_entete(wb)
    champs = set(entetes.mapping.values())
    assert champs == {"identifiant", "titre", "etapes", "resultat_attendu", "section",
                      "priorite", "statut", "testeur", "date", "type", "commentaires"}


def test_une_colonne_non_reconnue_reste_visible_dans_entetes_brutes_pour_correction_manuelle():
    """Trouvé en répondant à une question du porteur : si `entetes_brutes` ne contenait que les
    colonnes déjà devinées, une colonne jamais reconnue serait invisible dans l'aperçu — donc
    impossible à rattacher à un champ à la main, alors que c'est exactement le filet de sécurité
    promis pour un Excel pas propre."""
    entete = ["Test Case ID", "Description", "Étapes du Test", "Résultat Attendu",
             "Environnement de test"]  # dernière colonne : aucun synonyme ne la couvre
    ligne = ["TC-1", "Titre", "1. Étape", "Résultat", "Préprod"]
    wb = ei.lire_classeur(_classeur({"Cas": [entete, ligne]}))
    entetes = ei.detecter_feuille_et_entete(wb)
    assert 5 not in entetes.mapping  # pas reconnue automatiquement
    assert entetes.entetes_brutes[5] == "Environnement de test"  # mais visible, pour correction


def test_extrait_les_lignes_avec_etapes_decoupees_et_numerotation_retiree():
    wb = ei.lire_classeur(_classeur_cahier_reel())
    entetes = ei.detecter_feuille_et_entete(wb)
    lignes = ei.extraire_lignes(wb["Test Cases"], entetes)
    premiere = lignes[0]
    assert premiere.titre == "Connexion puis déconnexion"
    assert premiere.etapes == ["Ouvrir /login", "Se connecter", "Se déconnecter"]
    assert premiere.resultat_attendu == "Retour sur /login, déconnecté."
    assert premiere.priorite == "high"
    assert premiere.statut_manuel == "passed"
    assert premiere.type_cas == "fonctionnel"
    assert premiere.identifiant == "TC-AUTH-001"
    assert premiere.retenue is True
    assert premiere.avertissements == []


def test_falsifiable_une_priorite_non_reconnue_produit_un_avertissement_pas_un_defaut_muet():
    """Preuve de falsifiabilité : si cette valeur était un jour ajoutée à `_PRIORITES`, ce test
    échouerait — c'est voulu, il garde la promesse « jamais deviné en silence »."""
    wb = ei.lire_classeur(_classeur_cahier_reel())
    entetes = ei.detecter_feuille_et_entete(wb)
    lignes = ei.extraire_lignes(wb["Test Cases"], entetes)
    ligne = next(l for l in lignes if l.titre == "Cas avec priorité inconnue")
    assert ligne.priorite == "medium"  # le défaut appliqué
    assert any("priorité" in a and "Haute-ish" in a for a in ligne.avertissements)


def test_falsifiable_un_statut_non_reconnu_n_est_jamais_importe_comme_resultat():
    wb = ei.lire_classeur(_classeur_cahier_reel())
    entetes = ei.detecter_feuille_et_entete(wb)
    lignes = ei.extraire_lignes(wb["Test Cases"], entetes)
    ligne = next(l for l in lignes if l.titre == "Cas avec priorité inconnue")
    assert ligne.statut_manuel is None
    assert any("statut" in a and "En Cours" in a for a in ligne.avertissements)


def test_falsifiable_un_type_non_reconnu_produit_un_avertissement_pas_un_defaut_muet():
    """Même garde que pour la priorité (ligne 90) : si « Nominal » était un jour ajouté à
    `_TYPES`, ce test échouerait — c'est voulu."""
    wb = ei.lire_classeur(_classeur_cahier_reel())
    entetes = ei.detecter_feuille_et_entete(wb)
    lignes = ei.extraire_lignes(wb["Test Cases"], entetes)
    ligne = next(l for l in lignes if l.titre == "Cas avec priorité inconnue")
    assert ligne.type_cas == "fonctionnel"  # le défaut appliqué
    assert any("type" in a and "Nominal" in a for a in ligne.avertissements)


def test_ligne_sans_resultat_attendu_est_ignoree_par_defaut_mais_visible_avec_sa_raison():
    wb = ei.lire_classeur(_classeur_cahier_reel())
    entetes = ei.detecter_feuille_et_entete(wb)
    lignes = ei.extraire_lignes(wb["Test Cases"], entetes)
    ligne = next(l for l in lignes if l.titre == "Cas incomplet")
    assert ligne.retenue is False
    assert any("résultat attendu" in a for a in ligne.avertissements)


# ── Excels « sales » : le porteur a été explicite sur ce point ─────────────────────────────────

def test_colonnes_dans_un_ordre_different_sont_quand_meme_mappees():
    entete_melange = ["Priorité", "Résultat Attendu", "Test Case ID", "Étapes du Test",
                      "Description", "User Story"]
    ligne = ["P2 - Majeur", "Un résultat clair.", "TC-001", "1. Étape unique", "Un titre",
            "SECTION-X"]
    wb = ei.lire_classeur(_classeur({"Cas": [entete_melange, ligne]}))
    entetes = ei.detecter_feuille_et_entete(wb)
    lignes = ei.extraire_lignes(wb["Cas"], entetes)
    assert lignes[0].titre == "Un titre"
    assert lignes[0].priorite == "medium"
    assert lignes[0].section == "SECTION-X"


def test_entetes_en_anglais_sans_aucune_ligne_de_titre_au_dessus():
    entete_en = ["ID", "Title", "Steps", "Expected Result", "Priority"]
    ligne = ["T-1", "Login works", "1. Open login\n2. Submit", "User is logged in", "High"]
    wb = ei.lire_classeur(_classeur({"Sheet1": [entete_en, ligne]}))
    entetes = ei.detecter_feuille_et_entete(wb)
    assert entetes.index_ligne_entete == 1
    lignes = ei.extraire_lignes(wb["Sheet1"], entetes)
    assert lignes[0].titre == "Login works"
    assert lignes[0].etapes == ["Open login", "Submit"]
    assert lignes[0].priorite == "high"


def test_colonne_priorite_absente_ne_fait_pas_echouer_l_extraction():
    entete_sans_priorite = ["Test Case ID", "Description", "Étapes du Test", "Résultat Attendu"]
    ligne = ["TC-1", "Titre", "1. Étape", "Résultat"]
    wb = ei.lire_classeur(_classeur({"Cas": [entete_sans_priorite, ligne]}))
    entetes = ei.detecter_feuille_et_entete(wb)
    lignes = ei.extraire_lignes(wb["Cas"], entetes)
    assert lignes[0].priorite == "medium"  # défaut, sans avertissement (la colonne n'existe pas)
    assert lignes[0].retenue is True


def test_classeur_sans_aucune_ligne_reconnaissable_leve_une_erreur_claire():
    wb = ei.lire_classeur(_classeur({"Vide": [["x", "y", "z"], ["1", "2", "3"]]}))
    with pytest.raises(ei.FichierExcelInvalide):
        ei.detecter_feuille_et_entete(wb)


def test_hash_fichier_est_stable_et_depend_du_contenu():
    data1 = _classeur_cahier_reel()
    data2 = _classeur({"Autre": [["a", "b"]]})
    assert ei.hash_fichier(data1) == ei.hash_fichier(data1)
    assert ei.hash_fichier(data1) != ei.hash_fichier(data2)
