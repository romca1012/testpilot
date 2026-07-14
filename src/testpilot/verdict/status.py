"""Les DEUX axes de statut du verdict (§5), calculés depuis un ExecutionOutcome brut.

- StatutExécution : le test a-t-il pu tourner techniquement (pas de crash/timeout/env) ?
- StatutFonctionnel : l'application s'est-elle comportée conformément au besoin ?

Les deux sont indépendants et jamais confondus. Règle de dérivation validée (section C) :
un échec d'assertion métier ⇒ exécution=success, fonctionnel=non_conforme (le test a bien
tourné mais l'app répond faux) ; un échec technique ⇒ exécution=technical_error,
fonctionnel=indetermine. L'agrégation par-cas ne masque jamais un non_conforme.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from testpilot.execution.executor import ExecutionOutcome
from testpilot.verdict import defect_taxonomy as dt

# Axe exécution
EXEC_SUCCESS = "success"
EXEC_TECHNICAL_ERROR = "technical_error"
EXEC_NOT_EXECUTED = "not_executed"
# Axe fonctionnel
FUNC_CONFORME = "conforme"
FUNC_NON_CONFORME = "non_conforme"
FUNC_INDETERMINE = "indetermine"
FUNC_NOT_EVALUATED = "not_evaluated"


@dataclass
class ScenarioVerdict:
    name: str
    execution_status: str
    functional_status: str
    failure_type: str = ""
    cause_category: str = ""
    error: str = ""


@dataclass
class CaseVerdict:
    execution_status: str
    functional_status: str
    scenarios: list[ScenarioVerdict] = field(default_factory=list)
    scenarios_passed: int = 0
    scenarios_failed: int = 0


def _failures_by_scenario(failures) -> dict[str, list]:
    grouped: dict[str, list] = {}
    for f in failures or []:
        grouped.setdefault(f.scenario_name, []).append(f)
    return grouped


def scenario_verdict(scenario, failures: list) -> ScenarioVerdict:
    """Projette un scénario behave + ses échecs sur les deux axes."""
    if scenario.status == "passed":
        return ScenarioVerdict(scenario.name, EXEC_SUCCESS, FUNC_CONFORME)

    if scenario.status == "failed":
        cause = dt.dominant_category(failures) or dt.UNKNOWN
        failure_type = failures[0].failure_type if failures else ""
        if cause == dt.ASSERTION_MISMATCH:
            # A tourné techniquement, mais le comportement métier est faux → constat produit.
            return ScenarioVerdict(scenario.name, EXEC_SUCCESS, FUNC_NON_CONFORME,
                                   failure_type, cause, scenario.error)
        # Cause technique (ou indéterminée) → le test n'a pas pu juger le fonctionnel.
        return ScenarioVerdict(scenario.name, EXEC_TECHNICAL_ERROR, FUNC_INDETERMINE,
                               failure_type, cause, scenario.error)

    # skipped / autre : n'a pas tourné en entier → interruption technique.
    return ScenarioVerdict(scenario.name, EXEC_TECHNICAL_ERROR, FUNC_INDETERMINE,
                           "", "", scenario.error)


def derive_verdict(outcome: ExecutionOutcome) -> CaseVerdict:
    """Calcule le verdict à deux axes d'un cas depuis son ExecutionOutcome brut."""
    if not outcome.dry_run_passed:
        # Non résolvable (parsing/steps) → n'a jamais pu tourner techniquement.
        return CaseVerdict(EXEC_TECHNICAL_ERROR, FUNC_INDETERMINE)

    real = outcome.real_run
    if real is None or real.returncode < 0:
        # Crash / timeout du sous-processus → interruption technique.
        return CaseVerdict(EXEC_TECHNICAL_ERROR, FUNC_INDETERMINE)

    grouped = _failures_by_scenario(real.failures)
    verdicts = [scenario_verdict(s, grouped.get(s.name, [])) for s in real.scenarios]
    return aggregate(verdicts)


def aggregate(verdicts: list[ScenarioVerdict]) -> CaseVerdict:
    """Agrège les verdicts par-scénario au niveau du cas — sans jamais masquer un échec."""
    passed = sum(1 for v in verdicts
                 if v.execution_status == EXEC_SUCCESS and v.functional_status == FUNC_CONFORME)

    if not verdicts:
        execution_status = EXEC_NOT_EXECUTED
    elif any(v.execution_status == EXEC_TECHNICAL_ERROR for v in verdicts):
        execution_status = EXEC_TECHNICAL_ERROR
    else:
        execution_status = EXEC_SUCCESS

    if any(v.functional_status == FUNC_NON_CONFORME for v in verdicts):
        functional_status = FUNC_NON_CONFORME  # un vrai constat produit surface toujours
    elif not verdicts:
        functional_status = FUNC_NOT_EVALUATED
    elif execution_status == EXEC_SUCCESS and all(v.functional_status == FUNC_CONFORME for v in verdicts):
        functional_status = FUNC_CONFORME
    else:
        functional_status = FUNC_INDETERMINE

    return CaseVerdict(
        execution_status=execution_status,
        functional_status=functional_status,
        scenarios=verdicts,
        scenarios_passed=passed,
        scenarios_failed=len(verdicts) - passed,
    )
