"""Dépendances FastAPI — connexion SQLite par requête (ouverte/fermée proprement)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from testpilot import config
from testpilot.store.db import get_initialized_db


def get_conn() -> Iterator[Any]:
    """Connexion par requête, SQLite ou PostgreSQL selon ``TESTPILOT_DB_URL``."""
    conn = get_initialized_db()
    try:
        yield conn
    finally:
        conn.close()
