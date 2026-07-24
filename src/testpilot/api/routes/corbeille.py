"""La CORBEILLE — ce qui a été supprimé, et comment le récupérer (lot B, 2026-07-24).

Sans ces routes, la suppression douce serait invisible : l'utilisateur verrait ses éléments
disparaître sans jamais pouvoir les revoir ni les rendre. Le §7 exige que « nettoyer » signifie
**archiver puis repartir propre** — archiver sans pouvoir désarchiver n'est qu'une destruction
qui s'ignore.

Trois gestes, et leur asymétrie est voulue :

  • **lister** ce qui est à la corbeille — pour un projet donné ;
  • **restaurer** — l'inverse exact de la suppression ;
  • **purger** — la destruction, définitive. Elle n'est possible que sur ce qui est DÉJÀ à la
    corbeille : purger directement contournerait la corbeille et la rendrait décorative.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from testpilot.api import erreurs
from testpilot.api.deps import get_conn
from testpilot.store.repositories import (
    CaseGroupRepo,
    CaseRepo,
    ModuleRepo,
    ProjectRepo,
)

router = APIRouter(prefix="/api", tags=["corbeille"])

# Le type d'élément → son dépôt. Une table plutôt qu'une cascade de `if` : ajouter un type se
# fait ici, et l'API refuse d'emblée tout type inconnu au lieu de le traiter par défaut.
_DEPOTS = {
    "projet": ProjectRepo,
    "module": ModuleRepo,
    "specification": CaseGroupRepo,
    "cas": CaseRepo,
}


class ElementCorbeille(BaseModel):
    """Un élément supprimé. `deleted_by` est le nom déclaré à la connexion (lot 2) : une
    signature, pas une identité vérifiée — l'écran doit le présenter comme telle."""
    type: str
    id: int
    titre: str
    deleted_at: str
    deleted_by: str = ""


def _depot(conn, type_element: str):
    classe = _DEPOTS.get(type_element)
    if classe is None:
        raise erreurs.ErreurMetier(
            "requete_invalide",
            f"type d'élément inconnu : « {type_element} » "
            f"(attendu : {', '.join(sorted(_DEPOTS))})")
    return classe(conn)


@router.get("/projects/{project_id}/corbeille", response_model=list[ElementCorbeille])
def lister(project_id: int, conn=Depends(get_conn)):
    """Ce qui a été supprimé DANS ce projet, le plus récent d'abord."""
    return [ElementCorbeille(**e) for e in ProjectRepo(conn).corbeille(project_id)]


@router.post("/corbeille/{type_element}/{element_id}/restaurer", status_code=204)
def restaurer(type_element: str, element_id: int, conn=Depends(get_conn)):
    """Sort l'élément de la corbeille.

    ⚠️ Restaurer un enfant ne ressuscite PAS son parent supprimé : le cas resterait invisible
    tant que son module l'est. C'est la vérité, pas un défaut — et l'écran doit le dire plutôt
    que de laisser croire à un échec.
    """
    _depot(conn, type_element).restaurer(element_id)
    return Response(status_code=204)


@router.delete("/corbeille/{type_element}/{element_id}", status_code=204)
def purger(type_element: str, element_id: int, conn=Depends(get_conn)):
    """DÉTRUIT définitivement. Refuse ce qui n'est pas déjà à la corbeille."""
    try:
        _depot(conn, type_element).purger(element_id)
    except ValueError as exc:
        raise erreurs.ErreurMetier("etat_incompatible", str(exc)) from exc
    return Response(status_code=204)
