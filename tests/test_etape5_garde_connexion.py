"""Étape 5 du plan unique (AV-6) — la connexion déjà faite n'est pas réécrite par le test (interrupteur
`TESTPILOT_GARDE_CONNEXION`, éteint).

Mesuré en `base-4` : deux tests bloqués sur un compte inventé ; la consigne du prompt ne suffisait pas. Prouvé ici : un compte
non déclaré, une étape de connexion explicite, la page de connexion ou la saisie d'un mot de passe dans un cas qui ne porte
pas sur la connexion sont refusés à l'écriture ; un vrai test de connexion, un compte déclaré, et une intention inconnue
passent ; éteint, rien ne change.
"""

from __future__ import annotations

import pytest

from testpilot.generation import garde_connexion as g
from testpilot.generation import interrupteurs
from testpilot.generation import litteraux_observes as lo
from testpilot.generation.tools import ToolContext
from testpilot.generation.tools import write as w

MODELE = {"pages": {
    "/connexion": {"champs": [{"name": "identifiant", "label": "Identifiant"},
                              {"name": "mdp", "label": "Mot de passe", "type": "password"}],
                   "actions": [{"label": "Se connecter"}], "liens": []},
    "/produits": {"champs": [{"name": "quantite", "label": "Quantité"}], "actions": [{"label": "Ajouter"}], "liens": []},
}}


def _feature(*etapes):
    return "\n".join(["# language: fr", "Fonctionnalité: f", "  Scénario: s", *[f"    {e}" for e in etapes],
                      '    Alors la page affiche le texte "Produits"', ""])


@pytest.mark.parametrize("intention, attendu", [
    ("Ajouter un produit au panier", False),
    ("Connexion refusée avec un mot de passe erroné", True),
    ("Se déconnecter de l'application", True),
    ("La session expire après 30 minutes", True),
    ("Un compte verrouillé ne peut pas commander", True),
])
def test_porte_sur_la_connexion_lit_large(intention, attendu):
    assert g.porte_sur_la_connexion(intention) is attendu


def test_falsifiable_un_compte_invente_est_refuse_un_compte_declare_passe():
    feature = _feature('Soit je me connecte en tant que "admin"')
    assert g.refus(feature, porte_sur_la_connexion=None, comptes=["Commercial"])
    assert g.refus(_feature('Soit je me connecte en tant que "commercial"'), porte_sur_la_connexion=None,
                   comptes=["Commercial"]) == []
    assert g.refus(_feature('Soit je me connecte en tant que "Principal"'), porte_sur_la_connexion=None, comptes=[]) == []
    assert g.refus(feature, porte_sur_la_connexion=None, comptes=None) == [], "comptes inconnus : aucun contrôle"


@pytest.mark.parametrize("etape", [
    "Soit j'accède à la page de connexion sans me connecter",
    "Soit je me connecte avec mes identifiants utilisateur",
    'Soit j\'ouvre la page "/connexion"',
    'Quand je renseigne le champ "Mot de passe" avec la valeur "x"',
    'Quand je renseigne le champ "mdp" avec la valeur "x"',
])
def test_falsifiable_un_cas_qui_ne_porte_pas_sur_la_connexion_ne_la_reecrit_pas(etape):
    annuaire = lo.annuaire_depuis_modele(MODELE)
    feature = _feature(etape)
    kw = {"comptes": [], "page_connexion": annuaire.page_connexion, "champs_secrets": g.champs_secrets(annuaire)}
    assert g.refus(feature, porte_sur_la_connexion=False, **kw)
    assert g.refus(feature, porte_sur_la_connexion=True, **kw) == [], "un vrai test de connexion passe"
    assert g.refus(feature, porte_sur_la_connexion=None, **kw) == [], "intention inconnue : la garde se tait"


def test_l_accueil_qui_est_aussi_la_page_de_connexion_n_est_jamais_refuse():
    assert g.refus(_feature('Soit j\'ouvre la page "/"'), porte_sur_la_connexion=False, comptes=[],
                   page_connexion="/") == []


def test_les_etapes_d_un_contexte_et_d_un_plan_sont_lues():
    feature = "\n".join(["# language: fr", "Fonctionnalité: f", "  Contexte:",
                         "    Soit je me connecte avec mes identifiants utilisateur",
                         "  Scénario: s", '    Alors la page affiche le texte "Produits"', ""])
    assert g.refus(feature, porte_sur_la_connexion=False, comptes=[])


def _ctx(tmp_path, garde):
    return ToolContext(module_name="m", generated_dir=tmp_path, annuaire=lo.annuaire_depuis_modele(MODELE),
                       garde_connexion=garde)


def test_falsifiable_write_feature_file_refuse_seulement_garde_armee(tmp_path):
    feature = _feature("Soit je me connecte avec mes identifiants utilisateur")
    sortie = w.write_feature_file(_ctx(tmp_path, {"porte": False, "comptes": []}), feature)
    assert not sortie.ok and "CONNEXION_REECRITE" in sortie.observation
    assert not (tmp_path / "m.feature").exists()
    assert w.write_feature_file(_ctx(tmp_path / "eteint", None), feature).ok


def test_interrupteur_eteint_par_defaut():
    assert interrupteurs.garde_connexion_actif({}) is False
    assert interrupteurs.garde_connexion_actif({interrupteurs.ENV_GARDE_CONNEXION: "1"}) is True


def test_l_agent_arme_la_garde_avec_l_intention_declaree_et_les_comptes_seulement_allume(monkeypatch):
    from testpilot.analysis.plan import TestPlan
    from testpilot.generation.agent import GenerationAgent

    vus = []
    monkeypatch.setattr("testpilot.generation.agent.run_loop", lambda **kw: vus.append(kw["ctx"].garde_connexion))
    plan = TestPlan(module_name="m", models=[], scenarios=[], personas=[], portal_routes=[], risks=[], raw_spec="spec")
    metier = {"title": "Ajouter un produit au panier", "steps": ["Ajouter"], "expected_result": "Le panier compte 1"}
    projet = {"id": 1, "connector_type": "web", "comptes_libelles": [{"label": "Commercial", "business_role": ""}]}

    monkeypatch.delenv(interrupteurs.ENV_GARDE_CONNEXION, raising=False)
    GenerationAgent().generate(plan, metier=metier, projet=projet)
    monkeypatch.setenv(interrupteurs.ENV_GARDE_CONNEXION, "1")
    GenerationAgent().generate(plan, metier=metier, projet=projet)
    GenerationAgent().generate(plan, metier={**metier, "title": "Connexion refusée"}, projet=projet)

    assert vus == [None, {"porte": False, "comptes": ["Commercial"]}, {"porte": True, "comptes": ["Commercial"]}]
