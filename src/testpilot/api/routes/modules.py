"""Routes du module : détail (fil d'Ariane) et ajout d'un cas à partir d'une SPEC.

« Ajouter un cas » déclenche le flux spec → analyse → génération → gate (décision 0006) :
on ne crée jamais un cas sans version ni Gherkin. La génération étant longue et coûteuse,
elle tourne en tâche de fond (202 + polling du job), comme les exécutions.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from testpilot.api import schemas
from testpilot.api.deps import get_conn
from testpilot.api.services import generation_service
from testpilot.store.repositories import ModuleRepo, ProjectRepo

router = APIRouter(prefix="/api/modules", tags=["modules"])

_ERROR_STATUS = {"not_found": 404, "invalid_spec": 422}


@router.get("/{module_id}", response_model=schemas.ModuleDetail)
def get_module(module_id: int, conn=Depends(get_conn)):
    module = ModuleRepo(conn).get(module_id)
    if module is None:
        raise HTTPException(status_code=404, detail=f"module {module_id} introuvable")
    project = ProjectRepo(conn).get(module["project_id"])
    return schemas.ModuleDetail(
        module=schemas.module_summary(module | {"case_count": _case_count(conn, module_id)}),
        project=schemas.ProjectRef(id=project["id"], name=project["name"]),
    )


def _case_count(conn, module_id: int) -> int:
    return conn.execute("SELECT COUNT(*) AS n FROM test_case WHERE module_id=?",
                        (module_id,)).fetchone()["n"]


@router.post("/{module_id}/cases", response_model=schemas.GenerationJobOut, status_code=202)
def add_case(module_id: int, body: schemas.AddCaseIn, background: BackgroundTasks,
             conn=Depends(get_conn)):
    spec = body.spec_content
    if not spec and body.spec_path:
        path = Path(body.spec_path)
        if not path.is_file():
            raise HTTPException(status_code=422, detail=f"spécification introuvable : {path}")
        spec = path.read_text(encoding="utf-8")

    try:
        job_id, params = generation_service.start_generation(
            conn, module_id, spec_content=spec, title=body.title, author=body.author)
    except generation_service.GenerationError as err:
        raise HTTPException(status_code=_ERROR_STATUS.get(err.code, 400), detail=err.detail)

    background.add_task(generation_service.run_generation, job_id, **params)
    return schemas.GenerationJobOut(job_id=job_id, status="running")


@router.get("/jobs/{job_id}", response_model=schemas.GenerationJobOut)
def get_job(job_id: str):
    job = generation_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job introuvable")
    return schemas.GenerationJobOut(job_id=job_id, status=job["status"],
                                    case_id=job["case_id"], error=job["error"])
