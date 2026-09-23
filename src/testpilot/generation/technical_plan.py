"""Plan technique structuré compilé vers le catalogue partagé, sans Python inventé."""
from __future__ import annotations

import copy
import parse

from testpilot.generation.tool_validation import validate_tool_input

TEXT = {'type': 'string', 'minLength': 1}
SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'required': ['title', 'scenarios'],
    'properties': {'title': TEXT, 'scenarios': {
        'type': 'array', 'minItems': 1, 'items': {
            'type': 'object', 'additionalProperties': False,
            'required': ['name', 'requirement_ids', 'steps'],
            'properties': {'name': TEXT,
                'requirement_ids': {'type': 'array', 'minItems': 1, 'items': TEXT},
                'steps': {'type': 'array', 'minItems': 1, 'items': {
                    'type': 'object', 'additionalProperties': False,
                    'required': ['keyword', 'text', 'evidence_ids'],
                    'properties': {
                        'keyword': {'type': 'string', 'enum': ['Soit', 'Quand', 'Alors', 'Et', 'Mais']},
                        'text': TEXT, 'evidence_ids': {'type': 'array', 'items': TEXT}
                    }}}
            }}}}
}


def write_test_plan(ctx, plan):
    from testpilot.generation.tools import ToolOutcome
    from testpilot.generation.tools.write import write_feature_file
    error = validate_tool_input(plan, SCHEMA)
    if error:
        return ToolOutcome(f'[plan invalide : {error}]', ok=False)
    known = {e['id'] for e in ctx.observations}
    lines = ['# language: fr', 'Fonctionnalité: ' + plan['title']]
    values = [plan['title']]
    covered = set()
    for scenario in plan['scenarios']:
        values.append(scenario['name'])
        requirements = set(scenario['requirement_ids'])
        if not requirements <= set(ctx.requirements):
            return ToolOutcome('[plan : référence métier inconnue]', ok=False)
        covered.update(requirements)
        lines.append('  Scénario: ' + scenario['name'])
        effective = None
        assertion = False
        for step in scenario['steps']:
            keyword, text = step['keyword'], step['text']
            values.append(text)
            if keyword not in ('Et', 'Mais'):
                effective = {'Soit': 'given', 'Quand': 'when', 'Alors': 'then'}[keyword]
            if not effective:
                return ToolOutcome('[plan : première étape sans type]', ok=False)
            if not set(step['evidence_ids']) <= known:
                return ToolOutcome('[plan : preuve inconnue]', ok=False)
            found = False
            for shared in ctx.shared_steps:
                if shared.keyword not in (effective, 'step'):
                    continue
                try:
                    found = parse.parse(shared.label, text) is not None
                except (ValueError, KeyError, TypeError):
                    continue
                if found:
                    break
            if not found:
                return ToolOutcome('[plan : étape hors catalogue ; utiliser une extension explicite]', ok=False)
            assertion |= effective == 'then'
            lines.append(f'    {keyword} {text}')
        if not assertion:
            return ToolOutcome('[plan : résultat attendu sans assertion]', ok=False)
    if covered != set(ctx.requirements):
        return ToolOutcome('[plan : exigences métier non couvertes]', ok=False)
    if any('\n' in v or '\r' in v for v in values):
        return ToolOutcome('[plan : chaque libellé doit tenir sur une ligne]', ok=False)
    outcome = write_feature_file(ctx, '\n'.join(lines) + '\n')
    if outcome.ok:
        ctx.technical_plan = copy.deepcopy(plan)
    return outcome
