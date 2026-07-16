"""Reconstruction du rapport à deux axes depuis la base (sans relire de fichier).

Le rapport est rebâti à la demande depuis l'exécution persistée (execution + scenario_result
+ repair_attempt), via ``reporting.build_report`` — la même logique que le CLI, mais alimentée
par le référentiel plutôt que par un ``ExecutionOutcome`` en mémoire.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from testpilot.reporting import report as report_mod
from testpilot.store.repositories import (
    CaseRepo,
    ExecutionRepo,
    RepairRepo,
    VersionRepo,
)
from testpilot.verdict.defect_origin import DefectVerdict
from testpilot.verdict.status import CaseVerdict, ScenarioVerdict


def _verdict_from_db(execution: dict, scenario_rows: list[dict]) -> CaseVerdict:
    scenarios = [
        ScenarioVerdict(
            name=s["scenario_name"],
            execution_status=s["execution_status"],
            functional_status=s["functional_status"],
            failure_type=s.get("failure_type", ""),
            cause_category=s.get("cause_category", ""),
            error=s.get("error_summary", ""),
        )
        for s in scenario_rows
    ]
    return CaseVerdict(
        execution_status=execution["execution_status"],
        functional_status=execution["functional_status"],
        scenarios=scenarios,
        scenarios_passed=execution.get("scenarios_passed", 0),
        scenarios_failed=execution.get("scenarios_failed", 0),
    )


@dataclass
class _TentativeRapportee(DefectVerdict):
    """`DefectVerdict` + ce que l'agent a tenté (décision 0014).

    Sous-classe locale plutôt qu'un champ ajouté à `DefectVerdict` : celui-ci est un verdict
    d'ORIGINE (module pur du pilier verdict), pas une tentative de réparation. Les mélanger
    ferait remonter une notion de réparation dans un module qui n'en connaît aucune.
    """

    what_was_tried: str = ""


def _repairs_from_db(repair_rows: list[dict]) -> list[DefectVerdict]:
    return [
        _TentativeRapportee(
            cause_category=r.get("cause_category", ""),
            defect_origin=r.get("defect_origin", "indetermine"),
            confirmation_status=r.get("confirmation_status", "not_required"),
            what_was_tried=r.get("what_was_tried", "") or "",
        )
        for r in repair_rows
    ]


def build_report_for_execution(conn: sqlite3.Connection, execution_id: int):
    """Rebâtit le ``TestReport`` d'une exécution. None si l'exécution n'existe pas."""
    execs = ExecutionRepo(conn)
    execution = execs.get(execution_id)
    if execution is None:
        return None

    case = CaseRepo(conn).get(execution["test_case_id"])
    version = VersionRepo(conn).get(execution["version_id"])
    verdict = _verdict_from_db(execution, execs.list_scenario_results(execution_id))
    repairs = _repairs_from_db(RepairRepo(conn).list_for_execution(execution_id))

    return report_mod.build_report(
        verdict,
        # Affichage : nom métier du module (repli sur le slug technique si non rattaché).
        module_name=(case.get("module_name") or case.get("feature_slug") or "") if case else "",
        title=case["title"] if case else "",
        version_number=version["version_number"] if version else 1,
        cost_usd=execution.get("cost_usd", 0.0),
        cost_source="estimated",
        iterations=execution.get("iterations", 0),
        duration_seconds=execution.get("duration_seconds", 0.0),
        repairs=repairs,
        generated_at=execution.get("started_at"),
    )
