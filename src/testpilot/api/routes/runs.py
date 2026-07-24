"""Routes du RUN — une campagne de N cas (décision `0022` n°8, incrément 1).

Un run REGROUPE des cas à jouer ensemble ; le résultat d'un cas dans un run est une exécution
rattachée. Créer un run ne lance RIEN (`0022` 8.c.1) : il naît en brouillon, le lancement est
un geste explicite (incrément 1b). Ici : créer / lister / détailler.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from testpilot.api import erreurs, schemas
from testpilot.api.deps import get_conn
from testpilot.api.services import campaign_service
from testpilot.store.repositories import ProjectRepo, RunRepo

router = APIRouter(tags=["runs"])

def _summary(run: dict, case_count: int) -> schemas.RunSummary:
    return schemas.RunSummary(
        id=run["id"], project_id=run["project_id"], name=run["name"], status=run["status"],
        selection_mode=run["selection_mode"], case_count=case_count,
        tested_count=run.get("tested_count", 0), is_archived=bool(run.get("is_archived")),
        created_at=run.get("created_at", ""))


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


@router.post("/api/runs/{run_id}/launch", response_model=schemas.RunSummary, status_code=202)
def launch_run(run_id: int, background: BackgroundTasks, conn=Depends(get_conn)):
    """LANCE la campagne : exécute ses cas EN SÉQUENCE (tâche de fond).

    Geste explicite (`0022` 8.c.1) — créer un run ne lance rien. Un run vide est refusé : il
    finirait « terminé » sans avoir rien testé, un succès trompeur.
    """
    try:
        params = campaign_service.start_campaign(conn, run_id)
    except campaign_service.CampaignError as err:
        raise erreurs.depuis_service(err.code, err.detail)
    background.add_task(campaign_service.run_campaign, **params)
    repo = RunRepo(conn)
    return _summary(repo.get(run_id), len(repo.case_ids(run_id)))


@router.post("/api/runs/{run_id}/archive", response_model=schemas.RunSummary)
def archive_run(run_id: int, body: schemas.RunArchiveIn, conn=Depends(get_conn)):
    """Clôt (ou rouvre) une campagne. Archivée = LECTURE SEULE : on ne la relance plus.

    Réversible : une clôture par erreur ne doit pas être irrattrapable. Rien n'est effacé —
    archivage ≠ suppression (§2.10).
    """
    repo = RunRepo(conn)
    if repo.get(run_id) is None:
        raise HTTPException(status_code=404, detail=f"exécution {run_id} introuvable")
    repo.archive(run_id, body.archived)
    return _summary(repo.get(run_id), len(repo.case_ids(run_id)))


@router.get("/api/runs/{run_id}", response_model=schemas.RunDetailOut)
def get_run(run_id: int, conn=Depends(get_conn)):
    """Le run + ses cas, chacun avec son résultat DANS ce run (ou None = non testé)."""
    repo = RunRepo(conn)
    run = repo.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"exécution {run_id} introuvable")
    from testpilot.verdict.status import statut_de_test

    cases = []
    for c in repo.cases_with_results(run_id):
        res = c["result"] or {}
        ex, fo = res.get("execution_status"), res.get("functional_status")
        cases.append(schemas.RunCaseResult(
            id=c["id"], title=c["title"], execution_status=ex, functional_status=fo,
            execution_id=res.get("id"),
            # Un cas SANS exécution dans ce run est « non testé » — et c'est la même règle que
            # partout ailleurs, calculée au même endroit.
            statut=statut_de_test(ex, fo)))
    cibles = repo.cibles_du_run(run_id)
    return schemas.RunDetailOut(
        run=_summary(run, len(cases)), description=run.get("description", ""),
        refs=run.get("refs", ""), cases=cases,
        target_url=cibles[0]["target_url"] if cibles else "",
        target_database=cibles[0]["target_database"] if cibles else "",
        target_mixed=len(cibles) > 1)
