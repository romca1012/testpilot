"""Plans de test (migration 43) — regroupe plusieurs campagnes SOUS UN MÊME rapport consolidé.

Purement organisationnel : ne change rien à l'exécution ni au lancement d'un run — c'est la
troisième couche au-dessus (`Projet → Plan → Campagnes → Cas → Résultats`). Gardé au même
plancher que la création d'une campagne (Testeur+, via `require_project_access`), pas le
plancher plus strict des planifications (`routes/schedules.py`, Dev+) : un Plan ne coûte rien à
exécuter, il ne fait qu'organiser ce qui existe déjà.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from testpilot.api import access, schemas
from testpilot.api.deps import get_conn
from testpilot.store.repositories import PlanRepo, ProjectRepo, RunRepo

router = APIRouter(tags=["plans"])


def _out(plan: dict) -> schemas.PlanOut:
    return schemas.PlanOut(
        id=plan["id"], project_id=plan["project_id"], name=plan["name"],
        description=plan.get("description", ""), refs=plan.get("refs", ""),
        created_by=plan.get("created_by", ""), created_at=plan.get("created_at", ""))


@router.post("/api/projects/{project_id}/plans", response_model=schemas.PlanOut, status_code=201,
            dependencies=[Depends(access.require_project_access)])
def create_plan(project_id: int, body: schemas.PlanIn, request: Request, conn=Depends(get_conn)):
    if ProjectRepo(conn).get(project_id) is None:
        raise HTTPException(status_code=404, detail=f"projet {project_id} introuvable")
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="le nom du plan est requis")
    plan_id = PlanRepo(conn).create(
        project_id=project_id, name=body.name.strip(), description=body.description,
        refs=body.refs, created_by=access.utilisateur_de(request))
    return _out(PlanRepo(conn).get(plan_id))


@router.get("/api/projects/{project_id}/plans", response_model=list[schemas.PlanOut],
           dependencies=[Depends(access.require_project_access)])
def list_plans(project_id: int, conn=Depends(get_conn)):
    if ProjectRepo(conn).get(project_id) is None:
        raise HTTPException(status_code=404, detail=f"projet {project_id} introuvable")
    return [_out(p) for p in PlanRepo(conn).list_for_project(project_id)]


@router.get("/api/plans/{plan_id}", response_model=schemas.PlanDetailOut,
           dependencies=[Depends(access.require_project_access_depuis(
               "plan_id", access.project_id_depuis_plan))])
def get_plan(plan_id: int, conn=Depends(get_conn)):
    plan = PlanRepo(conn).get(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"plan {plan_id} introuvable")
    runs = [
        schemas.RunSummary(
            id=r["id"], project_id=r["project_id"], name=r["name"], status=r["status"],
            selection_mode=r["selection_mode"], mode=r.get("mode", "automatique"),
            case_count=(r["frozen_count"] if r["selection_mode"] == "frozen"
                       else len(RunRepo(conn).case_ids(r["id"]))),
            tested_count=r.get("tested_count", 0), manuel_count=r.get("manuel_count", 0),
            is_archived=bool(r.get("is_archived")), created_at=r.get("created_at", ""),
            plan_id=r.get("plan_id"))
        for r in PlanRepo(conn).runs_of_plan(plan_id)
    ]
    return schemas.PlanDetailOut(plan=_out(plan), runs=runs)


@router.post("/api/plans/{plan_id}/runs/{run_id}", response_model=schemas.PlanDetailOut,
            dependencies=[Depends(access.require_project_access_depuis(
                "plan_id", access.project_id_depuis_plan))])
def assign_run(plan_id: int, run_id: int, conn=Depends(get_conn)):
    """Rattache une campagne EXISTANTE à ce plan — ne crée ni ne modifie la campagne elle-même."""
    plan = PlanRepo(conn).get(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"plan {plan_id} introuvable")
    run = RunRepo(conn).get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"exécution {run_id} introuvable")
    if run["project_id"] != plan["project_id"]:
        raise HTTPException(status_code=422,
                            detail="cette campagne appartient à un autre projet que ce plan")
    PlanRepo(conn).assign_run(plan_id, run_id)
    return get_plan(plan_id, conn)


@router.delete("/api/plans/{plan_id}/runs/{run_id}", response_model=schemas.PlanDetailOut,
              dependencies=[Depends(access.require_project_access_depuis(
                  "plan_id", access.project_id_depuis_plan))])
def unassign_run(plan_id: int, run_id: int, conn=Depends(get_conn)):
    if PlanRepo(conn).get(plan_id) is None:
        raise HTTPException(status_code=404, detail=f"plan {plan_id} introuvable")
    PlanRepo(conn).unassign_run(run_id)
    return get_plan(plan_id, conn)
