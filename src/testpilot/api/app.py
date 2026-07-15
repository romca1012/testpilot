"""Application FastAPI — sous-incrément Interface 1.1.

Sert l'API sous ``/api`` et, en production, le frontend statique compilé sous ``/`` (monté
seulement s'il a été buildé). En dev, le frontend Vite tourne à part (CORS autorisé).
Lancement : ``uvicorn testpilot.api.app:app --reload``.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from testpilot import config
from testpilot.api.routes import cases, executions

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

    app.include_router(cases.router)
    app.include_router(executions.router)

    # Frontend compilé (prod) : monté à la racine s'il existe. Absent en dev → API seule.
    if _FRONTEND_DIST.is_dir():
        app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="frontend")

    return app


app = create_app()
