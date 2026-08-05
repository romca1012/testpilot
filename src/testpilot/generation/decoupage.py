"""Passe 4a-bis — le DÉCOUPAGE d'une spécification en user stories, puis en cas de test.

Avant ce module, une génération produisait UN SEUL cas, sans lien avec les user stories de la
spécification. Ici : identifier les **user stories** décrites, et pour chacune planifier
l'**ensemble minimal de cas** nécessaire pour la couvrir — un nombre **variable, jamais fixé
d'avance**.

⚠️ **« Variable » ne veut pas dire « maximal ».** Le prompt cherche explicitement le PLUS PETIT
ensemble de cas qui couvre toute la spécification, sans redondance entre eux — *« un cas de test
qui peut être validé par un autre n'est pas intéressant »* (arbitrage du porteur, 2026-08-05). On
ne demande donc jamais « énumère tout ce qui est possible ».

Ce module ne fait que PLANIFIER (titre + brief par cas) — il ne rédige aucun document métier.
C'est `metier_writer.propose_metier(plan, brief=...)` qui rédige chaque cas planifié ici, un par
un, en réutilisant le pipeline existant tel quel (rien n'est réinventé, juste répété en boucle).
"""

from __future__ import annotations

import json
import logging
import re

from testpilot import config
from testpilot.analysis.plan import TestPlan
from testpilot.llm.adapter import LLMAdapter

logger = logging.getLogger(__name__)

_SYSTEM = ("Tu découpes une spécification fonctionnelle en user stories, puis en cas de test "
           "de test nécessaires et suffisants pour couvrir chacune. Tu écris en français clair. "
           "Réponds uniquement en JSON valide.")

_CASE_BRIEF_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "brief": {"type": "string"},
    },
    "required": ["title", "brief"],
    "additionalProperties": False,
}

_STORY_SCHEMA = {
    "type": "object",
    "properties": {
        "user_story": {"type": "string"},
        "cases": {"type": "array", "items": _CASE_BRIEF_SCHEMA},
    },
    "required": ["user_story", "cases"],
    "additionalProperties": False,
}

_DECOUPAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "stories": {"type": "array", "items": _STORY_SCHEMA},
    },
    "required": ["stories"],
    "additionalProperties": False,
}


class CaseBrief:
    """UN cas planifié : juste de quoi orienter la passe métier qui le rédigera vraiment."""

    def __init__(self, *, title: str = "", brief: str = ""):
        self.title = title
        self.brief = brief

    def as_dict(self) -> dict:
        return {"title": self.title, "brief": self.brief}


class StoryPlan:
    """UNE user story et l'ensemble minimal de cas planifiés pour la couvrir."""

    def __init__(self, *, user_story: str = "", cases: list[CaseBrief] | None = None):
        self.user_story = user_story
        self.cases = cases or []

    def as_dict(self) -> dict:
        return {"user_story": self.user_story, "cases": [c.as_dict() for c in self.cases]}


def _build_prompt(plan: TestPlan) -> str:
    return f"""Découpe cette spécification en user stories, puis planifie les cas de test.

SPÉCIFICATION :
{plan.raw_spec}

Pour CHAQUE user story identifiée, trouve LE PLUS PETIT ENSEMBLE DE CAS qui, ensemble, couvrent
TOUT ce que la spécification décrit pour cette story — SANS REDONDANCE entre eux. Un cas de test
qui peut être validé par un autre cas de la même story n'est PAS intéressant : ne le propose pas.

N'énumère PAS « tout ce qui est possible » (toutes les variantes imaginables, tous les cas
limites concevables) : chaque cas proposé doit apporter une couverture que les AUTRES cas de la
même story n'apportent pas déjà. Une story simple peut n'avoir besoin que d'UN seul cas ; une
story qui décrit plusieurs comportements distincts (succès, refus, cas limite VRAIMENT différent)
en a besoin de plusieurs. Le nombre n'est jamais fixé d'avance : il dépend de ce que CETTE
spécification décrit.

Réponds en JSON :
{{
  "stories": [
    {{
      "user_story": "nom de la user story, en langage métier",
      "cases": [
        {{"title": "phrase métier décrivant ce que CE cas vérifie",
          "brief": "en une ou deux phrases, ce qui distingue ce cas des autres de la même story"}}
      ]
    }}
  ]
}}

RÈGLES IMPÉRATIVES :
1. Chaque user story vient de la spécification — n'en invente aucune qu'elle ne décrit pas.
2. Le TITRE de chaque cas est une phrase métier, jamais un préfixe de classement
   (« [NOMINAL] … » est INTERDIT).
3. Le BRIEF dit à qui rédigera ce cas ce qui le distingue des autres — pas un résumé de la
   spécification entière, juste l'angle propre à ce cas.
4. N'omets aucune user story de la spécification, mais ne dépasse jamais le nécessaire pour la
   couvrir."""


def _data_decoupage(llm, plan: TestPlan, model: str, cost_tracker) -> dict:
    """Le dict du découpage. Sorties structurées si l'adaptateur les expose (`call_json`),
    sinon parsing tolérant — ce qui garde inchangés les adaptateurs minimaux (fakes de test)."""
    user = _build_prompt(plan)
    modele = model or config.MODEL_FAST
    if hasattr(llm, "call_json"):
        return llm.call_json(system_prompt=_SYSTEM, user_content=user, schema=_DECOUPAGE_SCHEMA,
                             model=modele, max_tokens=4000, cost_tracker=cost_tracker,
                             label="decoupage") or {}
    raw = llm.call_simple(system_prompt=_SYSTEM, user_content=user, model=modele,
                          max_tokens=4000, cost_tracker=cost_tracker, label="decoupage")
    match = re.search(r"\{.*\}", raw or "", re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except Exception:
        return {}


def propose_decoupage(plan: TestPlan, *, llm: LLMAdapter | None = None,
                      cost_tracker=None, model: str = "") -> list[StoryPlan]:
    """Un appel LLM → les user stories de la spec, chacune avec l'ensemble minimal de cas
    planifiés pour la couvrir. Ne persiste rien, ne rédige aucun document métier.

    Une user story sans aucun cas exploitable, ou un titre de cas vide, est éliminée en silence
    plutôt que de fabriquer un plan à trous — la même prudence que `metier_writer.propose_metier`
    pour un document illisible.
    """
    llm = llm or LLMAdapter()
    data = _data_decoupage(llm, plan, model, cost_tracker)
    stories_raw = data.get("stories") or []
    stories: list[StoryPlan] = []
    for s in stories_raw:
        user_story = str((s or {}).get("user_story", "")).strip()
        cases = [
            CaseBrief(title=str(c.get("title", "")).strip(), brief=str(c.get("brief", "")).strip())
            for c in ((s or {}).get("cases") or [])
            if str(c.get("title", "")).strip()
        ]
        if user_story and cases:
            stories.append(StoryPlan(user_story=user_story, cases=cases))
    if not stories:
        logger.warning("[decoupage] aucune user story exploitable — plan vide")
    return stories
