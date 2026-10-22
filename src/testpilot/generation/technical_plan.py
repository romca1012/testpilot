"""Plan technique structuré compilé vers le catalogue partagé, sans Python inventé."""
from __future__ import annotations

import copy
import json

import parse

from testpilot.generation.tool_validation import validate_tool_input

TEXT = {'type': 'string', 'minLength': 1}

# Q3-a : ce dont l'agent n'est PAS sûr. Avant ce champ, la « clôture » du prompt (PILIER 4) n'était
# JAMAIS produite : le dry-run vert met fin à la boucle sans tour supplémentaire (`react_loop.py`),
# donc aucune phrase finale n'existait pour dire un doute à l'humain qui relit. Le champ voyage DANS
# le plan (déjà persisté en JSON dans `technical_plan` : aucune migration, aucune colonne).
# ⚠️ C'est une information destinée à l'humain, JAMAIS un critère : le texte de l'agent n'est pas une
# source de vérité (décision 0015) — aucun verdict, aucune réparation ne doit le lire pour décider.
# Optionnel : un plan sans ce champ reste valide (aucun plan existant ne casse).
HYPOTHESES_CLE = 'hypotheses_non_verifiees'
HYPOTHESES_MAX = 5
HYPOTHESE_MAX_CARACTERES = 200
_HYPOTHESES_SCHEMA = {
    'type': 'array', 'maxItems': HYPOTHESES_MAX,
    'items': {'type': 'string', 'minLength': 1, 'maxLength': HYPOTHESE_MAX_CARACTERES},
}

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
# Ajouté APRÈS `scenarios` : en sortie contrainte, l'API émet les propriétés dans l'ordre du schéma —
# l'agent énonce ses doutes une fois les scénarios écrits, pas avant de les connaître.
SCHEMA['properties'][HYPOTHESES_CLE] = _HYPOTHESES_SCHEMA


# Q3-a : exemples d'appel valides, envoyés avec l'outil (`input_examples`) SEULEMENT quand le mode
# strict est actif (`tools/api_definitions.py`). L'API refuse (400) un exemple invalide contre le
# schéma : ils sont donc VALIDÉS par un test contre le schéma local ET le schéma « compatible API »
# (`tests/test_tools_strict_q3a.py`), et leurs libellés sont compilés par `write_test_plan` contre le
# vrai catalogue de steps. Aucun nom d'instance client : ce sont des gabarits, pas des cas réels.
# Exemple 1 : cas nominal. Exemple 2 : une attente (« j'attends… ») placée APRÈS un `Alors` qui
# constate — l'attente ne remplace jamais le constat (Q1, D17) — et un doute déclaré.
INPUT_EXAMPLES = [
    {
        'title': "Ajout d'un article au panier",
        'scenarios': [{
            'name': "[Nominal] L'article ajouté est visible dans le panier",
            'requirement_ids': ['expected_result'],
            'steps': [
                {'keyword': 'Soit', 'text': "j'accède à la page d'accueil de l'application",
                 'evidence_ids': []},
                {'keyword': 'Quand', 'text': 'je clique sur le bouton "Ajouter au panier"',
                 'evidence_ids': ['observation-1']},
                {'keyword': 'Alors', 'text': 'l\'URL courante contient "/panier"',
                 'evidence_ids': ['observation-1']},
            ],
        }],
        HYPOTHESES_CLE: [],
    },
    {
        'title': "Envoi du formulaire de contact",
        'scenarios': [{
            'name': "[Nominal] Le formulaire valide est accepté",
            'requirement_ids': ['expected_result', 'step:1'],
            'steps': [
                {'keyword': 'Soit', 'text': "j'accède à la page d'accueil de l'application",
                 'evidence_ids': []},
                {'keyword': 'Quand',
                 'text': 'je remplis le formulaire de "/contact" avec des données valides',
                 'evidence_ids': ['observation-1']},
                {'keyword': 'Et', 'text': 'je clique sur le bouton "Envoyer"',
                 'evidence_ids': ['observation-1']},
                {'keyword': 'Alors', 'text': 'la page affiche le texte "Merci"',
                 'evidence_ids': []},
                {'keyword': 'Et', 'text': "j'attends la soumission du formulaire",
                 'evidence_ids': []},
            ],
        }],
        HYPOTHESES_CLE: [
            "Le texte exact du message de confirmation n'a pas été observé : l'assertion "
            "porte sur le mot « Merci » seulement.",
        ],
    },
]


def hypotheses_depuis_plan(technical_plan) -> list[str]:
    """Les hypothèses non vérifiées d'un `technical_plan` — dict, ou JSON tel que persisté en base.

    Pure et TOLÉRANTE : un plan ancien (sans le champ), vide, corrompu ou d'un autre type rend `[]`,
    jamais une exception — elle sert à l'affichage d'un cas déjà généré. Ne rend que des chaînes non
    vides, bornées comme à l'écriture (5 au plus), pour ne jamais afficher plus que ce que
    `write_test_plan` aurait accepté. Information pour l'humain seulement : voir `HYPOTHESES_CLE`.
    """
    if isinstance(technical_plan, str):
        try:
            technical_plan = json.loads(technical_plan) if technical_plan.strip() else {}
        except ValueError:
            return []
    if not isinstance(technical_plan, dict):
        return []
    brut = technical_plan.get(HYPOTHESES_CLE)
    if not isinstance(brut, list):
        return []
    propres = [t.strip() for t in brut if isinstance(t, str) and t.strip()]
    return propres[:HYPOTHESES_MAX]


def _refus_preuve_inconnue(citee: str, etape: str, connues: set) -> str:
    """Mesuré le 2026-10-22 (banc, conversations gardées) : « [plan : preuve inconnue] » ne disait ni laquelle ni quoi faire —
    l'IA le prenait pour un accord, écrivait le reste et s'arrêtait SANS test (2 générations sur 2 reproduites). Elle citait le
    relevé de l'exploration (« crawl-2026-10-22:/panier ») ou un essai (« essai-actions:/produits ») comme preuve."""
    valables = ", ".join(sorted(connues)) or "aucune pour l'instant (aucune page inspectée)"
    return (f"[write_test_plan] REFUSÉ — rien n'a été écrit. Preuve inconnue « {citee} » à l'étape « {etape} ». Une preuve est "
            "l'identifiant rendu par inspect_page_snapshot (« Preuve UI observation-N ») ; le relevé de l'exploration et les "
            f"essais n'en sont pas. Preuves valables : {valables}. Corrige evidence_ids (vide si aucune preuve) et renvoie le "
            "plan.")


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
        alors_non_assertifs = []
        for step in scenario['steps']:
            keyword, text = step['keyword'], step['text']
            values.append(text)
            if keyword not in ('Et', 'Mais'):
                effective = {'Soit': 'given', 'Quand': 'when', 'Alors': 'then'}[keyword]
            if not effective:
                return ToolOutcome('[plan : première étape sans type]', ok=False)
            inconnues = [e for e in step['evidence_ids'] if e not in known]
            if inconnues:
                return ToolOutcome(_refus_preuve_inconnue(inconnues[0], text, known), ok=False)
            found = False
            matched = None
            for shared in ctx.shared_steps:
                if shared.keyword not in (effective, 'step'):
                    continue
                try:
                    found = parse.parse(shared.label, text) is not None
                except (ValueError, KeyError, TypeError):
                    continue
                if found:
                    matched = shared
                    break
            if not found:
                return ToolOutcome('[plan : étape hors catalogue ; utiliser une extension explicite]', ok=False)
            if effective == 'then':
                # Q1 (D17) : un « Alors » n'est une assertion que si le step partagé apparié peut
                # constater. Une attente (« j'attends la soumission du formulaire ») ne prouve rien.
                if getattr(matched, 'asserte', True):
                    assertion = True
                else:
                    alors_non_assertifs.append(text)
            lines.append(f'    {keyword} {text}')
        if not assertion:
            if alors_non_assertifs:
                return ToolOutcome(
                    f"[plan : scénario « {scenario['name']} » sans assertion — "
                    f"« {alors_non_assertifs[0]} » est une attente ou une navigation, elle ne vérifie rien ; "
                    "ajoute un « Alors » du catalogue qui constate (présence, texte, valeur…)]", ok=False)
            return ToolOutcome('[plan : résultat attendu sans assertion]', ok=False)
    if covered != set(ctx.requirements):
        return ToolOutcome('[plan : exigences métier non couvertes]', ok=False)
    if any('\n' in v or '\r' in v for v in values):
        return ToolOutcome('[plan : chaque libellé doit tenir sur une ligne]', ok=False)
    outcome = write_feature_file(ctx, '\n'.join(lines) + '\n')
    if outcome.ok:
        ctx.technical_plan = copy.deepcopy(plan)
    return outcome
