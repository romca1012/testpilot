"""Connexion — comptes utilisateurs réels (2026-08-07, remplace le mot de passe unique partagé
du lot 2 du déploiement).

Routes : ouvrir une session avec un COMPTE (identifiant + mot de passe, vérifiés contre la table
`user`), savoir où on en est, se déconnecter, et — depuis le 2026-09-03 — changer SON PROPRE mot
de passe (`PATCH /password`, voir `changer_son_mot_de_passe` : jusqu'ici, seul un Admin pouvait en
réinitialiser un, `routes/users.py`). Le rôle est résolu et renvoyé pour que le frontend adapte
l'affichage — mais c'est toujours le SERVEUR, via le middleware, qui fait foi sur ce qui est
réellement autorisé (une décision se prend d'un seul côté).
"""

from __future__ import annotations

import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from testpilot import config
from testpilot.api import access, erreurs
from testpilot.api.deps import get_conn
from testpilot.store.repositories import UserRepo

router = APIRouter(prefix="/api/auth", tags=["auth"])

LOGIN_MAX_ECHECS = 5
LOGIN_FENETRE_SECONDES = 15 * 60
_echecs_connexion: dict[str, list[float]] = {}
_verrou_echecs = threading.Lock()
# Même coût de vérification pour un identifiant inexistant : évite de révéler l'existence d'un
# compte par une réponse sensiblement plus rapide.
_HACHAGE_FACTICE = access.hacher_mot_de_passe("mot-de-passe-factice-non-utilisable")


def _cle_limitation(request: Request, username: str) -> str:
    adresse = request.client.host if request.client else "inconnue"
    return f"{config.DB_PATH}|{adresse}|{username.casefold()}"


def _echecs_recents(cle: str, maintenant: float) -> list[float]:
    limite = maintenant - LOGIN_FENETRE_SECONDES
    return [instant for instant in _echecs_connexion.get(cle, []) if instant > limite]


def _est_bloque(cle: str, maintenant: float) -> bool:
    with _verrou_echecs:
        recents = _echecs_recents(cle, maintenant)
        if recents:
            _echecs_connexion[cle] = recents
        else:
            _echecs_connexion.pop(cle, None)
        return len(recents) >= LOGIN_MAX_ECHECS


def _enregistrer_echec(cle: str, maintenant: float) -> bool:
    with _verrou_echecs:
        recents = _echecs_recents(cle, maintenant)
        recents.append(maintenant)
        _echecs_connexion[cle] = recents
        return len(recents) >= LOGIN_MAX_ECHECS


def _oublier_echecs(cle: str) -> None:
    with _verrou_echecs:
        _echecs_connexion.pop(cle, None)


def _refuser_trop_de_tentatives() -> None:
    raise HTTPException(
        status_code=429,
        detail="Trop de tentatives de connexion. Réessayez dans 15 minutes.",
        headers={"Retry-After": str(LOGIN_FENETRE_SECONDES)},
    )


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
def login(body: LoginIn, request: Request, response: Response, conn=Depends(get_conn)):
    """Ouvre une session — identifiants vérifiés contre un COMPTE réel.

    ⚠️ La réponse d'échec ne distingue pas « identifiant inconnu » de « mot de passe faux » :
    un message trop précis aide qui tâtonne à deviner les identifiants existants.
    """
    identifiant = (body.username or "").strip()
    cle_limitation = _cle_limitation(request, identifiant)
    maintenant = time.monotonic()
    if _est_bloque(cle_limitation, maintenant):
        _refuser_trop_de_tentatives()

    utilisateur = UserRepo(conn).get_by_username(identifiant)
    hachage = utilisateur["password_hash"] if utilisateur is not None else _HACHAGE_FACTICE
    mot_de_passe_ok = access.verifier_mot_de_passe(body.password, hachage)
    if not mot_de_passe_ok or utilisateur is None or not utilisateur.get("is_active"):
        if _enregistrer_echec(cle_limitation, maintenant):
            _refuser_trop_de_tentatives()
        response.status_code = 401
        return SessionOut(authenticated=False)

    _oublier_echecs(cle_limitation)

    response.set_cookie(
        access.COOKIE, access.creer_jeton(utilisateur["id"], utilisateur["username"]),
        max_age=config.SESSION_DAYS * 86400,
        httponly=True,      # inaccessible au JavaScript : un script tiers ne peut pas la voler
        samesite="lax",     # pas envoyée depuis un autre site (protège des requêtes croisées)
        secure=config.COOKIE_SECURE,  # obligatoire derrière HTTPS en production
    )
    return SessionOut(authenticated=True, name=utilisateur["username"],
                      role=utilisateur["role"])


@router.post("/logout", response_model=SessionOut)
def logout(response: Response):
    response.delete_cookie(access.COOKIE)
    return SessionOut(authenticated=False)


class PasswordChangeIn(BaseModel):
    old_password: str = ""
    new_password: str = ""


@router.patch("/password", response_model=SessionOut)
def changer_son_mot_de_passe(body: PasswordChangeIn, request: Request, conn=Depends(get_conn)):
    """Un titulaire de compte change SON PROPRE mot de passe — jamais celui d'un autre.

    ⚠️ L'identité vient EXCLUSIVEMENT de la session (`request.state.user`, posé par le middleware
    `verrou_acces` sur toute requête authentifiée) — jamais d'un `user_id` dans le corps de la
    requête, qui se falsifie tout aussi facilement qu'un nom dans un formulaire HTML.

    Exige et vérifie l'ANCIEN mot de passe — différence structurante avec la réinitialisation par
    un Admin (`PATCH /api/admin/users/{id}`, `users.py`), qui n'exige rien de l'ancien : l'Admin
    agit précisément pour un compte qui a PERDU son mot de passe et ne peut donc pas le fournir ;
    ici, le titulaire le connaît encore, c'est la preuve qu'on lui demande.

    Pas de limitation de tentatives DÉDIÉE ici (contrairement à `/api/auth/login`, voir
    `LOGIN_MAX_ECHECS` ci-dessus) : contrairement au login, cette route exige DÉJÀ une session
    valide avant d'être seulement atteinte (`verrou_acces` répond 401 sinon) — un tâtonnement sur
    l'ancien mot de passe suppose donc d'avoir déjà volé une session active, un scénario que
    l'anti-brute-force du login ne couvre pas mieux : ajouter un second compteur ici ferait de la
    friction sans fermer un risque que la connexion elle-même n'a pas déjà laissé passer.

    La session en cours n'est PAS invalidée après un changement réussi : se protéger ne doit pas
    déconnecter la personne qui vient de le faire — elle resterait alors devant un écran de
    connexion juste après avoir prouvé qui elle est.
    """
    utilisateur = getattr(request.state, "user", None)
    if utilisateur is None:  # ne devrait jamais arriver — le middleware l'a déjà exigé
        raise HTTPException(status_code=401, detail="session requise")

    # `.get(...)` plutôt que `[...]` : le bouchon de test `_connecte_par_defaut`
    # (`tests/conftest.py`) pose un compte Admin de complaisance SANS `password_hash` quand aucun
    # cookie n'est présent — hors tests, un `utilisateur` réel en porte toujours un.
    if not access.verifier_mot_de_passe(body.old_password, utilisateur.get("password_hash", "")):
        raise erreurs.ErreurMetier("mot_de_passe_incorrect", "l'ancien mot de passe est incorrect")

    if len(body.new_password) < access.MOT_DE_PASSE_LONGUEUR_MIN:
        raise erreurs.ErreurMetier(
            "requete_invalide",
            f"le mot de passe doit compter au moins {access.MOT_DE_PASSE_LONGUEUR_MIN} caractères")

    UserRepo(conn).set_password_hash(
        utilisateur["id"], access.hacher_mot_de_passe(body.new_password))
    return SessionOut(authenticated=True, name=utilisateur["username"], role=utilisateur["role"])
