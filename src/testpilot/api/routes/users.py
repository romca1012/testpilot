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

from fastapi import APIRouter, Depends

from testpilot.api import access, erreurs, schemas
from testpilot.api.deps import get_conn
from testpilot.store.repositories import DuplicateName, UserRepo

router = APIRouter(prefix="/api/admin/users", tags=["users"],
                   dependencies=[Depends(access.require_role(access.ROLE_ADMIN))])


def _out(row: dict) -> schemas.UserOut:
    return schemas.UserOut(id=row["id"], username=row["username"], role=row["role"],
                           email=row.get("email") or "", is_active=bool(row["is_active"]),
                           created_at=row["created_at"])


@router.get("", response_model=list[schemas.UserOut])
def list_users(conn=Depends(get_conn)):
    return [_out(u) for u in UserRepo(conn).list_all()]


def _verifier_longueur_mot_de_passe(mot_de_passe: str) -> None:
    if len(mot_de_passe) < access.MOT_DE_PASSE_LONGUEUR_MIN:
        raise erreurs.ErreurMetier(
            "requete_invalide",
            f"le mot de passe doit compter au moins {access.MOT_DE_PASSE_LONGUEUR_MIN} caractères")


@router.post("", response_model=schemas.UserOut)
def create_user(body: schemas.UserCreateIn, conn=Depends(get_conn)):
    if body.role not in access.ROLES:
        raise erreurs.ErreurMetier("requete_invalide", f"rôle inconnu : « {body.role} »")
    _verifier_longueur_mot_de_passe(body.password)
    try:
        uid = UserRepo(conn).create(username=body.username,
                                    password_hash=access.hacher_mot_de_passe(body.password),
                                    role=body.role, email=body.email)
    except DuplicateName as exc:
        raise erreurs.ErreurMetier("nom_deja_pris", str(exc)) from exc
    return _out(UserRepo(conn).get(uid))


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
        repo.set_password_hash(user_id, access.hacher_mot_de_passe(body.new_password))
    if body.email is not None:
        repo.set_email(user_id, body.email)
    return _out(repo.get(user_id))
