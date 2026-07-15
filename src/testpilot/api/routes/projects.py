"""Routes de la hiérarchie §7 : projets et leurs modules.

Le projet est le contexte de premier niveau (au-dessus des onglets Gestion / Exécution) ;
les modules regroupent les cas d'un projet. Aucune auth à ce stade.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from testpilot.api import schemas
from testpilot.api.deps import get_conn
from testpilot.store.repositories import ModuleRepo, ProjectRepo

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=list[schemas.ProjectSummary])
def list_projects(conn=Depends(get_conn)):
    return [schemas.project_summary(r) for r in ProjectRepo(conn).list_all()]


@router.post("", response_model=schemas.ProjectSummary, status_code=201)
def create_project(body: schemas.ProjectIn, conn=Depends(get_conn)):
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="le nom du projet est requis")
    pid = ProjectRepo(conn).create(name=body.name.strip(), description=body.description)
    return schemas.ProjectSummary(id=pid, name=body.name.strip(), description=body.description)


@router.get("/{project_id}/modules", response_model=list[schemas.ModuleSummary])
def list_modules(project_id: int, conn=Depends(get_conn)):
    if ProjectRepo(conn).get(project_id) is None:
        raise HTTPException(status_code=404, detail=f"projet {project_id} introuvable")
    return [schemas.module_summary(r) for r in ModuleRepo(conn).list_for_project(project_id)]


@router.post("/{project_id}/modules", response_model=schemas.ModuleSummary, status_code=201)
def create_module(project_id: int, body: schemas.ModuleIn, conn=Depends(get_conn)):
    if ProjectRepo(conn).get(project_id) is None:
        raise HTTPException(status_code=404, detail=f"projet {project_id} introuvable")
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="le nom du module est requis")
    mid = ModuleRepo(conn).create(project_id=project_id, name=body.name.strip(),
                                  description=body.description)
    return schemas.ModuleSummary(id=mid, project_id=project_id, name=body.name.strip(),
                                 description=body.description, case_count=0)
