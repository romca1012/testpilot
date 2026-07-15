"""Dépendances FastAPI — connexion SQLite par requête (ouverte/fermée proprement)."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

from testpilot import config
from testpilot.store.db import get_initialized_db


def get_conn() -> Iterator[sqlite3.Connection]:
    """Connexion par requête. Le schéma est idempotent (CREATE IF NOT EXISTS)."""
    conn = get_initialized_db(config.DB_PATH)
    try:
        yield conn
    finally:
        conn.close()
