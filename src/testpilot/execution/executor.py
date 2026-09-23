"""Exécuteur d'un module : dry-run obligatoire puis run réel, avec retry timeout UI.

Produit un ``ExecutionOutcome`` BRUT (résultats behave par scénario). Il ne calcule PAS
les deux statuts du verdict (§5) ni ne distingue « test à réparer » de « vrai bug » — c'est
le rôle du pilier ``verdict``, qui consomme cet outcome.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import time

from testpilot.execution.behave_result import BehaveResult


@dataclass
class ExecutionOutcome:
    module_name: str
    dry_run_passed: bool
    real_run: BehaveResult | None = None
    retried: bool = False
    error: str = ""
    attempts: list[BehaveResult] = field(default_factory=list)


class Executor:
    def __init__(self, runner, *, max_retries: int = 1,
                 on_attempt_start=None, on_attempt_finish=None):
        self.runner = runner
        self.max_retries = max_retries
        self.on_attempt_start = on_attempt_start
        self.on_attempt_finish = on_attempt_finish

    def execute(self, module_name: str) -> ExecutionOutcome:
        dry = self.runner.dry_run(module_name)
        if not (dry.success and not dry.undefined_steps and not dry.ambiguous_steps):
            return ExecutionOutcome(
                module_name=module_name, dry_run_passed=False,
                error=self._dry_summary(dry),
            )

        attempts = []

        def run_attempt(number, reason):
            if self.on_attempt_start:
                self.on_attempt_start(number, reason)
            started = time.perf_counter()
            try:
                result = self.runner.real_run(module_name)
            except Exception as exc:
                result = BehaveResult(success=False, returncode=-1, raw_stderr=str(exc))
                attempts.append(result)
                if self.on_attempt_finish:
                    self.on_attempt_finish(number, result, time.perf_counter() - started)
                raise
            attempts.append(result)
            if self.on_attempt_finish:
                self.on_attempt_finish(number, result, time.perf_counter() - started)
            return result

        real = run_attempt(1, "initial")
        retried = False
        # Retry uniquement si TOUS les échecs sont des timeouts UI (flakiness), une fois.
        if (not real.success and real.failures and self.max_retries > 0
                and all(f.failure_type == "ui_timeout" for f in real.failures)):
            retried = True
            real = run_attempt(2, "ui_timeout")

        return ExecutionOutcome(module_name=module_name, dry_run_passed=True,
                                real_run=real, retried=retried, attempts=attempts)

    @staticmethod
    def _dry_summary(dry: BehaveResult) -> str:
        parts = []
        if dry.undefined_steps:
            parts.append(f"steps non définis : {dry.undefined_steps[:5]}")
        if dry.ambiguous_steps:
            parts.append(f"steps ambigus : {dry.ambiguous_steps[:3]}")
        if dry.raw_stderr:
            parts.append(dry.raw_stderr[:200])
        return " | ".join(parts) or "dry-run en échec"
