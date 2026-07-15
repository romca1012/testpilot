"""Assemblage des prompts du pilier generation.

Deux fonctions pures (ou quasi : lecture de fichier) :
  - ``build_system_prompt`` : socle connector-agnostic + catalogue des steps partagés
    + règles du connecteur actif.
  - ``build_initial_message`` : convertit le TestPlan en premier message utilisateur.
"""

from __future__ import annotations

from testpilot import config
from testpilot.analysis.plan import NavStep, TestPlan
from testpilot.connectors.base import Connector
from testpilot.generation import steps_library
from testpilot.generation.steps_library import SharedStep

_SYSTEM_PROMPT_PATH = config.PROMPTS_DIR / "system_prompt.md"


def build_system_prompt(connector: Connector | None = None,
                        shared_steps: list[SharedStep] | None = None) -> str:
    """Prompt système + catalogue des steps partagés + règles du connecteur actif.

    Le catalogue est indispensable : le prompt demande de réutiliser la bibliothèque et
    interdit de la redéfinir, mais l'agent ne pouvait pas la voir — il inventait donc ses
    propres steps (et son propre transport HTTP). Cf. décision 0003.
    """
    base = _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")

    catalogue = steps_library.as_prompt_section(shared_steps or [])
    if catalogue:
        base += "\n\n---\n\n## Steps partagés disponibles (à réutiliser)\n\n" + catalogue

    rules = connector.rules() if connector else ""
    if rules:
        base += "\n\n---\n\n## Connecteur actif\n\n" + rules
    return base


def _nav_to_gherkin_hint(navigation: list[NavStep]) -> str:
    """Traduit une séquence de navigation en indices Gherkin (aide, non contraignant)."""
    hints = []
    for step in navigation:
        if step.kind == "goto":
            hints.append(f'navigue vers "{step.target}"')
        elif step.kind == "click_tab":
            hints.append(f'clique sur l\'onglet "{step.target}"')
        elif step.kind == "click_item":
            hints.append(f'sélectionne "{step.target}"')
        elif step.kind == "js_trigger":
            hints.append(f'déclenche "{step.target}"')
    return " → ".join(hints)


def build_initial_message(plan: TestPlan) -> str:
    """Message utilisateur initial : le plan mis en forme pour la boucle ReAct."""
    lines = [
        f"# Génère les tests Behave pour le module « {plan.module_name} »",
        "",
        f"Type de système : {plan.connector_type}",
        f"Modèles impliqués : {', '.join(f'`{m}`' for m in plan.models) or '(à découvrir)'}",
        f"Personas : {', '.join(plan.personas)}",
        f"Routes : {', '.join(plan.portal_routes) or '(aucune)'}",
    ]
    if plan.entry_url:
        lines.append(f"URL d'entrée : {plan.entry_url}")
    if plan.server_injected_fields:
        lines.append(f"Champs injectés côté serveur : {', '.join(plan.server_injected_fields)}")
    if plan.required_role:
        lines.append(f"Rôle requis : {plan.required_role}")
    if plan.risks:
        lines.append("Ambiguïtés signalées : " + "; ".join(plan.risks))

    lines.append("\n## Scénarios à couvrir\n")
    for s in plan.scenarios:
        lines.append(f"### [{s.type.upper()}] {s.name}")
        lines.append(f"- Action : {s.action}")
        lines.append(f"- Persona : {s.persona}")
        if s.preconditions:
            lines.append(f"- Prérequis : {', '.join(s.preconditions)}")
        lines.append(f"- Résultat attendu : {s.expected_outcome}")
        nav = _nav_to_gherkin_hint(s.navigation)
        if nav:
            lines.append(f"- Navigation indicative : {nav}")
        if s.assertions:
            checks = "; ".join(f"{a.get('field')}={a.get('expected')}" for a in s.assertions)
            lines.append(f"- Assertions : {checks}")
        lines.append("")

    if plan.raw_spec:
        lines.append("## Spécification originale (extrait)\n")
        lines.append(plan.raw_spec[:3000])

    return "\n".join(lines)
