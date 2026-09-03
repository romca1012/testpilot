"""Application FastAPI — sous-incrément Interface 1.1.

Sert l'API sous ``/api`` et, en production, le frontend statique compilé sous ``/`` (monté
seulement s'il a été buildé). En dev, le frontend Vite tourne à part (CORS autorisé).
Lancement : ``uvicorn testpilot.api.app:app --reload``.
"""

from __future__ import annotations

import logging
import hmac
import os
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

from testpilot import config
from testpilot.api import access, erreurs
from testpilot.api.routes import (
    auth,
    cases,
    corbeille,
    executions,
    groups,
    modules,
    projects,
    runs,
    settings,
    users,
)
from testpilot.store.db import get_initialized_db

_REQUETES = Counter(
    "testpilot_http_requests_total", "Requêtes HTTP", ["method", "route", "status"])
_LATENCE = Histogram(
    "testpilot_http_request_duration_seconds", "Durée des requêtes HTTP", ["method", "route"])
_JOBS_RUNNING = Gauge("testpilot_jobs_running", "Tâches de fond actives dans ce processus")
_JOBS_WAITING = Gauge("testpilot_jobs_waiting", "Tâches de fond en attente dans ce processus")

# Origines du serveur de dev Vite (aucune auth : usage interne, réseau local).
_DEV_ORIGINS = [
    "http://localhost:5173", "http://127.0.0.1:5173",
    "http://localhost:4173", "http://127.0.0.1:4173",
]

_FRONTEND_DIST = config.BASE_DIR / "frontend" / "dist"


def create_app() -> FastAPI:
    config.validate_production()
    app = FastAPI(
        title="TestPilot API", version="0.1.0",
        description="Référentiel de tests à deux axes + gate de relecture (Inc. 1.1)",
        docs_url="/api/docs", redoc_url="/api/redoc", openapi_url="/api/openapi.json",
    )

    async def entetes_securite_et_trace(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", "").strip()[:100] or uuid.uuid4().hex
        debut = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; base-uri 'self'; frame-ancestors 'none'; object-src 'none'; "
            "script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; connect-src 'self'"
        )
        if config.COOKIE_SECURE:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        logging.getLogger("testpilot.http").info(
            "request_id=%s method=%s path=%s status=%s duration_ms=%.1f",
            request_id, request.method, request.url.path, response.status_code,
            (time.perf_counter() - debut) * 1000,
        )
        route = getattr(request.scope.get("route"), "path", request.url.path)
        duree = time.perf_counter() - debut
        _REQUETES.labels(request.method, route, str(response.status_code)).inc()
        _LATENCE.labels(request.method, route).observe(duree)
        return response

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

        conn = get_initialized_db()
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

    # Enregistré APRÈS le verrou afin de l'envelopper aussi lorsque celui-ci retourne directement
    # un 401/403 sans appeler la route.
    app.middleware("http")(entetes_securite_et_trace)

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
        allow_origins=[] if config.PRODUCTION else _DEV_ORIGINS,
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

    @app.get("/api/health/live", tags=["meta"])
    def liveness():
        """Le processus HTTP répond. Aucun accès externe : adapté au redémarrage automatique."""
        return {"status": "ok", "version": config.APP_VERSION}

    @app.get("/api/health/ready", tags=["meta"])
    def readiness():
        """L'instance peut recevoir du trafic : base et stockage local indispensables accessibles."""
        conn = None
        try:
            conn = get_initialized_db()
            conn.execute("SELECT 1").fetchone()
            dossier = Path(config.DATA_DIR)
            if not dossier.is_dir() or not os.access(dossier, os.W_OK):
                raise OSError("répertoire de données indisponible")
        except Exception:
            logging.getLogger(__name__).exception("[readiness] dépendance indisponible")
            return JSONResponse(status_code=503, content={
                "status": "not_ready", "version": config.APP_VERSION,
            })
        finally:
            if conn is not None:
                conn.close()
        return {"status": "ready", "version": config.APP_VERSION}

    @app.get("/metrics", include_in_schema=False)
    def metrics(request: Request):
        jeton = config.METRICS_TOKEN.strip()
        fourni = request.headers.get("Authorization", "")
        attendu = f"Bearer {jeton}"
        if jeton and not hmac.compare_digest(fourni, attendu):
            # Le format volontairement générique ne confirme pas l'existence de l'endpoint.
            raise HTTPException(status_code=404, detail="not found")
        from testpilot.guardrails import concurrency

        etat_file = concurrency.get_queue().status()
        _JOBS_RUNNING.set(etat_file.running)
        _JOBS_WAITING.set(etat_file.waiting)
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

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
    conn = get_initialized_db()
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
