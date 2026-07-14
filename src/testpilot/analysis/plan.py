"""Structures du plan de test produit par l'analyse d'une spécification.

Vocabulaire volontairement générique (web/API/ERP) : ces objets ne présument pas
d'Odoo. Les champs techniques (navigation, soumission, champs injectés côté serveur)
restent vides si la spec ne les décrit pas — l'agent les découvre en explorant
l'application en marche (boîte noire).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class NavStep:
    """Une étape de navigation (vocabulaire web universel)."""
    kind: Literal["goto", "click_tab", "click_item", "js_trigger"]
    target: str = ""
    selector: str = ""
    method: str = "GET"


@dataclass
class SubmissionSpec:
    """Mécanisme de soumission d'un formulaire."""
    mechanism: Literal["button_click", "fetch_post", "js_post"]
    endpoint: str = ""
    trigger_selector: str = ""


@dataclass
class ScenarioIntent:
    """Intention d'un scénario : ce qu'il vérifie, pas encore le Gherkin."""
    name: str
    type: Literal["nominal", "erreur", "limite"]
    action: str
    persona: str
    preconditions: list[str] = field(default_factory=list)
    expected_outcome: str = ""
    models_involved: list[str] = field(default_factory=list)
    navigation: list[NavStep] = field(default_factory=list)
    assertions: list[dict] = field(default_factory=list)  # {model, field, expected}


@dataclass
class TestPlan:
    """Plan de test structuré extrait d'une spécification."""
    __test__ = False  # pas une classe de test pytest malgré le préfixe « Test »

    module_name: str
    models: list[str]
    scenarios: list[ScenarioIntent]
    personas: list[str]
    portal_routes: list[str]
    risks: list[str]
    connector_type: str = "odoo"
    cost_usd: float = 0.0
    raw_spec: str = ""
    # Navigation / soumission de première classe (vides = non décrits par la spec).
    entry_url: str = ""
    server_injected_fields: list[str] = field(default_factory=list)
    submission: SubmissionSpec | None = None
    required_role: str = ""
