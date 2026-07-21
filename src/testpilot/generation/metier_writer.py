"""Passe 4a — le DOCUMENT MÉTIER d'un cas, écrit avant tout code technique.

Décision `0022` n°5 : la génération se fait en **deux passes**, et la première produit ce qu'un
humain lit — titre, préconditions, étapes numérotées, résultat attendu. Un humain valide ce
document **avant** que le Gherkin ne soit écrit : on ne paie plus du code technique pour une
intention fausse. C'est aussi ce qui remplit enfin les champs créés par la migration 14, restés
vides jusqu'ici (l'écran les *dérivait* du Gherkin, faute de mieux — un affichage qui avait l'air
rédigé sans l'être).

Cette passe est **délibérément séparée de l'analyse** (`SpecAnalyzer`) : l'analyse extrait de la
matière technique pour l'agent (modèles, routes, sélecteurs) ; ici on écrit du français destiné à
un lecteur humain. Les fusionner produirait un document contaminé par du vocabulaire technique —
exactement ce que le §5 du brief réserve au mode dev.
"""

from __future__ import annotations

import json
import logging
import re

from testpilot import config
from testpilot.analysis.plan import TestPlan
from testpilot.llm.adapter import LLMAdapter

logger = logging.getLogger(__name__)

_SYSTEM = ("Tu rédiges des cas de test fonctionnels pour des testeurs métier. "
           "Tu écris en français clair, jamais en langage technique. "
           "Réponds uniquement en JSON valide.")

# Angles connus. `angle` reste une ÉTIQUETTE LIBRE en base (décision 0022 n°9) : cette liste
# guide le modèle sans l'enfermer — une valeur hors liste est acceptée telle quelle.
_ANGLES = ("nominal", "erreur", "limite", "autre")

# ⚠️ Un titre ne doit JAMAIS porter son angle en préfixe (décision 0022 n°3, rappelée au backlog
# avec un exemple TestRail réel). `[NOMINAL] …` est un artefact du prompt « triptyque » d'avant :
# l'angle est une métadonnée, pas une partie du titre lu par un humain.
_PREFIXE_ANGLE = re.compile(r"^\s*[\[\(]?\s*(nominal|erreur|limite|autre|cas\s+\w+)\s*[\]\)]?\s*[:\-–]?\s*",
                            re.IGNORECASE)

# Mots-clés Gherkin : interdits dans les ÉTAPES métier (consigne du porteur — pas de
# Given/When/Then à l'écran). On les retire au lieu de rejeter la réponse : le contenu de l'étape
# reste bon, seul son habillage est fautif.
# `que`/`qu'` est consommé avec le mot-clé : « Étant donné QUE j'ouvre… » doit donner
# « j'ouvre… », pas « que j'ouvre… » — sinon l'étape reste une subordonnée sans principale.
_GHERKIN_KW = re.compile(
    r"^\s*(soit|étant donné(?:e|s)?|etant donné(?:e|s)?|quand|alors|et|mais|"
    r"given|when|then|and|but)\b\s*(qu[e']\s*)?", re.IGNORECASE)

# Numérotation manuelle (« 3. », « 2) »). Rendue par l'interface : la laisser l'afficherait deux
# fois et casserait la renumérotation à l'insertion d'une étape.
_NUMEROTATION = re.compile(r"^\s*\d+\s*[.)]\s*")


class MetierDraft:
    """Le document métier proposé pour UN cas (un angle). Toujours éditable par l'humain."""

    def __init__(self, *, title: str = "", preconditions: str = "",
                 steps: list[str] | None = None, expected_result: str = "", angle: str = ""):
        self.title = title
        self.preconditions = preconditions
        self.steps = steps or []
        self.expected_result = expected_result
        self.angle = angle

    def as_dict(self) -> dict:
        return {"title": self.title, "preconditions": self.preconditions,
                "steps": list(self.steps), "expected_result": self.expected_result,
                "angle": self.angle}

    @property
    def complete(self) -> bool:
        """Titre + étapes + résultat attendu sont OBLIGATOIRES (décision `0022` n°3.c).

        Un cas sans ces trois-là ne teste rien — c'est le « cas fantôme » que `0006` refusait.
        Les préconditions et l'angle restent facultatifs.
        """
        return bool(self.title.strip() and self.steps and self.expected_result.strip())


def _clean_title(raw: str) -> str:
    """Retire un éventuel préfixe d'angle. Le titre est une PHRASE MÉTIER, rien d'autre."""
    return _PREFIXE_ANGLE.sub("", str(raw or "")).strip()


def _clean_step(raw: str) -> str:
    """Retire la numérotation manuelle PUIS un éventuel mot-clé Gherkin en tête d'étape.

    ⚠️ L'ordre compte : « 3. Alors j'envoie » garde son « Alors » si on cherche le mot-clé
    d'abord, puisqu'il n'est alors pas en tête de chaîne. Le numéro part en premier.
    """
    s = _NUMEROTATION.sub("", str(raw or "").strip())
    return _GHERKIN_KW.sub("", s).strip()


def _build_prompt(plan: TestPlan, angle: str) -> str:
    return f"""Rédige LE DOCUMENT MÉTIER d'un cas de test, à partir de cette spécification.

SPÉCIFICATION :
{plan.raw_spec}

ANGLE À COUVRIR : {angle}

Réponds en JSON :
{{
  "title": "phrase métier décrivant ce qui est vérifié",
  "preconditions": "le contexte nécessaire avant de commencer, en langage clair (ou \\"\\")",
  "steps": ["Ouvrir …", "Saisir …", "Cliquer …"],
  "expected_result": "UNE phrase de verdict global",
  "angle": "{angle}"
}}

RÈGLES IMPÉRATIVES :
1. Le TITRE est une phrase métier qui dit ce qui est vérifié.
   JAMAIS de préfixe d'angle : « [NOMINAL] … » est INTERDIT.
   Bon : « Réception et délivrance d'une commande ».
2. Les ÉTAPES sont des actions numérotées simples, à la suite.
   AUCUN mot-clé Gherkin (Soit / Étant donné / Quand / Alors / Given / When / Then).
   Ne numérote pas toi-même : écris juste l'action.
3. Le RÉSULTAT ATTENDU est UNE seule phrase de verdict global pour tout le cas,
   pas un résultat par étape.
4. Écris pour un testeur MÉTIER : pas de sélecteur CSS, pas de nom de modèle technique,
   pas de route. Ce document sera lu par quelqu'un qui ne code pas.
5. Titre, étapes et résultat attendu sont OBLIGATOIRES et ne peuvent pas être vides."""


def propose_metier(plan: TestPlan, *, angle: str = "nominal", llm: LLMAdapter | None = None,
                   cost_tracker=None, model: str = "") -> MetierDraft:
    """Un appel LLM → le document métier d'UN cas (un angle). Ne persiste rien.

    Aucun contenu n'est fabriqué en cas d'échec : si le modèle ne rend pas de JSON exploitable,
    on renvoie un brouillon VIDE (`complete` faux) et l'appelant le signale. Inventer un titre
    plausible donnerait à un document non rédigé l'air d'être rédigé — le même piège que
    l'arbitrage A.1 de la migration 14, qui a refusé de dériver le métier du Gherkin.
    """
    llm = llm or LLMAdapter()
    raw = llm.call_simple(
        system_prompt=_SYSTEM,
        user_content=_build_prompt(plan, angle),
        model=model or config.MODEL_FAST,
        max_tokens=2000,
        cost_tracker=cost_tracker,
        label="metier",
    )
    match = re.search(r"\{.*\}", raw or "", re.DOTALL)
    if not match:
        logger.warning("[metier] aucune réponse JSON exploitable — brouillon vide")
        return MetierDraft(angle=angle)
    try:
        data = json.loads(match.group(0))
    except Exception:
        logger.warning("[metier] JSON illisible — brouillon vide")
        return MetierDraft(angle=angle)

    steps = [_clean_step(s) for s in (data.get("steps") or []) if str(s or "").strip()]
    return MetierDraft(
        title=_clean_title(data.get("title", "")),
        preconditions=str(data.get("preconditions", "") or "").strip(),
        steps=[s for s in steps if s],
        expected_result=str(data.get("expected_result", "") or "").strip(),
        angle=str(data.get("angle", "") or angle).strip(),
    )
