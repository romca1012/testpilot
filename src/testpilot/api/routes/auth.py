"""Connexion — comptes utilisateurs réels (2026-08-07, remplace le mot de passe unique partagé
du lot 2 du déploiement).

Deux routes : ouvrir une session avec un COMPTE (identifiant + mot de passe, vérifiés contre la
table `user`), et savoir où on en est. Le rôle est résolu et renvoyé pour que le frontend adapte
l'affichage — mais c'est toujours le SERVEUR, via le middleware, qui fait foi sur ce qui est
réellement autorisé (une décision se prend d'un seul côté).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from testpilot import config
from testpilot.api import access
from testpilot.api.deps import get_conn
from testpilot.store.repositories import UserRepo

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str = ""
    password: str = ""


class SessionOut(BaseModel):
    """État de la session tel que l'écran doit le comprendre. `lock_enabled` reste présent
    (toujours `True` désormais) pour ne pas casser un frontend qui le lisait déjà."""
    lock_enabled: bool = True
    authenticated: bool
    name: str = ""
    role: str = ""


@router.get("/session", response_model=SessionOut)
def session(request: Request, conn=Depends(get_conn)):
    utilisateur = access.utilisateur_actuel(conn, request)
    if utilisateur is None:
        return SessionOut(authenticated=False)
    return SessionOut(authenticated=True, name=utilisateur["username"],
                      role=utilisateur["role"])


@router.post("/login", response_model=SessionOut)
def login(body: LoginIn, response: Response, conn=Depends(get_conn)):
    """Ouvre une session — identifiants vérifiés contre un COMPTE réel.

    ⚠️ La réponse d'échec ne distingue pas « identifiant inconnu » de « mot de passe faux » :
    un message trop précis aide qui tâtonne à deviner les identifiants existants.
    """
    utilisateur = UserRepo(conn).get_by_username((body.username or "").strip())
    mot_de_passe_ok = (utilisateur is not None
                       and access.verifier_mot_de_passe(body.password,
                                                        utilisateur["password_hash"]))
    if not mot_de_passe_ok or not utilisateur.get("is_active"):
        response.status_code = 401
        return SessionOut(authenticated=False)

    response.set_cookie(
        access.COOKIE, access.creer_jeton(utilisateur["id"], utilisateur["username"]),
        max_age=config.SESSION_DAYS * 86400,
        httponly=True,      # inaccessible au JavaScript : un script tiers ne peut pas la voler
        samesite="lax",     # pas envoyée depuis un autre site (protège des requêtes croisées)
    )
    return SessionOut(authenticated=True, name=utilisateur["username"],
                      role=utilisateur["role"])


@router.post("/logout", response_model=SessionOut)
def logout(response: Response):
    response.delete_cookie(access.COOKIE)
    return SessionOut(authenticated=False)
