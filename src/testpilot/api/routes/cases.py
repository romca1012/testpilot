"""Routes des cas de test : liste, détail (Gherkin + versions + relectures + exécutions),
déclenchement d'exécution, et action de relecture (gate actionnable depuis l'UI)."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from testpilot.api import schemas
from testpilot.api.deps import get_conn
from testpilot.api.services import run_service
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
def list_cases(conn=Depends(get_conn)):
    return [schemas.case_summary(r) for r in CaseRepo(conn).list_all()]


@router.get("/{case_id}", response_model=schemas.CaseDetail)
def get_case(case_id: int, conn=Depends(get_conn)):
    case = CaseRepo(conn).get(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"cas {case_id} introuvable")

    version_id = case.get("current_version_id")
    gate = None
    if version_id:
        decision = review_gate.evaluate_gate(ReviewRepo(conn), version_id)
        gate = schemas.GateOut(allowed=decision.allowed, needs_review=decision.needs_review,
                               reason=decision.reason)
    executions = [
        schemas.execution_summary(r, running=run_service.is_running(r["id"]))
        for r in ExecutionRepo(conn).list_for_case(case_id)
    ]
    return schemas.CaseDetail(
        case=schemas.case_summary(case),
        current_version_id=version_id,
        versions=[schemas.version_out(v) for v in VersionRepo(conn).list_for_case(case_id)],
        reviews=[schemas.review_out(r) for r in ReviewRepo(conn).list_for_case(case_id)],
        executions=executions,
        gate=gate,
    )


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
