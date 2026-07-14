"""Exécuteur d'un module : dry-run obligatoire puis run réel, avec retry timeout UI.

Produit un ``ExecutionOutcome`` BRUT (résultats behave par scénario). Il ne calcule PAS
les deux statuts du verdict (§5) ni ne distingue « test à réparer » de « vrai bug » — c'est
le rôle du pilier ``verdict``, qui consomme cet outcome.
"""

from __future__ import annotations

from dataclasses import dataclass

from testpilot.execution.behave_result import BehaveResult


@dataclass
class ExecutionOutcome:
    module_name: str
    dry_run_passed: bool
    real_run: BehaveResult | None = None
    retried: bool = False
    error: str = ""


class Executor:
    def __init__(self, runner, *, max_retries: int = 1):
        self.runner = runner
        self.max_retries = max_retries

    def execute(self, module_name: str) -> ExecutionOutcome:
        dry = self.runner.dry_run(module_name)
        if not (dry.success and not dry.undefined_steps and not dry.ambiguous_steps):
            return ExecutionOutcome(
                module_name=module_name, dry_run_passed=False,
                error=self._dry_summary(dry),
            )

        real = self.runner.real_run(module_name)
        retried = False
        # Retry uniquement si TOUS les échecs sont des timeouts UI (flakiness), une fois.
        if (not real.success and real.failures and self.max_retries > 0
                and all(f.failure_type == "ui_timeout" for f in real.failures)):
            retried = True
            real = self.runner.real_run(module_name)

        return ExecutionOutcome(module_name=module_name, dry_run_passed=True,
                                real_run=real, retried=retried)

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
