"""Accès SQLite bas niveau : connexion et initialisation du schéma.

Le schéma vit dans ``schema.sql`` (SQL portable). Ce module ne fait qu'ouvrir la
connexion et exécuter le DDL — aucune logique métier ici.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from testpilot import config

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Ouvre une connexion SQLite avec les lignes indexables par nom et les FK actives."""
    path = Path(db_path) if db_path else config.DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Crée les tables si elles n'existent pas (idempotent)."""
    conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()


def get_initialized_db(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Raccourci : connexion + schéma prêt à l'emploi."""
    conn = connect(db_path)
    init_db(conn)
    return conn
