"""Planifications récurrentes (migration 43) — déclenche automatiquement une campagne sur une
horloge (`scheduler_service.tick()`), en réutilisant TEL QUEL le moteur d'exécution existant.

⚠️ **Créer/éditer/supprimer/activer une planification exige Dev+, PAS Testeur** — à la
différence de la création d'une campagne à la main (Testeur+). Une planification s'exécute SANS
présence humaine : un réglage erroné (ex. « toutes les nuits » sur une sélection trop large)
consomme des coûts LLM/navigateur sans que personne ne le voie partir. La LECTURE (lister/voir)
reste Testeur+, comme pour une campagne.

⚠️ **Aucun champ `mode` nulle part ici** : une planification est TOUJOURS automatique — voir
`schemas.ScheduledRunIn` et `scheduler_service.py`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from testpilot.api import access, schemas
from testpilot.api.deps import get_conn
from testpilot.store.repositories import ProjectRepo, ScheduledRunRepo

router = APIRouter(tags=["schedules"])


def _out(planif: dict) -> schemas.ScheduledRunOut:
    return schemas.ScheduledRunOut(
        id=planif["id"], project_id=planif["project_id"], name=planif["name"],
        selection_mode=planif["selection_mode"], frequency=planif["frequency"],
        hour=planif["hour"], minute=planif["minute"], weekday=planif.get("weekday"),
        is_active=bool(planif.get("is_active", True)), created_by=planif.get("created_by", ""),
        created_at=planif.get("created_at", ""), last_run_id=planif.get("last_run_id"),
        last_triggered_at=planif.get("last_triggered_at"))


@router.post("/api/projects/{project_id}/schedules", response_model=schemas.ScheduledRunOut,
            status_code=201,
            dependencies=[Depends(access.require_project_role(access.ROLE_DEV))])
def create_schedule(project_id: int, body: schemas.ScheduledRunIn, request: Request,
                    conn=Depends(get_conn)):
    if ProjectRepo(conn).get(project_id) is None:
        raise HTTPException(status_code=404, detail=f"projet {project_id} introuvable")
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="le nom de la planification est requis")
    if body.selection_mode not in ("all", "frozen"):
        raise HTTPException(status_code=422,
                            detail="sélection inconnue — « tous les cas » ou une sélection figée")
    if body.selection_mode == "frozen" and not body.case_ids:
        raise HTTPException(status_code=422,
                            detail="une sélection figée doit contenir au moins un cas")
    if body.frequency not in ("daily", "weekly"):
        raise HTTPException(status_code=422,
                            detail="fréquence inconnue — « daily » ou « weekly »")
    if body.frequency == "weekly" and body.weekday is None:
        raise HTTPException(status_code=422,
                            detail="une planification hebdomadaire doit préciser le jour")
    if not (0 <= body.hour <= 23 and 0 <= body.minute <= 59):
        raise HTTPException(status_code=422, detail="heure invalide")
    scheduled_id = ScheduledRunRepo(conn).create(
        project_id=project_id, name=body.name.strip(), selection_mode=body.selection_mode,
        frequency=body.frequency, hour=body.hour, minute=body.minute, weekday=body.weekday,
        case_ids=body.case_ids, created_by=access.utilisateur_de(request))
    return _out(ScheduledRunRepo(conn).get(scheduled_id))


@router.get("/api/projects/{project_id}/schedules", response_model=list[schemas.ScheduledRunOut],
           dependencies=[Depends(access.require_project_access)])
def list_schedules(project_id: int, conn=Depends(get_conn)):
    if ProjectRepo(conn).get(project_id) is None:
        raise HTTPException(status_code=404, detail=f"projet {project_id} introuvable")
    return [_out(p) for p in ScheduledRunRepo(conn).list_for_project(project_id)]


@router.patch("/api/schedules/{scheduled_id}", response_model=schemas.ScheduledRunOut,
             dependencies=[Depends(access.require_project_role_depuis(
                 "scheduled_id", access.project_id_depuis_scheduled_run, access.ROLE_DEV))])
def patch_schedule(scheduled_id: int, body: schemas.ScheduledRunPatchIn, conn=Depends(get_conn)):
    repo = ScheduledRunRepo(conn)
    if repo.get(scheduled_id) is None:
        raise HTTPException(status_code=404, detail=f"planification {scheduled_id} introuvable")
    if body.is_active is not None:
        repo.set_active(scheduled_id, body.is_active)
    return _out(repo.get(scheduled_id))


@router.delete("/api/schedules/{scheduled_id}", status_code=204,
              dependencies=[Depends(access.require_project_role_depuis(
                  "scheduled_id", access.project_id_depuis_scheduled_run, access.ROLE_DEV))])
def delete_schedule(scheduled_id: int, conn=Depends(get_conn)):
    repo = ScheduledRunRepo(conn)
    if repo.get(scheduled_id) is None:
        raise HTTPException(status_code=404, detail=f"planification {scheduled_id} introuvable")
    repo.delete(scheduled_id)
