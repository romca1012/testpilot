"""Routes de la hiérarchie §7 : projets et leurs modules.

Le projet est le contexte de premier niveau (au-dessus des onglets Gestion / Exécution) ;
les modules regroupent les cas d'un projet.

Toute route qui porte `project_id` DIRECTEMENT dans son chemin est gardée par
`Depends(access.require_project_access)` (migration 31, 2026-08-10) — la surcharge d'accès par
projet, en plus du rôle global déjà vérifié par le middleware. `list_projects` (`GET ""`, sans
`project_id`) filtre la liste elle-même : c'est ce qui rend un projet réellement CACHÉ.
"""

from __future__ import annotations

import asyncio
import json
import queue as queue_mod

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from testpilot.api import access, erreurs, schemas
from testpilot.api.deps import get_conn
from testpilot.api.services import events_bus, exploration_service
from testpilot.api.services.project_membership_service import ProjectMembershipService
from testpilot.guardrails import durable_jobs
from testpilot.store.repositories import (
    CaseGroupRepo,
    DuplicateName,
    ModuleRepo,
    ProjectAccessRepo,
    ProjectGroupAccessRepo,
    ProjectMemberRepo,
    ProjectRepo,
    UserGroupRepo,
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
    visibles = []
    for row in ProjectRepo(conn).list_all():
        role = access.role_effectif_projet(conn, utilisateur, row["id"])
        if role == access.ACCES_PROJET_REFUSE:
            continue
        visibles.append(schemas.project_summary({**row, "effective_role": role}))
    return visibles


@router.get("/catalogue-admin", response_model=list[schemas.ProjectSummary],
            dependencies=[Depends(access.require_role(access.ROLE_ADMIN))])
def list_projects_for_admin(request: Request, conn=Depends(get_conn)):
    """Catalogue complet réservé à l'administration.

    Il est volontairement distinct du sélecteur de travail : un Admin d'instance doit pouvoir
    attribuer un projet sans devenir membre, tandis qu'un utilisateur ordinaire ne doit jamais
    apprendre l'existence d'un projet masqué.
    """
    utilisateur = request.state.user
    return [schemas.project_summary({
        **row, "effective_role": access.role_effectif_projet(conn, utilisateur, row["id"]),
    }) for row in ProjectRepo(conn).list_all()]


@router.post("", response_model=schemas.ProjectSummary, status_code=201,
             dependencies=[Depends(access.require_role(access.ROLE_ADMIN))])
def create_project(body: schemas.ProjectIn, request: Request = None, conn=Depends(get_conn)):
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="le nom du projet est requis")
    # ⚠️ PAS `... and request.state.user["id"]` : l'id `0` (compte Admin de complaisance posé par
    # `tests/conftest.py::_connecte_par_defaut`) est un id VALIDE mais falsy en Python — le
    # tronquer en `None` ici a déjà produit, une fois, un projet fermé sans AUCUN Admin explicite,
    # y compris pour son propre créateur (mesuré 2026-09-07 : ~90 tests en échec en cascade).
    utilisateur = getattr(request, "state", None) and getattr(request.state, "user", None)
    try:
        project_id = ProjectRepo(conn).create(
            name=body.name.strip(), description=body.description,
            connector_type=body.connector_type, connector_version=body.connector_version,
            base_url=body.base_url, database=body.database,
            username=body.username, password=body.password, private=True,
            owner_id=utilisateur["id"] if utilisateur is not None else None)
    except DuplicateName as exc:
        raise _conflict(exc) from exc
    return schemas.project_summary(_summary_row(conn, project_id))


@router.patch("/{project_id}", response_model=schemas.ProjectSummary,
             dependencies=[Depends(access.require_project_role(access.ROLE_ADMIN))])
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
        project_id, connector_type=body.connector_type, connector_version=body.connector_version,
        base_url=body.base_url, database=body.database, username=body.username,
        password=body.password)
    if body.calibration_writes_enabled is not None:
        repo.set_calibration_writes_enabled(project_id, body.calibration_writes_enabled)
    return schemas.project_summary(_summary_row(conn, project_id))


@router.delete("/{project_id}", status_code=204,
              dependencies=[Depends(access.require_project_role(access.ROLE_ADMIN))])
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
            dependencies=[Depends(access.require_project_role(access.ROLE_ADMIN))])
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

    # Plafonné (guardrails/concurrency.py) : l'exploration ouvre elle aussi un navigateur réel —
    # attend son tour dans la file partagée avec générations et exécutions.
    durable_jobs.submit(conn, background, kind="exploration", args=[job_id], kwargs=params,
                        queue_label=f"exploration:{job_id}")
    return schemas.ExplorationOut(running=True, job_id=job_id)


@router.get("/{project_id}/modules", response_model=list[schemas.ModuleSummary],
           dependencies=[Depends(access.require_project_access)])
def list_modules(project_id: int, conn=Depends(get_conn)):
    if ProjectRepo(conn).get(project_id) is None:
        raise HTTPException(status_code=404, detail=f"projet {project_id} introuvable")
    return [schemas.module_summary(r) for r in ModuleRepo(conn).list_for_project(project_id)]


async def _flux_evenements(project_id: int, request: Request):
    """Le générateur SSE lui-même — extrait de la route pour être testable directement (asyncio,
    sans passer par une vraie connexion HTTP en flux, mal supportée par le client de test)."""
    q = events_bus.abonner(project_id)
    try:
        yield "retry: 3000\n\n"
        while True:
            if await request.is_disconnected():
                break
            try:
                # Bloquant côté thread (queue.Queue n'a pas d'attente async) — jamais sur la
                # boucle asyncio elle-même, `to_thread` l'isole. Le délai borne l'attente pour
                # qu'on revienne vérifier régulièrement si le navigateur est parti, et sert
                # aussi de battement de cœur qui empêche un proxy intermédiaire de couper une
                # connexion qu'il croirait inactive.
                event = await asyncio.to_thread(q.get, True, 15)
            except queue_mod.Empty:
                yield ": heartbeat\n\n"
                continue
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
    finally:
        events_bus.desabonner(project_id, q)


@router.get("/{project_id}/events", dependencies=[Depends(access.require_project_access)])
async def project_events(project_id: int, request: Request, conn=Depends(get_conn)):
    """Flux Server-Sent Events : prévient en direct les écrans ouverts sur CE projet qu'un cas a
    changé — édité, créé, déplacé — au lieu qu'ils affichent un contenu périmé jusqu'au prochain
    rechargement manuel (audit 2026-09-07, « vrai temps réel »).

    ⚠️ **Confort, jamais une autorité.** Un événement raté (onglet en veille, reconnexion,
    redémarrage du serveur) ne doit JAMAIS pouvoir faire agir un écran sur une donnée qu'il
    n'aurait pas relue lui-même — voir le garde-fou `expected_version_id` de `CaseRepo.update_metier`,
    qui reste la VRAIE protection contre une édition concurrente. Ce flux ne fait qu'inviter à
    recharger plus tôt ; jamais de décision métier prise sur la seule foi d'un événement reçu.

    Gardé par `require_project_access` comme n'importe quelle autre route du projet : un compte
    sans accès ne doit pas plus pouvoir ÉCOUTER ce qui change dans un projet fermé qu'il ne peut
    le LIRE par les routes habituelles — la même fermeture par défaut s'applique ici.

    SSE plutôt que WebSocket : un seul sens (serveur → écran) suffit à ce besoin, ça traverse les
    réseaux d'entreprise sans configuration particulière (pas de handshake de protocole à part),
    et le navigateur gère lui-même la reconnexion — rien à écrire côté client pour ça.
    """
    if ProjectRepo(conn).get(project_id) is None:
        raise HTTPException(status_code=404, detail=f"projet {project_id} introuvable")
    return StreamingResponse(
        _flux_evenements(project_id, request), media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Nginx bufferise les réponses en flux par défaut, ce qui retarderait chaque
            # événement jusqu'au remplissage du tampon — inutile de le redécouvrir en
            # production faute de l'avoir documenté ici.
            "X-Accel-Buffering": "no",
        })


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
                  for r in repo.overrides_for_project(project_id)],
        group_overrides=[schemas.ProjectGroupAccessOut(**r)
                         for r in ProjectGroupAccessRepo(conn).list_for_project(project_id)])


def _admins_effectifs(conn, project_id: int) -> int:
    return sum(
        1 for user in UserRepo(conn).list_all()
        if user["is_active"] and access.role_effectif_projet(conn, user, project_id) == access.ROLE_ADMIN)


@router.post("/{project_id}/access/groups", response_model=schemas.ProjectAccessOut,
             dependencies=[Depends(access.require_role(access.ROLE_ADMIN))])
def set_project_group_access(project_id: int, body: schemas.ProjectGroupAccessIn,
                             conn=Depends(get_conn)):
    if ProjectRepo(conn).get(project_id) is None:
        raise HTTPException(status_code=404, detail=f"projet {project_id} introuvable")
    if UserGroupRepo(conn).get(body.group_id) is None:
        raise HTTPException(status_code=404, detail=f"groupe {body.group_id} introuvable")
    if body.role not in ("", *_ROLES_ACCES_PROJET):
        raise HTTPException(status_code=422, detail=f"accès inconnu : « {body.role} »")
    repo = ProjectGroupAccessRepo(conn)
    precedent = repo.get(project_id, body.group_id)
    repo.set(project_id, body.group_id, body.role)
    if _admins_effectifs(conn, project_id) == 0:
        precedent is None and repo.remove(project_id, body.group_id)
        precedent is not None and repo.set(project_id, body.group_id, precedent)
        raise erreurs.ErreurMetier(
            "etat_incompatible", "impossible : cette attribution laisserait le projet sans Admin actif")
    return get_project_access(project_id, conn)


@router.delete("/{project_id}/access/groups/{group_id}", response_model=schemas.ProjectAccessOut,
               dependencies=[Depends(access.require_role(access.ROLE_ADMIN))])
def remove_project_group_access(project_id: int, group_id: int, conn=Depends(get_conn)):
    if ProjectRepo(conn).get(project_id) is None:
        raise HTTPException(status_code=404, detail=f"projet {project_id} introuvable")
    repo = ProjectGroupAccessRepo(conn)
    precedent = repo.get(project_id, group_id)
    if precedent is None:
        raise HTTPException(status_code=404, detail="attribution de groupe introuvable")
    repo.remove(project_id, group_id)
    if _admins_effectifs(conn, project_id) == 0:
        repo.set(project_id, group_id, precedent)
        raise erreurs.ErreurMetier(
            "etat_incompatible", "impossible : cette suppression laisserait le projet sans Admin actif")
    return get_project_access(project_id, conn)


@router.patch("/{project_id}/access", response_model=schemas.ProjectAccessOut,
             dependencies=[Depends(access.require_role(access.ROLE_ADMIN))])
def set_project_default_access(project_id: int, body: schemas.ProjectDefaultAccessIn,
                               request: Request, conn=Depends(get_conn)):
    if ProjectRepo(conn).get(project_id) is None:
        raise HTTPException(status_code=404, detail=f"projet {project_id} introuvable")
    if body.default_access and not _role_projet_valide(body.default_access):
        raise HTTPException(status_code=422,
                            detail=f"accès inconnu : « {body.default_access} »")
    ProjectMembershipService(
        conn, request.state.user["id"]).set_default_access(project_id, body.default_access)
    return get_project_access(project_id, conn)


@router.post("/{project_id}/access/users", response_model=schemas.ProjectAccessOut,
            dependencies=[Depends(access.require_role(access.ROLE_ADMIN))])
def set_project_access_override(project_id: int, body: schemas.ProjectAccessOverrideIn,
                                request: Request, conn=Depends(get_conn)):
    if ProjectRepo(conn).get(project_id) is None:
        raise HTTPException(status_code=404, detail=f"projet {project_id} introuvable")
    if UserRepo(conn).get(body.user_id) is None:
        raise HTTPException(status_code=404, detail=f"utilisateur {body.user_id} introuvable")
    if not _role_projet_valide(body.role):
        raise HTTPException(status_code=422, detail=f"accès inconnu : « {body.role} »")
    service = ProjectMembershipService(conn, request.state.user["id"])
    if body.role == access.ACCES_PROJET_REFUSE:
        service.remove(project_id, body.user_id)
    else:
        service.set_active_member(
            project_id, body.user_id, body.role, action="LEGACY_OVERRIDE_SET")
    return get_project_access(project_id, conn)


@router.delete("/{project_id}/access/users/{user_id}", response_model=schemas.ProjectAccessOut,
              dependencies=[Depends(access.require_role(access.ROLE_ADMIN))])
def remove_project_access_override(project_id: int, user_id: int, request: Request,
                                   conn=Depends(get_conn)):
    if ProjectRepo(conn).get(project_id) is None:
        raise HTTPException(status_code=404, detail=f"projet {project_id} introuvable")
    ProjectMembershipService(
        conn, request.state.user["id"]).remove_legacy_override(project_id, user_id)
    return get_project_access(project_id, conn)


_STATUTS_MEMBRE_MODIFIABLES = ("active", "suspended")


def _member_out(row: dict) -> schemas.ProjectMemberOut:
    return schemas.ProjectMemberOut(**{k: row[k] for k in (
        "user_id", "username", "email", "role", "status", "created_at")})


def _require_project_and_user(conn, project_id: int, user_id: int | None = None) -> dict | None:
    if ProjectRepo(conn).get(project_id) is None:
        raise HTTPException(status_code=404, detail=f"projet {project_id} introuvable")
    if user_id is None:
        return None
    user = UserRepo(conn).get(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"utilisateur {user_id} introuvable")
    return user


@router.get("/{project_id}/members", response_model=list[schemas.ProjectMemberOut],
            dependencies=[Depends(access.require_role(access.ROLE_ADMIN))])
def list_project_members(project_id: int, conn=Depends(get_conn)):
    _require_project_and_user(conn, project_id)
    return [_member_out(row) for row in ProjectMemberRepo(conn).list_for_project(project_id)]


@router.post("/{project_id}/members", response_model=schemas.ProjectMemberOut, status_code=201,
             dependencies=[Depends(access.require_role(access.ROLE_ADMIN))])
def add_project_member(project_id: int, body: schemas.ProjectMemberCreateIn,
                       request: Request, conn=Depends(get_conn)):
    user = _require_project_and_user(conn, project_id, body.user_id)
    if body.role not in access.ROLES:
        raise HTTPException(status_code=422, detail=f"rôle inconnu : « {body.role} »")
    if not user["is_active"]:
        raise HTTPException(status_code=409, detail="ce compte est désactivé")
    ProjectMembershipService(conn, request.state.user["id"]).set_active_member(
        project_id, body.user_id, body.role, action="MEMBER_ADDED")
    return _member_out(ProjectMemberRepo(conn).get(project_id, body.user_id) | {
        "username": user["username"], "email": user["email"]})


@router.patch("/{project_id}/members/{user_id}", response_model=schemas.ProjectMemberOut,
              dependencies=[Depends(access.require_role(access.ROLE_ADMIN))])
def patch_project_member(project_id: int, user_id: int, body: schemas.ProjectMemberPatchIn,
                         request: Request, conn=Depends(get_conn)):
    user = _require_project_and_user(conn, project_id, user_id)
    repo = ProjectMemberRepo(conn)
    member = repo.get(project_id, user_id)
    if member is None:
        raise HTTPException(status_code=404, detail="membre du projet introuvable")
    role = body.role if body.role is not None else member["role"]
    status = body.status if body.status is not None else member["status"]
    if role not in access.ROLES:
        raise HTTPException(status_code=422, detail=f"rôle inconnu : « {role} »")
    if status not in _STATUTS_MEMBRE_MODIFIABLES:
        raise HTTPException(status_code=422, detail=f"statut inconnu : « {status} »")
    if status == "active" and not user["is_active"]:
        raise HTTPException(status_code=409, detail="ce compte est désactivé")
    if status == "active":
        ProjectMembershipService(conn, request.state.user["id"]).set_active_member(
            project_id, user_id, role, action="MEMBER_UPDATED")
    else:
        ProjectMembershipService(conn, request.state.user["id"]).suspend(
            project_id, user_id, role)
    return _member_out(repo.get(project_id, user_id) | {
        "username": user["username"], "email": user["email"]})


@router.delete("/{project_id}/members/{user_id}", response_model=schemas.ProjectMemberOut,
               dependencies=[Depends(access.require_role(access.ROLE_ADMIN))])
def remove_project_member(project_id: int, user_id: int, request: Request,
                          conn=Depends(get_conn)):
    user = _require_project_and_user(conn, project_id, user_id)
    repo = ProjectMemberRepo(conn)
    if repo.get(project_id, user_id) is None:
        raise HTTPException(status_code=404, detail="membre du projet introuvable")
    ProjectMembershipService(conn, request.state.user["id"]).remove(project_id, user_id)
    return _member_out(repo.get(project_id, user_id) | {
        "username": user["username"], "email": user["email"]})
