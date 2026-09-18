"""Tests du pilier analysis — déterministes, sans réseau (LLM simulé).

Verrouillent : construction du TestPlan, réparation d'un JSON tronqué, retry sur plan
vide, et le fait que les champs techniques absents de la spec restent vides (« n'invente
rien » — invariant boîte noire).
"""

import json

from testpilot.analysis.spec_analyzer import SpecAnalyzer, spec_hash


class FakeLLM:
    """LLM simulé : renvoie des réponses scriptées et enregistre les appels."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def call_simple(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0) if self._responses else ""


_SPEC_REALISTE = ("Le portail /myservices permet de demander du matériel : la soumission crée "
                 "un helpdesk.ticket rattaché au demandeur.")

_FULL_PLAN = {
    "models": [{"name": "helpdesk.ticket", "citation": "crée un helpdesk.ticket"}],
    "personas": ["utilisateur du portail"],
    "portal_routes": ["/myservices"],
    "ambiguities": ["catégorie de matériel non précisée"],
    "entry_url": "/myservices",
    "server_injected_fields": ["product", "team_id"],
    "submission": {"mechanism": "fetch_post", "endpoint": "/website/form/helpdesk.ticket",
                   "trigger_selector": ".btnRequest"},
    "required_role": "portal",
    "scenarios": [
        {"name": "[Nominal] Demande simple", "type": "nominal", "action": "soumettre",
         "persona": "portail", "preconditions": ["connecté"], "expected_outcome": "ticket créé",
         "models_involved": ["helpdesk.ticket"],
         "navigation": [{"kind": "goto", "target": "/myservices", "method": "GET"},
                        {"kind": "js_trigger", "target": "Demander", "selector": ".btnRequest", "method": "POST"}],
         "assertions": [{"model": "helpdesk.ticket", "field": "name", "expected": "[TEST] Demande"}]},
        {"name": "[Erreur] Champs manquants", "type": "erreur", "action": "soumettre vide",
         "persona": "portail", "preconditions": [], "expected_outcome": "erreur de validation",
         "models_involved": ["helpdesk.ticket"]},
        {"name": "[Limite] Nom très long", "type": "limite", "action": "nom max",
         "persona": "portail", "preconditions": [], "expected_outcome": "ticket créé",
         "models_involved": ["helpdesk.ticket"]},
    ],
}


def test_builds_full_plan_from_valid_json():
    llm = FakeLLM([json.dumps(_FULL_PLAN)])
    plan = SpecAnalyzer(llm=llm).analyze_spec_content("demande_materiel", _SPEC_REALISTE)

    assert plan.module_name == "demande_materiel"
    assert plan.models == ["helpdesk.ticket"]
    assert len(plan.scenarios) == 3
    assert {s.type for s in plan.scenarios} == {"nominal", "erreur", "limite"}
    # Navigation et soumission de première classe correctement typées.
    nominal = plan.scenarios[0]
    assert nominal.navigation[0].kind == "goto"
    assert nominal.navigation[1].method == "POST"
    assert plan.submission.mechanism == "fetch_post"
    assert plan.server_injected_fields == ["product", "team_id"]
    assert nominal.assertions[0]["field"] == "name"


def test_extracts_json_wrapped_in_prose():
    wrapped = "Voici le plan :\n```json\n" + json.dumps(_FULL_PLAN) + "\n```\nVoilà."
    plan = SpecAnalyzer(llm=FakeLLM([wrapped])).analyze_spec_content("m", "spec")
    assert len(plan.scenarios) == 3


def test_repairs_truncated_json():
    full = json.dumps(_FULL_PLAN)
    truncated = full[: int(len(full) * 0.7)]  # coupé en plein vol
    plan = SpecAnalyzer(llm=FakeLLM([truncated])).analyze_spec_content("m", "spec")
    # Au moins le préfixe valide est récupéré (≥ 1 scénario), pas un plan totalement vide.
    assert len(plan.scenarios) >= 1


def test_retries_when_first_plan_empty():
    empty = json.dumps({"models": [], "scenarios": []})
    llm = FakeLLM([empty, json.dumps(_FULL_PLAN)])
    plan = SpecAnalyzer(llm=llm).analyze_spec_content("m", "spec")
    assert len(llm.calls) == 2  # un retry a bien eu lieu
    assert len(plan.scenarios) == 3


def test_absent_technical_fields_stay_empty():
    """Boîte noire : une spec sans détail technique ⇒ champs techniques vides, pas inventés."""
    minimal = {
        "models": ["sale.order"],
        "scenarios": [
            {"name": "[Nominal]", "type": "nominal", "action": "créer",
             "persona": "u", "preconditions": [], "expected_outcome": "ok",
             "models_involved": ["sale.order"]},
        ],
    }
    plan = SpecAnalyzer(llm=FakeLLM([json.dumps(minimal)])).analyze_spec_content("m", "spec")
    assert plan.entry_url == ""
    assert plan.server_injected_fields == []
    assert plan.submission is None
    assert plan.scenarios[0].navigation == []


# ── Citer ou retirer (backlog 1.2) ────────────────────────────────────────────
#
# Un site « texte pur » (`call_simple`, aucun outil d'observation) : jusqu'ici, un modèle
# plausible pour le domaine mais absent de la spec traversait cette étape sans aucun contrôle.
# Technique Anthropic (« reduce hallucinations ») : ancrer sur une citation vérifiable, retirer
# ce qu'aucune citation ne soutient.

def test_un_modele_avec_citation_verifiable_est_retenu():
    plan_json = json.dumps({
        "models": [{"name": "equipment.order", "citation": "crée un equipment.order"}],
        "scenarios": [{"name": "[Nominal]", "type": "nominal", "action": "créer",
                      "persona": "u", "preconditions": [], "expected_outcome": "ok",
                      "models_involved": []}],
    })
    plan = SpecAnalyzer(llm=FakeLLM([plan_json])).analyze_spec_content(
        "m", "Le bouton Confirmer crée un equipment.order dans Parc IT.")

    assert plan.models == ["equipment.order"]


def test_un_modele_SANS_citation_verifiable_est_ecarte():
    """Le cas mesuré : un modèle plausible pour le domaine, mais qu'aucune phrase de la spec ne
    nomme réellement — exactement le risque qu'un modèle halluciné passe inaperçu."""
    plan_json = json.dumps({
        "models": [{"name": "equipment.type", "citation": "gère le equipment.type"}],
        "scenarios": [{"name": "[Nominal]", "type": "nominal", "action": "créer",
                      "persona": "u", "preconditions": [], "expected_outcome": "ok",
                      "models_involved": []}],
    })
    plan = SpecAnalyzer(llm=FakeLLM([plan_json])).analyze_spec_content(
        "m", "Le bouton Confirmer crée un equipment.order dans Parc IT.")

    assert plan.models == []


def test_une_citation_reformulee_ne_suffit_pas():
    """La citation doit être un extrait MOT POUR MOT — une paraphrase, même fidèle sur le fond,
    ne prouve pas que le modèle est réellement nommé dans la spec."""
    plan_json = json.dumps({
        "models": [{"name": "equipment.order",
                   "citation": "un enregistrement d'équipement est généré"}],
        "scenarios": [{"name": "[Nominal]", "type": "nominal", "action": "créer",
                      "persona": "u", "preconditions": [], "expected_outcome": "ok",
                      "models_involved": []}],
    })
    plan = SpecAnalyzer(llm=FakeLLM([plan_json])).analyze_spec_content(
        "m", "Le bouton Confirmer crée un equipment.order dans Parc IT.")

    assert plan.models == []


def test_repli_retrocompatible_sur_une_liste_de_chaines_nues():
    """Ancien format (liste de chaînes) toujours accepté — mais SEULEMENT si le nom apparaît
    tel quel dans la spec, jamais à l'aveugle."""
    plan_json = json.dumps({
        "models": ["equipment.order"],
        "scenarios": [{"name": "[Nominal]", "type": "nominal", "action": "créer",
                      "persona": "u", "preconditions": [], "expected_outcome": "ok",
                      "models_involved": []}],
    })
    plan = SpecAnalyzer(llm=FakeLLM([plan_json])).analyze_spec_content(
        "m", "Le formulaire crée un equipment.order.")
    assert plan.models == ["equipment.order"]

    plan_absent = SpecAnalyzer(llm=FakeLLM([plan_json])).analyze_spec_content(
        "m", "Le formulaire crée un ticket.")
    assert plan_absent.models == []


def test_plusieurs_modeles_certains_verifies_d_autres_non():
    plan_json = json.dumps({
        "models": [
            {"name": "equipment.order", "citation": "crée un equipment.order"},
            {"name": "res.partner.invente", "citation": "notifie le res.partner.invente"},
        ],
        "scenarios": [{"name": "[Nominal]", "type": "nominal", "action": "créer",
                      "persona": "u", "preconditions": [], "expected_outcome": "ok",
                      "models_involved": []}],
    })
    plan = SpecAnalyzer(llm=FakeLLM([plan_json])).analyze_spec_content(
        "m", "Le bouton Confirmer crée un equipment.order dans Parc IT.")

    assert plan.models == ["equipment.order"]


def test_spec_hash_stable_and_sensitive():
    assert spec_hash("abc") == spec_hash("abc")
    assert spec_hash("abc") != spec_hash("abd")
