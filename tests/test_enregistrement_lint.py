"""F26, point 1 (2026-10-01) — garde-fou au gate de relecture. Les 4 cas réels (Portail Sapian -
Integration) servis comme référence par le porteur : C133/C134 DOIVENT déclencher le signal, un
cas qui crée et utilise sa propre donnée (C131 corrigé, C132) ne doit JAMAIS le déclencher.
"""
from __future__ import annotations

from testpilot.generation.enregistrement_lint import (
    KIND_ENREGISTREMENT_NON_CREE,
    lint_enregistrements_non_crees,
)

# Reconstruit depuis le Gherkin réel observé le 2026-10-01 (script affiché à l'écran, pas inventé).

_C131_CORRIGE = """# language: fr
Fonctionnalité: Affecter un équipement à une agence et vérifier que l'utilisateur assigné appartient à cette agence
  Scénario: [Nominal] Affecter un équipement à une agence de recette et vérifier la persistance
    Soit la variable d'environnement "ODOO_ENV" n'est pas définie à "prod"
    Et aucun enregistrement dont le nom commence par "BDD-AFFECT-" n'existe dans le modèle "maintenance.equipment"
    Et je me connecte en tant que "principal"
    Quand j'ouvre le formulaire de création du modèle "maintenance.equipment"
    Et je renseigne le champ "name" avec la valeur "BDD-AFFECT-001"
    Et je renseigne le champ "brand" avec la valeur "Athesi_Professional"
    Et j'enregistre le document
    Et j'ouvre l'enregistrement "BDD-AFFECT-001" du modèle "maintenance.equipment"
    Et je renseigne la relation "agency" avec "AGENCE DE SAINT-ETIENNE"
    Quand j'ouvre l'enregistrement "BDD-AFFECT-001" du modèle "maintenance.equipment"
    Alors l'état technique de ce document est "assigned"
"""

_C132 = """# language: fr
Fonctionnalité: Le statut d'un équipement passe automatiquement à Affecté dès que l'agence est renseignée
  Contexte:
    Soit je suis authentifié en tant qu'utilisateur défini dans "ODOO_USER" avec le mot de passe défini dans "ODOO_PASSWORD"
    Et je nettoie les enregistrements "EQ-BDD-AFFECTATION" du modèle "maintenance.equipment"

  Scénario: PI-04 — Affecter un équipement à une agence déclenche automatiquement le statut Affecté
    Quand j'ouvre le formulaire de création du modèle "maintenance.equipment"
    Et je renseigne le champ "name" avec la valeur "EQ-BDD-AFFECTATION"
    Et j'enregistre le document
    Et j'ouvre l'enregistrement "EQ-BDD-AFFECTATION" du modèle "maintenance.equipment"
    Et je renseigne la relation "agency" avec "AGENCE DE SAINT-ETIENNE"
"""

_C133 = """# language: fr
Fonctionnalité: Réaffectation d'un équipement vers un autre utilisateur de la même agence depuis le portail
  Scénario: [PI-10] Réaffecter un équipement vers un utilisateur de la même agence
    Soit la variable d'environnement "ODOO_ENV" n'est pas définie à "prod"
    Et le module Odoo "maintenance" est installé et actif sur la base définie dans "ODOO_DB"
    Et je suis authentifié en tant qu'utilisateur défini dans "ODOO_USER" avec le mot de passe défini dans "ODOO_PASSWORD"
    Et j'ouvre l'enregistrement "[S057SAM4C20A001280] AP5705S" du modèle "maintenance.equipment"
    Quand je me connecte avec mes identifiants utilisateur
    Et je navigue vers le menu Odoo "Parc IT / Gestion d'équipements / Équipements"
    Et j'ouvre l'enregistrement "[S057SAM4C20A001280] AP5705S" du modèle "maintenance.equipment"
    Et je clique sur le bouton d'action "action_reassign_equipment"
    Et je renseigne la relation "owner_user_id" avec "Testpilot QA"
"""

_C134 = """# language: fr
Fonctionnalité: Réaffectation d'un équipement refusée ou impossible vers un utilisateur d'une autre agence
  Contexte:
    Soit je suis authentifié en tant qu'utilisateur défini dans "ODOO_USER" avec le mot de passe défini dans "ODOO_PASSWORD"
    Et le nombre d'enregistrements dans le modèle "equipment.assignation.order" est enregistré pour comparaison

  Scénario: [PI-10] Réaffectation inter-agences refusée — l'affectation de l'équipement reste inchangée
    Quand je navigue vers le menu Odoo "Parc IT / Affectations / Équipements"
    Et j'ouvre le formulaire de création du modèle "equipment.assignation.order"
    Et j'ajoute une ligne à "equipment_assignation_line_ids" avec :
      | champ           | valeur                          |
      | equipment_id    | [S057SAM4C20A001280] AP5705S    |
    Et je clique sur le bouton d'action "confirm_order"
"""


def test_falsifiable_c133_declenche_le_signal():
    warnings = lint_enregistrements_non_crees(_C133)
    assert len(warnings) == 2  # les deux ouvertures de "[S057SAM4C20A001280] AP5705S"
    assert all(w["kind"] == KIND_ENREGISTREMENT_NON_CREE for w in warnings)
    assert "S057SAM4C20A001280" in warnings[0]["step"]


def test_falsifiable_c134_declenche_le_signal_via_la_ligne_de_tableau():
    """C134 ne passe JAMAIS par `j'ouvre l'enregistrement` — l'équipement réel est injecté
    directement dans une cellule de tableau (`equipment_id | [CODE] AP5705S`). Motif distinct de
    C133, couvert par la détection du format d'affichage décoré Odoo (`[CODE] Libellé`)."""
    warnings = lint_enregistrements_non_crees(_C134)
    assert len(warnings) == 1
    assert warnings[0]["kind"] == KIND_ENREGISTREMENT_NON_CREE
    assert "S057SAM4C20A001280" in warnings[0]["step"]


def test_c131_corrige_ne_declenche_jamais():
    assert lint_enregistrements_non_crees(_C131_CORRIGE) == []


def test_c132_ne_declenche_jamais():
    assert lint_enregistrements_non_crees(_C132) == []


def test_falsifiable_une_ouverture_sans_creation_prealable_declenche():
    feature = """# language: fr
Fonctionnalité: x
  Scénario: s
    Quand j'ouvre l'enregistrement "Produit existant" du modèle "product.template"
"""
    warnings = lint_enregistrements_non_crees(feature)
    assert len(warnings) == 1
    assert warnings[0]["kind"] == KIND_ENREGISTREMENT_NON_CREE


def test_une_creation_dans_le_contexte_couvre_tous_les_scenarios():
    """Le Contexte est PARTAGÉ : un enregistrement créé en Background ne déclenche le signal dans
    AUCUN scénario qui l'ouvre ensuite."""
    feature = """# language: fr
Fonctionnalité: x
  Contexte:
    Quand j'ouvre le formulaire de création du modèle "m"
    Et je renseigne le champ "name" avec la valeur "Partagé"
    Et j'enregistre le document

  Scénario: s1
    Quand j'ouvre l'enregistrement "Partagé" du modèle "m"

  Scénario: s2
    Quand j'ouvre l'enregistrement "Partagé" du modèle "m"
"""
    assert lint_enregistrements_non_crees(feature) == []


def test_une_creation_dans_un_scenario_ne_couvre_pas_un_AUTRE_scenario():
    """Deux scénarios INDÉPENDANTS : le nom créé dans `s1` ne couvre pas `s2` — exactement F26(b),
    reconstruit au niveau du Gherkin."""
    feature = """# language: fr
Fonctionnalité: x
  Scénario: s1
    Quand j'ouvre le formulaire de création du modèle "m"
    Et je renseigne le champ "name" avec la valeur "Local-s1"
    Et j'enregistre le document
    Et j'ouvre l'enregistrement "Local-s1" du modèle "m"

  Scénario: s2
    Quand j'ouvre l'enregistrement "Local-s1" du modèle "m"
"""
    warnings = lint_enregistrements_non_crees(feature)
    assert len(warnings) == 1
    assert "s2" not in warnings[0]["step"]  # le signal porte sur l'étape fautive, pas le titre
    assert warnings[0]["line"] == 10


# C136 (rejeu réel du 2026-10-01, après F26(b) — contrôle structuré) : la création passe par une
# LIGNE DE TABLEAU (assistant `equipment.order`), pas par `je renseigne le champ "name"`. A produit
# un FAUX POSITIF avec la première version du détecteur (portée trop étroite), corrigé ensuite.
_C136 = """# language: fr
Fonctionnalité: Vérifier que le statut d'un équipement passe automatiquement à Affecté dès que l'agence est renseignée
  Contexte:
    Soit je me connecte en tant que "principal"
    Et je nettoie les enregistrements "BDD-TEST-SN-" du modèle "maintenance.equipment"

  Scénario: [Nominal] PI-02 + PI-04
    Quand je navigue vers le menu Odoo "Parc IT / Générer des équipements"
    Et j'ouvre le formulaire de création du modèle "equipment.order"
    Et j'ajoute une ligne à "equipment_ids" avec :
      | champ      | valeur                |
      | partner_id | AGENCE D'ABBEVILLE    |
      | serial_no  | BDD-TEST-SN-001       |
      | brand      | TestBrand             |
      | model      | TestModel             |
    Et je clique sur le bouton d'action "confirm_order"
    Et j'ouvre l'enregistrement "[BDD-TEST-SN-001] TestModel" du modèle "maintenance.equipment"
    Alors l'état technique de ce document est "assigned"
"""


def test_falsifiable_une_creation_par_ligne_de_tableau_est_reconnue_c136():
    """Contre-essai du faux positif mesuré : `serial_no` (ligne de tableau, pas `je renseigne le
    champ "name"`) doit être reconnu comme une création — aucun signal."""
    assert lint_enregistrements_non_crees(_C136) == []


def test_falsifiable_un_champ_finissant_par__id_n_est_jamais_traite_comme_une_creation():
    """`partner_id` (ligne de tableau, motif C136) et `equipment_id` (motif C134) sont des
    RÉFÉRENCES Odoo (many2one) — jamais une valeur que ce scénario a créée, même posée via une
    ligne de tableau qui ressemble à une création."""
    feature = """# language: fr
Fonctionnalité: x
  Scénario: s
    Quand j'ouvre le formulaire de création du modèle "m"
    Et j'ajoute une ligne à "lignes" avec :
      | champ        | valeur              |
      | agence_id    | [X01] Agence réelle |
    Et j'ouvre l'enregistrement "[X01] Agence réelle" du modèle "res.partner"
"""
    warnings = lint_enregistrements_non_crees(feature)
    # Deux signaux : la valeur décorée en cellule de tableau, ET l'ouverture — "agence_id" n'a
    # jamais neutralisé l'un ou l'autre puisque ce n'est pas une création.
    assert len(warnings) == 2


def test_un_nom_affiche_decore_par_odoo_est_tolere():
    """`"[REF] Nom"` contient le nom créé `"Nom"` — pas de faux positif sur un simple habillage
    d'affichage (motif réellement observé : `"[S057SAM4C20A001280] AP5705S"`)."""
    feature = """# language: fr
Fonctionnalité: x
  Scénario: s
    Quand j'ouvre le formulaire de création du modèle "m"
    Et je renseigne le champ "name" avec la valeur "Nom"
    Et j'enregistre le document
    Et j'ouvre l'enregistrement "[REF-001] Nom" du modèle "m"
"""
    assert lint_enregistrements_non_crees(feature) == []
