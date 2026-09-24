"""Outils de la boucle ReAct : définitions (schéma Anthropic) + dispatch.

Deux familles séparées pour rester lisibles et sous le seuil de taille :
  - ``write``   : écriture des fichiers Behave (avec validation).
  - ``inspect`` : exploration de l'application vivante (délègue au Connector injecté).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from testpilot.connectors.base import Connector
from testpilot.generation.tools import inspect as inspect_tools
from testpilot.generation.tools import write as write_tools


@dataclass
class ToolContext:
    """Contexte partagé passé à chaque tool."""
    module_name: str
    generated_dir: Path
    connector: Connector | None = None
    reserved_steps: frozenset[str] = field(default_factory=frozenset)
    # Migration 45 (2026-09-16) : calibration en ÉCRITURE pendant la génération — éteinte par
    # défaut, activée par le porteur du projet (`project.calibration_writes_enabled`). Vérifiée
    # ICI (le tool), pas dans le connecteur : un connecteur ne connaît pas les réglages du projet.
    calibration_writes_enabled: bool = False
    qualification: bool = False
    # Lot 12 : le projet, pour relire SES règles apprises (formats de saisie déjà mesurés) — `None`
    # hors projet (tests, outils isolés) : aucune règle, jamais une erreur.
    project_id: int | None = None
    target_sha256: str = ""
    observations: list[dict] = field(default_factory=list)
    calibration_attempts: list[str] = field(default_factory=list)
    technical_plan: dict = field(default_factory=dict)
    requirements: dict[str, str] = field(default_factory=dict)
    shared_steps: list = field(default_factory=list)


@dataclass
class ToolOutcome:
    """Résultat d'un tool : observation (renvoyée au LLM) + effets pour l'état."""
    observation: str
    ok: bool = True
    feature_content: str | None = None
    steps_content: str | None = None
    verified_fields: dict[str, list[str]] = field(default_factory=dict)


TOOLS_DEFINITIONS: list[dict] = [
    {
        "name": "inspect_schema",
        "description": "Retourne les champs d'un modèle (nom, type, requis) via le connecteur.",
        "input_schema": {
            "type": "object",
            "properties": {"model": {"type": "string"}},
            "required": ["model"],
        },
    },
    {
        "name": "query_data",
        "description": "Lit quelques enregistrements réels d'un modèle (perception boîte noire).",
        "input_schema": {
            "type": "object",
            "properties": {
                "model": {"type": "string"},
                "fields": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer"},
            },
            "required": ["model"],
        },
    },
    {
        "name": "inspect_page_form",
        "description": "Observe un formulaire réel : champs requis et mécanisme de soumission.",
        "input_schema": {
            "type": "object",
            "properties": {"page_url": {"type": "string"}},
            "required": ["page_url"],
        },
    },
    {
        "name": "discover_route",
        "description": "Sonde une route pour découvrir son URL/statut/méthode réels.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path_pattern": {"type": "string"},
                "sample_id": {"type": "integer"},
            },
            "required": ["path_pattern"],
        },
    },
    {
        "name": "attempt_login",
        "description": (
            "Soumet CES identifiants au formulaire de connexion et rend le message RÉELLEMENT "
            "affiché après coup. À appeler AVANT d'écrire une assertion sur un message lié à une "
            "tentative de connexion (identifiants valides, mot de passe erroné, compte "
            "verrouillé...) — jamais deviner ce texte de mémoire."),
        "input_schema": {
            "type": "object",
            "properties": {
                "username": {"type": "string"},
                "password": {"type": "string"},
            },
            "required": ["username", "password"],
        },
    },
    {
        "name": "attempt_form_submission",
        "description": (
            "Remplit CES champs (par nom technique) sur le VRAI formulaire et le soumet, puis "
            "rend le message RÉELLEMENT affiché — et nettoie ce qui a été créé quand c'est "
            "possible. Réservé aux formulaires qui CRÉENT un enregistrement (pas la connexion, "
            "voir `attempt_login`) et aux projets qui ont explicitement autorisé cette "
            "calibration en écriture. Fournis `model` (le nom technique du modèle Odoo) pour "
            "que la donnée créée puisse être supprimée après lecture du message."),
        "input_schema": {
            "type": "object",
            "properties": {
                "page_url": {"type": "string"},
                "field_values": {"type": "object"},
                "model": {"type": "string"},
            },
            "required": ["page_url", "field_values"],
        },
    },
    {
        "name": "write_feature_file",
        # ⚠️ « REMPLACE » et « entier » : sans ce contrat, l'agent rend un EXTRAIT et écrase le
        # reste. Mesuré en run réel (0014 étape 6) sur le fichier de steps.
        "description": ("REMPLACE le fichier .feature (Gherkin français) du module par le "
                        "contenu fourni. Rends le fichier ENTIER : ce que tu n'écris pas est "
                        "perdu."),
        "input_schema": {
            "type": "object",
            "properties": {"content": {"type": "string"}},
            "required": ["content"],
        },
    },
    {
        "name": "write_steps_file",
        # ⚠️ Le contrat n'était écrit NULLE PART (« Écrit le fichier… »). En réparation, l'agent
        # a rendu le seul step qu'il corrigeait : les 3 autres ont disparu, le dry-run a échoué,
        # le test ne tournait plus. Mesuré en run réel (0014 étape 6).
        "description": ("REMPLACE le fichier _steps.py du module par le contenu fourni. Rends le "
                        "fichier ENTIER — tous les steps, y compris ceux que tu ne modifies pas : "
                        "ce que tu n'écris pas est PERDU et son step deviendra `undefined`. "
                        "Validé : ASCII, pas de step partagé redéfini."),
        "input_schema": {
            "type": "object",
            "properties": {"content": {"type": "string"}},
            "required": ["content"],
        },
    },
]


from testpilot.generation.technical_plan import SCHEMA as TECHNICAL_PLAN_SCHEMA

TOOLS_DEFINITIONS.append({
    'name': 'write_test_plan',
    'description': 'Compile un plan technique ENTIER en Gherkin à partir des étapes du catalogue. '
                   'Relie les scénarios aux identifiants métier fournis et aux preuves observées. '
                   'Écris ensuite le fichier de steps (vide si tout vient du catalogue).',
    'input_schema': TECHNICAL_PLAN_SCHEMA,
})


def dispatch(name: str, tool_input: dict, ctx: ToolContext) -> ToolOutcome:
    """Route un appel de tool vers son implémentation. Jamais d'exception vers la boucle."""
    try:
        from testpilot.generation.tool_validation import validate_tool_input
        definition = next((t for t in TOOLS_DEFINITIONS if t['name'] == name), None)
        if definition:
            error = validate_tool_input(tool_input, definition['input_schema'])
            if error:
                return ToolOutcome(observation=f"[arguments invalides : {error}]", ok=False)
        if name in {'attempt_login', 'attempt_form_submission'}:
            if ctx.qualification:
                return ToolOutcome(observation='[qualification : calibration métier interdite]', ok=False)
            ctx.calibration_attempts.append(name)
        if name == "write_feature_file":
            outcome = write_tools.write_feature_file(ctx, tool_input.get("content", ""))
            if outcome.ok:
                ctx.technical_plan = {}  # une réécriture libre invalide le lien du plan précédent
            return outcome
        if name == 'write_test_plan':
            from testpilot.generation.technical_plan import write_test_plan
            return write_test_plan(ctx, tool_input)
        if name == "write_steps_file":
            return write_tools.write_steps_file(ctx, tool_input.get("content", ""))
        if name == "inspect_schema":
            return inspect_tools.inspect_schema(ctx, tool_input.get("model", ""))
        if name == "query_data":
            if ctx.qualification:
                return ToolOutcome(observation='[qualification : utiliser les prérequis de test '
                                   'déclarés ; lecture libre de données métier désactivée]', ok=False)
            return inspect_tools.query_data(
                ctx, tool_input.get("model", ""),
                tool_input.get("fields"), tool_input.get("limit", 3),
            )
        if name == "inspect_page_form":
            return inspect_tools.inspect_page_form(ctx, tool_input.get("page_url", ""))
        if name == "discover_route":
            return inspect_tools.discover_route(
                ctx, tool_input.get("path_pattern", ""), tool_input.get("sample_id"),
            )
        if name == "attempt_login":
            return inspect_tools.attempt_login(
                ctx, tool_input.get("username", ""), tool_input.get("password", ""),
            )
        if name == "attempt_form_submission":
            return inspect_tools.attempt_form_submission(
                ctx, tool_input.get("page_url", ""), tool_input.get("field_values") or {},
                tool_input.get("model", ""),
            )
        return ToolOutcome(observation=f"[tool inconnu : {name}]", ok=False)
    except Exception as exc:  # garde : un tool ne casse jamais la boucle
        return ToolOutcome(observation=f"[erreur tool {name} : {exc}]", ok=False)
