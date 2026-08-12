"""Routes de la hiérarchie §7 : projets et leurs modules.

Le projet est le contexte de premier niveau (au-dessus des onglets Gestion / Exécution) ;
les modules regroupent les cas d'un projet.

Toute route qui porte `project_id` DIRECTEMENT dans son chemin est gardée par
`Depends(access.require_project_access)` (migration 31, 2026-08-10) — la surcharge d'accès par
projet, en plus du rôle global déjà vérifié par le middleware. `list_projects` (`GET ""`, sans
`project_id`) filtre la liste elle-même : c'est ce qui rend un projet réellement CACHÉ.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response

from testpilot.api import access, erreurs, schemas
from testpilot.api.deps import get_conn
from testpilot.api.services import exploration_service
from testpilot.store.repositories import (
    CaseGroupRepo,
    DuplicateName,
    ModuleRepo,
    ProjectAccessRepo,
    ProjectRepo,
    UserRepo,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])



def _conflict(exc: DuplicateName) -> erreurs.ErreurMetier:
    """409 `nom_deja_pris` — le nom est déjà pris à sa portée d'unicité.

    409 et non 422 : la requête est bien formée, c'est l'état du référentiel qui s'y oppose.
    Le message du repo nomme le conflit en clair (il est affiché tel quel à l'utilisateur), et
    le **code** permet au client de réagir sans lire cette phrase.

    ⚠️ Cette fonction d'aide avait été OUBLIÉE par la conversion du lot B, qui cherchait le motif
    `raise HTTPException(...)` : les doublons de projet et de module retombaient donc sur le code
    générique `etat_incompatible`. Trouvé par le test du contrat, pas à la relecture.
    """
    return erreurs.ErreurMetier("nom_deja_pris", str(exc))


def _summary_row(conn, project_id: int) -> dict | None:
    for r in ProjectRepo(conn).list_all():
        if r["id"] == project_id:
            return r
    return None


@router.get("", response_model=list[schemas.ProjectSummary])
def list_projects(request: Request, conn=Depends(get_conn)):
    """⚠️ Retire tout projet en `no_access` pour l'utilisateur courant (migration 31, 2026-08-10)
    — c'est ce filtre qui rend un projet réellement CACHÉ, pas seulement refusé si on force son
    URL (`require_project_access` s'en charge, en 404, sur les routes qui prennent `project_id`)."""
    utilisateur = request.state.user
    return [schemas.project_summary(r) for r in ProjectRepo(conn).list_all()
           if access.role_effectif_projet(conn, utilisateur, r["id"]) != access.ACCES_PROJET_REFUSE]


@router.post("", response_model=schemas.ProjectSummary, status_code=201)
def create_project(body: schemas.ProjectIn, conn=Depends(get_conn)):
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="le nom du projet est requis")
    try:
        ProjectRepo(conn).create(
            name=body.name.strip(), description=body.description,
            connector_type=body.connector_type, base_url=body.base_url, database=body.database,
            username=body.username, password=body.password)
    except DuplicateName as exc:
        raise _conflict(exc) from exc
    return schemas.project_summary(_summary_row(conn, _last_project_id(conn)))


def _last_project_id(conn) -> int:
    return conn.execute("SELECT MAX(id) AS m FROM project").fetchone()["m"]


@router.patch("/{project_id}", response_model=schemas.ProjectSummary,
             dependencies=[Depends(access.require_project_access)])
def update_project(project_id: int, body: schemas.ProjectPatch, conn=Depends(get_conn)):
    """Édite un projet : nom, description **et connexion** (décision `0005`).

    ⚠️ La connexion était jusqu'ici **non éditable** — le corps était accepté avec ses champs de
    connecteur, et la route les jetait en silence. Une faute de frappe dans l'URL obligeait à
    supprimer le projet, donc à perdre modules, cas et historique. C'est aussi le préalable à
    l'exploration : on ne cartographie pas une application qu'on ne peut pas corriger.

    Seuls les champs FOURNIS changent (`None` = « n'y touche pas ») — voir `ProjectPatch`.
    """
    if ProjectRepo(conn).get(project_id) is None:
        raise HTTPException(status_code=404, detail=f"projet {project_id} introuvable")
    if body.name is not None and not body.name.strip():
        raise HTTPException(status_code=422, detail="le nom du projet est requis")
    repo = ProjectRepo(conn)
    try:
        if body.name is not None:
            repo.rename(project_id, name=body.name.strip(), description=body.description)
        elif body.description is not None:
            current = repo.get(project_id)
            repo.rename(project_id, name=current["name"], description=body.description)
    except DuplicateName as exc:
        raise _conflict(exc) from exc
    repo.update_connection(
        project_id, connector_type=body.connector_type, base_url=body.base_url,
        database=body.database, username=body.username, password=body.password)
    return schemas.project_summary(_summary_row(conn, project_id))


@router.delete("/{project_id}", status_code=204,
              dependencies=[Depends(access.require_project_access)])
def delete_project(project_id: int, request: Request, conn=Depends(get_conn)):
    if ProjectRepo(conn).get(project_id) is None:
        raise HTTPException(status_code=404, detail=f"projet {project_id} introuvable")
    ProjectRepo(conn).delete(project_id, par=access.utilisateur_de(request))
    return Response(status_code=204)


@router.get("/{project_id}/exploration", response_model=schemas.ExplorationOut,
           dependencies=[Depends(access.require_project_access)])
def get_exploration(project_id: int, conn=Depends(get_conn)):
    """La cartographie du projet : existe-t-elle, de quand date-t-elle, que couvre-t-elle."""
    projet = ProjectRepo(conn).get(project_id)
    if projet is None:
        raise HTTPException(status_code=404, detail=f"projet {project_id} introuvable")
    etat = exploration_service.etat(project_id, projet)
    job = exploration_service.get_job(etat["job_id"]) if etat["job_id"] else None
    return schemas.ExplorationOut(**etat, error=(job or {}).get("error", ""))


@router.post("/{project_id}/exploration", response_model=schemas.ExplorationOut, status_code=202,
            dependencies=[Depends(access.require_project_access)])
def start_exploration(project_id: int, background: BackgroundTasks, conn=Depends(get_conn)):
    """Explore l'application du projet et construit SA cartographie (aucun LLM).

    Payé une fois par projet : toutes les générations suivantes liront cette mesure au lieu de
    deviner routes et champs. Déclenchement EXPLICITE — comme le lancement d'un run (`0022`
    n°8.c.1), une opération longue ne doit jamais partir sans qu'on l'ait demandée.
    """
    try:
        job_id, params = exploration_service.start_exploration(conn, project_id)
    except exploration_service.ExplorationError as err:
        raise erreurs.depuis_service(err.code, err.detail,
                                     defaut="exploration_en_cours" if err.code == "already_running"
                                            else "non_gere")

    background.add_task(exploration_service.run_exploration, job_id, **params)
    return schemas.ExplorationOut(running=True, job_id=job_id)


@router.get("/{project_id}/modules", response_model=list[schemas.ModuleSummary],
           dependencies=[Depends(access.require_project_access)])
def list_modules(project_id: int, conn=Depends(get_conn)):
    if ProjectRepo(conn).get(project_id) is None:
        raise HTTPException(status_code=404, detail=f"projet {project_id} introuvable")
    return [schemas.module_summary(r) for r in ModuleRepo(conn).list_for_project(project_id)]


@router.get("/{project_id}/groups", response_model=list[schemas.GroupSummary],
           dependencies=[Depends(access.require_project_access)])
def list_groups(project_id: int, conn=Depends(get_conn)):
    """Les spécifications (case_group) du projet, pour l'arbre latéral et les compteurs."""
    if ProjectRepo(conn).get(project_id) is None:
        raise HTTPException(status_code=404, detail=f"projet {project_id} introuvable")
    return [schemas.GroupSummary(id=r["id"], module_id=r["module_id"], title=r["title"],
                                 case_count=r.get("case_count", 0),
                                 parent_group_id=r.get("parent_group_id"))
            for r in CaseGroupRepo(conn).list_for_project(project_id)]


@router.post("/{project_id}/modules", response_model=schemas.ModuleSummary, status_code=201,
            dependencies=[Depends(access.require_project_access)])
def create_module(project_id: int, body: schemas.ModuleIn, conn=Depends(get_conn)):
    if ProjectRepo(conn).get(project_id) is None:
        raise HTTPException(status_code=404, detail=f"projet {project_id} introuvable")
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="le nom du module est requis")
    try:
        mid = ModuleRepo(conn).create(project_id=project_id, name=body.name.strip(),
                                      description=body.description)
    except DuplicateName as exc:
        raise _conflict(exc) from exc
    return schemas.ModuleSummary(id=mid, project_id=project_id, name=body.name.strip(),
                                 description=body.description, case_count=0)


# ── Accès par projet — gestion réservée à l'Admin (migration 31, 2026-08-10) ──────────────────
# ⚠️ Pas de `require_project_access` ici : ces routes GÈRENT l'accès, un Admin doit toujours
# pouvoir les atteindre même sur un projet qu'il vient lui-même de passer en `no_access` (sinon
# il se coincerait dehors sans recours — même piège qu'un rôle qui pourrait bloquer sa propre
# gestion, cf. l'avertissement de TestRail sur les rôles d'administrateur).
_ROLES_ACCES_PROJET = (access.ACCES_PROJET_REFUSE, *access.ROLES)


def _role_projet_valide(role: str) -> bool:
    return role in _ROLES_ACCES_PROJET


@router.get("/{project_id}/access", response_model=schemas.ProjectAccessOut,
           dependencies=[Depends(access.require_role(access.ROLE_ADMIN))])
def get_project_access(project_id: int, conn=Depends(get_conn)):
    if ProjectRepo(conn).get(project_id) is None:
        raise HTTPException(status_code=404, detail=f"projet {project_id} introuvable")
    repo = ProjectAccessRepo(conn)
    return schemas.ProjectAccessOut(
        default_access=repo.default_access(project_id),
        overrides=[schemas.ProjectAccessOverrideOut(user_id=r["user_id"], username=r["username"],
                                                     role=r["role"])
                  for r in repo.overrides_for_project(project_id)])


@router.patch("/{project_id}/access", response_model=schemas.ProjectAccessOut,
             dependencies=[Depends(access.require_role(access.ROLE_ADMIN))])
def set_project_default_access(project_id: int, body: schemas.ProjectDefaultAccessIn,
                               conn=Depends(get_conn)):
    if ProjectRepo(conn).get(project_id) is None:
        raise HTTPException(status_code=404, detail=f"projet {project_id} introuvable")
    if body.default_access and not _role_projet_valide(body.default_access):
        raise HTTPException(status_code=422,
                            detail=f"accès inconnu : « {body.default_access} »")
    ProjectAccessRepo(conn).set_default_access(project_id, body.default_access)
    return get_project_access(project_id, conn)


@router.post("/{project_id}/access/users", response_model=schemas.ProjectAccessOut,
            dependencies=[Depends(access.require_role(access.ROLE_ADMIN))])
def set_project_access_override(project_id: int, body: schemas.ProjectAccessOverrideIn,
                                conn=Depends(get_conn)):
    if ProjectRepo(conn).get(project_id) is None:
        raise HTTPException(status_code=404, detail=f"projet {project_id} introuvable")
    if UserRepo(conn).get(body.user_id) is None:
        raise HTTPException(status_code=404, detail=f"utilisateur {body.user_id} introuvable")
    if not _role_projet_valide(body.role):
        raise HTTPException(status_code=422, detail=f"accès inconnu : « {body.role} »")
    ProjectAccessRepo(conn).set_override(project_id, body.user_id, body.role)
    return get_project_access(project_id, conn)


@router.delete("/{project_id}/access/users/{user_id}", response_model=schemas.ProjectAccessOut,
              dependencies=[Depends(access.require_role(access.ROLE_ADMIN))])
def remove_project_access_override(project_id: int, user_id: int, conn=Depends(get_conn)):
    if ProjectRepo(conn).get(project_id) is None:
        raise HTTPException(status_code=404, detail=f"projet {project_id} introuvable")
    ProjectAccessRepo(conn).remove_override(project_id, user_id)
    return get_project_access(project_id, conn)
