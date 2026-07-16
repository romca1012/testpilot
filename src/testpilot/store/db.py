"""Accès SQLite bas niveau : connexion, initialisation du schéma et migrations.

Le schéma CIBLE vit dans ``schema.sql`` (SQL portable, ``CREATE IF NOT EXISTS``). Les bases
DÉJÀ existantes sont amenées à la cible par des migrations versionnées via ``PRAGMA
user_version`` — chaque migration est idempotente (gardée par introspection). Aucune logique
métier ici.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from testpilot import config

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")

# Version cible du schéma. Incrémentée à chaque migration ajoutée ci-dessous.
_SCHEMA_VERSION = 4


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Ouvre une connexion SQLite avec les lignes indexables par nom et les FK actives."""
    path = Path(db_path) if db_path else config.DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Crée les tables manquantes (idempotent) puis applique les migrations en attente."""
    conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()
    _run_migrations(conn)


def get_initialized_db(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Raccourci : connexion + schéma prêt à l'emploi (migrations incluses)."""
    conn = connect(db_path)
    init_db(conn)
    return conn


# ── Migrations ────────────────────────────────────────────────────────────────
def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}


def _run_migrations(conn: sqlite3.Connection) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version < 1:
        _migrate_1_project_module(conn)
    if version < 2:
        _migrate_2_project_connector(conn)
    if version < 3:
        _migrate_3_case_priority(conn)
    if version < 4:
        _migrate_4_execution_field_fallbacks(conn)
    conn.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
    conn.commit()


def _migrate_1_project_module(conn: sqlite3.Connection) -> None:
    """Hiérarchie Projet → Module → Cas (§7) + séparation feature_slug / module_id.

    Amène une base d'avant la hiérarchie (colonne texte ``test_case.module``) à la cible :
    tables project/module, colonnes ``module_id`` + ``feature_slug`` sur test_case, backfill
    des cas existants sous un projet « Odoo », puis suppression de la colonne ``module``.
    Idempotent : sur une base déjà à la cible, chaque étape est ignorée. Voir décision 0004.
    """
    now = datetime.now(timezone.utc).isoformat()
    cols = _column_names(conn, "test_case")

    # 1. Colonnes ajoutées seulement si absentes (base neuve : déjà présentes via schema.sql).
    if "module_id" not in cols:
        conn.execute("ALTER TABLE test_case ADD COLUMN module_id INTEGER REFERENCES module(id)")
    if "feature_slug" not in cols:
        conn.execute("ALTER TABLE test_case ADD COLUMN feature_slug TEXT NOT NULL DEFAULT ''")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_case_module ON test_case(module_id)")

    # 2. Backfill : uniquement si l'ancienne colonne texte ``module`` existe encore.
    if "module" in cols:
        rows = conn.execute(
            "SELECT DISTINCT module FROM test_case WHERE module IS NOT NULL AND module <> ''"
        ).fetchall()
        if rows:
            project_id = _ensure_project(conn, "Odoo", now)
            for row in rows:
                slug = row["module"]
                module_id = _ensure_module(conn, project_id, _prettify(slug), now)
                conn.execute(
                    "UPDATE test_case SET module_id=?, feature_slug=? WHERE module=?",
                    (module_id, slug, slug),
                )
        # 3. Suppression de la colonne obsolète (double rôle éliminé — décision 0004).
        conn.execute("ALTER TABLE test_case DROP COLUMN module")


def _migrate_2_project_connector(conn: sqlite3.Connection) -> None:
    """Le connecteur remonte au PROJET, et quitte le cas de test (décision 0005).

    Ajoute connector_type + paramètres de connexion sur ``project`` ; renomme le projet
    par défaut « Odoo » (nom de connecteur, erroné) en « Portail Sapian » avec sa connexion
    reprise de la config ; supprime ``test_case.connector_type``. Idempotent.
    """
    pcols = _column_names(conn, "project")
    for col in ("connector_type", "base_url", "database", "username", "password"):
        if col not in pcols:
            default = "'odoo'" if col == "connector_type" else "''"
            conn.execute(f"ALTER TABLE project ADD COLUMN {col} TEXT NOT NULL DEFAULT {default}")

    # Reprise de la connexion existante (config env) pour le projet par défaut mal nommé.
    odoo = conn.execute("SELECT id FROM project WHERE name='Odoo'").fetchone()
    if odoo:
        conn.execute(
            "UPDATE project SET name='Portail Sapian', connector_type='odoo',"
            " base_url=?, database=?, username=?, password=? WHERE id=?",
            (config.ODOO_URL, config.ODOO_DB, config.ODOO_USER, config.ODOO_PASSWORD, odoo["id"]))

    if "connector_type" in _column_names(conn, "test_case"):
        conn.execute("ALTER TABLE test_case DROP COLUMN connector_type")


def _migrate_3_case_priority(conn: sqlite3.Connection) -> None:
    """Priorité de lecture sur le cas (décision 0006). Idempotent.

    Étiquette assumée (low|medium|high) : elle ne promet AUCUN ordre d'exécution — celui-ci
    est dicté par l'ordre des scénarios dans le .feature. On n'ajoute donc pas de colonne
    ``position`` décorative (l'ancien prototype en avait une, jamais alimentée).
    """
    if "priority" not in _column_names(conn, "test_case"):
        conn.execute("ALTER TABLE test_case ADD COLUMN priority TEXT NOT NULL DEFAULT 'medium'")


def _migrate_4_execution_field_fallbacks(conn: sqlite3.Connection) -> None:
    """Replis « libellé → nom technique » attachés à l'exécution (décision 0007, phase B+).
    Idempotent.

    Liste JSON des replis tracés par les helpers UI pendant le run. Attachée à l'EXÉCUTION (pas
    au scénario) : le repli doit rester lisible a posteriori, y compris sur un run vert, sinon
    un champ réellement renommé côté application serait absorbé sans que personne ne le voie.
    """
    if "field_fallbacks" not in _column_names(conn, "execution"):
        conn.execute("ALTER TABLE execution ADD COLUMN field_fallbacks TEXT NOT NULL DEFAULT ''")


def _ensure_project(conn: sqlite3.Connection, name: str, now: str) -> int:
    row = conn.execute("SELECT id FROM project WHERE name=?", (name,)).fetchone()
    if row:
        return int(row["id"])
    cur = conn.execute(
        "INSERT INTO project (name, description, created_at) VALUES (?,?,?)", (name, "", now))
    return int(cur.lastrowid)


def _ensure_module(conn: sqlite3.Connection, project_id: int, name: str, now: str) -> int:
    row = conn.execute(
        "SELECT id FROM module WHERE project_id=? AND name=?", (project_id, name)).fetchone()
    if row:
        return int(row["id"])
    cur = conn.execute(
        "INSERT INTO module (project_id, name, description, created_at) VALUES (?,?,?,?)",
        (project_id, name, "", now))
    return int(cur.lastrowid)


def _prettify(slug: str) -> str:
    """'demande_materiel' → 'Demande materiel' (nom métier lisible depuis un slug technique)."""
    s = slug.replace("_", " ").replace("-", " ").strip()
    return s[:1].upper() + s[1:] if s else s
