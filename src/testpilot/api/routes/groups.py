"""Routes de la SPÉCIFICATION (`case_group`) — le CRUD minimal de l'étape 2.

La Spécification est LE DOCUMENT fourni une fois, source des cas qu'on en tirera (décision
`0022`). Une spécification produit **1 à N cas** : le nombre dépend des situations retenues par
l'humain à l'étape de confirmation, jamais d'une découpe automatique.

C'est un conteneur SIMPLE : ni statut, ni version, ni gate, ni coût — tout cela reste sur le CAS.
Ce CRUD ne fait donc qu'écrire un document et le nommer ; il ne déclenche aucune génération et ne
dépense rien. La génération LIRA ce document.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from testpilot.api import access, erreurs, schemas
from testpilot.api.deps import get_conn
from testpilot.store.repositories import CaseGroupRepo, DuplicateName, NotEmpty, ProfondeurInvalide

router = APIRouter(prefix="/api/groups", tags=["groups"])


def _load(conn, group_id: int) -> dict:
    group = CaseGroupRepo(conn).get(group_id)
    if group is None:
        raise HTTPException(status_code=404, detail=f"spécification {group_id} introuvable")
    return group | {"case_count": CaseGroupRepo(conn).case_count(group_id)}


@router.get("/{group_id}", response_model=schemas.GroupDetail,
           dependencies=[Depends(access.require_project_access_depuis(
               "group_id", access.project_id_depuis_group))])
def get_group(group_id: int, conn=Depends(get_conn)):
    """La spécification AVEC son document — la vue de l'écran d'édition."""
    return schemas.group_detail(_load(conn, group_id))


@router.patch("/{group_id}", response_model=schemas.GroupDetail,
             dependencies=[Depends(access.require_project_access_depuis(
                 "group_id", access.project_id_depuis_group))])
def update_group(group_id: int, body: schemas.GroupPatch, conn=Depends(get_conn)):
    """Édition partielle. Éditer le document ne crée AUCUNE version et ne rebloque AUCUN gate :
    ceux-ci vivent sur le cas (`0022` n°10). La conséquence d'une spec modifiée se lira sur les
    cas qui en sont nés, par l'écart de `spec_hash` (`0022` n°6)."""
    _load(conn, group_id)
    if body.title is not None and not body.title.strip():
        raise HTTPException(status_code=422, detail="le titre de la spécification est requis")
    try:
        CaseGroupRepo(conn).update(
            group_id,
            title=body.title.strip() if body.title is not None else None,
            description=body.description,
            spec_content=body.spec_content)
    except DuplicateName as exc:
        raise erreurs.ErreurMetier("nom_deja_pris", str(exc)) from exc
    return schemas.group_detail(_load(conn, group_id))


@router.post("/{group_id}/deplacer", response_model=schemas.GroupDetail,
            dependencies=[Depends(access.require_project_access_depuis(
                "group_id", access.project_id_depuis_group))])
def deplacer_group(group_id: int, body: schemas.GroupMoveIn, conn=Depends(get_conn)):
    """Glisser-déposer d'une Section (étape 2bis) — la réattache à une autre Section (ou la
    promeut au premier niveau si `parent_group_id` est `null`). Jamais de copie : une Section ne
    se duplique pas (voir `CaseRepo.copier`, réservé aux cas)."""
    _load(conn, group_id)
    try:
        CaseGroupRepo(conn).deplacer(group_id, body.parent_group_id)
    # ⚠️ `ProfondeurInvalide` hérite de `ValueError` — ce `except` DOIT rester avant le générique,
    # sinon il est avalé par lui et une imbrication invalide rend 404 au lieu de 422 (mesuré).
    except ProfondeurInvalide as exc:
        raise erreurs.ErreurMetier("profondeur_invalide", str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return schemas.group_detail(_load(conn, group_id))


@router.delete("/{group_id}", status_code=204,
              dependencies=[Depends(access.require_project_access_depuis(
                  "group_id", access.project_id_depuis_group))])
def delete_group(group_id: int, request: Request, conn=Depends(get_conn)):
    """Supprime une spécification VIDE ; 409 tant qu'elle porte des cas.

    Pas de cascade, délibérément : un cas porte versions, exécutions et coûts — de l'historique,
    que le projet ne détruit jamais en silence (§2.10). Le message dit combien de cas restent.
    """
    _load(conn, group_id)
    try:
        CaseGroupRepo(conn).delete(group_id, par=access.utilisateur_de(request))
    except NotEmpty as exc:
        raise erreurs.ErreurMetier("conteneur_non_vide", str(exc)) from exc
    return Response(status_code=204)
