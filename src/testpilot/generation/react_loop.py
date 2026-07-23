"""Boucle ReAct — mécanique pure : tour LLM → dispatch tools → dry-run → gardes.

Toute la logique métier vit ailleurs (tools, prompt, état). Ce module ne fait
qu'orchestrer les tours et appliquer les garde-fous (coût / itérations / stall dry-run).
Il n'exécute JAMAIS le test réel — seulement ``behave --dry-run`` via le DryRunner injecté.
"""

from __future__ import annotations

import hashlib
import logging

from testpilot.generation.state import AgentState
from testpilot.generation.tools import TOOLS_DEFINITIONS, ToolContext, dispatch
from testpilot.guardrails.cost_tracker import CostLimitExceeded

logger = logging.getLogger(__name__)


def _assistant_message(resp, raw) -> dict:
    """Message assistant à ajouter à l'historique (compatible SDK réel ou fake)."""
    if raw is not None and getattr(raw, "content", None) is not None:
        return {"role": "assistant", "content": raw.content}
    blocks: list[dict] = [{"type": "text", "text": t} for t in resp.text_blocks if t]
    for call in resp.tool_calls:
        blocks.append({"type": "tool_use", "id": call.id, "name": call.name, "input": call.input})
    return {"role": "assistant", "content": blocks or [{"type": "text", "text": ""}]}


def _dryrun_signature(result) -> str:
    basis = "|".join(sorted(result.undefined_steps) + sorted(result.ambiguous_steps))
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


def _maybe_dry_run(state: AgentState, dry_runner, stall_limit: int) -> str:
    """Lance le dry-run si les deux fichiers sont écrits et non encore validés.

    Retourne : 'passed' | 'stalled' | 'failed' | 'skip'.
    """
    if dry_runner is None:
        return "skip"
    if not (state.feature_written and state.steps_written and not state.dry_run_passed):
        return "skip"

    result = dry_runner.dry_run(state.module_name)
    if result.success and not result.undefined_steps and not result.ambiguous_steps:
        state.dry_run_passed = True
        state.stall_count = 0
        return "passed"

    signature = _dryrun_signature(result)
    if state.last_dryrun_signature is not None and signature == state.last_dryrun_signature:
        state.stall_count += 1
    else:
        state.stall_count = 0
    state.last_dryrun_signature = signature

    if state.stall_count >= stall_limit:
        state.stalled = True
        return "stalled"

    _append_user_text(
        state,
        "[dry-run] échec de parsing — "
        f"undefined={result.undefined_steps} ambiguous={result.ambiguous_steps}. "
        "Corrige le .feature ou les steps, puis rappelle write_*_file.",
    )
    return "failed"


def _append_user_text(state: AgentState, text: str) -> None:
    state.messages.append({"role": "user", "content": [{"type": "text", "text": text}]})


def run_loop(*, llm, system_prompt: str, state: AgentState, ctx: ToolContext,
             dry_runner, cost_tracker, max_iterations: int, stall_limit: int) -> AgentState:
    """Exécute la boucle jusqu'à un dry-run vert ou l'activation d'un garde-fou."""
    for i in range(max_iterations):
        state.iterations = i + 1
        try:
            resp, raw = llm.call_with_tools(
                system_prompt=system_prompt,
                messages=state.messages,
                tools=TOOLS_DEFINITIONS,
                cost_tracker=cost_tracker,
            )
        except CostLimitExceeded:
            state.stopped_reason = "cost_exceeded"
            return state

        # ⚠️ §2bis A3 — un tour TRONQUÉ ou DÉCLINÉ n'est pas un tour valide. On l'intercepte AVANT
        # de l'ajouter à l'historique : ne pas prendre un Gherkin coupé pour un succès (le défaut
        # que le durcissement `stop_reason` ferme), ni dispatcher un tool_use partiel.
        if resp.raw_stop_reason == "refusal":
            logger.warning("[react] tour DÉCLINÉ par le modèle (refusal) — génération interrompue")
            state.stopped_reason = "refusal"
            return state
        if resp.raw_stop_reason == "max_tokens":
            logger.warning("[react] tour TRONQUÉ (max_tokens) — sortie incomplète, arrêt "
                           "(augmenter max_tokens ou resserrer le périmètre)")
            state.stopped_reason = "max_tokens_truncated"
            return state

        state.messages.append(_assistant_message(resp, raw))

        if resp.stop_reason == "tool_use":
            results = []
            for call in resp.tool_calls:
                outcome = dispatch(call.name, call.input, ctx)
                _apply_effect(state, call.name, outcome)
                results.append({"type": "tool_result", "tool_use_id": call.id,
                                "content": outcome.observation})
            state.messages.append({"role": "user", "content": results})

        # Dry-run automatique dès que les deux fichiers sont prêts.
        verdict = _maybe_dry_run(state, dry_runner, stall_limit)
        if verdict == "passed":
            state.stopped_reason = "done"
            return state
        if verdict == "stalled":
            state.stopped_reason = "dry_run_stalled"
            return state

        # end_turn sans rien de plus à tenter → on clôt.
        if resp.stop_reason == "end_turn" and verdict == "skip":
            state.stopped_reason = "done" if state.dry_run_passed else "incomplete"
            return state

    state.stopped_reason = state.stopped_reason or "max_iterations"
    return state


def _apply_effect(state: AgentState, tool_name: str, outcome) -> None:
    """Reporte les effets d'un tool réussi sur l'état de génération."""
    if not outcome.ok:
        return
    if tool_name == "write_feature_file" and outcome.feature_content is not None:
        state.feature_written = True
        state.feature_content = outcome.feature_content
        state.dry_run_passed = False  # le contenu a changé : revalider
    elif tool_name == "write_steps_file" and outcome.steps_content is not None:
        state.steps_written = True
        state.steps_content = outcome.steps_content
        state.dry_run_passed = False
