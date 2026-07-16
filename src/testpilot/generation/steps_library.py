"""Catalogue des steps de la bibliothèque partagée (§6, décision 0003).

Sert deux besoins qui doivent parler du MÊME catalogue :
- ce qu'on **montre** à l'agent (pour qu'il réutilise au lieu de réinventer) ;
- ce qu'on **refuse** à l'écriture (redéfinition d'un step existant).

Extraction par AST et non par regex : les libellés de la bibliothèque sont souvent écrits
en concaténation implicite multi-lignes ::

    @then('aucun enregistrement en double avec le champ "{field}" égal à "{value}" '
          'n\\'existe dans le modèle "{model}"')

Une regex ne capture que le premier fragment et **tronque** le libellé — on montrerait alors
à l'agent un step inexistant, et la détection de collision porterait sur un texte partiel.
Le parseur Python, lui, fusionne ces littéraux : l'AST rend le libellé entier.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from testpilot import config

_DECORATORS = {"given", "when", "then", "step"}

# Mot-clé Gherkin (fr) correspondant au décorateur — pour que l'agent sache l'employer.
GHERKIN_KEYWORD = {
    "given": "Soit",
    "when": "Quand",
    "then": "Alors",
    "step": "Soit/Quand/Alors",
}


@dataclass(frozen=True)
class SharedStep:
    keyword: str  # given | when | then | step
    label: str
    source: str = ""  # fichier d'origine


def _decorator_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def extract_steps(source_code: str, source: str = "") -> list[SharedStep]:
    """Steps déclarés dans un module Python (libellés entiers). Vide si le code est invalide."""
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return []

    steps: list[SharedStep] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for deco in node.decorator_list:
            if not isinstance(deco, ast.Call) or not deco.args:
                continue
            name = _decorator_name(deco.func).lower()
            if name not in _DECORATORS:
                continue
            arg = deco.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                steps.append(SharedStep(keyword=name, label=arg.value.strip(), source=source))
    return steps


def catalogue(directory: Path | None = None) -> list[SharedStep]:
    """Tous les steps de la bibliothèque partagée. Vide si elle est absente (best-effort)."""
    directory = directory or config.STEPS_LIBRARY_DIR
    if not directory.exists():
        return []
    steps: list[SharedStep] = []
    for path in sorted(directory.glob("*.py")):
        try:
            steps.extend(extract_steps(path.read_text(encoding="utf-8"), source=path.name))
        except OSError:
            continue
    return steps


def reserved_labels(directory: Path | None = None) -> frozenset[str]:
    """Libellés réservés — un step généré ne doit jamais les redéfinir (AmbiguousStep)."""
    return frozenset(step.label for step in catalogue(directory))


def as_prompt_section(steps: list[SharedStep]) -> str:
    """Rend le catalogue pour le prompt système, groupé par mot-clé Gherkin.

    Sans cette section, l'agent ne PEUT PAS réutiliser la bibliothèque : on lui demandait de
    ne pas la redéfinir sans jamais la lui montrer (décision 0003).

    Le catalogue dit aussi ce que `{field}` DÉSIGNE (décision 0007, A1) : montrer le libellé
    d'un step sans la sémantique de ses paramètres laissait l'agent combler le vide par une
    convention raisonnable mais fausse (le libellé humain), d'où un `[name="Raison de la
    demande"]` introuvable. Le repli technique (phase B) rattrape ce cas ; cette annotation
    apprend la convention propre — sélecteur exact, donc plus fiable.
    """
    if not steps:
        return ""
    by_keyword: dict[str, list[str]] = {}
    for step in steps:
        by_keyword.setdefault(step.keyword, []).append(step.label)

    lines = [
        "Ces steps EXISTENT DÉJÀ et sont chargés automatiquement. Réutilise-les en copiant le",
        "libellé **mot pour mot** dans le `.feature` — ne les redéfinis pas (rejeté), et n'écris",
        "pas de variante qui ferait la même chose sous un autre nom.",
        "",
        "**Paramètre `{field}`** — c'est TOUJOURS le nom TECHNIQUE du champ, JAMAIS son libellé",
        "affiché : l'attribut HTML `name` du contrôle dans les steps d'interface (renseigner /",
        "sélectionner / laisser vide), le nom du champ du modèle dans les steps de vérification",
        "Odoo. Les deux se lisent sur l'application réelle. Un champ dont le libellé affiché est",
        "« Raison de la demande » peut très bien s'appeler `name`.",
        "",
        "En revanche, un bouton, un onglet ou un produit se désigne bien par son libellé VISIBLE",
        "(`{label}`, `{name}`) : ces steps-là résolvent par le texte affiché, pas par un sélecteur.",
        "",
    ]
    for keyword in ("given", "when", "then", "step"):
        labels = sorted(by_keyword.get(keyword, []))
        if not labels:
            continue
        lines.append(f"### {GHERKIN_KEYWORD[keyword]} (`@{keyword}`)")
        lines.extend(f"- {label}" for label in labels)
        lines.append("")
    return "\n".join(lines).rstrip()
