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
from testpilot.verdict.status import CaseVerdict

logger = logging.getLogger(__name__)

_SYSTEM = ("Tu expliques le résultat d'un test automatique à un lecteur qui ne code pas. "
           "Tu écris en français clair, jamais en langage technique : aucun nom de classe "
           "d'erreur, aucun sélecteur, aucune trace de pile, aucun terme de code. Une ou deux "
           "phrases factuelles qui disent CE QUI a été vérifié et POURQUOI le résultat est "
           "celui-là. Réponds uniquement en JSON valide.")

_SCHEMA = {
    "type": "object",
    "properties": {"explication": {"type": "string"}},
    "required": ["explication"],
    "additionalProperties": False,
}


def _resume_scenario(s) -> str:
    cause = dt.LABELS.get(s.cause_category, "") if s.cause_category else ""
    etat = "réussi" if s.functional_status == "conforme" else "en échec"
    detail = f" ({cause})" if cause else ""
    return f"- « {s.name} » : {etat}{detail}"


def _build_prompt(verdict: CaseVerdict, module_name: str) -> str:
    lignes = "\n".join(_resume_scenario(s) for s in verdict.scenarios) \
        or "(aucun scénario n'a pu être joué)"
    cible = f" sur « {module_name} »" if module_name else ""
    return f"""Un test automatique vient de tourner{cible}.

Résultat technique (le test a-t-il pu s'exécuter) : {verdict.execution_status}
Résultat fonctionnel (l'application s'est-elle comportée comme attendu) : {verdict.functional_status}
Scénarios réussis : {verdict.scenarios_passed} sur {len(verdict.scenarios)}

Détail par scénario :
{lignes}

Réponds en JSON : {{"explication": "..."}}

RÈGLES IMPÉRATIVES :
1. Explique CE QUI a été vérifié et POURQUOI ce résultat, en une ou deux phrases.
2. Jamais de jargon technique — écris pour quelqu'un qui ne code pas.
3. Si le résultat est positif, dis ce qui a été confirmé, pas seulement « tout est bon »."""


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
    return texte, round(tracker.total_cost, 6)
