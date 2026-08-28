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

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from testpilot.api import access, erreurs
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


def _project_id_depuis_element(conn, type_element: str, element_id: int) -> int | None:
    """Résout le projet d'un élément de la CORBEILLE (2026-08-11) — SANS filtrer sur `deleted_at`,
    contrairement aux résolveurs génériques d'`access.py` : ces routes manipulent PRÉCISÉMENT des
    éléments déjà supprimés. `CaseRepo.get()`/`ModuleRepo.get()`/`CaseGroupRepo.get()` filtrent
    tous sur les lignes VIVANTES — les réutiliser ici renverrait systématiquement « introuvable »
    pour l'élément même que `restaurer`/`purger` doivent traiter (piège trouvé en planifiant)."""
    if type_element == "projet":
        return element_id
    if type_element == "module":
        ligne = conn.execute("SELECT project_id FROM module WHERE id=?", (element_id,)).fetchone()
        return ligne["project_id"] if ligne else None
    if type_element == "specification":
        ligne = conn.execute(
            "SELECT m.project_id AS project_id FROM case_group g"
            " JOIN module m ON g.module_id = m.id WHERE g.id = ?", (element_id,)).fetchone()
        return ligne["project_id"] if ligne else None
    if type_element == "cas":
        ligne = conn.execute(
            "SELECT m.project_id AS project_id FROM test_case tc"
            " JOIN module m ON tc.module_id = m.id WHERE tc.id = ?", (element_id,)).fetchone()
        return ligne["project_id"] if ligne else None
    return None


def require_corbeille_access(type_element: str, element_id: int, request: Request,
                             conn=Depends(get_conn)) -> str:
    """Dépendance dédiée (2026-08-11), même contrat EXACT que `access.require_project_access` —
    404 si `no_access` (jamais 403), 403 si écriture et rôle effectif sous Testeur.

    Dédiée plutôt que `access.require_project_access_depuis()` : `type_element`/`element_id` sont
    POLYMORPHES (un type d'élément différent par appel, y compris `type_element="projet"`), ce
    qu'aucun résolveur unique de `access.py` ne couvre. **Le trou le plus grave fermé par ce
    chantier** : `purger` est IRRÉVERSIBLE, et pouvait jusqu'ici détruire un projet entier (ou
    n'importe lequel de ses modules/sections/cas) sans le moindre contrôle d'accès."""
    utilisateur = getattr(request.state, "user", None)
    if utilisateur is None:
        raise HTTPException(status_code=401, detail="session requise")

    # Un `type_element` inconnu est une erreur de REQUÊTE (422, message qui liste les types
    # valides) — pas une question d'accès. Vérifié ICI, avant la résolution, pour ne pas la
    # transformer en 404 « ressource introuvable » qui masquerait le vrai problème.
    if type_element not in _DEPOTS:
        raise erreurs.ErreurMetier(
            "requete_invalide",
            f"type d'élément inconnu : « {type_element} » "
            f"(attendu : {', '.join(sorted(_DEPOTS))})")

    # Refus fermé : une ressource inconnue ou orpheline n'a aucun périmètre d'autorisation
    # vérifiable. C'est particulièrement important ici puisque `purger` est irréversible.
    project_id = _project_id_depuis_element(conn, type_element, element_id)
    if project_id is None:
        raise HTTPException(status_code=404, detail="ressource introuvable")

    role = access.role_effectif_projet(conn, utilisateur, project_id)
    if role == access.ACCES_PROJET_REFUSE:
        raise HTTPException(status_code=404, detail=f"projet {project_id} introuvable")
    # La corbeille est une fonction d'administration du projet. La purge est irréversible et la
    # restauration peut ressusciter toute une arborescence : un Testeur ne doit pas les obtenir
    # en contournant l'interface.
    if not access.role_suffisant(role, access.ROLE_ADMIN):
        raise HTTPException(status_code=403, detail="droits insuffisants")
    return role


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


@router.get("/projects/{project_id}/corbeille", response_model=list[ElementCorbeille],
           dependencies=[Depends(access.require_project_access)])
def lister(project_id: int, conn=Depends(get_conn)):
    """Ce qui a été supprimé DANS ce projet, le plus récent d'abord."""
    return [ElementCorbeille(**e) for e in ProjectRepo(conn).corbeille(project_id)]


@router.post("/corbeille/{type_element}/{element_id}/restaurer", status_code=204,
            dependencies=[Depends(require_corbeille_access)])
def restaurer(type_element: str, element_id: int, conn=Depends(get_conn)):
    """Sort l'élément de la corbeille.

    ⚠️ Restaurer un enfant ne ressuscite PAS son parent supprimé : le cas resterait invisible
    tant que son module l'est. C'est la vérité, pas un défaut — et l'écran doit le dire plutôt
    que de laisser croire à un échec.
    """
    _depot(conn, type_element).restaurer(element_id)
    return Response(status_code=204)


@router.delete("/corbeille/{type_element}/{element_id}", status_code=204,
              dependencies=[Depends(require_corbeille_access)])
def purger(type_element: str, element_id: int, conn=Depends(get_conn)):
    """DÉTRUIT définitivement. Refuse ce qui n'est pas déjà à la corbeille."""
    try:
        _depot(conn, type_element).purger(element_id)
    except ValueError as exc:
        raise erreurs.ErreurMetier("etat_incompatible", str(exc)) from exc
    return Response(status_code=204)
