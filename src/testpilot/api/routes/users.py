"""Gestion des comptes utilisateurs — réservée au rôle Admin (2026-08-07).

Pas de suppression définitive d'un compte : seulement `is_active` (voir `UserRepo.set_active`,
`store/repositories.py`) — cohérent avec la suppression douce déjà pratiquée ailleurs dans l'app,
et ça évite de perdre la trace de qui a signé quoi si un compte est un jour désactivé.

Aucune de ces routes n'a besoin de `require_role("admin")` en apparence — le middleware bloque
déjà toute écriture pour `lecture_seule`/`testeur` — mais gérer des COMPTES est un cran au-dessus
de « testeur » : sans cette garde, un Testeur pourrait se créer lui-même un accès Admin.

**Peaufinage du 2026-08-11** (aucun de ces trois n'existait avant, trouvés en relisant ce module) :
- **Dernier Admin protégé** : `patch_user` refuse de désactiver/rétrograder le dernier compte Admin
  actif — sinon plus personne ne pourrait plus gérer ni comptes ni accès.
- **Réinitialisation de mot de passe** (`UserPatchIn.new_password`) : un Admin peut fixer un
  nouveau mot de passe sur un compte qui a oublié le sien — jusqu'ici, aucun recours n'existait.
- **Longueur minimale** (`access.MOT_DE_PASSE_LONGUEUR_MIN`), posée à la création ET à la
  réinitialisation — un mot de passe d'un seul caractère était accepté jusque-là.
"""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request

from testpilot.api import access, erreurs, schemas
from testpilot.api.deps import get_conn
from testpilot.api.services import notification_service
from testpilot.api.services.project_membership_service import ProjectMembershipService
from testpilot.store.repositories import (
    DuplicateName,
    ProjectRepo,
    UserGroupRepo,
    UserRepo,
)

router = APIRouter(prefix="/api/admin/users", tags=["users"],
                   dependencies=[Depends(access.require_role(access.ROLE_ADMIN))])


def _out(row: dict) -> schemas.UserOut:
    return schemas.UserOut(id=row["id"], username=row["username"], role=row["role"],
                           email=row.get("email") or "", is_active=bool(row["is_active"]),
                           created_at=row["created_at"])


def _group_out(repo: UserGroupRepo, row: dict) -> schemas.UserGroupOut:
    return schemas.UserGroupOut(
        id=row["id"], name=row["name"], member_count=row.get("member_count", 0),
        created_at=row["created_at"], members=[schemas.UserGroupMemberOut(
            id=u["id"], username=u["username"], email=u.get("email") or "",
            role=u["role"], is_active=bool(u["is_active"])) for u in repo.members(row["id"])])


def _verifier_membres_groupe(conn, user_ids: list[int]) -> None:
    if len(user_ids) != len(set(user_ids)):
        raise erreurs.ErreurMetier("requete_invalide", "un utilisateur ne peut figurer qu’une fois dans le groupe")
    connus = {u["id"] for u in UserRepo(conn).list_all()}
    inconnus = set(user_ids) - connus
    if inconnus:
        raise erreurs.ErreurMetier("requete_invalide", f"utilisateur inconnu : {min(inconnus)}")


@router.get("/groups", response_model=list[schemas.UserGroupOut])
def list_groups(conn=Depends(get_conn)):
    repo = UserGroupRepo(conn)
    return [_group_out(repo, row) for row in repo.list_all()]


@router.post("/groups", response_model=schemas.UserGroupOut)
def create_group(body: schemas.UserGroupIn, conn=Depends(get_conn)):
    _verifier_membres_groupe(conn, body.user_ids)
    repo = UserGroupRepo(conn)
    try:
        group_id = repo.create(body.name, body.user_ids)
    except (DuplicateName, ValueError) as exc:
        raise erreurs.ErreurMetier("nom_deja_pris" if isinstance(exc, DuplicateName) else "requete_invalide", str(exc)) from exc
    return _group_out(repo, repo.get(group_id))


@router.put("/groups/{group_id}", response_model=schemas.UserGroupOut)
def update_group(group_id: int, body: schemas.UserGroupIn, conn=Depends(get_conn)):
    repo = UserGroupRepo(conn)
    if repo.get(group_id) is None:
        raise erreurs.ErreurMetier("introuvable", f"groupe {group_id} introuvable")
    _verifier_membres_groupe(conn, body.user_ids)
    ancien = repo.get(group_id)
    anciens_membres = [u["id"] for u in repo.members(group_id)]
    try:
        repo.update(group_id, body.name, body.user_ids)
    except (DuplicateName, ValueError) as exc:
        raise erreurs.ErreurMetier("nom_deja_pris" if isinstance(exc, DuplicateName) else "requete_invalide", str(exc)) from exc
    projets_affectes = [row["project_id"] for row in conn.execute(
        "SELECT project_id FROM project_group_access WHERE group_id=?", (group_id,)).fetchall()]
    for project_id in projets_affectes:
        admins = sum(1 for user in UserRepo(conn).list_all()
                     if user["is_active"] and access.role_effectif_projet(
                         conn, user, project_id) == access.ROLE_ADMIN)
        if admins == 0:
            repo.update(group_id, ancien["name"], anciens_membres)
            raise erreurs.ErreurMetier(
                "etat_incompatible",
                "impossible : cette composition laisserait un projet sans Admin actif")
    return _group_out(repo, repo.get(group_id))


@router.delete("/groups/{group_id}", status_code=204)
def delete_group(group_id: int, conn=Depends(get_conn)):
    repo = UserGroupRepo(conn)
    if repo.get(group_id) is None:
        raise erreurs.ErreurMetier("introuvable", f"groupe {group_id} introuvable")
    if conn.execute(
            "SELECT 1 FROM project_group_access WHERE group_id=? LIMIT 1", (group_id,)).fetchone():
        raise erreurs.ErreurMetier(
            "etat_incompatible",
            "ce groupe possède encore des accès projet — retirez-les avant de supprimer le groupe")
    repo.delete(group_id)


@router.get("", response_model=list[schemas.UserOut])
def list_users(conn=Depends(get_conn)):
    return [_out(u) for u in UserRepo(conn).list_all()]


@router.get("/{user_id}", response_model=schemas.UserOut)
def get_user(user_id: int, conn=Depends(get_conn)):
    utilisateur = UserRepo(conn).get(user_id)
    if utilisateur is None:
        raise erreurs.ErreurMetier("introuvable", f"utilisateur {user_id} introuvable")
    return _out(utilisateur)


def _verifier_longueur_mot_de_passe(mot_de_passe: str) -> None:
    access.verifier_politique_mot_de_passe(mot_de_passe)


def _verifier_acces_projets(conn, projects: list[schemas.UserProjectAccessIn]) -> None:
    ids_connus = {p["id"] for p in ProjectRepo(conn).list_all()}
    ids_vus: set[int] = set()
    for choix in projects:
        if choix.project_id in ids_vus:
            raise erreurs.ErreurMetier("requete_invalide", "un projet ne peut être sélectionné qu’une fois")
        ids_vus.add(choix.project_id)
        if choix.project_id not in ids_connus:
            raise HTTPException(status_code=404, detail=f"projet {choix.project_id} introuvable")
        if choix.role not in access.ROLES:
            raise erreurs.ErreurMetier("requete_invalide", f"rôle inconnu : « {choix.role} »")


def _appliquer_acces_projets(conn, actor_user_id: int, user_id: int,
                             projects: list[schemas.UserProjectAccessIn]) -> None:
    choix = {p.project_id: p.role for p in projects}
    service = ProjectMembershipService(conn, actor_user_id)
    for projet in ProjectRepo(conn).list_all():
        project_id = projet["id"]
        if project_id in choix:
            service.set_active_member(project_id, user_id, choix[project_id], action="USER_PROJECT_SET")
        else:
            service.remove(project_id, user_id)


@router.post("", response_model=schemas.UserCreateOut)
def create_user(body: schemas.UserCreateIn, request: Request, conn=Depends(get_conn)):
    """⚠️ **Le mot de passe n'est plus l'Admin qui l'invente** (audit 2026-09-09) : un Admin qui
    transmet lui-même le mot de passe d'un compte qu'il ne détient pas est exactement la faille
    corrigée ici — laisser `password` vide fait générer un mot de passe temporaire côté serveur
    et l'envoyer par email si l'adresse est connue, comme pour n'importe quel autre service."""
    if body.role not in access.ROLES:
        raise erreurs.ErreurMetier("requete_invalide", f"rôle inconnu : « {body.role} »")
    # Un mot de passe EXPLICITEMENT choisi par l'Admin reste vérifié contre la politique — celui
    # qu'on génère ci-dessous (24 caractères aléatoires) la dépasse toujours largement.
    if body.password:
        _verifier_longueur_mot_de_passe(body.password)
    mot_de_passe = body.password or secrets.token_urlsafe(18)
    if body.projects is not None:
        _verifier_acces_projets(conn, body.projects)
    try:
        uid = UserRepo(conn).create(username=body.username,
                                    password_hash=access.hacher_mot_de_passe(mot_de_passe),
                                    role=body.role, email=body.email, must_change_password=True)
    except DuplicateName as exc:
        raise erreurs.ErreurMetier("nom_deja_pris", str(exc)) from exc
    if body.projects is not None:
        _appliquer_acces_projets(conn, request.state.user["id"], uid, body.projects)

    email_envoye = False
    if body.email:
        email_envoye, _erreur = notification_service.envoyer(
            conn, destinataire=body.email, sujet="Votre compte TestPilot",
            corps=(f"Un compte TestPilot vient d'être créé pour vous.\n\n"
                   f"Identifiant : {body.username}\n"
                   f"Mot de passe temporaire : {mot_de_passe}\n\n"
                   f"Connectez-vous puis choisissez votre propre mot de passe — le temporaire "
                   f"ne sera plus valide une fois cette étape faite."))
    sortie = _out(UserRepo(conn).get(uid))
    return schemas.UserCreateOut(
        **sortie.model_dump(), email_envoye=email_envoye,
        # Affiché une seule fois : c'est le SEUL moyen de transmettre l'accès quand l'email n'a
        # pas pu partir (pas d'adresse renseignée, SMTP indisponible…) — jamais reconsultable.
        mot_de_passe_initial=None if email_envoye else mot_de_passe)


@router.get("/{user_id}/projects", response_model=list[schemas.UserProjectAccessOut])
def get_user_projects(user_id: int, conn=Depends(get_conn)):
    if UserRepo(conn).get(user_id) is None:
        raise erreurs.ErreurMetier("introuvable", f"utilisateur {user_id} introuvable")
    members = {m["project_id"]: m for m in conn.execute(
        "SELECT * FROM project_member WHERE user_id=?", (user_id,)).fetchall()}
    return [schemas.UserProjectAccessOut(
        project_id=p["id"], project_name=p["name"],
        role=(members.get(p["id"])["role"] if members.get(p["id"]) else access.ROLE_LECTURE_SEULE),
        has_access=bool(members.get(p["id"]) and members[p["id"]]["status"] == "active"),
    ) for p in ProjectRepo(conn).list_all()]


@router.put("/{user_id}/projects", response_model=list[schemas.UserProjectAccessOut])
def put_user_projects(user_id: int, body: schemas.UserProjectAccessListIn,
                      request: Request, conn=Depends(get_conn)):
    if UserRepo(conn).get(user_id) is None:
        raise erreurs.ErreurMetier("introuvable", f"utilisateur {user_id} introuvable")
    _verifier_acces_projets(conn, body.projects)
    _appliquer_acces_projets(conn, request.state.user["id"], user_id, body.projects)
    return get_user_projects(user_id, conn)


@router.patch("/{user_id}", response_model=schemas.UserOut)
def patch_user(user_id: int, body: schemas.UserPatchIn, conn=Depends(get_conn)):
    repo = UserRepo(conn)
    utilisateur = repo.get(user_id)
    if utilisateur is None:
        raise erreurs.ErreurMetier("introuvable", f"utilisateur {user_id} introuvable")

    # ⚠️ Dernier Admin actif protégé (2026-08-11) — même risque d'auto-blocage que la surcharge
    # d'accès par projet évite déjà, mais ICI : plus personne ne pourrait gérer AUCUN compte ni
    # AUCUN accès. Vérifié AVANT toute écriture, sur l'état réel du compte visé (pas sur l'intention
    # brute du patch) : rétrograder ou désactiver un Admin qui n'est déjà plus Admin/actif ne pose
    # aucun problème.
    perd_le_statut = (
        (body.role is not None and body.role != access.ROLE_ADMIN)
        or body.is_active is False)
    if (utilisateur["role"] == access.ROLE_ADMIN and utilisateur["is_active"]
            and perd_le_statut and repo.admins_actifs_restants(exclude_user_id=user_id) == 0):
        raise erreurs.ErreurMetier(
            "etat_incompatible",
            "impossible : c'est le dernier compte Admin actif — l'instance se retrouverait sans "
            "personne pour gérer les comptes et les accès")

    if body.role is not None:
        if body.role not in access.ROLES:
            raise erreurs.ErreurMetier("requete_invalide", f"rôle inconnu : « {body.role} »")
        repo.set_role(user_id, body.role)
    if body.is_active is not None:
        repo.set_active(user_id, body.is_active)
    if body.new_password is not None:
        _verifier_longueur_mot_de_passe(body.new_password)
        repo.set_password_hash(user_id, access.hacher_mot_de_passe(body.new_password), temporary=True)
    if body.email is not None:
        repo.set_email(user_id, body.email)
    return _out(repo.get(user_id))
