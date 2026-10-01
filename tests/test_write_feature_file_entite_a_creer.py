"""F26(b), migration 58 (2026-10-01) — le GATING de `verifier_entite_a_creer` dans
`write_feature_file` : actif UNIQUEMENT quand le métier du cas a déclaré
`ctx.depend_dun_autre_cas_du_groupe` (jamais une heuristique générale sur la nature de la
référence — confirme par la négative que le cas SauceDemo, qui ne déclare jamais cette
dépendance, reste hors de portée, exactement le faux positif mesuré en diagnostic).
"""
from __future__ import annotations

from testpilot.generation.tools import ToolContext
from testpilot.generation.tools import write as write_tools

_C138 = """# language: fr
Fonctionnalité: Réaffecter un équipement local vers un autre utilisateur de la même agence
  Scénario: [Nominal] PI-10
    Soit la variable d'environnement "ODOO_ENV" n'est pas définie à "prod"
    Et je me connecte en tant que "DA"
    Quand je clique sur "Réaffecter" dans la ligne contenant "AP5705S"
    Et je renseigne la relation "employee_id" avec "Utilisateur agence locale"
"""

_CREE_PUIS_REFERENCE = """# language: fr
Fonctionnalité: Réaffecter un équipement créé par ce cas
  Scénario: S
    Soit la variable d'environnement "ODOO_ENV" n'est pas définie à "prod"
    Quand j'ouvre le formulaire de création du modèle "equipment.order"
    Et je renseigne le champ "serial_no" avec la valeur "TEST-BDD-SN-001"
    Et je clique sur le bouton d'action "confirm_order"
    Et je clique sur "Réaffecter" dans la ligne contenant "TEST-BDD-SN-001"
"""

# Motif SauceDemo réel (ajouter_un_produit_au_panier_et_finalise_3492e8.feature) : un produit de
# catalogue FIXE, jamais « créé » par aucun scénario — légitime, hors de portée de cette garde
# puisqu'aucun métier SauceDemo ne déclare `depend_dun_autre_cas_du_groupe`.
_SAUCEDEMO_CATALOGUE = """# language: fr
Fonctionnalité: Ajouter un produit au panier et finaliser une commande
  Scénario: ACH-01
    Soit je me connecte en tant que "principal"
    Et j'ouvre la page "/inventory.html"
    Quand je clique sur "Add to cart" dans la ligne contenant "Sauce Labs Backpack"
"""


def _ctx(tmp_path, *, depend: bool, etat: str = "créer un équipement avant de le réaffecter"):
    return ToolContext(module_name="m", generated_dir=tmp_path,
                       depend_dun_autre_cas_du_groupe=depend,
                       etat_a_creer_par_ce_cas=etat if depend else "")


def test_falsifiable_c138_est_refuse_quand_le_metier_declare_la_dependance(tmp_path):
    resultat = write_tools.write_feature_file(_ctx(tmp_path, depend=True), _C138)

    assert resultat.ok is False
    assert "ENTITE_NON_CREEE" in resultat.observation
    assert "AP5705S" in resultat.observation
    assert not (tmp_path / "m.feature").exists()


def test_une_entite_creee_puis_reutilisee_est_acceptee_meme_avec_la_dependance_declaree(tmp_path):
    resultat = write_tools.write_feature_file(_ctx(tmp_path, depend=True), _CREE_PUIS_REFERENCE)

    assert resultat.ok is True
    assert (tmp_path / "m.feature").exists()


def test_c138_est_accepte_sans_la_declaration_de_dependance_la_garde_ne_s_applique_pas(tmp_path):
    """Prouve le GATING lui-même : LE MÊME contenu C138, mais sans dépendance déclarée, n'est plus
    refusé par CETTE garde — exactement ce qui protège SauceDemo (cas suivant)."""
    resultat = write_tools.write_feature_file(_ctx(tmp_path, depend=False), _C138)

    assert resultat.ok is True


def test_falsifiable_le_catalogue_saucedemo_n_est_jamais_bloque_motif_reel_mesure(tmp_path):
    """Faux positif mesuré en diagnostic (2026-10-01) : un produit de catalogue fixe référencé par
    le même step que C138, mais sans dépendance déclarée — doit rester accepté."""
    resultat = write_tools.write_feature_file(_ctx(tmp_path, depend=False), _SAUCEDEMO_CATALOGUE)

    assert resultat.ok is True
