"""Boucle ReAct — mécanique pure : tour LLM → dispatch tools → dry-run → gardes.

Toute la logique métier vit ailleurs (tools, prompt, état). Ce module ne fait
qu'orchestrer les tours et appliquer les garde-fous (coût / itérations / stall dry-run).
Il n'exécute JAMAIS le test réel — seulement ``behave --dry-run`` via le DryRunner injecté.
"""

from __future__ import annotations

import hashlib
import logging

from testpilot.execution.behave_result import meaningful_error
from testpilot.generation.state import AgentState
from testpilot.generation.tools import ToolContext, dispatch
from testpilot.generation.tools.api_definitions import tools_for_api
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


def _dryrun_diagnostic(result) -> str:
    """Cause utile des erreurs de parsing/import, même sans step indéfini."""
    return meaningful_error(
        getattr(result, "raw_stderr", "") or getattr(result, "raw_stdout", ""), limit=1500)


def _dryrun_signature(result) -> str:
    basis = repr((sorted(result.undefined_steps), sorted(result.ambiguous_steps),
                  getattr(result, "returncode", None), _dryrun_diagnostic(result)))
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

    state.dernier_dry_run = (_dryrun_diagnostic(result) or ", ".join(
        [*result.undefined_steps, *result.ambiguous_steps]))[:300]
    signature = _dryrun_signature(result)
    if state.last_dryrun_signature is not None and signature == state.last_dryrun_signature:
        state.stall_count += 1
    else:
        state.stall_count = 0
    state.last_dryrun_signature = signature

    if state.stall_count >= stall_limit:
        state.stalled = True
        # ⚠️ Seule ligne de log de tout ce chemin (2026-09-28) : jusqu'ici, `dry_run_stalled`
        # perdait le diagnostic (steps `undefined`/`ambiguous`, sortie Behave) sans laisser aucune
        # trace nulle part — ni ici, ni dans la ligne persistée (`GenerationJobRepo.maj` ne garde
        # que le mot `dry_run_stalled`). Mesuré en staging : un job resté indiagnosticable faute
        # de cette ligne.
        logger.warning(
            "[react] dry-run stalled pour '%s' après %d tentative(s) identiques — "
            "undefined=%s ambiguous=%s. Diagnostic Behave : %s",
            state.module_name, state.stall_count, result.undefined_steps,
            result.ambiguous_steps, _dryrun_diagnostic(result) or "aucun diagnostic disponible")
        return "stalled"

    _append_user_text(
        state,
        "[dry-run] échec de parsing — "
        f"undefined={result.undefined_steps} ambiguous={result.ambiguous_steps}. "
        f"Diagnostic Behave : {_dryrun_diagnostic(result) or 'aucun diagnostic disponible'}. "
        "Corrige le .feature ou les steps, puis rappelle write_*_file.",
    )
    return "failed"


def _append_user_text(state: AgentState, text: str) -> None:
    state.messages.append({"role": "user", "content": [{"type": "text", "text": text}]})


def message_de_controle(avis: list[dict]) -> str:
    """Étape 2 (A61) : ce que l'IA reçoit quand son test passe la vérification à blanc mais garde des points de vigilance.
    Les textes viennent des contrôles de TestPilot, jamais de l'agent."""
    lignes = []
    for a in avis[:20]:
        ou = f" (ligne {a['line']})" if a.get("line") else ""
        lignes.append(f"- [{a.get('kind', '?')}]{ou} {a.get('message') or a.get('step') or ''}".rstrip())
    return ("[contrôle de fin d'écriture] Le test passe la vérification à blanc, mais ces points le laisseraient BLOQUÉ "
            "au lancement :\n" + "\n".join(lignes) + "\nCe que le test VÉRIFIE (« Alors », Exemples, fonctions "
            "@then) est désormais gelé : une réécriture qui y touche sera refusée. Corrige le reste en réécrivant le "
            "fichier concerné (write_feature_file, write_steps_file) — pour un champ jamais vu, observe d'abord la page "
            "(inspect_page_form) ; pour un message, soumets le formulaire (attempt_form_submission). Si un point ne "
            "s'applique pas à ce test, termine sans rien réécrire : le test sera livré bloqué avec ce point, et une "
            "personne tranchera.")


def run_loop(*, llm, system_prompt: str, state: AgentState, ctx: ToolContext,
             dry_runner, cost_tracker, max_iterations: int, stall_limit: int,
             model: str = "", controle_fin=None, tours_de_controle: int = 2) -> AgentState:
    """Exécute la boucle jusqu'à un dry-run vert ou l'activation d'un garde-fou.

    `controle_fin` (étape 2, A61 — interrupteur `TESTPILOT_CONTROLE_FIN_ECRITURE`) : `state -> avis`. Quand le dry-run
    passe et qu'il reste des avis, ils sont renvoyés à l'IA (au plus `tours_de_controle` fois) au lieu de clore ; si elle
    termine sans réécrire, la génération est réussie avec des avis restants — le test sera livré bloqué (A63). Absent :
    la boucle d'avant, à l'identique."""
    # Q3-a : les outils sont calculés UNE fois par run (jamais par tour : un préfixe d'outils qui
    # changerait en cours de route invaliderait le cache de prompt). Interrupteurs éteints, c'est
    # exactement l'ancienne liste `TOOLS_DEFINITIONS`.
    from testpilot.generation.tools import outils_optionnels
    tools = tools_for_api(avec=outils_optionnels(ctx))
    for i in range(max_iterations):
        state.iterations = i + 1
        try:
            resp, raw = llm.call_with_tools(
                system_prompt=system_prompt,
                messages=state.messages,
                tools=tools,
                cost_tracker=cost_tracker,
                **({"model": model} if model else {}),
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
                if not outcome.ok:   # AV-7 : les derniers refus, pour instruire une génération qui n'aboutit pas
                    state.refus_recents = [*state.refus_recents, outcome.observation[:160]][-5:]
                results.append({"type": "tool_result", "tool_use_id": call.id,
                                "content": outcome.observation})
            state.messages.append({"role": "user", "content": results})

        # Dry-run automatique dès que les deux fichiers sont prêts.
        verdict = _maybe_dry_run(state, dry_runner, stall_limit)
        if verdict == "passed":
            avis = controle_fin(state) if controle_fin and state.tours_de_controle < tours_de_controle else []
            if avis and i + 1 < max_iterations:
                # Revue de l'étape 2 (B1) : dès le premier renvoi, les vérifications sont GELÉES (comme en réparation,
                # VH-03) — l'IA ne peut plus faire taire un point en affaiblissant ce que le test prouve.
                if ctx.gel_feature is None and ctx.gel_steps is None:
                    ctx.gel_feature, ctx.gel_steps, ctx.gel_motif = state.feature_content, state.steps_content, "controle"
                state.tours_de_controle += 1
                state.avis_envoyes += [a.get("kind") or "" for a in avis]
                _append_user_text(state, message_de_controle(avis))
                continue
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
    if tool_name in {"inspect_schema", "inspect_page_form"}:
        for source, names in outcome.verified_fields.items():
            state.verified_fields[source] = sorted(
                set(state.verified_fields.get(source, [])) | set(names))
    if tool_name in {"write_feature_file", "write_test_plan"} and outcome.feature_content is not None:
        state.feature_written = True
        state.feature_content = outcome.feature_content
        state.dry_run_passed = False  # le contenu a changé : revalider
    elif tool_name == "write_steps_file" and outcome.steps_content is not None:
        state.steps_written = True
        state.steps_content = outcome.steps_content
        state.dry_run_passed = False
