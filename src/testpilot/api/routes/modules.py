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
from testpilot.store.repositories import CaseRepo, ModuleRepo, ProjectRepo

router = APIRouter(prefix="/api/modules", tags=["modules"])

# 409 pour `duplicate` : la requête est bien formée, c'est l'état du référentiel qui s'y oppose.
_ERROR_STATUS = {"not_found": 404, "invalid_spec": 422, "duplicate": 409}


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


@router.put("/{module_id}/cases/order", response_model=list[schemas.CaseSummary])
def reorder_cases(module_id: int, body: schemas.ReorderCasesIn, conn=Depends(get_conn)):
    """Fixe l'ordre d'AFFICHAGE des cas du module (décision 0009).

    ⚠️ Ordre de LECTURE, jamais d'exécution : celle-ci suit l'ordre des scénarios du `.feature`.
    Cet endpoint n'écrit que `position`, lu par le seul affichage.

    En LOT et transactionnel : un glissement change N positions ; N appels laisseraient un ordre
    incohérent si l'un échouait. La liste doit décrire exactement les cas du module (409 sinon) —
    une liste partielle laisserait des cas à une position périmée.
    """
    if ModuleRepo(conn).get(module_id) is None:
        raise HTTPException(status_code=404, detail=f"module {module_id} introuvable")
    try:
        CaseRepo(conn).reorder(module_id, body.case_ids)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return [schemas.case_summary(r) for r in CaseRepo(conn).list_all(module_id=module_id)]


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
