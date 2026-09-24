"""Lot 07a — avis DÉTECTIF : un cas déclaré « test de connexion » qui s'ouvrirait déjà connecté.

Le step d'entrée connecte automatiquement. Un cas dont le sujet est la connexion (échec, compte
verrouillé…) doit s'ouvrir par « j'accède à la page de connexion sans me connecter ». On avertit AVANT
l'exécution — jamais on ne bloque, jamais on ne change un verdict (aucune voie vers un faux PASSED).

⚠️ L'intention est celle DÉCLARÉE à la génération (contenu métier du cas), jamais le Gherkin final
(décision 0015) : un test le fixe.
"""

from __future__ import annotations

import pytest

from testpilot.api.services import generation_service as gs
from testpilot.generation import smoke_check as sc

_FEATURE_CONNECTE = """Fonctionnalité: Connexion
  Scénario: Compte verrouillé
    Soit j'accède à la page d'accueil de l'application
    Quand je renseigne le champ "user-name" avec la valeur "locked_out_user"
    Alors une erreur de validation est affichée dans le formulaire
"""
_FEATURE_SANS_CONNEXION = _FEATURE_CONNECTE.replace(
    "j'accède à la page d'accueil de l'application", "j'accède à la page de connexion sans me connecter")
_FEATURE_EXPLICITE = _FEATURE_CONNECTE.replace(
    "j'accède à la page d'accueil de l'application", "je me connecte avec mes identifiants utilisateur")


@pytest.mark.parametrize("intention", [
    "Échec de connexion avec un mot de passe erroné",
    "Le compte verrouillé ne peut pas se connecter",
    "Connexion refusée pour un utilisateur bloqué",
    "Identifiants invalides : message d'erreur",
    "Impossible de se connecter avec un login inconnu",
    "locked out user cannot log in",
])
def test_une_intention_de_test_de_connexion_est_reconnue(intention):
    assert sc.intention_de_connexion(intention)


@pytest.mark.parametrize("intention", [
    "Ajouter un produit au panier après connexion",
    "Passer une commande complète",
    "Vérifier le tri du catalogue par prix",
    "",
])
def test_un_cas_qui_utilise_simplement_la_connexion_n_est_pas_un_test_de_connexion(intention):
    assert not sc.intention_de_connexion(intention)


def test_avertit_quand_l_intention_est_la_connexion_et_que_le_cas_arrive_deja_connecte():
    avis = sc.check_intention_connexion("Compte verrouillé : la connexion est refusée", _FEATURE_CONNECTE)

    assert [a["kind"] for a in avis] == ["connexion_non_testee"]
    assert "sans me connecter" in avis[0]["message"]
    assert set(avis[0]) == {"step", "line", "kind", "message"}, "même contrat que LintWarning"


@pytest.mark.parametrize("feature", [_FEATURE_SANS_CONNEXION, _FEATURE_EXPLICITE])
def test_se_tait_quand_le_cas_emploie_l_un_des_deux_steps(feature):
    assert sc.check_intention_connexion("Compte verrouillé : la connexion est refusée", feature) == []


def test_se_tait_quand_l_intention_n_est_pas_la_connexion():
    assert sc.check_intention_connexion("Ajouter un produit au panier", _FEATURE_CONNECTE) == []


def test_la_detection_ne_lit_jamais_le_gherkin_pour_deviner_l_intention():
    """Le Gherkin parle de compte verrouillé, l'intention DÉCLARÉE non : aucun avis (0015)."""
    assert "locked_out_user" in _FEATURE_CONNECTE
    assert sc.check_intention_connexion("Consulter le catalogue", _FEATURE_CONNECTE) == []


def test_l_intention_declaree_vient_du_contenu_metier_pas_du_gherkin():
    intention = gs._intention_declaree(
        {"title": "Compte verrouillé", "description": ""},
        {"title": "", "preconditions": "", "test_steps": '["Saisir un compte verrouillé"]',
         "expected_result": "L'accès est refusé", "feature_content": _FEATURE_CONNECTE})

    assert "verrouillé" in intention and "locked_out_user" not in intention


def test_l_avis_n_apparait_que_pour_un_projet_web(monkeypatch):
    class _Repo:
        def __init__(self, conn):
            pass

        def get(self, _id):
            return _Repo.projet

    monkeypatch.setattr("testpilot.store.repositories.ProjectRepo", _Repo)
    monkeypatch.setattr("testpilot.generation.domain_model.charger_modele", lambda p: None)
    version = {"id": 1, "title": "Compte verrouillé : connexion refusée", "steps_content": "",
               "feature_content": _FEATURE_CONNECTE, "created_by": "ia"}
    cas = {"project_id": 3, "title": "Compte verrouillé", "description": ""}

    _Repo.projet = {"id": 3, "connector_type": "web"}
    kinds_web = [w["kind"] for w in gs.lint_warnings_for_version(None, cas, [version], 1)]
    _Repo.projet = {"id": 3, "connector_type": "odoo"}
    kinds_odoo = [w["kind"] for w in gs.lint_warnings_for_version(None, cas, [version], 1)]

    assert "connexion_non_testee" in kinds_web
    assert "connexion_non_testee" not in kinds_odoo


def test_le_gate_et_le_prompt_connaissent_le_nouvel_avis_et_les_deux_steps():
    from pathlib import Path

    racine = Path(__file__).resolve().parent.parent
    gate = (racine / "frontend" / "src" / "components" / "ReviewGate.vue").read_text(encoding="utf-8")
    prompt = (racine / "src" / "testpilot" / "generation" / "prompts" / "system_prompt.md").read_text(
        encoding="utf-8")

    assert "connexion_non_testee: 'connexion'" in gate  # aucune valeur brute à l'écran (§4.7)
    assert "j'accède à la page de connexion sans me connecter" in prompt
    assert "n'écris JAMAIS de step de connexion" in prompt
