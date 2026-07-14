"""Orchestrateur mince du pilier generation.

``generate(plan)`` : assemble prompt + contexte, lance la boucle ReAct, construit le
GenerationResult, et (si des repos sont fournis) persiste la version + pose le statut de
validation « en attente de relecture ». N'exécute jamais le test et n'appelle jamais le
gate de relecture — il ne fait qu'exposer l'information pour que ``verdict`` s'y branche.
"""

from __future__ import annotations

import logging
import re

from testpilot import config
from testpilot.analysis.plan import TestPlan
from testpilot.analysis.spec_analyzer import spec_hash
from testpilot.generation import prompt as prompt_mod
from testpilot.generation.interfaces import Connector, DryRunner
from testpilot.generation.react_loop import run_loop
from testpilot.generation.state import AgentState, GenerationResult
from testpilot.generation.tools import ToolContext
from testpilot.guardrails.cost_tracker import CostTracker
from testpilot.llm.adapter import LLMAdapter

logger = logging.getLogger(__name__)

_STEP_DECORATOR = re.compile(r"@(?:given|when|then|step)\(\s*[\"']([^\"']+)[\"']", re.IGNORECASE)


class GenerationAgent:
    def __init__(self, *, llm: LLMAdapter | None = None, connector: Connector | None = None,
                 dry_runner: DryRunner | None = None, cost_tracker: CostTracker | None = None,
                 case_repo=None, version_repo=None, max_iterations: int | None = None,
                 stall_limit: int | None = None):
        self.llm = llm or LLMAdapter()
        self.connector = connector
        self.dry_runner = dry_runner
        self.cost_tracker = cost_tracker or CostTracker()
        self.case_repo = case_repo
        self.version_repo = version_repo
        self.max_iterations = max_iterations if max_iterations is not None else config.MAX_ITERATIONS
        self.stall_limit = stall_limit if stall_limit is not None else config.REPAIR_STALL_LIMIT

    def generate(self, plan: TestPlan, *, case_id: int | None = None,
                 title: str = "", author: str = "") -> GenerationResult:
        state = AgentState(module_name=plan.module_name)
        state.messages.append({"role": "user", "content": prompt_mod.build_initial_message(plan)})
        ctx = ToolContext(
            module_name=plan.module_name,
            generated_dir=config.GENERATED_DIR,
            connector=self.connector,
            reserved_steps=self._reserved_steps(),
        )
        run_loop(
            llm=self.llm,
            system_prompt=prompt_mod.build_system_prompt(self.connector),
            state=state,
            ctx=ctx,
            dry_runner=self.dry_runner,
            cost_tracker=self.cost_tracker,
            max_iterations=self.max_iterations,
            stall_limit=self.stall_limit,
        )
        result = self._build_result(plan, state)
        if result.success and self.case_repo is not None and self.version_repo is not None:
            self._persist(plan, result, case_id=case_id, title=title, author=author)
        return result

    def _build_result(self, plan: TestPlan, state: AgentState) -> GenerationResult:
        success = state.dry_run_passed and state.stopped_reason == "done"
        return GenerationResult(
            success=success,
            module_name=plan.module_name,
            stopped_reason=state.stopped_reason or "incomplete",
            dry_run_passed=state.dry_run_passed,
            iterations=state.iterations,
            cost_usd=round(self.cost_tracker.total_cost, 6),
            feature_path=(config.GENERATED_DIR / f"{plan.module_name}.feature") if state.feature_written else None,
            steps_path=(config.GENERATED_DIR / f"{plan.module_name}_steps.py") if state.steps_written else None,
            feature_content=state.feature_content,
            steps_content=state.steps_content,
            spec_hash=spec_hash(plan.raw_spec),
            awaiting_review=success,
        )

    def _persist(self, plan: TestPlan, result: GenerationResult, *,
                 case_id: int | None, title: str, author: str) -> None:
        """Crée/repère le cas, écrit la nouvelle version, pose le statut « à relire »."""
        if case_id is None:
            case_id = self.case_repo.create(
                title=title or plan.module_name, module=plan.module_name,
                author=author, description=plan.raw_spec[:500], connector_type=plan.connector_type,
            )
            validation_status = "never_executed"
        else:
            existing = self.case_repo.get(case_id) or {}
            # Re-version d'un cas déjà validé (spec évoluée) → à réviser (§5).
            validation_status = "to_review" if existing.get("validation_status") == "validated" else "never_executed"

        version_id = self.version_repo.create(
            test_case_id=case_id,
            spec_content=plan.raw_spec,
            spec_hash=result.spec_hash,
            feature_content=result.feature_content,
            steps_content=result.steps_content,
            feature_path=str(result.feature_path or ""),
            steps_path=str(result.steps_path or ""),
            change_summary="Génération IA",
            created_by=author,
        )
        self.case_repo.set_current_version(case_id, version_id)
        self.case_repo.set_validation_status(case_id, validation_status)
        result.case_id = case_id
        result.version_id = version_id
        result.awaiting_review = True

    @staticmethod
    def _reserved_steps() -> frozenset[str]:
        """Libellés de steps de la bibliothèque partagée (best-effort ; vide si absente)."""
        directory = config.STEPS_LIBRARY_DIR
        if not directory.exists():
            return frozenset()
        reserved: set[str] = set()
        for path in directory.glob("*.py"):
            try:
                reserved.update(m.strip() for m in _STEP_DECORATOR.findall(path.read_text(encoding="utf-8")))
            except OSError:
                continue
        return frozenset(reserved)
