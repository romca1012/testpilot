"""Agent de CORRECTION — propose UNE correction à partir de points de vigilance STATIQUES
(amendement §4.3-bis, 2026-09-15).

⚠️ Distinct de `repair_agent.py` sur le déclencheur : la réparation part d'un ÉCHEC RÉEL
(le test a tourné et planté) et gèle le `.feature` (relu et approuvé par un humain). Ici, le
signal vient d'une analyse STATIQUE (`generation.smoke_check`/`assertion_lint`), AVANT toute
exécution — la version n'a jamais été relue, donc rien n'est gelé : le `.feature` reste
modifiable, exactement comme à la génération.

Même mécanique que `repair_agent.propose_fix` (l'agent ne pilote pas la boucle, propose une seule
fois, l'orchestrateur décide de la suite) : réutilise `run_loop`, le dry-run valide le correctif
avant que l'appelant ne le persiste comme nouvelle version.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from testpilot import config
from testpilot.generation import steps_library
from testpilot.generation.interfaces import Connector, DryRunner
from testpilot.generation.react_loop import run_loop
from testpilot.generation.state import AgentState
from testpilot.generation.tools import ToolContext
from testpilot.guardrails.cost_tracker import CostTracker
from testpilot.llm.adapter import LLMAdapter

logger = logging.getLogger(__name__)

_CORRECTION_PROMPT_PATH = config.PROMPTS_DIR / "correction_prompt.md"


@dataclass
class CorrectionProposal:
    """Ce que l'agent propose. `changed` est faux s'il n'a rien réécrit — un aveu utile."""

    changed: bool
    feature_content: str = ""
    steps_content: str = ""
    summary: str = ""          # ce que l'agent dit avoir fait — montré à un humain tel quel
    cost_usd: float = 0.0
    stopped_reason: str = ""


def build_correction_prompt(connector: Connector | None = None,
                            connector_type: str | None = None,
                            connector_version: str = "") -> str:
    """Prompt de correction + catalogue des steps + règles du connecteur — même patron que
    `repair_agent.build_repair_prompt`."""
    from testpilot.generation.prompt import _nom_connecteur

    base = _CORRECTION_PROMPT_PATH.read_text(encoding="utf-8")

    prefix = ""
    catalogue = steps_library.as_prompt_section(steps_library.catalogue(connector_type=connector_type))
    if catalogue:
        bloc = "## Steps partagés disponibles (à réutiliser)\n\n" + catalogue
        prefix = f"<bibliotheque_de_steps>\n\n{bloc}\n\n</bibliotheque_de_steps>\n\n---\n\n"

    suffix = ""
    rules = connector.rules() if connector else ""
    version_ligne = f"Version déclarée : {connector_version}\n\n" if connector_version else ""
    if rules or version_ligne:
        bloc = version_ligne + (f"## Connecteur actif\n\n{rules}" if rules else "")
        nom = _nom_connecteur(connector)
        ouverture = f'<regles_connecteur nom="{nom}">' if nom else "<regles_connecteur>"
        suffix = f"\n\n---\n\n{ouverture}\n\n{bloc}\n\n</regles_connecteur>"

    return prefix + base + suffix


def _signal_report(lint_warnings: list[dict], feature_content: str, steps_content: str) -> str:
    """Les points de vigilance détectés, tels qu'on les donne à l'agent — factuel, comme
    `repair_agent._failure_report`, mais pour un signal STATIQUE plutôt qu'un échec observé."""
    lignes = ["# Points de vigilance relevés PAR ANALYSE STATIQUE — ce test n'a jamais tourné", ""]
    for w in lint_warnings:
        lignes.append(f"## {w.get('kind', 'signal')} — {w.get('step', '')}"
                     + (f" (ligne {w['line']})" if w.get("line") else ""))
        lignes.append(w.get("message", ""))
        lignes.append("")
    lignes.append("## Contenu ACTUEL de `.feature` — pars de lui, renvoie-le ENTIER si tu le touches")
    lignes.append("```gherkin")
    lignes.append(feature_content)
    lignes.append("```")
    lignes.append("")
    lignes.append("## Contenu ACTUEL de `_steps.py` — pars de lui, renvoie-le ENTIER si tu le touches")
    lignes.append("```python")
    lignes.append(steps_content)
    lignes.append("```")
    lignes.append("")
    lignes.append(
        "Corrige les points ci-dessus en réécrivant `.feature` et/ou `_steps.py` selon ce qui est "
        "nécessaire — `write_feature_file`/`write_steps_file` REMPLACENT le fichier : tout ce que "
        "tu n'écris pas dans un fichier que tu touches est PERDU. Si tu ne sais pas corriger un "
        "point avec certitude, dis-le plutôt que d'inventer une référence non vérifiée.")
    return "\n".join(lignes)


def propose_correction(*, module_name: str, lint_warnings: list[dict],
                       feature_content: str, steps_content: str,
                       llm: LLMAdapter | None = None, connector: Connector | None = None,
                       connector_type: str | None = None, connector_version: str = "",
                       dry_runner: DryRunner | None = None,
                       cost_tracker: CostTracker | None = None,
                       max_iterations: int | None = None,
                       calibration_writes_enabled: bool = False) -> CorrectionProposal:
    """Une tentative de correction depuis des points de vigilance statiques. Ne lance JAMAIS le
    test réel — même contrat que `repair_agent.propose_fix`."""
    llm = llm or LLMAdapter()
    cost_tracker = cost_tracker or CostTracker()
    cout_avant = cost_tracker.total_cost

    # Les fichiers EXISTENT déjà sur disque et ont déjà passé un dry-run à la génération : on part
    # de cet état, comme `repair_agent.propose_fix` (même rationale, cf. sa docstring).
    state = AgentState(module_name=module_name, feature_written=True, steps_written=True,
                       dry_run_passed=True)
    state.messages.append({"role": "user",
                           "content": _signal_report(lint_warnings, feature_content, steps_content)})

    shared_steps = steps_library.catalogue(connector_type=connector_type)
    ctx = ToolContext(
        module_name=module_name,
        generated_dir=config.GENERATED_DIR,
        connector=connector,
        reserved_steps=frozenset(s.label for s in shared_steps),
        calibration_writes_enabled=calibration_writes_enabled,
    )
    run_loop(
        llm=llm,
        system_prompt=build_correction_prompt(connector, connector_type, connector_version),
        state=state,
        ctx=ctx,
        dry_runner=dry_runner,
        cost_tracker=cost_tracker,
        max_iterations=max_iterations if max_iterations is not None else config.MAX_ITERATIONS,
        stall_limit=config.REPAIR_STALL_LIMIT,
    )

    changed = bool(state.steps_content or state.feature_content)
    if not changed:
        logger.info("[correction] l'agent n'a rien réécrit (%s)", state.stopped_reason)
    return CorrectionProposal(
        changed=changed,
        feature_content=state.feature_content or feature_content,
        steps_content=state.steps_content or steps_content,
        summary=_last_assistant_text(state),
        cost_usd=round(cost_tracker.total_cost - cout_avant, 6),
        stopped_reason=state.stopped_reason or "incomplete",
    )


def _last_assistant_text(state: AgentState) -> str:
    """Dernier texte libre de l'agent — ce qu'il dit avoir fait (même helper que `repair_agent`,
    dupliqué ici pour ne pas coupler deux modules indépendants pour une fonction de 10 lignes)."""
    for message in reversed(state.messages):
        if message.get("role") != "assistant":
            continue
        contenu = message.get("content")
        if isinstance(contenu, str):
            return contenu.strip()
        for bloc in reversed(contenu or []):
            texte = bloc.get("text") if isinstance(bloc, dict) else getattr(bloc, "text", None)
            if texte and texte.strip():
                return texte.strip()
    return ""
