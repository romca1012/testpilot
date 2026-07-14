"""INVARIANT CRITIQUE §5 — les deux axes de statut sont indépendants et jamais confondus.

Le point capital : un échec d'assertion métier donne exécution=success MAIS
fonctionnel=non_conforme (le test a tourné, l'app répond faux) ; et un non_conforme
n'est JAMAIS masqué par des échecs techniques concomitants.
"""

from testpilot.execution.behave_result import BehaveFailure, BehaveResult, BehaveScenario
from testpilot.execution.executor import ExecutionOutcome
from testpilot.verdict import status as st


def _outcome(scenarios, failures, dry_ok=True, returncode=0):
    real = BehaveResult(success=(returncode == 0), returncode=returncode,
                        scenarios=scenarios, failures=failures)
    return ExecutionOutcome(module_name="m", dry_run_passed=dry_ok,
                            real_run=real if dry_ok else None)


def test_passing_scenario_is_success_and_conforme():
    v = st.derive_verdict(_outcome([BehaveScenario("[Nominal] ok", "passed")], []))
    assert v.execution_status == st.EXEC_SUCCESS
    assert v.functional_status == st.FUNC_CONFORME


def test_business_assertion_failure_is_success_but_non_conforme():
    """Indépendance des axes : a TOURNÉ (success) mais comportement FAUX (non_conforme)."""
    scenarios = [BehaveScenario("[Erreur] montant", "failed", error="AssertionError")]
    failures = [BehaveFailure("[Erreur] montant", "Alors le total vaut 0", "assertion",
                              "AssertionError: attendu 0, obtenu 5")]
    v = st.derive_verdict(_outcome(scenarios, failures))
    assert v.execution_status == st.EXEC_SUCCESS
    assert v.functional_status == st.FUNC_NON_CONFORME


def test_technical_failure_is_technical_error_and_indetermine():
    scenarios = [BehaveScenario("[Nominal]", "failed", error="TimeoutError")]
    failures = [BehaveFailure("[Nominal]", "Quand je clique", "ui_timeout",
                              "TimeoutError: locator not found")]
    v = st.derive_verdict(_outcome(scenarios, failures))
    assert v.execution_status == st.EXEC_TECHNICAL_ERROR
    assert v.functional_status == st.FUNC_INDETERMINE


def test_non_conforme_is_never_masked_by_technical_failure():
    """Un vrai constat produit surface même si un autre scénario casse techniquement."""
    scenarios = [
        BehaveScenario("[Erreur] métier", "failed", error="AssertionError"),
        BehaveScenario("[Nominal] technique", "failed", error="TimeoutError"),
    ]
    failures = [
        BehaveFailure("[Erreur] métier", "Alors erreur affichée", "assertion", "AssertionError: x"),
        BehaveFailure("[Nominal] technique", "Quand je vais", "ui_timeout", "TimeoutError: y"),
    ]
    v = st.derive_verdict(_outcome(scenarios, failures))
    # Exécution dégradée par la panne technique, MAIS le fonctionnel reste non_conforme.
    assert v.execution_status == st.EXEC_TECHNICAL_ERROR
    assert v.functional_status == st.FUNC_NON_CONFORME


def test_mixed_pass_and_business_failure_is_success_non_conforme():
    scenarios = [
        BehaveScenario("[Nominal] ok", "passed"),
        BehaveScenario("[Erreur] métier", "failed", error="AssertionError"),
    ]
    failures = [BehaveFailure("[Erreur] métier", "Alors x", "assertion", "AssertionError: z")]
    v = st.derive_verdict(_outcome(scenarios, failures))
    assert v.execution_status == st.EXEC_SUCCESS
    assert v.functional_status == st.FUNC_NON_CONFORME
    assert v.scenarios_passed == 1 and v.scenarios_failed == 1


def test_failed_dry_run_is_technical_error_indetermine():
    v = st.derive_verdict(ExecutionOutcome("m", dry_run_passed=False, real_run=None))
    assert v.execution_status == st.EXEC_TECHNICAL_ERROR
    assert v.functional_status == st.FUNC_INDETERMINE


def test_subprocess_crash_is_technical_error():
    v = st.derive_verdict(_outcome([], [], dry_ok=True, returncode=-2))
    assert v.execution_status == st.EXEC_TECHNICAL_ERROR
    assert v.functional_status == st.FUNC_INDETERMINE


def test_axes_are_independent_all_combinations_reachable():
    """Les quatre combinaisons utiles (success/tech × conforme/non_conforme/indetermine)."""
    green = st.derive_verdict(_outcome([BehaveScenario("a", "passed")], []))
    bug = st.derive_verdict(_outcome([BehaveScenario("b", "failed", error="AssertionError")],
                                     [BehaveFailure("b", "s", "assertion", "AssertionError")]))
    broken = st.derive_verdict(_outcome([BehaveScenario("c", "failed", error="Timeout")],
                                        [BehaveFailure("c", "s", "ui_timeout", "TimeoutError")]))
    combos = {(green.execution_status, green.functional_status),
              (bug.execution_status, bug.functional_status),
              (broken.execution_status, broken.functional_status)}
    assert (st.EXEC_SUCCESS, st.FUNC_CONFORME) in combos
    assert (st.EXEC_SUCCESS, st.FUNC_NON_CONFORME) in combos
    assert (st.EXEC_TECHNICAL_ERROR, st.FUNC_INDETERMINE) in combos
