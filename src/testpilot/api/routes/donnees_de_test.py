"""Données de test d'un projet (lot PT-02, décisions A26 à A31) : variables × jeux de données.

Un test écrit `{{nom}}` ; au lancement, l'outil y pose la valeur du jeu de données choisi. Ces routes tiennent le TABLEAU.

Droits (A30) : tout membre du projet LIT ; testeurs, développeurs et administrateurs du projet AJOUTENT et MODIFIENT, comme
pour les tests (`require_project_access` refuse l'écriture sous le rôle testeur). La SUPPRESSION — une mise à la corbeille,
restaurable (A31) — reste à l'administrateur du projet, comme toutes les suppressions de l'outil : c'est lui seul qui peut
restaurer. Une valeur est déclarée par une PERSONNE ; l'agent de génération ne connaîtra que les noms (PT-02d).

Les noms et les valeurs sont validés par `parametres/resolution.py` — les règles mêmes du remplacement : ce que ces routes
acceptent est exactement ce qu'un test pourra recevoir sans être cassé.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from testpilot.api import access, erreurs, schemas
from testpilot.api.deps import get_conn
from testpilot.parametres import resolution
from testpilot.store.repositories import DonneeDeTestInvalide, DuplicateName, ProjectRepo, TestDataRepo

router = APIRouter(prefix="/api/projects/{project_id}/donnees-de-test", tags=["donnees-de-test"])

_MEMBRE = [Depends(access.require_project_access)]                       # lecture : tout membre ; écriture : testeur et plus
_ADMIN = [Depends(access.require_project_role(access.ROLE_ADMIN))]       # suppression


def _depot(conn, project_id: int) -> TestDataRepo:
    if ProjectRepo(conn).get(project_id) is None:
        raise HTTPException(status_code=404, detail=f"projet {project_id} introuvable")
    return TestDataRepo(conn)


def _refus(exc: Exception) -> Exception:
    if isinstance(exc, DuplicateName):
        return erreurs.ErreurMetier("nom_deja_pris", str(exc))
    return HTTPException(status_code=422, detail=str(exc))


def _tableau(depot: TestDataRepo, project_id: int) -> schemas.DonneesDeTestOut:
    t = depot.tableau(project_id)
    return schemas.DonneesDeTestOut(
        variables=[schemas.VariableOut(**v) for v in t["variables"]],
        jeux=[schemas.JeuDeDonneesOut(**j, valeurs={str(vid): valeur for vid, valeur in t["valeurs"][j["id"]].items()})
              for j in t["jeux"]])


@router.get("", response_model=schemas.DonneesDeTestOut, dependencies=_MEMBRE)
def lire_le_tableau(project_id: int, conn=Depends(get_conn)):
    """Les variables, les jeux (le jeu « Par défaut » en tête) et leurs valeurs ; une case vide n'y figure pas."""
    return _tableau(_depot(conn, project_id), project_id)


@router.post("/variables", response_model=schemas.DonneesDeTestOut, status_code=201, dependencies=_MEMBRE)
def creer_une_variable(project_id: int, body: schemas.VariableIn, conn=Depends(get_conn)):
    depot = _depot(conn, project_id)
    try:
        depot.creer_variable(project_id, nom=resolution.valider_nom(body.nom), description=body.description)
    except (resolution.NomInvalide, DonneeDeTestInvalide, DuplicateName) as exc:
        raise _refus(exc) from exc
    return _tableau(depot, project_id)


@router.patch("/variables/{variable_id}", response_model=schemas.DonneesDeTestOut, dependencies=_MEMBRE)
def decrire_une_variable(project_id: int, variable_id: int, body: schemas.VariablePatch, conn=Depends(get_conn)):
    """Seule la description change : un test désigne la variable par son NOM, qui ne se modifie pas."""
    depot = _depot(conn, project_id)
    if not depot.decrire_variable(project_id, variable_id, body.description):
        raise HTTPException(status_code=404, detail=f"variable {variable_id} introuvable")
    return _tableau(depot, project_id)


@router.get("/cas-avec-variables", response_model=list[int], dependencies=_MEMBRE)
def tests_qui_ecrivent_des_variables(project_id: int, conn=Depends(get_conn)):
    """Les tests du projet qui écrivent des variables — pour que l'écran de lancement annonce, avant de créer, combien
    seront joués pour chaque jeu au-delà du premier (décision A35)."""
    return _depot(conn, project_id).cas_qui_ecrivent_des_variables(project_id)


@router.get("/variables/{variable_id}/usages", response_model=list[schemas.UsageDeVariable], dependencies=_MEMBRE)
def tests_qui_utilisent_la_variable(project_id: int, variable_id: int, conn=Depends(get_conn)):
    """Les tests du projet qui écrivent cette variable — montrés AVANT de la supprimer (A31)."""
    depot = _depot(conn, project_id)
    variable = next((v for v in depot.variables(project_id) if v["id"] == variable_id), None)
    if variable is None:
        raise HTTPException(status_code=404, detail=f"variable {variable_id} introuvable")
    return [schemas.UsageDeVariable(**u) for u in depot.usages(project_id, variable["nom"])]


@router.delete("/variables/{variable_id}", status_code=204, dependencies=_ADMIN)
def supprimer_une_variable(project_id: int, variable_id: int, request: Request, conn=Depends(get_conn)):
    if not _depot(conn, project_id).supprimer_variable(project_id, variable_id, par=access.utilisateur_de(request)):
        raise HTTPException(status_code=404, detail=f"variable {variable_id} introuvable")
    return Response(status_code=204)


@router.post("/jeux", response_model=schemas.DonneesDeTestOut, status_code=201, dependencies=_MEMBRE)
def creer_un_jeu(project_id: int, body: schemas.JeuDeDonneesIn, conn=Depends(get_conn)):
    depot = _depot(conn, project_id)
    try:
        depot.creer_jeu(project_id, nom=body.nom)
    except (DonneeDeTestInvalide, DuplicateName) as exc:
        raise _refus(exc) from exc
    return _tableau(depot, project_id)


@router.patch("/jeux/{dataset_id}", response_model=schemas.DonneesDeTestOut, dependencies=_MEMBRE)
def renommer_un_jeu(project_id: int, dataset_id: int, body: schemas.JeuDeDonneesIn, conn=Depends(get_conn)):
    depot = _depot(conn, project_id)
    try:
        trouve = depot.renommer_jeu(project_id, dataset_id, body.nom)
    except (DonneeDeTestInvalide, DuplicateName) as exc:
        raise _refus(exc) from exc
    if not trouve:
        raise HTTPException(status_code=404, detail=f"jeu de données {dataset_id} introuvable")
    return _tableau(depot, project_id)


@router.put("/jeux/{dataset_id}/valeurs", response_model=schemas.DonneesDeTestOut, dependencies=_MEMBRE)
def poser_les_valeurs_d_un_jeu(project_id: int, dataset_id: int, body: schemas.ValeursDuJeuIn, conn=Depends(get_conn)):
    """Écrit les cases FOURNIES (`{id de variable: valeur}`) ; les autres ne bougent pas. Une valeur vide vide la case, qui
    reprend alors le jeu « Par défaut » (A27). Tout est validé AVANT d'écrire : rien n'est enregistré à moitié."""
    depot = _depot(conn, project_id)
    if not all(cle.isascii() and cle.isdigit() and not cle.startswith("0") for cle in body.valeurs):
        # « 01 », « 1 », «  1 » désignaient la même variable, et la dernière gagnait en silence (revue du 2026-10-14).
        raise HTTPException(status_code=422, detail="chaque case est désignée par l'identifiant de sa variable, écrit une seule fois")
    try:
        valeurs = {int(variable_id): resolution.valider_valeur(valeur) for variable_id, valeur in body.valeurs.items()}
        trouve = depot.poser_valeurs(project_id, dataset_id, valeurs)
    except (resolution.ValeurInvalide, DonneeDeTestInvalide, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not trouve:
        raise HTTPException(status_code=404, detail=f"jeu de données {dataset_id} introuvable")
    return _tableau(depot, project_id)


@router.delete("/jeux/{dataset_id}", status_code=204, dependencies=_ADMIN)
def supprimer_un_jeu(project_id: int, dataset_id: int, request: Request, conn=Depends(get_conn)):
    try:
        trouve = _depot(conn, project_id).supprimer_jeu(project_id, dataset_id, par=access.utilisateur_de(request))
    except DonneeDeTestInvalide as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not trouve:
        raise HTTPException(status_code=404, detail=f"jeu de données {dataset_id} introuvable")
    return Response(status_code=204)
