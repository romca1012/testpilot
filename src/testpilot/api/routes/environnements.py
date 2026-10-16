"""Environnements d'un projet (lot PT-04a, décisions A48 à A50) : recette, préproduction… où rejouer les tests.

L'environnement PAR DÉFAUT (identifiant 0) est le projet lui-même : son adresse, sa base et sa version se règlent toujours
dans « Identité et application » ; ici, seul son NOM change. Les environnements AJOUTÉS se créent, se modifient et vont à la
corbeille ici, avec une nature obligatoire (A48) : « Test », ou « Production », qui n'est jamais joué.

Droits : tout membre du projet LIT (le formulaire de lancement les propose) ; seul l'administrateur du projet les RÈGLE,
comme le reste de la page « Paramètres de test » — un environnement décide de l'application que les tests vont toucher.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from testpilot.api import access, schemas
from testpilot.api.deps import get_conn
from testpilot.api.services import environnements_service
from testpilot.parametres import environnements as env
from testpilot.store.repositories import ProjectEnvironmentRepo, ProjectRepo

router = APIRouter(prefix="/api/projects/{project_id}/environnements", tags=["environnements"])

_MEMBRE = [Depends(access.require_project_access)]
_ADMIN = [Depends(access.require_project_role(access.ROLE_ADMIN))]


def _projet(conn, project_id: int) -> dict:
    projet = ProjectRepo(conn).get(project_id)
    if projet is None:
        raise HTTPException(status_code=404, detail=f"projet {project_id} introuvable")
    return projet


def _liste(conn, project_id: int) -> list[schemas.EnvironnementOut]:
    return [schemas.environnement_out(e) for e in environnements_service.liste(conn, _projet(conn, project_id))]


def _champs(body: schemas.EnvironnementIn, projet: dict) -> dict:
    try:
        champs = env.valider(nom=body.nom, base_url=body.base_url, nature=body.nature,
                             connector_version=body.connector_version, database=body.database,
                             oracle_base_url=body.oracle_base_url)
    except env.EnvironnementInvalide as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    # Revue du 2026-10-16 : un environnement Odoo sans base serait refusé au lancement avec un message qui renvoie à
    # l'écran Projets — demandé ICI, jamais repris de la base du projet (elle viserait une autre application).
    if (projet.get("connector_type") or "odoo").lower() == "odoo" and not champs["database"]:
        raise HTTPException(status_code=422, detail="la base est requise pour un environnement Odoo")
    return champs


@router.get("", response_model=list[schemas.EnvironnementOut], dependencies=_MEMBRE)
def lister(project_id: int, conn=Depends(get_conn)):
    """L'environnement par défaut en tête, puis les environnements ajoutés vivants."""
    return _liste(conn, project_id)


@router.post("", response_model=list[schemas.EnvironnementOut], status_code=201, dependencies=_ADMIN)
def creer(project_id: int, body: schemas.EnvironnementIn, conn=Depends(get_conn)):
    projet = _projet(conn, project_id)
    try:
        ProjectEnvironmentRepo(conn).creer(project_id, _champs(body, projet))
    except env.EnvironnementInvalide as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _liste(conn, project_id)


@router.patch("/{environment_id}", response_model=list[schemas.EnvironnementOut], dependencies=_ADMIN)
def modifier(project_id: int, environment_id: int, body: schemas.EnvironnementIn, conn=Depends(get_conn)):
    """Pour l'environnement par défaut (0), seul le nom change : le reste est le projet (« Identité et application »)."""
    projet = _projet(conn, project_id)
    depot = ProjectEnvironmentRepo(conn)
    try:
        if environment_id == env.DEFAUT:
            nom = env.valider_nom(body.nom)
            if any(e["nom"].casefold() == nom.casefold() for e in depot.liste(project_id)):
                raise env.EnvironnementInvalide(f"un environnement « {nom} » existe déjà sur ce projet")
            ProjectRepo(conn).set_environnement_nom(project_id, "" if nom == env.NOM_PAR_DEFAUT else nom)
        elif not depot.modifier(project_id, environment_id, _champs(body, projet)):
            raise HTTPException(status_code=404, detail=f"environnement {environment_id} introuvable")
    except env.EnvironnementInvalide as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _liste(conn, project_id)


@router.delete("/{environment_id}", status_code=204, dependencies=_ADMIN)
def supprimer(project_id: int, environment_id: int, request: Request, conn=Depends(get_conn)):
    """À la corbeille (restaurable). L'environnement par défaut ne se supprime pas : c'est le projet."""
    _projet(conn, project_id)
    if environment_id == env.DEFAUT:
        raise HTTPException(status_code=422, detail="l'environnement par défaut ne se supprime pas")
    if not ProjectEnvironmentRepo(conn).supprimer(project_id, environment_id, par=access.utilisateur_de(request)):
        raise HTTPException(status_code=404, detail=f"environnement {environment_id} introuvable")
    return Response(status_code=204)
