"""Application FastAPI — sous-incrément Interface 1.1.

Sert l'API sous ``/api`` et, en production, le frontend statique compilé sous ``/`` (monté
seulement s'il a été buildé). En dev, le frontend Vite tourne à part (CORS autorisé).
Lancement : ``uvicorn testpilot.api.app:app --reload``.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from testpilot import config
from testpilot.api import access, erreurs
from testpilot.api.routes import (
    auth, cases, corbeille, executions, groups, modules, projects, runs, settings,
    steps_library, users,
)
from testpilot.store.db import get_initialized_db

# Origines du serveur de dev Vite (aucune auth : usage interne, réseau local).
_DEV_ORIGINS = [
    "http://localhost:5173", "http://127.0.0.1:5173",
    "http://localhost:4173", "http://127.0.0.1:4173",
]

_FRONTEND_DIST = config.BASE_DIR / "frontend" / "dist"


def create_app() -> FastAPI:
    app = FastAPI(title="TestPilot API", version="0.1.0",
                  description="Référentiel de tests à deux axes + gate de relecture (Inc. 1.1)")

    @app.middleware("http")
    async def verrou_acces(request: Request, call_next):
        """Connexion obligatoire (2026-08-07 — comptes utilisateurs, remplace le mot de passe
        unique partagé du lot 2). Deux refus possibles :

        - **401** : pas de session valide (jeton absent/invalide/expiré) OU le compte pointé a
          été désactivé entre-temps — l'écran affiche le formulaire de connexion.
        - **403** : session valide, mais rôle `lecture_seule` sur une écriture — l'écran dit
          « droits insuffisants », pas « déconnecté ».

        Le rôle et l'état actif sont relus EN BASE ici, PAS depuis le jeton (voir
        `access.utilisateur_actuel`) : une désactivation ou un changement de rôle par un Admin
        doit mordre tout de suite, pas attendre l'expiration de la session (30 jours par défaut).
        `request.state.user` est posé pour le reste de la requête (routes, `require_role`) —
        évite une seconde lecture base pour qui en a besoin.

        ⚠️ **`OPTIONS` (préflight CORS) passe TOUJOURS**, jamais authentifié — un navigateur
        n'envoie pas le cookie de session sur cette requête-là (elle précède la vraie, qui seule
        le porte).
        """
        if request.method == "OPTIONS" or access.chemin_libre(request.url.path):
            return await call_next(request)

        conn = get_initialized_db(config.DB_PATH)
        try:
            utilisateur = access.utilisateur_actuel(conn, request)
        finally:
            conn.close()

        if utilisateur is None:
            return JSONResponse(status_code=401, content={"detail": "session requise"})
        if access.ecriture_bloquee(utilisateur["role"], request.method, request.url.path):
            return JSONResponse(status_code=403, content={"detail": "droits insuffisants"})

        request.state.user = utilisateur
        return await call_next(request)

    # ⚠️ **AJOUTÉ APRÈS `verrou_acces`, délibérément** — Starlette empile les middlewares en
    # LIFO (le dernier ajouté est le plus EXTÉRIEUR). `CORSMiddleware` doit envelopper
    # `verrou_acces`, pas l'inverse : un 401/403 renvoyé PAR `verrou_acces` SANS appeler
    # `call_next` ne traverse alors jamais `CORSMiddleware`, qui n'a donc pas l'occasion d'y
    # ajouter les en-têtes CORS attendus — le navigateur voit une réponse cross-origin sans ces
    # en-têtes et la remonte comme `net::ERR_FAILED`, jamais comme le vrai code HTTP (bug réel,
    # trouvé en vérification live 2026-08-07 : un compte Lecture seule bloqué à raison affichait
    # une erreur réseau opaque, pas « droits insuffisants »). Avec `CORSMiddleware` extérieur, le
    # 401/403 de `verrou_acces` EST la réponse que `CORSMiddleware` reçoit de son propre
    # `call_next` — il la décore normalement, quelle que soit son origine dans la pile.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_DEV_ORIGINS,
        allow_methods=["*"],
        # `allow_credentials` : le cookie de session doit accompagner les appels du serveur Vite
        # en développement. Avec une liste d'origines explicite (jamais « * »), c'est licite.
        allow_credentials=True,
        allow_headers=["*"],
    )

    access.journaliser_l_etat_au_demarrage()
    _amorcer_premier_admin()

    # Contrat d'erreur unique (RFC 9457, lot B). Les DEUX gestionnaires sont posés : les erreurs
    # métier converties, et les `HTTPException` restantes — sinon un client devrait gérer deux
    # formats selon la route qu'il appelle, ce qui est exactement ce qu'un contrat doit éviter.
    app.add_exception_handler(erreurs.ErreurMetier, erreurs.gerer_erreur_metier)
    app.add_exception_handler(HTTPException, erreurs.gerer_http_exception)

    @app.get("/api/health", tags=["meta"])
    def health():
        """Santé + **état du verrou d'accès** (`access_lock`, toujours `True` depuis le
        2026-08-07 — la connexion est désormais obligatoire, conservé pour ne pas casser un
        appelant qui le lisait déjà). Volontairement **libre d'accès** : il faut pouvoir
        constater l'état de l'instance sans y entrer, et ça ne révèle rien d'exploitable."""
        return {"status": "ok", "version": config.APP_VERSION,
                "access_lock": access.verrou_actif()}

    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(corbeille.router)
    app.include_router(projects.router)
    app.include_router(modules.router)
    app.include_router(groups.router)
    app.include_router(runs.router)
    app.include_router(cases.router)
    app.include_router(executions.router)
    app.include_router(settings.router)
    app.include_router(steps_library.router)

    # Frontend compilé (prod) : assets hashés + fallback SPA vers index.html pour que les
    # deep-links client (/cases, /executions/1) fonctionnent au rafraîchissement. Absent en
    # dev → API seule (le front tourne sous Vite). Monté APRÈS les routers /api.
    if _FRONTEND_DIST.is_dir():
        assets = _FRONTEND_DIST / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")
        index = _FRONTEND_DIST / "index.html"

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa_fallback(full_path: str):
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="not found")
            candidate = _FRONTEND_DIST / full_path
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(index)

    return app


def _amorcer_premier_admin() -> None:
    """Crée le tout premier compte Admin, UNE SEULE FOIS, depuis `TESTPILOT_ADMIN_USERNAME` /
    `TESTPILOT_ADMIN_PASSWORD` (2026-08-07) — le problème que ça résout : une base neuve n'a
    AUCUN compte, et personne ne peut se connecter pour en créer un.

    ⚠️ Ne joue QUE si la table `user` est encore VIDE — jamais si un Admin existe déjà, même si
    les variables restent renseignées après coup (sinon un admin qui change son propre mot de
    passe le verrait silencieusement réécrasé au prochain redémarrage du serveur)."""
    from testpilot.store.repositories import UserRepo

    if not (config.ADMIN_USERNAME and config.ADMIN_PASSWORD):
        return
    conn = get_initialized_db(config.DB_PATH)
    try:
        repo = UserRepo(conn)
        if repo.count() > 0:
            return
        repo.create(username=config.ADMIN_USERNAME,
                   password_hash=access.hacher_mot_de_passe(config.ADMIN_PASSWORD),
                   role=access.ROLE_ADMIN)
        logging.getLogger(__name__).info(
            "[accès] premier compte Admin créé : %s", config.ADMIN_USERNAME)
    finally:
        conn.close()


app = create_app()
