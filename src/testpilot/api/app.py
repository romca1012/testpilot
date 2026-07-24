"""Application FastAPI — sous-incrément Interface 1.1.

Sert l'API sous ``/api`` et, en production, le frontend statique compilé sous ``/`` (monté
seulement s'il a été buildé). En dev, le frontend Vite tourne à part (CORS autorisé).
Lancement : ``uvicorn testpilot.api.app:app --reload``.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from testpilot import config
from testpilot.api import access, erreurs
from testpilot.api.routes import (
    auth, cases, corbeille, executions, groups, modules, projects, runs,
)

# Origines du serveur de dev Vite (aucune auth : usage interne, réseau local).
_DEV_ORIGINS = [
    "http://localhost:5173", "http://127.0.0.1:5173",
    "http://localhost:4173", "http://127.0.0.1:4173",
]

_FRONTEND_DIST = config.BASE_DIR / "frontend" / "dist"


def create_app() -> FastAPI:
    app = FastAPI(title="TestPilot API", version="0.1.0",
                  description="Référentiel de tests à deux axes + gate de relecture (Inc. 1.1)")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_DEV_ORIGINS,
        allow_methods=["*"],
        # `allow_credentials` : le cookie de session doit accompagner les appels du serveur Vite
        # en développement. Avec une liste d'origines explicite (jamais « * »), c'est licite.
        allow_credentials=True,
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def verrou_acces(request: Request, call_next):
        """Verrou d'instance (2026-07-24). Inactif tant qu'aucun mot de passe n'est configuré.

        Un refus est un **401 explicite** : le frontend affiche son écran de connexion au lieu de
        laisser croire à une panne. Les fichiers du frontend restent servis — sans quoi
        l'utilisateur verrait une page blanche plutôt que le formulaire.
        """
        if access.verrou_actif() and not access.chemin_libre(request.url.path):
            if not access.lire_jeton(request.cookies.get(access.COOKIE)):
                return JSONResponse(status_code=401,
                                    content={"detail": "session requise"})
        return await call_next(request)

    access.journaliser_l_etat_au_demarrage()

    # Contrat d'erreur unique (RFC 9457, lot B). Les DEUX gestionnaires sont posés : les erreurs
    # métier converties, et les `HTTPException` restantes — sinon un client devrait gérer deux
    # formats selon la route qu'il appelle, ce qui est exactement ce qu'un contrat doit éviter.
    app.add_exception_handler(erreurs.ErreurMetier, erreurs.gerer_erreur_metier)
    app.add_exception_handler(HTTPException, erreurs.gerer_http_exception)

    @app.get("/api/health", tags=["meta"])
    def health():
        """Santé + **état du verrou d'accès**.

        ⚠️ `access_lock` est ici parce que le journal ne suffisait pas : lancé par la commande
        `uvicorn` de la procédure de déploiement, le message d'état au démarrage
        (`logger.info`) **n'apparaît nulle part** — uvicorn ne configure pas les journaux de
        l'application. Un exploitant qui suivait la procédure croyait donc vérifier que son
        instance est verrouillée, et ne vérifiait rien. Trouvé en démarrant réellement le
        serveur, jamais par les tests : ils passent par le client de test, pas par uvicorn.

        Cette route est volontairement **libre d'accès** (il faut pouvoir constater qu'une
        instance est verrouillée sans y entrer) et ne révèle rien d'exploitable : savoir qu'un
        verrou existe n'aide pas à le franchir.
        """
        return {"status": "ok", "version": config.APP_VERSION,
                "access_lock": access.verrou_actif()}

    app.include_router(auth.router)
    app.include_router(corbeille.router)
    app.include_router(projects.router)
    app.include_router(modules.router)
    app.include_router(groups.router)
    app.include_router(runs.router)
    app.include_router(cases.router)
    app.include_router(executions.router)

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


app = create_app()
