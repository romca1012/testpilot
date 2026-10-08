"""Lot VH-05 — un test ne cite que ce qui a été observé sur l'application (T1, T4, T9 ; plan verdict honnête).

Chaque cas reproduit une erreur technique RÉELLE de la campagne `base-3` (2026-10-08) : champ technique inventé (`username`),
libellé réécrit sans accent (`Quantite de …`), sélecteur par texte libre, appel HTTP direct, attribut de contexte inventé. Le
sens inverse est prouvé aussi : les littéraux réellement observés passent, et une route inconnue n'est jamais un refus à tort.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from testpilot import config
from testpilot.generation import litteraux_observes as lo

MODELE = {
    "pages": {
        "/connexion": {"champs": [{"name": "identifiant", "label": "Identifiant"},
                                  {"name": "mot_de_passe", "label": "Mot de passe", "type": "password"}],
                       "actions": [{"label": "Se connecter"}], "liens": []},
        "/produits": {"champs": [{"name": "quantite", "label": "Quantité de Clavier mécanique"}],
                      "actions": [{"label": "Ajouter Clavier mécanique au panier"}],
                      "liens": [{"text": "Clients", "href": "/clients"}]},
        "/clients": {"champs": [], "actions": [], "liens": [{"text": "Nouveau client", "href": "/clients/nouveau"}]},
        "/clients/nouveau": {"champs": [{"name": "nom", "label": "Nom"}], "actions": [{"label": "Enregistrer"}], "liens": []},
    }
}


@pytest.fixture
def annuaire():
    return lo.annuaire_depuis_modele(MODELE)


def _feature(*etapes):
    return "\n".join(["# language: fr", "Fonctionnalité: f", "  Scénario: s", *[f"    {e}" for e in etapes]])


# ── .feature ──────────────────────────────────────────────────────────────────────────────────────────────


def test_falsifiable_un_champ_technique_invente_est_signale_avec_le_nom_observe(annuaire):
    """`base-3` : `connexion_refusee` ×3 et `connexion_valide` essai 2 — erreur technique en mode strict."""
    ecarts = lo.controler_feature(_feature("Soit j'accède à la page de connexion sans me connecter",
                                           'Quand je renseigne le champ "username" avec la valeur "testeur"'), annuaire)

    assert [(e.regle, e.cite) for e in ecarts] == [("champ", "username")]
    assert "page /connexion" in ecarts[0].raison


def test_les_champs_observes_passent_par_nom_technique_ou_par_libelle(annuaire):
    ecarts = lo.controler_feature(_feature("Soit j'accède à la page de connexion sans me connecter",
                                           'Quand je renseigne le champ "identifiant" avec la valeur "testeur"',
                                           'Et je renseigne le champ "Mot de passe" avec la valeur "x"',
                                           'Et je clique sur le bouton "Se connecter"'), annuaire)

    assert ecarts == []


def test_un_libelle_a_l_accent_pres_propose_l_orthographe_observee(annuaire):
    ecarts = lo.controler_feature(_feature('Soit j\'ouvre la page "/produits"',
                                           'Quand je renseigne le champ "Quantite de Clavier mecanique" avec la valeur "2"'),
                                  annuaire)

    assert ecarts[0].observe == "Quantité de Clavier mécanique"


def test_un_element_qui_existe_ailleurs_mais_pas_sur_la_page_courante_est_signale(annuaire):
    ecarts = lo.controler_feature(_feature('Soit j\'ouvre la page "/produits"', 'Quand je clique sur le bouton "Enregistrer"'),
                                  annuaire)

    assert ecarts and "pas sur la page /produits" in ecarts[0].raison


def test_un_lien_observe_fait_suivre_la_route(annuaire):
    ecarts = lo.controler_feature(_feature('Soit j\'ouvre la page "/clients"', 'Quand je clique sur le bouton "Nouveau client"',
                                           'Et je renseigne le champ "nom" avec la valeur "Dupont"'), annuaire)

    assert ecarts == []


def test_apres_une_action_qui_peut_soumettre_la_route_est_inconnue_jamais_un_refus_a_tort(annuaire):
    """Page d'arrivée inconnue → contrôle « existe dans l'application » (plus faible, mais aucun refus d'un test juste)."""
    ecarts = lo.controler_feature(_feature('Soit j\'ouvre la page "/clients/nouveau"', 'Quand je clique sur le bouton "Enregistrer"',
                                           'Et je clique sur le bouton "Nouveau client"'), annuaire)

    assert ecarts == []


def test_une_page_absente_de_l_annuaire_est_signalee(annuaire):
    ecarts = lo.controler_feature(_feature('Soit j\'ouvre la page "/produit"'), annuaire)

    assert ecarts[0].regle == "page" and ecarts[0].observe == "/produits"


# ── _steps.py ─────────────────────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def autorises():
    return lo.attributs_du_harnais(config.BEHAVE_RUNTIME_DIR)


def _regles(code, annuaire, autorises):
    return sorted({e.regle for e in lo.controler_steps(code, annuaire, autorises)})


def test_falsifiable_un_libelle_reecrit_sans_accent_dans_une_f_string_est_signale(annuaire, autorises):
    """`base-3` : `panier_total_tva` essais 2 et 3, `commande_persistance_serveur` essai 2."""
    code = "def s(context, name):\n    context.page.get_by_label(f\"Quantite de {name}\").fill('2')\n"

    ecarts = lo.controler_steps(code, annuaire, autorises)

    assert [e.regle for e in ecarts] == ["libelle"] and ecarts[0].observe.startswith("Quantité de")


def test_le_libelle_observe_dans_une_f_string_passe(annuaire, autorises):
    code = "def s(context, name):\n    context.page.get_by_label(f\"Quantité de {name}\").fill('2')\n"

    assert lo.controler_steps(code, annuaire, autorises) == []


@pytest.mark.parametrize("code, regle", [
    ("def s(context):\n    context.page.locator(\"button:has-text('Ajouter')\").click()\n", "selecteur"),
    ("def s(context):\n    context.page.locator('text=Total').inner_text()\n", "selecteur"),
    ("def s(context):\n    context.page.request.get('/__etat')\n", "reseau"),
    ("def s(context):\n    context.page.evaluate(\"fetch('/__etat')\")\n", "reseau"),
    ("def s(context):\n    u = context.base_url\n", "contexte"),
    ("def s(context):\n    p = context.web_password\n", "contexte"),
])
def test_falsifiable_les_pratiques_interdites_sont_signalees(code, regle, annuaire, autorises):
    assert regle in _regles(code, annuaire, autorises)


def test_un_attribut_pose_par_le_harnais_ou_par_le_test_lui_meme_passe(annuaire, autorises):
    code = ("def a(context):\n    context.numero = context.page.inner_text('#n')\n"
            "def b(context):\n    assert context.numero and context.page and context.table is not None\n")

    assert _regles(code, annuaire, autorises) == []


def test_le_harnais_pose_bien_les_attributs_usuels():
    autorises = lo.attributs_du_harnais(Path(config.BEHAVE_RUNTIME_DIR))

    assert {"page", "odoo", "created", "table"} <= autorises and "base_url" not in autorises
