"""Routes des exécutions : liste (onglet Exécution), détail à deux axes, et rapport
(JSON + rendu HTML réutilisant le pilier reporting)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse

from testpilot.api import schemas
from testpilot.api.deps import get_conn
from testpilot.api.services import report_service, run_service
from testpilot.reporting import report as report_mod
from testpilot.store.repositories import ExecutionRepo

router = APIRouter(prefix="/api/executions", tags=["executions"])


@router.get("", response_model=list[schemas.ExecutionSummary])
def list_executions(limit: int = 50, conn=Depends(get_conn)):
    return [
        schemas.execution_summary(r, running=run_service.is_running(r["id"]))
        for r in ExecutionRepo(conn).list_recent(limit)
    ]


@router.get("/{execution_id}", response_model=schemas.ExecutionDetail)
def get_execution(execution_id: int, conn=Depends(get_conn)):
    execs = ExecutionRepo(conn)
    row = execs.get(execution_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"exécution {execution_id} introuvable")
    summary = schemas.execution_summary(row, running=run_service.is_running(execution_id))
    scenarios = [schemas.scenario_result_out(s) for s in execs.list_scenario_results(execution_id)]
    return schemas.ExecutionDetail(**summary.model_dump(), scenarios=scenarios)


@router.get("/{execution_id}/report")
def get_report_json(execution_id: int, conn=Depends(get_conn)):
    report = report_service.build_report_for_execution(conn, execution_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"exécution {execution_id} introuvable")
    return report.to_dict()


@router.get("/{execution_id}/report.html", response_class=HTMLResponse)
def get_report_html(execution_id: int, conn=Depends(get_conn)):
    report = report_service.build_report_for_execution(conn, execution_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"exécution {execution_id} introuvable")
    return HTMLResponse(content=report_mod.render_html(report))
