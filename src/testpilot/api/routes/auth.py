"""Ouverture de session : le verrou d'instance et le nom du testeur (2026-07-24).

Deux routes, volontairement minuscules — ce n'est pas un système de comptes (§8 du brief, hors
V1), c'est ce qu'il faut pour qu'un serveur interne ne soit pas grand ouvert et pour savoir
**qui** a créé un cas.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from testpilot import config
from testpilot.api import access

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    password: str = ""
    name: str = ""


class SessionOut(BaseModel):
    """État de la session tel que l'écran doit le comprendre.

    `lock_enabled=False` signifie « cette instance n'a aucun verrou » — l'écran ne doit alors
    **pas** afficher un formulaire de connexion rassurant qui ne protège rien.
    """
    lock_enabled: bool
    authenticated: bool
    name: str = ""


@router.get("/session", response_model=SessionOut)
def session(request: Request):
    nom = access.utilisateur_de(request)
    return SessionOut(lock_enabled=access.verrou_actif(),
                      authenticated=(not access.verrou_actif())
                      or bool(access.lire_jeton(request.cookies.get(access.COOKIE))),
                      name=nom)


@router.post("/login", response_model=SessionOut)
def login(body: LoginIn, response: Response):
    """Ouvre une session. Sans verrou configuré, on enregistre seulement le nom.

    ⚠️ Le mot de passe est comparé à **temps constant** et la réponse d'échec ne distingue pas
    « mot de passe vide » de « mot de passe faux » : un message trop bavard aide qui tâtonne.
    """
    if access.verrou_actif() and not access.mot_de_passe_valide(body.password):
        # 401 sans détail : l'écran dit « mot de passe incorrect », le serveur n'en dit pas plus.
        response.status_code = 401
        return SessionOut(lock_enabled=True, authenticated=False)

    nom = (body.name or "").strip()[:60]
    response.set_cookie(
        access.COOKIE, access.creer_jeton(nom),
        max_age=config.SESSION_DAYS * 86400,
        httponly=True,      # inaccessible au JavaScript : un script tiers ne peut pas la voler
        samesite="lax",     # pas envoyée depuis un autre site (protège des requêtes croisées)
    )
    return SessionOut(lock_enabled=access.verrou_actif(), authenticated=True, name=nom)


@router.post("/logout", response_model=SessionOut)
def logout(response: Response):
    response.delete_cookie(access.COOKIE)
    return SessionOut(lock_enabled=access.verrou_actif(),
                      authenticated=not access.verrou_actif())
