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

⚠️ **Délibérément SANS citation-ou-retrait (backlog 1.2), à la différence de `spec_analyzer.py`
et `decoupage.py`.** Deux raisons, pas un oubli :
1. Ce document est une ÉLABORATION en étapes concrètes d'une capacité décrite en général par la
   spec ("l'utilisateur peut réinitialiser son mot de passe" → "1. Cliquer sur…"), pas une
   citation par nature — exiger un extrait mot pour mot par étape rejetterait des documents
   parfaitement fidèles, exactement le faux positif bloquant que ce projet refuse partout
   ailleurs (`check_step_soumission`, `smoke_check` : détective, jamais bloquant).
2. Cette passe est déjà protégée par le garde-fou le plus fort du dépôt : AUCUN coût technique
   n'est engagé avant qu'un humain valide ce document (décision `0022` n°5). Une user story
   hallucinée ne peut de toute façon plus l'atteindre — `decoupage.propose_decoupage` l'aurait
   déjà écartée faute de citation vérifiable.
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

# Schéma des SORTIES STRUCTURÉES (§2bis A2) : quand le modèle les honore, l'API garantit un JSON
# conforme — plus de regex `{…}` + `json.loads` qui échoue sur une virgule en trop ou du texte
# autour. `additionalProperties: false` + tous `required` sont imposés par la fonctionnalité.
_METIER_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "preconditions": {"type": "string"},
        "steps": {"type": "array", "items": {"type": "string"}},
        "expected_result": {"type": "string"},
    },
    "required": ["title", "preconditions", "steps", "expected_result"],
    "additionalProperties": False,
}


def _data_metier(llm, plan: TestPlan, model: str, cost_tracker, brief: str = "") -> dict:
    """Le dict du document métier. Sorties structurées si l'adaptateur les expose (`call_json`),
    sinon parsing tolérant — ce qui garde inchangés les adaptateurs minimaux (fakes de test).

    ⚠️ **`cached_prefix` = la partie STABLE, `user_content` = le cas précis.** `propose_metier`
    est appelé une fois PAR CAS pour la MÊME spec (`decoupage` en découpe N) — la spec ne change
    pas d'un cas à l'autre, seul `brief` change. Voir `adapter._contenu_utilisateur`.
    """
    stable = _build_prompt(plan)
    variable = _consigne_cas(brief)
    modele = model or config.MODEL_FAST
    if hasattr(llm, "call_json"):
        return llm.call_json(system_prompt=_SYSTEM, cached_prefix=stable, user_content=variable,
                             schema=_METIER_SCHEMA, model=modele, max_tokens=2000,
                             cost_tracker=cost_tracker, label="metier") or {}
    raw = llm.call_simple(system_prompt=_SYSTEM, cached_prefix=stable, user_content=variable,
                          model=modele, max_tokens=2000, cost_tracker=cost_tracker, label="metier")
    match = re.search(r"\{.*\}", raw or "", re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except Exception:
        return {}

# ⚠️ Un titre ne doit JAMAIS porter une étiquette en préfixe (décision 0022 n°3, avec un exemple
# TestRail réel). `[NOMINAL] …` est un artefact du prompt « triptyque » d'avant : un titre est une
# PHRASE MÉTIER, pas une case de classement. Le nettoyage SURVIT au retrait du champ `angle`
# (migration 26) : le modèle a appris ces préfixes sur du corpus, il les propose encore alors que
# plus rien ne les lui demande.
_PREFIXE_CLASSEMENT = re.compile(
    r"^\s*[\[\(]?\s*(nominal|erreur|limite|autre|cas\s+\w+)\s*[\]\)]?\s*[:\-–]?\s*",
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
    """Le document métier proposé pour UN cas. Toujours éditable par l'humain."""

    def __init__(self, *, title: str = "", preconditions: str = "",
                 steps: list[str] | None = None, expected_result: str = ""):
        self.title = title
        self.preconditions = preconditions
        self.steps = steps or []
        self.expected_result = expected_result

    def as_dict(self) -> dict:
        return {"title": self.title, "preconditions": self.preconditions,
                "steps": list(self.steps), "expected_result": self.expected_result}

    @property
    def complete(self) -> bool:
        """Titre + étapes + résultat attendu sont OBLIGATOIRES (décision `0022` n°3.c).

        Un cas sans ces trois-là ne teste rien — c'est le « cas fantôme » que `0006` refusait.
        Les préconditions restent facultatives.
        """
        return bool(self.title.strip() and self.steps and self.expected_result.strip())


def _clean_title(raw: str) -> str:
    """Retire un éventuel préfixe de classement. Le titre est une PHRASE MÉTIER, rien d'autre."""
    return _PREFIXE_CLASSEMENT.sub("", str(raw or "")).strip()


def _clean_step(raw: str) -> str:
    """Retire la numérotation manuelle PUIS un éventuel mot-clé Gherkin en tête d'étape.

    ⚠️ L'ordre compte : « 3. Alors j'envoie » garde son « Alors » si on cherche le mot-clé
    d'abord, puisqu'il n'est alors pas en tête de chaîne. Le numéro part en premier.
    """
    s = _NUMEROTATION.sub("", str(raw or "").strip())
    return _GHERKIN_KW.sub("", s).strip()


def _build_prompt(plan: TestPlan) -> str:
    """La partie STABLE du prompt métier — indépendante du cas précis (`brief`).

    ⚠️ **Ordre délibéré pour le cache de prompt (audit coûts, 2026-09-16).** Tout ce qui NE
    dépend PAS de `brief` (la spec, le format JSON, les règles) vit ici, en un seul bloc
    contigu — c'est ce bloc que `_data_metier` marque `cache_control: ephemeral`. Le cas précis
    (`_consigne_cas`, ci-dessous) vient TOUJOURS après, jamais mélangé dedans : le moindre octet
    variable AVANT la fin du préfixe cassait le cache pour tout le monde.
    """
    return f"""Rédige LE DOCUMENT MÉTIER d'un cas de test, à partir de cette spécification.

SPÉCIFICATION :
{plan.raw_spec}

Réponds en JSON :
{{
  "title": "phrase métier décrivant ce qui est vérifié",
  "preconditions": "le contexte nécessaire avant de commencer, en langage clair (ou \\"\\")",
  "steps": ["Ouvrir …", "Saisir …", "Cliquer …"],
  "expected_result": "UNE phrase de verdict global"
}}

RÈGLES IMPÉRATIVES :
1. Le TITRE est une phrase métier qui dit ce qui est vérifié.
   JAMAIS de préfixe de classement : « [NOMINAL] … » est INTERDIT.
   Bon : « Réception et délivrance d'une commande ».
2. Les ÉTAPES sont des actions numérotées simples, à la suite.
   AUCUN mot-clé Gherkin (Soit / Étant donné / Quand / Alors / Given / When / Then).
   Ne numérote pas toi-même : écris juste l'action.
3. Le RÉSULTAT ATTENDU est UNE seule phrase de verdict global pour tout le cas,
   pas un résultat par étape.
4. Écris pour un testeur MÉTIER : pas de sélecteur CSS, pas de nom de modèle technique,
   pas de route. Ce document sera lu par quelqu'un qui ne code pas.
5. Titre, étapes et résultat attendu sont OBLIGATOIRES et ne peuvent pas être vides."""


def _consigne_cas(brief: str = "") -> str:
    """La partie VARIABLE du prompt — CE CAS précis, jamais mise en cache.

    `brief` vient du découpage (`decoupage.propose_decoupage`) : il dit CE CAS précis à écrire
    dans le contexte de la spécification entière — il s'AJOUTE au texte complet (`_build_prompt`),
    il ne le remplace jamais (l'agent a besoin de tout le contexte pour rédiger un document
    cohérent). Vide (défaut) : un seul document pour toute la spec — le chemin CLI / cas manuel.
    """
    if not brief:
        return ""
    return f"""CE CAS PRÉCIS :
{brief}

Rédige UNIQUEMENT ce cas — pas les autres cas de la même spécification, ils sont rédigés
séparément. Le brief ci-dessus dit ce qui le distingue des autres ; le reste de la spécification
est le contexte dans lequel il s'inscrit."""


def propose_metier(plan: TestPlan, *, llm: LLMAdapter | None = None,
                   cost_tracker=None, model: str = "", brief: str = "") -> MetierDraft:
    """Un appel LLM → le document métier d'UN cas. Ne persiste rien.

    `brief` — vient du découpage (§9a) : quel cas précis rédiger dans cette spécification, parmi
    tous ceux planifiés pour la même user story. Vide (défaut) : comportement d'avant, un seul
    document pour toute la spec — c'est le chemin CLI et l'automatisation d'un cas manuel.

    Aucun contenu n'est fabriqué en cas d'échec : si le modèle ne rend pas de JSON exploitable,
    on renvoie un brouillon VIDE (`complete` faux) et l'appelant le signale. Inventer un titre
    plausible donnerait à un document non rédigé l'air d'être rédigé — le même piège que
    l'arbitrage A.1 de la migration 14, qui a refusé de dériver le métier du Gherkin.
    """
    llm = llm or LLMAdapter()
    data = _data_metier(llm, plan, model, cost_tracker, brief)
    if not data:
        logger.warning("[metier] aucune donnée JSON exploitable — brouillon vide")
        return MetierDraft()

    steps = [_clean_step(s) for s in (data.get("steps") or []) if str(s or "").strip()]
    return MetierDraft(
        title=_clean_title(data.get("title", "")),
        preconditions=str(data.get("preconditions", "") or "").strip(),
        steps=[s for s in steps if s],
        expected_result=str(data.get("expected_result", "") or "").strip(),
    )
