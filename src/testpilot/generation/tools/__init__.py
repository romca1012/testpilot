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


@dataclass
class ToolOutcome:
    """Résultat d'un tool : observation (renvoyée au LLM) + effets pour l'état."""
    observation: str
    ok: bool = True
    feature_content: str | None = None
    steps_content: str | None = None


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
        "name": "write_feature_file",
        "description": "Écrit le fichier .feature (Gherkin français) du module.",
        "input_schema": {
            "type": "object",
            "properties": {"content": {"type": "string"}},
            "required": ["content"],
        },
    },
    {
        "name": "write_steps_file",
        "description": "Écrit le fichier _steps.py du module (validé : ASCII, pas de step partagé redéfini).",
        "input_schema": {
            "type": "object",
            "properties": {"content": {"type": "string"}},
            "required": ["content"],
        },
    },
]


def dispatch(name: str, tool_input: dict, ctx: ToolContext) -> ToolOutcome:
    """Route un appel de tool vers son implémentation. Jamais d'exception vers la boucle."""
    try:
        if name == "write_feature_file":
            return write_tools.write_feature_file(ctx, tool_input.get("content", ""))
        if name == "write_steps_file":
            return write_tools.write_steps_file(ctx, tool_input.get("content", ""))
        if name == "inspect_schema":
            return inspect_tools.inspect_schema(ctx, tool_input.get("model", ""))
        if name == "query_data":
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
        return ToolOutcome(observation=f"[tool inconnu : {name}]", ok=False)
    except Exception as exc:  # garde : un tool ne casse jamais la boucle
        return ToolOutcome(observation=f"[erreur tool {name} : {exc}]", ok=False)
