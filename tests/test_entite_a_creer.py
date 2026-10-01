"""F26(b), migration 58 (2026-10-01) — garde BLOQUANTE `enregistrement_lint.verifier_entite_a_creer`,
complémentaire au contrôle détective du point 1 (`lint_enregistrements_non_crees`). Teste la
fonction de détection seule ; `test_write_feature_file_entite_a_creer.py` teste le GATING
(`ToolContext.depend_dun_autre_cas_du_groupe`) qui la rend sans effet hors de sa portée prévue.
"""
from __future__ import annotations

from testpilot.generation.enregistrement_lint import verifier_entite_a_creer

# C138 — rejeu réel du 2026-10-01 (Portail Sapian - Integration, projet 12), reconstruit
# verbatim depuis le Gherkin affiché à l'écran. Motif 4 : chaîne nue dans un step de clic, sans
# crochets ni ligne de tableau — angle mort mesuré du point 1 (`lint_enregistrements_non_crees`).
_C138 = """# language: fr
Fonctionnalité: Réaffecter un équipement local vers un autre utilisateur de la même agence
  Scénario: [Nominal] PI-10 — Réaffectation locale d'un équipement vers un utilisateur de la même agence
    Soit la variable d'environnement "ODOO_ENV" n'est pas définie à "prod"
    Et je me connecte en tant que "DA"
    Et je navigue vers l'URL du portail "/my/equipments"
    Quand je clique sur "Réaffecter" dans la ligne contenant "AP5705S"
    Et je renseigne la relation "employee_id" avec "Utilisateur agence locale"
    Et je clique sur le bouton "Confirmer"
    Alors l'étape affichée est "done"
    Et le champ "owner_user_id" de cet enregistrement n'est pas vide
"""

# C139 — même rejeu, l'autre cas produit par la même spec PI-10. Motif 3 (valeur décorée en
# cellule de tableau) : déjà couvert par le point 1, donc aussi par cette garde (mêmes briques).
_C139 = """# language: fr
Fonctionnalité: Réaffecter localement un équipement en respectant la limite d'agence
  Contexte:
    Soit la variable d'environnement "ODOO_ENV" n'est pas définie à "prod"
    Et je me connecte en tant que "DA"
    Et un équipement de test "[S057SAM4C20A001280] AP5705S" existe dans le modèle "maintenance.equipment"

  Scénario: [Nominal] Réaffectation locale d'un équipement vers un utilisateur de la même agence
    Quand j'ajoute une ligne à "equipment_assignation_line_ids" avec :
      | champ           | valeur                          |
      | equipment_id    | [S057SAM4C20A001280] AP5705S    |
      | agency_dest_id  | SAPIAN SIEGE                    |
    Et j'enregistre le document
"""

_C131_CORRIGE = """# language: fr
Fonctionnalité: Affecter un équipement à une agence et vérifier que l'utilisateur assigné appartient à cette agence
  Scénario: [Nominal] Affecter un équipement à une agence de recette et vérifier la persistance
    Soit la variable d'environnement "ODOO_ENV" n'est pas définie à "prod"
    Et je me connecte en tant que "principal"
    Quand j'ouvre le formulaire de création du modèle "maintenance.equipment"
    Et je renseigne le champ "name" avec la valeur "BDD-AFFECT-001"
    Et j'enregistre le document
    Et j'ouvre l'enregistrement "BDD-AFFECT-001" du modèle "maintenance.equipment"
    Et je renseigne la relation "agency" avec "AGENCE DE SAINT-ETIENNE"
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

# Cas construit à la main (demande explicite du porteur) : un step de clic référence une valeur
# créée PLUS TÔT dans le MÊME scénario — ne doit JAMAIS déclencher.
_CLIC_SUR_VALEUR_CREEE = """# language: fr
Fonctionnalité: x
  Scénario: s
    Quand j'ouvre le formulaire de création du modèle "equipment.order"
    Et je renseigne le champ "serial_no" avec la valeur "TEST-BDD-SN-001"
    Et je clique sur le bouton d'action "confirm_order"
    Et je clique sur "Réaffecter" dans la ligne contenant "TEST-BDD-SN-001"
"""


def test_falsifiable_c138_declenche_le_refus():
    refus = verifier_entite_a_creer(_C138)
    assert refus is not None
    assert "ENTITE_NON_CREEE" in refus
    assert "AP5705S" in refus


def test_falsifiable_c139_declenche_le_refus_via_la_valeur_decoree():
    refus = verifier_entite_a_creer(_C139)
    assert refus is not None
    assert "AP5705S" in refus


def test_c131_corrige_ne_declenche_jamais():
    assert verifier_entite_a_creer(_C131_CORRIGE) is None


def test_c132_ne_declenche_jamais():
    assert verifier_entite_a_creer(_C132) is None


def test_un_clic_sur_une_valeur_creee_plus_tot_dans_le_meme_scenario_ne_declenche_pas():
    """Demande explicite : ne pas confondre « référence une entité réelle » et « référence ce que
    CE scénario vient de créer » — c'est exactement la distinction que motive cette garde."""
    assert verifier_entite_a_creer(_CLIC_SUR_VALEUR_CREEE) is None


def test_falsifiable_le_message_dit_quoi_faire_pas_seulement_ce_qui_est_interdit():
    """Principe cité (docs.claude.com/prompt-engineering) : dire CE QU'IL FAUT FAIRE, pas
    seulement ce qui est refusé — vérifié littéralement, pas supposé."""
    refus = verifier_entite_a_creer(_C138)
    assert "Ajoute" in refus and "CRÉENT cette entité" in refus
    assert "Rappelle ensuite write_feature_file" in refus
