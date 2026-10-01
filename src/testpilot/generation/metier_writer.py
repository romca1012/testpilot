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
        # F26(b), 2026-10-01 : sortie structurée plutôt qu'une règle en prose (qui a été mesurée
        # insuffisante — voir `verifier_dependance_inter_cas`). L'API ne supporte PAS les
        # contraintes conditionnelles (if/then/else, dependentRequired) sur le schéma JSON
        # (vérifié sur platform.claude.com/docs/build-with-claude/structured-outputs avant
        # d'écrire ce schéma) : `etat_a_creer_par_ce_cas` est donc TOUJOURS une chaîne (vide si
        # non applicable), et c'est `verifier_dependance_inter_cas` qui applique la vraie
        # condition, en Python, déterministe — jamais un jugement du modèle qui se fait confiance
        # à lui-même.
        "depend_dun_autre_cas_du_groupe": {
            "type": "boolean",
            "description": "Vrai si une précondition de ce cas suppose un état (un "
                           "enregistrement, une donnée) qui n'existe QUE parce qu'un AUTRE cas "
                           "de la même spécification l'a créé. Faux si ce cas peut tourner seul, "
                           "sans qu'aucun autre cas n'ait été exécuté avant."},
        "etat_a_creer_par_ce_cas": {
            "type": "string",
            "description": "Si le champ précédent est vrai : une phrase qui dit comment CE cas "
                           "crée lui-même l'état nécessaire — à intégrer dans préconditions et "
                           "étapes, pas un champ décoratif à part. Si le champ précédent est "
                           "faux, chaîne vide."},
    },
    "required": ["title", "preconditions", "steps", "expected_result",
                "depend_dun_autre_cas_du_groupe", "etat_a_creer_par_ce_cas"],
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
    """Le document métier proposé pour UN cas. Toujours éditable par l'humain.

    `depend_dun_autre_cas_du_groupe` / `etat_a_creer_par_ce_cas` (F26, 2026-10-01) : sortie
    structurée, d'abord utilisée par `verifier_dependance_inter_cas` (contrôle à la relecture
    métier). Portées dans `as_dict()` depuis la migration 58 : C138 (rejeu réel, 2026-10-01) a
    montré que ce contrôle seul ne suffit pas — un cas peut passer la relecture métier puis,
    lors de l'écriture du Gherkin (étape séparée, parfois différée, round-trip par la base), finir
    par référencer un enregistrement réel plutôt que de créer le sien. Sans persistance, le signal
    ne survivait pas à ce round-trip et n'atteignait jamais `write_feature_file`, seul capable de
    refuser la référence AU MOMENT où l'agent l'écrit (`tools/write.py`,
    `verifier_entite_a_creer`)."""

    def __init__(self, *, title: str = "", preconditions: str = "",
                 steps: list[str] | None = None, expected_result: str = "",
                 depend_dun_autre_cas_du_groupe: bool = False,
                 etat_a_creer_par_ce_cas: str = ""):
        self.title = title
        self.preconditions = preconditions
        self.steps = steps or []
        self.expected_result = expected_result
        self.depend_dun_autre_cas_du_groupe = depend_dun_autre_cas_du_groupe
        self.etat_a_creer_par_ce_cas = etat_a_creer_par_ce_cas

    def as_dict(self) -> dict:
        return {"title": self.title, "preconditions": self.preconditions,
                "steps": list(self.steps), "expected_result": self.expected_result,
                "depend_dun_autre_cas_du_groupe": self.depend_dun_autre_cas_du_groupe,
                "etat_a_creer_par_ce_cas": self.etat_a_creer_par_ce_cas}

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
  "expected_result": "UNE phrase de verdict global",
  "depend_dun_autre_cas_du_groupe": true ou false,
  "etat_a_creer_par_ce_cas": "si le champ précédent est vrai, comment CE cas crée l'état lui-même (sinon \\"\\")"
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
5. Titre, étapes et résultat attendu sont OBLIGATOIRES et ne peuvent pas être vides.
6. Chaque scénario Behave est autonome et ne partage jamais d'état avec un autre scénario — il
   n'a accès à rien de ce qu'un AUTRE scénario a fait, même de la même spécification. Si une
   précondition de la spécification décrit un état qui, en pratique, n'existe que parce qu'un
   AUTRE cas de cette spécification l'a produit : réponds `depend_dun_autre_cas_du_groupe: true`
   et remplis `etat_a_creer_par_ce_cas` avec la phrase d'action que TES PROPRES préconditions et
   étapes doivent alors intégrer pour créer cet état elles-mêmes, au lieu de le supposer
   préexistant. Sinon, `depend_dun_autre_cas_du_groupe: false` et `etat_a_creer_par_ce_cas: ""`.
   Exemple (F26, 2026-10-01, Portail Sapian - Integration) : la spécification dit « un équipement
   créé par le run » comme précondition d'un cas d'affectation — aucun scénario Behave ne peut
   garantir qu'un AUTRE cas a tourné avant lui lors d'une exécution ultérieure isolée. Le cas
   d'affectation doit donc déclarer `depend_dun_autre_cas_du_groupe: true` et répondre
   `etat_a_creer_par_ce_cas: "créer un équipement avec une référence unique avant de l'affecter"`
   — puis intégrer cette création dans ses PROPRES préconditions et étapes."""


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
        depend_dun_autre_cas_du_groupe=bool(data.get("depend_dun_autre_cas_du_groupe", False)),
        etat_a_creer_par_ce_cas=str(data.get("etat_a_creer_par_ce_cas", "") or "").strip(),
    )


# F26(b) — seuil mesuré le 2026-10-01, pas choisi sans preuve : sur 4 paraphrases construites à la
# main qui gardent le MÊME sens passif que la précondition d'origine (juste des mots différents,
# ex. « lors du test précédent » → « par un cas antérieur »), le ratio `SequenceMatcher` est TOUJOURS
# entre 0.69 et 0.87 ; sur 2 réponses correctes (une action concrète réellement différente), il est
# TOUJOURS entre 0.34 et 0.40. Écart net, aucun chevauchement sur cet échantillon — 0.6 prend la
# marge médiane. Mesuré sur 6 exemples construits, pas une validation statistique exhaustive : à
# ajuster si des faux positifs/négatifs réels apparaissent en usage.
_SEUIL_SIMILARITE_ETAT_PRECONDITION = 0.6


def verifier_dependance_inter_cas(draft: MetierDraft) -> str | None:
    """`None` si le cas est cohérent, sinon le message de rejet (JAMAIS une approbation silencieuse
    — F26(b), 2026-10-01). Contrôle 100% déterministe : aucun jugement du modèle ici, seulement ce
    que `propose_metier` a répondu dans son propre JSON structuré."""
    if not draft.depend_dun_autre_cas_du_groupe:
        return None
    etat = draft.etat_a_creer_par_ce_cas.strip()
    if not etat:
        return ("dépend d'un autre cas du groupe (« depend_dun_autre_cas_du_groupe ») mais ne "
                "décrit aucun état à créer lui-même (« etat_a_creer_par_ce_cas » vide)")
    from difflib import SequenceMatcher
    ratio = SequenceMatcher(None, etat.lower(), draft.preconditions.strip().lower()).ratio()
    if ratio > _SEUIL_SIMILARITE_ETAT_PRECONDITION:
        return (f"« état à créer » ({ratio:.2f} de similarité avec la précondition d'origine) "
                "reformule la précondition au lieu de décrire une action de création propre à ce cas")
    return None
