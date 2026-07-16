"""Routes de l'arbitrage humain des diagnostics (décision 0013).

Un diagnostic (`repair_attempt`) est une **déduction** de la machine, jamais un constat : une
assertion qui échoue peut venir de l'application, d'un test qui attend la mauvaise chose, ou de
l'environnement. Les distinguer est un jugement humain.

Ce que ces routes ajoutent : la possibilité de **confirmer** ou d'**infirmer** ce jugement.
Jusqu'ici il n'en existait aucune — mesuré : les 8 diagnostics produits avaient tous
`confirmed_by = NULL`. Un `pending_human` attendait une confirmation qui ne pouvait pas arriver,
un `not_required` était irrévocable même faux.

⚠️ Deux invariants tenus ici :
- l'arbitrage ne **réécrit jamais** `defect_origin` (couche distincte) ;
- l'arbitrage ne **recalcule jamais** les deux axes du run (§4.2) : un avis humain ne réécrit pas
  ce qui s'est passé. Il porte sur l'ORIGINE du défaut, pas sur le verdict d'exécution.

Aucun blocage : un diagnostic non tranché ne retient rien. Le gate reste le seul verrou (§4.3).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from testpilot.api import schemas
from testpilot.api.deps import get_conn
from testpilot.store.repositories import RepairRepo

router = APIRouter(prefix="/api/repairs", tags=["repairs"])


@router.get("", response_model=list[schemas.RepairOut])
def list_repairs(project_id: int | None = None, status: str = "pending",
                 conn=Depends(get_conn)):
    """File des diagnostics à trancher.

    `status=pending` (défaut) : ceux qui exigent une confirmation (`pending_human`).
    `status=all` : **y compris les `not_required`** — c'est tout l'objet de 0013, un
    « vrai bug » déduit à tort doit pouvoir être infirmé.
    Les diagnostics déjà arbitrés sont exclus dans les deux cas.
    """
    if status not in ("pending", "all"):
        raise HTTPException(status_code=422, detail="status doit être 'pending' ou 'all'")
    rows = RepairRepo(conn).list_to_arbitrate(project_id=project_id,
                                              pending_only=(status == "pending"))
    return [schemas.repair_out(r) for r in rows]


@router.post("/{attempt_id}/verdict", response_model=schemas.RepairOut)
def set_verdict(attempt_id: int, body: schemas.RepairVerdictIn, conn=Depends(get_conn)):
    """Confirme ou infirme un diagnostic.

    409 si déjà arbitré : écraser en silence effacerait le jugement d'un autre relecteur.
    """
    repo = RepairRepo(conn)
    row = repo.get(attempt_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"diagnostic {attempt_id} introuvable")
    if row.get("human_verdict"):
        raise HTTPException(
            status_code=409,
            detail=f"diagnostic déjà arbitré par {row.get('confirmed_by') or 'un relecteur'} "
                   f"({row['human_verdict']})")
    try:
        repo.set_human_verdict(attempt_id, verdict=body.verdict, origin=body.origin,
                               comment=body.comment,
                               reviewer=body.reviewer.strip() or "anonyme")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return schemas.repair_out(repo.get(attempt_id))
