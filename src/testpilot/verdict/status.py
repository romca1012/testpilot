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
# 4ᵉ verdict (§2bis) : le test a TOURNÉ (exécution=success) mais sa DONNÉE a été refusée —
# l'application n'est pas en cause, c'est le test à corriger. Nouvelle VALEUR de l'axe
# fonctionnel, jamais un 3ᵉ axe : l'invariant « les deux axes ne fusionnent jamais » tient.
FUNC_DONNEE_INVALIDE = "donnee_invalide"


@dataclass
class ScenarioVerdict:
    name: str
    execution_status: str
    functional_status: str
    failure_type: str = ""
    cause_category: str = ""
    error: str = ""
    # Le step en échec — TRACE, jamais critère. Il est écrit par l'agent : le lire pour classer
    # revenait à juger l'agent sur son propre texte (décision 0015, `defect_taxonomy`). Il est
    # transporté puis persisté pour qu'on puisse AUDITER `cause_category` a posteriori — sans
    # lui, aucune classification passée n'est vérifiable.
    step_text: str = ""


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
        step_text = failures[0].step_text if failures else ""
        if cause == dt.ASSERTION_MISMATCH:
            # A tourné techniquement, mais le comportement métier est faux → constat produit.
            return ScenarioVerdict(scenario.name, EXEC_SUCCESS, FUNC_NON_CONFORME,
                                   failure_type, cause, scenario.error, step_text)
        if cause == dt.DONNEE_REFUSEE:
            # A tourné techniquement ; c'est la DONNÉE du test qui a été refusée (4ᵉ verdict) —
            # l'application n'est PAS en cause. On n'accuse plus : on nomme un test à corriger.
            return ScenarioVerdict(scenario.name, EXEC_SUCCESS, FUNC_DONNEE_INVALIDE,
                                   failure_type, cause, scenario.error, step_text)
        # Cause technique (ou indéterminée) → le test n'a pas pu juger le fonctionnel.
        return ScenarioVerdict(scenario.name, EXEC_TECHNICAL_ERROR, FUNC_INDETERMINE,
                               failure_type, cause, scenario.error, step_text)

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
        functional_status = FUNC_NON_CONFORME  # un vrai constat (défaut applicatif) surface toujours
    elif any(v.functional_status == FUNC_DONNEE_INVALIDE for v in verdicts):
        # Sous le non_conforme, au-DESSUS du conforme : un scénario dont la donnée a été refusée
        # n'a rien pu prouver — il ne doit pas être masqué par les scénarios verts (§2bis).
        functional_status = FUNC_DONNEE_INVALIDE
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


# ── Le statut de LECTURE d'un cas (déplacé depuis le frontend le 2026-07-24) ──────────────────
# Les deux axes du §5 sont la vérité ; ce statut est leur PROJECTION en une étiquette unique, pour
# les listes et les tableaux de bord. Il ne remplace jamais les deux axes : il les résume.
#
# ⚠️ **Cette règle vivait UNIQUEMENT en TypeScript.** Filtrer une liste par statut côté serveur
# aurait donc exigé de la réécrire en SQL — deux implémentations de la même règle, qui divergent
# le jour où l'une évolue, et dont l'écart est invisible (les deux « marchent »). On l'a déplacée
# ici : un seul endroit décide, et le frontend lit ce que le serveur a calculé.

STATUT_PASSED = "passed"
STATUT_FAILED = "failed"
STATUT_RETEST = "retest"
STATUT_BLOCKED = "blocked"
STATUT_UNTESTED = "untested"

# Ordre canonique (légende des graphiques, colonnes de filtre).
STATUTS = (STATUT_PASSED, STATUT_BLOCKED, STATUT_RETEST, STATUT_FAILED, STATUT_UNTESTED)


def statut_de_test(execution: str | None, functional: str | None) -> str:
    """Projette les DEUX axes en une étiquette de lecture.

    L'ordre des tests n'est pas décoratif — le fonctionnel prime sur l'exécution :

    - `conforme` → **passed** ;
    - `non_conforme` → **failed** ;
    - `donnee_invalide` → **retest** (4ᵉ verdict) : le test est à corriger. **Jamais `failed`**,
      qui accuserait l'application, ni `passed`, alors que rien n'a été prouvé ;
    - `indetermine` → **retest** s'il a tourné, **untested** s'il n'a jamais été lancé ;
    - sans verdict fonctionnel, c'est le déroulement qui parle : `technical_error` → **blocked**,
      `success` → **passed** ;
    - à défaut → **untested**.
    """
    if functional == FUNC_CONFORME:
        return STATUT_PASSED
    if functional == FUNC_NON_CONFORME:
        return STATUT_FAILED
    if functional == FUNC_DONNEE_INVALIDE:
        return STATUT_RETEST
    if functional == FUNC_INDETERMINE:
        return STATUT_UNTESTED if execution == EXEC_NOT_EXECUTED else STATUT_RETEST
    if execution == EXEC_TECHNICAL_ERROR:
        return STATUT_BLOCKED
    if execution == EXEC_SUCCESS:
        return STATUT_PASSED
    return STATUT_UNTESTED


# Expression SQL équivalente, pour FILTRER et TRIER sans charger la table entière.
# ⚠️ Elle est dérivée de la fonction ci-dessus, et un test compare les deux sur TOUTES les
# combinaisons possibles : sans cette comparaison, la version SQL divergerait un jour en silence.
def sql_statut(execution: str, functional: str) -> str:
    """Rend un CASE SQL calculant le statut depuis deux colonnes nommées."""
    return (
        f"CASE"
        f" WHEN {functional} = '{FUNC_CONFORME}' THEN '{STATUT_PASSED}'"
        f" WHEN {functional} = '{FUNC_NON_CONFORME}' THEN '{STATUT_FAILED}'"
        f" WHEN {functional} = '{FUNC_DONNEE_INVALIDE}' THEN '{STATUT_RETEST}'"
        f" WHEN {functional} = '{FUNC_INDETERMINE}' THEN"
        f"   (CASE WHEN {execution} = '{EXEC_NOT_EXECUTED}' THEN '{STATUT_UNTESTED}'"
        f"         ELSE '{STATUT_RETEST}' END)"
        f" WHEN {execution} = '{EXEC_TECHNICAL_ERROR}' THEN '{STATUT_BLOCKED}'"
        f" WHEN {execution} = '{EXEC_SUCCESS}' THEN '{STATUT_PASSED}'"
        f" ELSE '{STATUT_UNTESTED}' END"
    )
