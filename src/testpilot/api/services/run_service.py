"""Déclenchement et exécution d'un cas depuis l'API (tâche de fond).

Un run UI ré-exécute la version courante APPROUVÉE d'un cas via le vrai runner Behave, puis
calcule le verdict à deux axes et le persiste — même logique que le CLI (§5), sans étape de
génération ni coût LLM. L'état « en cours » est suivi en mémoire (serveur mono-processus).
"""

from __future__ import annotations

import logging
import time

from testpilot import config
from testpilot.connectors.runtime_env import project_env
from testpilot.execution.behave_runner import BehaveRunner
from testpilot.execution.executor import Executor
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import (
    CaseRepo,
    ExecutionRepo,
    ProjectRepo,
    RepairRepo,
    ReviewRepo,
    now_iso,
)
from testpilot.verdict import defect_origin as do
from testpilot.verdict import review_gate
from testpilot.verdict.status import EXEC_TECHNICAL_ERROR, FUNC_INDETERMINE, derive_verdict

logger = logging.getLogger(__name__)

# Exécutions en cours (id) — suivi mémoire, suffisant pour le serveur de dev mono-processus.
_RUNNING: set[int] = set()


def is_running(execution_id: int) -> bool:
    return execution_id in _RUNNING


class RunError(Exception):
    """Erreur métier de déclenchement (traduite en HTTP par la route)."""

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code       # not_found | no_version | needs_review
        self.detail = detail


def trigger_run(conn, case_id: int) -> tuple[int, str, int, int]:
    """Valide le gate et crée la ligne d'exécution. Renvoie (execution_id, feature_slug, case_id, version_id)."""
    case = CaseRepo(conn).get(case_id)
    if case is None:
        raise RunError("not_found", f"cas {case_id} introuvable")
    version_id = case.get("current_version_id")
    if not version_id:
        raise RunError("no_version", "aucune version générée pour ce cas")

    gate = review_gate.evaluate_gate(ReviewRepo(conn), version_id)
    if not gate.allowed:
        raise RunError("needs_review", gate.reason)

    execs = ExecutionRepo(conn)
    trigger = "rerun" if execs.list_for_case(case_id) else "first_run"
    eid = execs.create(test_case_id=case_id, version_id=version_id, trigger=trigger)
    _RUNNING.add(eid)
    # feature_slug = nom du .feature (technique), distinct du module métier (§7 / décision 0004).
    return eid, case["feature_slug"], case_id, version_id


def resolve_connection(conn, case_id: int) -> dict[str, str]:
    """Connexion (variables d'env) du PROJET auquel appartient le cas.

    Le run doit taper l'application du projet affiché, pas la config globale — sinon
    l'interface promettrait un multi-projet que le runtime ne tiendrait pas. Vide si le
    projet n'a pas de connexion saisie → repli sur la config globale.
    """
    case = CaseRepo(conn).get(case_id)
    project_id = (case or {}).get("project_id")
    project = ProjectRepo(conn).get(project_id) if project_id else None
    return project_env(project)


def run_execution(execution_id: int, module_name: str, case_id: int, version_id: int) -> None:
    """Tâche de fond : lance Behave réel, calcule + persiste le verdict à deux axes."""
    conn = get_initialized_db(config.DB_PATH)
    try:
        started = time.perf_counter()
        # Le runtime tape l'application DU PROJET du cas (décision 0005).
        runner = BehaveRunner(connection=resolve_connection(conn, case_id))
        outcome = Executor(runner).execute(module_name)
        duration = time.perf_counter() - started
        verdict = derive_verdict(outcome)
        _persist(conn, execution_id, case_id, verdict, outcome, duration)
    except Exception as exc:  # jamais laisser l'exécution « en cours » sur un plantage
        logger.exception("[run] exécution %s en échec : %s", execution_id, exc)
        _finalize_error(conn, execution_id, case_id, str(exc))
    finally:
        _RUNNING.discard(execution_id)
        conn.close()


def _persist(conn, execution_id, case_id, verdict, outcome, duration) -> None:
    execs = ExecutionRepo(conn)
    for s in verdict.scenarios:
        execs.add_scenario_result(
            execution_id=execution_id, scenario_name=s.name,
            execution_status=s.execution_status, functional_status=s.functional_status,
            failure_type=s.failure_type, cause_category=s.cause_category,
            error_summary=(s.error or "")[:500],
        )

    if outcome.real_run is not None and outcome.real_run.failures:
        dv = do.diagnose(outcome.real_run.failures)
        if dv is not None:
            from testpilot.guardrails.repair_circuit import failure_signature
            RepairRepo(conn).create(
                execution_id=execution_id, attempt_number=1,
                failure_signature=failure_signature(outcome.real_run.failures),
                cause_category=dv.cause_category, defect_origin=dv.defect_origin,
                confirmation_status=dv.confirmation_status)

    execs.finalize(
        execution_id, execution_status=verdict.execution_status,
        functional_status=verdict.functional_status,
        scenarios_total=len(verdict.scenarios),
        scenarios_passed=verdict.scenarios_passed, scenarios_failed=verdict.scenarios_failed,
        cost_usd=0.0, iterations=0, duration_seconds=duration)

    cases = CaseRepo(conn)
    prev = cases.get(case_id)
    cases.set_validation_status(case_id, review_gate.validation_status_after_run(
        prev["validation_status"] if prev else "never_executed", verdict.execution_status))
    cases.update_last_outcome(case_id, execution_status=verdict.execution_status,
                              functional_status=verdict.functional_status, executed_at=now_iso())


def _finalize_error(conn, execution_id, case_id, message: str) -> None:
    """Clôt une exécution plantée comme erreur technique (verdict honnête, jamais 'conforme')."""
    try:
        ExecutionRepo(conn).finalize(
            execution_id, execution_status=EXEC_TECHNICAL_ERROR,
            functional_status=FUNC_INDETERMINE, scenarios_total=0, scenarios_passed=0,
            scenarios_failed=0, cost_usd=0.0, iterations=0, duration_seconds=0.0)
        CaseRepo(conn).update_last_outcome(
            case_id, execution_status=EXEC_TECHNICAL_ERROR,
            functional_status=FUNC_INDETERMINE, executed_at=now_iso())
    except Exception:
        logger.exception("[run] échec de la clôture d'erreur pour %s", execution_id)


def submit_review(conn, case_id: int, version_id: int, *, approved: bool,
                  reviewer: str, comment: str):
    """Enregistre une décision de relecture et renvoie le gate qui en découle."""
    return review_gate.submit_review(
        ReviewRepo(conn), case_id=case_id, version_id=version_id,
        approved=approved, reviewer=reviewer, comment=comment)
