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
from testpilot.generation import domain_model, steps_library
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


def _section_champs_requis(plan: TestPlan, modele: dict | None) -> str:
    """La CONTRAINTE de complétude : les champs requis du formulaire visé, + l'obligation de
    soumettre. **Impérative, pas indicative.**

    ⚠️ **Pourquoi une contrainte et non une suggestion.** Le prompt système demandait déjà
    d'observer les champs requis (« lis-les sur le formulaire réel ») — une instruction qui dépend
    de l'exploration, donc du tirage, et que **rien ne vérifiait**. Mesuré sur la MÊME spec
    (2026-07-19) : une génération remplit 6 champs et soumet explicitement, la suivante en remplit
    **2 sur 8** et se contente d'« attendre la soumission ». Le second test ne crée rien : 4
    scénarios `non_conforme`, prouvés côté test (sonde HTTP/RPC : aucun POST, delta 0 ticket).
    L'annuaire connaissait pourtant les 8 requis depuis toujours — personne ne les lui donnait.

    Rien n'est injecté si aucun formulaire n'est identifié : on n'invente pas de contrainte
    (mieux vaut le silence qu'une consigne fausse). La section porte **la date du modèle** — c'est
    une photo, et le filet du gate reste le garant vivant (borne du principe 2).
    """
    routes = list(plan.portal_routes or [])
    if plan.entry_url:
        routes.append(plan.entry_url)
    formulaires = domain_model.formulaires_requis(modele, routes)
    if not formulaires:
        return ""

    date = (modele or {}).get("mesure_le", "?")
    lignes = [f"## Champs OBLIGATOIRES du formulaire — CONTRAINTE (annuaire mesuré le {date})", ""]
    for form in formulaires:
        noms = [c["name"] for c in form["requis"]]
        lignes.append(f"Le formulaire `{form['route']}` EXIGE ces {len(noms)} champs requis. "
                      f"Tout scénario qui prétend CRÉER un enregistrement DOIT les remplir TOUS :")
        for champ in form["requis"]:
            detail = ""
            if champ["options"]:
                detail = f" — valeurs possibles : {', '.join(champ['options'][:6])}"
            elif champ["tag"]:
                detail = f" ({champ['tag']})"
            lignes.append(f"  - `{champ['name']}`{detail}")
        lignes.append("")
    lignes += [
        "**Deux obligations, non négociables :**",
        "1. **Remplir TOUS les champs requis ci-dessus** avant de soumettre. Un formulaire "
        "incomplet est refusé par l'application : rien n'est créé, et l'assertion de création "
        "échoue. Remplir un sous-ensemble produit un test qui ne teste rien.",
        "2. **Soumettre EXPLICITEMENT** par un step qui déclenche l'envoi (clic sur « Envoyer »). "
        "⚠️ « j'attends la soumission du formulaire » **n'envoie RIEN** — ce step se contente "
        "d'attendre. Un scénario qui remplit puis « attend » ne crée jamais rien.",
        "",
        "*(Exception légitime : un scénario `[ERREUR]` qui teste précisément l'omission d'un champ "
        "requis — là, l'omission est le sujet du test et doit être assumée comme telle.)*",
        "",
    ]
    return "\n".join(lignes)


def build_initial_message(plan: TestPlan, modele: dict | None = None) -> str:
    """Message utilisateur initial : le plan mis en forme pour la boucle ReAct.

    `modele` — l'annuaire du domaine (`domain_model.charger_modele`). Optionnel : sans lui, le
    message est celui d'avant (aucune contrainte de complétude n'est inventée)."""
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

    # La contrainte de complétude AVANT les scénarios : elle conditionne la façon de les écrire.
    contrainte = _section_champs_requis(plan, modele)
    if contrainte:
        lines.append("\n" + contrainte)

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
