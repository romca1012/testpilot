"""Routes du RUN — une campagne de N cas (décision `0022` n°8, incrément 1).

Un run REGROUPE des cas à jouer ensemble ; le résultat d'un cas dans un run est une exécution
rattachée. Créer un run ne lance RIEN (`0022` 8.c.1) : il naît en brouillon, le lancement est
un geste explicite (incrément 1b). Ici : créer / lister / détailler.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from testpilot.api import schemas
from testpilot.api.deps import get_conn
from testpilot.store.repositories import ProjectRepo, RunRepo

router = APIRouter(tags=["runs"])


def _summary(run: dict, case_count: int) -> schemas.RunSummary:
    return schemas.RunSummary(
        id=run["id"], project_id=run["project_id"], name=run["name"], status=run["status"],
        selection_mode=run["selection_mode"], case_count=case_count,
        tested_count=run.get("tested_count", 0), created_at=run.get("created_at", ""))


@router.post("/api/projects/{project_id}/runs", response_model=schemas.RunSummary, status_code=201)
def create_run(project_id: int, body: schemas.RunIn, conn=Depends(get_conn)):
    """Crée une campagne en BROUILLON. Le mode `all` est vivant (les cas du projet) ; `frozen`
    fige la sélection fournie. Le filtrage dynamique n'est pas géré (422)."""
    if ProjectRepo(conn).get(project_id) is None:
        raise HTTPException(status_code=404, detail=f"projet {project_id} introuvable")
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="le nom de l'exécution est requis")
    if body.selection_mode not in ("all", "frozen"):
        raise HTTPException(status_code=422,
                            detail="le filtrage dynamique n'est pas encore disponible — "
                                   "choisissez « tous les cas » ou une sélection figée")
    if body.selection_mode == "frozen" and not body.case_ids:
        raise HTTPException(status_code=422,
                            detail="une sélection figée doit contenir au moins un cas")
    repo = RunRepo(conn)
    run_id = repo.create(project_id=project_id, name=body.name.strip(),
                         description=body.description, refs=body.refs,
                         selection_mode=body.selection_mode, case_ids=body.case_ids)
    return _summary(repo.get(run_id), len(repo.case_ids(run_id)))


@router.get("/api/projects/{project_id}/runs", response_model=list[schemas.RunSummary])
def list_runs(project_id: int, conn=Depends(get_conn)):
    if ProjectRepo(conn).get(project_id) is None:
        raise HTTPException(status_code=404, detail=f"projet {project_id} introuvable")
    repo = RunRepo(conn)
    out = []
    for run in repo.list_for_project(project_id):
        count = run["frozen_count"] if run["selection_mode"] == "frozen" else len(repo.case_ids(run["id"]))
        out.append(_summary(run, count))
    return out


@router.get("/api/runs/{run_id}", response_model=schemas.RunDetailOut)
def get_run(run_id: int, conn=Depends(get_conn)):
    """Le run + ses cas, chacun avec son résultat DANS ce run (ou None = non testé)."""
    repo = RunRepo(conn)
    run = repo.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"exécution {run_id} introuvable")
    cases = [schemas.RunCaseResult(
        id=c["id"], title=c["title"],
        execution_status=(c["result"] or {}).get("execution_status") if c["result"] else None,
        functional_status=(c["result"] or {}).get("functional_status") if c["result"] else None,
        execution_id=(c["result"] or {}).get("id") if c["result"] else None)
        for c in repo.cases_with_results(run_id)]
    return schemas.RunDetailOut(
        run=_summary(run, len(cases)), description=run.get("description", ""),
        refs=run.get("refs", ""), cases=cases)
