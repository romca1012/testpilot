"""Définitions d'outils TELLES QU'ENVOYÉES à l'API Anthropic (lot Q3-a) — pures, sans réseau.

Deux vues d'un même outil, volontairement distinctes :

- **la vue locale** (`TOOLS_DEFINITIONS`, `tool_validation`) : le schéma COMPLET, avec toutes ses
  bornes (`minLength`, `maxItems`…). C'est elle qui VALIDE ce que l'agent appelle, et qui fait foi ;
- **la vue API** (`tools_for_api`) : ce que le SDK envoie. Par défaut, EXACTEMENT la vue locale telle
  qu'avant Q3-a. Avec les interrupteurs de `interrupteurs.py`, elle peut devenir : strict + exemples,
  descriptions V2, champ d'hypothèses.

⚠️ **Pourquoi le mode strict n'est pas « on le met partout ».** `strict: true` fait contraindre par
l'API les paramètres d'appel (types, champs requis, énumérations) : une classe entière de refus
« arguments invalides » disparaît. Mais (doc « Structured outputs », relue le 2026-10-07) :

- l'API ne supporte pas `minLength`, `maxLength`, `minimum`, `maximum`, `multipleOf`, `maxItems` ni
  `minItems` au-delà de 0 ou 1 : un schéma qui en porte est REFUSÉ (400) en strict. On les RETIRE de la
  vue API — la validation locale les garde — et on les rappelle dans la description du paramètre ;
- `additionalProperties` doit valoir `false` sur tout objet : un objet libre (ex. le dictionnaire
  `field_values` de `attempt_form_submission`) est INCOMPATIBLE — d'où une liste d'outils stricts
  explicite (`OUTILS_STRICTS`) plutôt qu'un « strict partout » ;
- 20 outils stricts, 24 paramètres optionnels et 16 unions au plus par requête : on met TOUS les
  paramètres en `required` (une liste vide dit « rien à signaler ») ; on est à 3 outils et 0 option ;
- le premier appel compile une grammaire (latence en plus ; mise en cache 24 h) : à mesurer.

`strict` garantit la FORME de l'appel, pas la VÉRITÉ de son contenu : un plan strict peut citer un
step faux ou une preuve inventée. `write_test_plan` continue de les refuser, localement.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping

from testpilot.generation.interrupteurs import (
    descriptions_v2_actif,
    prompt_hypotheses_actif,
    tools_strict_actif,
)
from testpilot.generation.technical_plan import HYPOTHESES_CLE, INPUT_EXAMPLES
from testpilot.generation.tools import TOOLS_DEFINITIONS
from testpilot.generation.tools.descriptions_v2 import appliquer_v2

# Les outils dont l'appel doit être garanti bien formé : ceux qui ÉCRIVENT les fichiers du test.
# Les outils d'inspection restent non stricts (paramètres optionnels, objet libre) : leur échec est
# peu coûteux et ils n'écrivent rien.
OUTILS_STRICTS: tuple[str, ...] = ("write_test_plan", "write_feature_file", "write_steps_file")
_OUTIL_AVEC_EXEMPLES = "write_test_plan"

# Mots-clés que l'API refuse en strict (hors `minItems`, traité à part : 0 et 1 sont acceptés).
_NON_SUPPORTES = ("minLength", "maxLength", "minimum", "maximum", "multipleOf", "maxItems")


def _note(mot: str, valeur) -> str:
    """La contrainte retirée, dite à l'agent — l'API ne la garantit plus, la validation locale oui."""
    if mot == "minLength":
        return "non vide" if valeur == 1 else f"au moins {valeur} caractères"
    if mot == "maxLength":
        return f"{valeur} caractères au plus"
    if mot == "maxItems":
        return f"{valeur} éléments au plus"
    if mot == "minItems":
        return f"au moins {valeur} éléments"
    return f"{mot} : {valeur}"


def _transformer(noeud: dict) -> None:
    """Rend `noeud` (et ses descendants) acceptable par l'API en strict — modifie en place."""
    notes = []
    for mot in _NON_SUPPORTES:
        if mot in noeud:
            valeur = noeud.pop(mot)
            if not (mot == "minLength" and valeur == 0):
                notes.append(_note(mot, valeur))
    if noeud.get("minItems", 0) > 1:
        notes.append(_note("minItems", noeud.pop("minItems")))
    if noeud.get("type") == "object":
        proprietes = noeud.get("properties")
        if not proprietes:
            # Un objet libre n'a aucune forme que l'API puisse contraindre : le déclarer strict
            # reviendrait à n'accepter que `{}`. On refuse plutôt que d'envoyer un schéma faux.
            raise ValueError("objet sans propriétés déclarées : incompatible avec le mode strict")
        noeud["additionalProperties"] = False
        noeud["required"] = list(proprietes)
        for sous in proprietes.values():
            _transformer(sous)
    elif noeud.get("type") == "array" and isinstance(noeud.get("items"), dict):
        _transformer(noeud["items"])
    if notes:
        existante = noeud.get("description", "")
        noeud["description"] = (existante + " " if existante else "") + f"[{' ; '.join(notes)}]"


def schema_compatible_api(schema: dict) -> dict:
    """Le schéma d'entrée d'un outil, rendu acceptable par l'API en mode strict. PUR.

    Copie, jamais d'effet sur l'entrée : le schéma local complet reste celui qui valide. Retire les
    mots-clés non supportés (en les rappelant dans la description), pose `additionalProperties:
    false` sur chaque objet et met chaque propriété en `required`. Lève `ValueError` sur un objet
    libre (voir la docstring du module).
    """
    copie = copy.deepcopy(schema)
    _transformer(copie)
    return copie


def _sans_hypotheses(definition: dict) -> None:
    """Retire le champ d'hypothèses de la vue envoyée tant que son interrupteur est éteint : l'API
    ne le voit pas, l'agent ne peut donc pas le remplir sans y avoir été invité."""
    schema = definition.get("input_schema") or {}
    (schema.get("properties") or {}).pop(HYPOTHESES_CLE, None)
    if HYPOTHESES_CLE in schema.get("required", []):
        schema["required"] = [n for n in schema["required"] if n != HYPOTHESES_CLE]


def exemples_pour(schema_api: dict) -> list[dict]:
    """Les `input_examples` de `write_test_plan`, ajustés au schéma EFFECTIVEMENT envoyé.

    L'API refuse (400) un exemple invalide contre le schéma : un exemple qui porte
    `hypotheses_non_verifiees` alors que le champ n'est pas exposé (`additionalProperties: false`)
    le ferait. On retire donc du premier niveau toute clé que le schéma envoyé ne déclare pas.
    """
    connues = set((schema_api.get("properties") or {}))
    return [{cle: copy.deepcopy(val) for cle, val in exemple.items() if cle in connues}
            for exemple in INPUT_EXAMPLES]


def tools_for_api(env: Mapping[str, str] | None = None, avec: tuple[str, ...] = ()) -> list[dict]:
    """La liste d'outils à passer à `call_with_tools`. PURE ; `env=None` lit `os.environ`.

    Tous les interrupteurs éteints (défaut) : égale, octet pour octet, à ce qui était envoyé avant
    Q3-a — `tests/fixtures/tools_definitions_avant_q3a.json` en est le témoin figé.

    `avec` (lot VH-07) : noms d'outils OPTIONNELS à ajouter en fin de liste (`tools.OUTILS_OPTIONNELS`), quand le contexte
    les rend possibles. Vide (défaut) : rien ne change.
    """
    strict = tools_strict_actif(env)
    v2 = descriptions_v2_actif(env)
    hypotheses = prompt_hypotheses_actif(env)
    sortie = []
    for definition in TOOLS_DEFINITIONS:
        d = copy.deepcopy(definition)
        if not hypotheses:
            _sans_hypotheses(d)
        if v2:
            d = appliquer_v2(d)
        if strict and d["name"] in OUTILS_STRICTS:
            schema_api = schema_compatible_api(d["input_schema"])
            d = {"name": d["name"], "description": d["description"], "strict": True,
                 "input_schema": schema_api}
            if d["name"] == _OUTIL_AVEC_EXEMPLES:
                d["input_examples"] = exemples_pour(schema_api)
        sortie.append(d)
    if avec:
        from testpilot.generation.tools import OUTILS_OPTIONNELS
        sortie += [copy.deepcopy(OUTILS_OPTIONNELS[nom]) for nom in avec if nom in OUTILS_OPTIONNELS]
    return sortie
