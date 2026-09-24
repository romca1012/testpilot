"""Le commentaire qui accompagne CHAQUE résultat automatique (§A du plan « fiabiliser le verdict
automatique », 2026-08-06) — la même preuve de traçabilité qu'un humain écrit à la main pour un
résultat manuel (`AddResultDialog.vue`), mais produite par la machine, pour TOUS les statuts.

Décision du porteur, verbatim : « il est mieux de le faire sur tout les statuts, cela garantit une
possible vérification humaine d'une exécution automatisée grâce à une IA » — donc aucune
distinction entre passed/failed/blocked/retest : chaque verdict reçoit son explication.

Patron répliqué de `generation/metier_writer.py::propose_metier` (même discipline : système-prompt
en français clair pour un lecteur non technique, `call_json`, `config.MODEL_FAST`, coût mesuré par
delta sur un `CostTracker` — cf. `generation/repair_agent.py::propose_fix`).
"""

from __future__ import annotations

import json
import logging
import re

from testpilot import config
from testpilot.guardrails.cost_tracker import CostTracker
from testpilot.llm.adapter import LLMAdapter
from testpilot.verdict import defect_taxonomy as dt
from testpilot.verdict.status import EXEC_BLOCKED, GROUND_TRUTH_UI_ONLY, CaseVerdict

logger = logging.getLogger(__name__)

# Note DÉTERMINISTE, jamais confiée au LLM (étape 2.2 du plan de consolidation, 2026-09-15 — audit
# « Le pari Mabl/Testim ») : la fiabilité d'un verdict générique est un FAIT structurel du
# connecteur (`GenericWebConnector` n'a aucune méthode RPC — `connectors/generic_web.py`), pas une
# nuance à faire deviner à un modèle de langage. Ajoutée APRÈS coup au texte de l'IA, jamais dans
# le prompt : une IA qui « oublierait » de le mentionner laisserait croire à une vérification aussi
# solide qu'un cas Odoo, exactement la confusion que ce champ existe pour éviter.
_NOTE_UI_ONLY = (
    "Vérification limitée à ce que l'écran affiche : cette application ne permet pas de "
    "recouper le résultat avec une donnée de référence côté serveur.")

# Note DÉTERMINISTE (lot 02, D1), jamais confiée au LLM — même principe que `_NOTE_UI_ONLY` : « bloqué »
# ne dit RIEN de l'application. Une IA qui l'oublierait ou l'enroberait laisserait croire à un défaut.
_NOTE_BLOQUE = (
    "Ce test n'a pas pu être joué : un prérequis de l'environnement n'est pas rempli (par exemple "
    "un module non installé, une connexion impossible ou des données déjà présentes). Ce n'est "
    "pas un défaut de l'application ni du test — il faut préparer l'environnement, puis relancer.")

# Note DÉTERMINISTE (lot 03, D3) : un test « vert » sans aucune vérification exécutée ne prouve rien.
_NOTE_AUCUN_CONSTAT = (
    "Ce test est allé au bout, mais aucune vérification ne s'est exécutée : rien n'a été constaté sur "
    "l'application. Ce n'est pas une preuve qu'elle est conforme — le test est à revoir, puis à relancer.")

_SYSTEM = ("Tu expliques le résultat d'un test automatique à un lecteur qui ne code pas. "
           "Tu écris en français clair, jamais en langage technique : aucun nom de classe "
           "d'erreur, aucun sélecteur, aucune trace de pile, aucun terme de code. Une ou deux "
           "phrases factuelles qui disent CE QUI a été vérifié et POURQUOI le résultat est "
           "celui-là. "
           "⚠️ Base-toi UNIQUEMENT sur « Ce que le test a réellement mesuré » quand cette ligne "
           "est fournie pour un scénario — jamais sur ce que son TITRE semble annoncer. Le titre "
           "dit l'INTENTION du scénario, pas ce qui s'est passé : un titre « connexion refusée » "
           "qui échoue ne veut pas forcément dire que l'application a accepté la connexion — "
           "lis le détail mesuré pour savoir. Si aucun détail réel n'est fourni, reste prudent "
           "et général plutôt que d'inventer une cause plausible mais fausse. "
           "Réponds uniquement en JSON valide.")

_SCHEMA = {
    "type": "object",
    "properties": {"explication": {"type": "string"}, "citation": {"type": "string"}},
    "required": ["explication", "citation"],
    "additionalProperties": False,
}

# Repli SÛR (backlog 1.3) : jamais un récit inventé, quand la citation attendue est absente ou
# introuvable dans ce qui a été réellement mesuré — même principe que la note UI_ONLY ci-dessus,
# transposé de « fait structurel » à « affirmation non vérifiable ».
_EXPLICATION_REPLI = (
    "Un résultat a été mesuré pour ce test, mais l'explication automatique n'a pas pu être "
    "confirmée par rapport au détail réellement observé — voir le détail technique du scénario "
    "pour l'analyse exacte.")

# Même borne que `run_service._persist` (`error_summary=(s.error or "")[:500]`) — assez pour
# porter une comparaison attendu/obtenu, jamais une trace de pile entière.
_ERREUR_MAX = 500


def _resume_scenario(s) -> str:
    cause = dt.LABELS.get(s.cause_category, "") if s.cause_category else ""
    etat = "réussi" if s.functional_status == "conforme" else "en échec"
    if s.execution_status == EXEC_BLOCKED:
        etat = "bloqué avant d'avoir pu être joué"
    detail = f" ({cause})" if cause else ""
    ligne = f"- « {s.name} » : {etat}{detail}"
    # ⚠️ **Le défaut qui produisait des explications FAUSSES** (mesuré le 2026-09-14, SauceDemo) :
    # sans ce détail, le LLM ne voyait que le TITRE du scénario + une étiquette générale
    # (« assertion métier en échec ») — et RECONSTRUISAIT un récit à partir de ce que le scénario
    # était censé vérifier, pas de ce qui s'était réellement passé. Cas mesuré : un message
    # d'erreur attendu avec un point final, obtenu sans — l'application avait PARFAITEMENT refusé
    # la connexion, et le commentaire généré a pourtant affirmé « l'application a accepté la
    # connexion... un problème de sécurité dans le système d'authentification ». Le détail RÉEL
    # de la comparaison (porté par `ScenarioVerdict.error`, déjà mesuré, jamais transmis jusqu'ici)
    # doit primer sur toute reconstruction à partir du seul titre.
    if s.functional_status != "conforme" and (s.error or "").strip():
        ligne += f"\n  Ce que le test a réellement mesuré : {s.error.strip()[:_ERREUR_MAX]}"
    return ligne


def _detail_reel_combine(verdict: CaseVerdict) -> str:
    """Tout ce qui a été RÉELLEMENT mesuré, jamais un titre — la seule matière sur laquelle une
    citation peut être vérifiée (backlog 1.3)."""
    return "\n".join(
        s.error.strip()[:_ERREUR_MAX] for s in verdict.scenarios
        if s.functional_status != "conforme" and (s.error or "").strip())


def _avertissement_bloque(verdict: CaseVerdict) -> str:
    """Un test bloqué n'a RIEN constaté sur l'application : le dire au modèle, sinon il reconstruit
    un récit d'échec à partir du titre du scénario (défaut mesuré le 2026-09-14)."""
    if verdict.execution_status != EXEC_BLOCKED:
        return ""
    return ("⚠️ Ce test n'a PAS pu être joué : un prérequis de l'environnement n'est pas rempli. "
            "Ne conclus JAMAIS que l'application est défectueuse ni que le test est faux ; "
            "dis seulement qu'il n'a pas pu commencer.\n\n")


def _build_prompt(verdict: CaseVerdict, module_name: str) -> str:
    lignes = "\n".join(_resume_scenario(s) for s in verdict.scenarios) \
        or "(aucun scénario n'a pu être joué)"
    cible = f" sur « {module_name} »" if module_name else ""
    return f"""Un test automatique vient de tourner{cible}.

Résultat technique (le test a-t-il pu s'exécuter) : {verdict.execution_status}
Résultat fonctionnel (l'application s'est-elle comportée comme attendu) : {verdict.functional_status}
Scénarios réussis : {verdict.scenarios_passed} sur {len(verdict.scenarios)}

{_avertissement_bloque(verdict)}Détail par scénario :
{lignes}

Réponds en JSON : {{"explication": "...", "citation": "..."}}

RÈGLES IMPÉRATIVES :
1. Explique CE QUI a été vérifié et POURQUOI ce résultat, en une ou deux phrases.
2. Jamais de jargon technique — écris pour quelqu'un qui ne code pas.
3. Si le résultat est positif, dis ce qui a été confirmé, pas seulement « tout est bon ».
4. Si une ligne « Ce que le test a réellement mesuré » est donnée pour un scénario en échec,
   décris CE fait précis — jamais une idée devinée depuis le seul titre du scénario.
5. `citation` : s'il existe au moins une ligne « Ce que le test a réellement mesuré » ci-dessus,
   copie MOT POUR MOT l'extrait exact sur lequel ton explication se base — jamais une
   reformulation. Sans une telle ligne (tout a réussi, rien à confronter), laisse citation vide."""


def _data_explication(llm, verdict: CaseVerdict, module_name: str, model: str,
                      cost_tracker) -> dict:
    """Patron identique à `metier_writer._data_metier` : sorties structurées si l'adaptateur les
    expose, sinon parsing tolérant d'un JSON entouré de texte."""
    user = _build_prompt(verdict, module_name)
    modele = model or config.MODEL_FAST
    if hasattr(llm, "call_json"):
        return llm.call_json(system_prompt=_SYSTEM, user_content=user, schema=_SCHEMA,
                             model=modele, max_tokens=400, cost_tracker=cost_tracker,
                             label="explication") or {}
    raw = llm.call_simple(system_prompt=_SYSTEM, user_content=user, model=modele,
                          max_tokens=400, cost_tracker=cost_tracker, label="explication")
    match = re.search(r"\{.*\}", raw or "", re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except Exception:
        return {}


def propose_explication(verdict: CaseVerdict, *, module_name: str = "",
                        llm: LLMAdapter | None = None, model: str = "") -> tuple[str, float]:
    """Un appel LLM → `(commentaire en français clair, coût en USD)` pour CE verdict.

    ⚠️ **Best-effort ABSOLU, jamais bloquant** — même discipline que la capture d'écran
    (`behave_runtime/environment.py::_capturer_ecran`) : un appel IA qui échoue rend `("", 0.0)`
    plutôt que de lever. Le verdict, lui, doit TOUJOURS s'écrire ; un commentaire manquant est un
    défaut mineur, une exécution jamais close en serait un grave.

    Le coût est mesuré par DELTA sur un `CostTracker` dédié à cet appel (même patron que
    `repair_agent.propose_fix`) — l'appelant décide quoi en faire (ledger, phase `"explication"`,
    hors du budget §9 qui ne mesure que la CRÉATION d'un cas, décision du porteur).
    """
    llm = llm or LLMAdapter()
    tracker = CostTracker()
    try:
        data = _data_explication(llm, verdict, module_name, model, tracker)
    except Exception:
        logger.warning("[explication] appel IA impossible — commentaire vide", exc_info=True)
        return "", 0.0
    texte = str(data.get("explication", "") or "").strip()

    # ⚠️ Citer ou replier (backlog 1.3) : technique Anthropic (guide « reduce hallucinations »),
    # transposée de « fait structurel » (la note UI_ONLY ci-dessus) à « affirmation non
    # vérifiable ». S'il existe un détail RÉELLEMENT mesuré à confronter, l'explication doit
    # citer un extrait vérifiable de ce détail — sinon repli sûr, jamais le récit non vérifié
    # (c'est exactement le défaut mesuré le 2026-09-14 sur SauceDemo : un récit plausible mais
    # faux, construit sur le seul titre du scénario).
    detail_reel = _detail_reel_combine(verdict)
    if texte and detail_reel:
        citation = str(data.get("citation", "") or "").strip()
        if not citation or citation.lower() not in detail_reel.lower():
            logger.warning(
                "[explication] citation absente ou introuvable dans le détail mesuré — repli sûr")
            texte = _EXPLICATION_REPLI

    if texte and verdict.ground_truth == GROUND_TRUTH_UI_ONLY:
        texte = f"{texte} {_NOTE_UI_ONLY}"
    if texte and verdict.execution_status == EXEC_BLOCKED:
        texte = f"{texte} {_NOTE_BLOQUE}"
    if texte and any(getattr(v, "cause_category", "") == "aucun_constat" for v in verdict.scenarios):
        texte = f"{texte} {_NOTE_AUCUN_CONSTAT}"
    return texte, round(tracker.total_cost, 6)
