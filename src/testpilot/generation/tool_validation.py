"""Validation locale des schémas d'outils avant toute observation ou écriture.

⚠️ Ce validateur lit le schéma COMPLET (celui de `TOOLS_DEFINITIONS`), pas le schéma « compatible
API » envoyé en mode strict (`tools/api_definitions.py`) : l'API ne garantit ni `minLength`, ni
`maxLength`, ni `maxItems` (doc « Structured outputs », relue le 2026-10-07). Ces bornes restent
donc vérifiées ICI, quoi que le mode strict garantisse par ailleurs (types, champs requis, énums).
"""
from __future__ import annotations


def validate_tool_input(value, schema: dict, path: str = 'input') -> str:
    types = {'object': dict, 'array': list, 'string': str, 'integer': int, 'boolean': bool}
    kind = schema.get('type')
    expected = types.get(kind)
    if expected and (not isinstance(value, expected) or (kind == 'integer' and isinstance(value, bool))):
        return f'{path}: type attendu {kind}'
    if 'enum' in schema and value not in schema['enum']:
        return f'{path}: valeur hors catalogue'
    if kind == 'object':
        for name in schema.get('required', []):
            if name not in value:
                return f'{path}.{name}: requis'
        properties = schema.get('properties', {})
        if schema.get('additionalProperties') is False:
            unknown = set(value) - set(properties)
            if unknown:
                return f'{path}: propriétés inconnues {sorted(unknown)}'
        for name, definition in properties.items():
            if name in value:
                error = validate_tool_input(value[name], definition, f'{path}.{name}')
                if error:
                    return error
    elif kind == 'array':
        if len(value) < schema.get('minItems', 0):
            return f'{path}: liste vide interdite'
        # Q3-a : borne HAUTE (ex. 5 hypothèses au plus). Absente jusqu'ici ; le mode strict de
        # l'API ne sait pas l'imposer, c'est donc le seul endroit où elle est tenue.
        if 'maxItems' in schema and len(value) > schema['maxItems']:
            return f"{path}: {schema['maxItems']} éléments au plus"
        for i, item in enumerate(value):
            error = validate_tool_input(item, schema.get('items', {}), f'{path}[{i}]')
            if error:
                return error
    elif kind == 'string':
        if len(value.strip()) < schema.get('minLength', 0):
            return f'{path}: texte vide interdit'
        if 'maxLength' in schema and len(value) > schema['maxLength']:
            return f"{path}: {schema['maxLength']} caractères au plus"
    return ''
