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


_FULL_PLAN = {
    "models": ["helpdesk.ticket"],
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
    plan = SpecAnalyzer(llm=llm).analyze_spec_content("demande_materiel", "spec...")

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


def test_spec_hash_stable_and_sensitive():
    assert spec_hash("abc") == spec_hash("abc")
    assert spec_hash("abc") != spec_hash("abd")
