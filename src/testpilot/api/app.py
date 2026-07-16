"""Application FastAPI — sous-incrément Interface 1.1.

Sert l'API sous ``/api`` et, en production, le frontend statique compilé sous ``/`` (monté
seulement s'il a été buildé). En dev, le frontend Vite tourne à part (CORS autorisé).
Lancement : ``uvicorn testpilot.api.app:app --reload``.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from testpilot import config
from testpilot.api.routes import cases, executions, modules, projects, repairs

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
        allow_headers=["*"],
    )

    @app.get("/api/health", tags=["meta"])
    def health():
        return {"status": "ok", "version": config.APP_VERSION}

    app.include_router(projects.router)
    app.include_router(modules.router)
    app.include_router(cases.router)
    app.include_router(executions.router)
    app.include_router(repairs.router)

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
