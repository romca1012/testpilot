"""Routes des cas de test : liste, détail (Gherkin + versions + relectures + exécutions),
déclenchement d'exécution, et action de relecture (gate actionnable depuis l'UI)."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from testpilot.api import schemas
from testpilot.api.deps import get_conn
from testpilot.api.services import run_service
from testpilot.generation import assertion_lint
from testpilot.store.repositories import (
    CaseRepo,
    ExecutionRepo,
    ReviewRepo,
    VersionRepo,
)
from testpilot.verdict import review_gate

router = APIRouter(prefix="/api/cases", tags=["cases"])

_RUN_ERROR_STATUS = {"not_found": 404, "no_version": 409, "needs_review": 409}


@router.get("", response_model=list[schemas.CaseSummary])
def list_cases(project_id: int | None = None, module_id: int | None = None, conn=Depends(get_conn)):
    rows = CaseRepo(conn).list_all(project_id=project_id, module_id=module_id)
    return [schemas.case_summary(r) for r in rows]


@router.get("/{case_id}", response_model=schemas.CaseDetail)
def get_case(case_id: int, conn=Depends(get_conn)):
    case = CaseRepo(conn).get(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"cas {case_id} introuvable")

    # Fil d'Ariane Projet > Module > Cas.
    project = module = None
    if case.get("project_id"):
        project = schemas.ProjectRef(id=case["project_id"], name=case.get("project_name") or "—")
    if case.get("module_id"):
        module = schemas.ModuleRef(id=case["module_id"], name=case.get("module_name") or "—")

    version_rows = VersionRepo(conn).list_for_case(case_id)
    version_id = case.get("current_version_id")
    gate = None
    if version_id:
        decision = review_gate.evaluate_gate(ReviewRepo(conn), version_id)
        # Lint non-bloquant des assertions de la version courante (décision 0008) : informe le
        # relecteur sans jamais changer `allowed` — le gate reste souverain.
        current = next((v for v in version_rows if v["id"] == version_id), None)
        warnings = assertion_lint.lint_steps(current.get("steps_content", "") if current else "")
        gate = schemas.GateOut(allowed=decision.allowed, needs_review=decision.needs_review,
                               reason=decision.reason,
                               lint_warnings=[schemas.LintWarning(**w) for w in warnings])
    executions = [
        schemas.execution_summary(r, running=run_service.is_running(r["id"]))
        for r in ExecutionRepo(conn).list_for_case(case_id)
    ]
    return schemas.CaseDetail(
        case=schemas.case_summary(case),
        project=project,
        module=module,
        current_version_id=version_id,
        versions=[schemas.version_out(v) for v in version_rows],
        reviews=[schemas.review_out(r) for r in ReviewRepo(conn).list_for_case(case_id)],
        executions=executions,
        gate=gate,
    )


@router.patch("/{case_id}", response_model=schemas.CaseSummary)
def update_case(case_id: int, body: schemas.CasePatch, conn=Depends(get_conn)):
    """Met à jour la priorité de LECTURE d'un cas (étiquette — aucun ordre d'exécution)."""
    cases = CaseRepo(conn)
    if cases.get(case_id) is None:
        raise HTTPException(status_code=404, detail=f"cas {case_id} introuvable")
    if body.priority not in ("low", "medium", "high"):
        raise HTTPException(status_code=422, detail="priorité invalide (low | medium | high)")
    cases.set_priority(case_id, body.priority)
    return schemas.case_summary(cases.get(case_id))


@router.get("/{case_id}/scenarios", response_model=list[schemas.ScenarioResultOut])
def get_case_scenarios(case_id: int, conn=Depends(get_conn)):
    """Scénarios du DERNIER run du cas (dépliage) — vide si jamais exécuté.

    Le scénario n'est pas une entité de premier rang : il n'existe qu'au travers d'une
    exécution. On expose donc la granularité fine là où elle existe réellement.
    """
    execs = ExecutionRepo(conn)
    runs = execs.list_for_case(case_id)
    if not runs:
        return []
    last = max(runs, key=lambda r: r["id"])
    return [schemas.scenario_result_out(s) for s in execs.list_scenario_results(last["id"])]


@router.post("/{case_id}/runs", response_model=schemas.RunResponse, status_code=202)
def start_run(case_id: int, background: BackgroundTasks, conn=Depends(get_conn)):
    try:
        eid, module, cid, vid = run_service.trigger_run(conn, case_id)
    except run_service.RunError as err:
        raise HTTPException(status_code=_RUN_ERROR_STATUS.get(err.code, 400), detail=err.detail)
    background.add_task(run_service.run_execution, eid, module, cid, vid)
    return schemas.RunResponse(execution_id=eid, status="running")


@router.post("/{case_id}/review", response_model=schemas.ReviewResponse)
def submit_review(case_id: int, body: schemas.ReviewIn, conn=Depends(get_conn)):
    case = CaseRepo(conn).get(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"cas {case_id} introuvable")
    version_id = case.get("current_version_id")
    if not version_id:
        raise HTTPException(status_code=409, detail="aucune version à relire pour ce cas")

    decision = run_service.submit_review(
        conn, case_id, version_id, approved=body.approved,
        reviewer=body.reviewer, comment=body.comment)
    # Un rejet repositionne le cas « à relire » ; l'approbation n'ouvre que le gate.
    if not body.approved:
        CaseRepo(conn).set_validation_status(case_id, "to_review")
    refreshed = CaseRepo(conn).get(case_id)
    return schemas.ReviewResponse(
        decision="approved" if body.approved else "rejected",
        validation_status=refreshed["validation_status"],
        gate=schemas.GateOut(allowed=decision.allowed, needs_review=decision.needs_review,
                             reason=decision.reason),
    )
