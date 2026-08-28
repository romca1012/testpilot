"""Environnement Alembic — fondation PostgreSQL, phase 1/3 (voir docs/POSTGRES-MIGRATION.md).

⚠️ **N'est branché sur RIEN aujourd'hui.** Ce scaffolding sert à PROUVER que le modèle portable
(`testpilot.store.schema_sa`) se recrée proprement sur SQLite et sur PostgreSQL — la phase 3
(bascule réelle) est un chantier séparé, qui décidera alors comment `db.py`/le déploiement
appellent Alembic (ou pas) au démarrage.

**Résolution de l'URL de connexion**, dans cet ordre :
1. `TESTPILOT_DB_URL` (variable d'environnement) — ex. ``postgresql+psycopg://user:pass@host/db``
   pour pointer Alembic vers un PostgreSQL, jetable ou non.
2. À défaut, repli sur le chemin SQLite ACTUEL de l'application (`testpilot.config.DB_PATH`) —
   pour que quiconque n'a pas défini la variable obtienne un comportement identique à avant ce
   lot : rien ne casse pour qui ignore l'existence de cette fondation.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# `alembic/` vit à la racine du dépôt, mais le code applicatif est sous `src/` (même raccord que
# les scripts de `scripts/` et que `pythonpath = ["src", "."]` dans pyproject.toml).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from testpilot import config as testpilot_config
from testpilot.store import schema_sa

# Objet Config d'Alembic — accès aux valeurs de alembic.ini.
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# La CIBLE que `autogenerate`/`upgrade` doivent recréer : le modèle portable, pas les migrations
# SQLite de `db.py` (celles-ci restent le chemin réel tant que la bascule — phase 3 — n'a pas eu
# lieu). Voir le garde-fou `tests/test_schema_sa_portable.py` qui vérifie leur synchronisation.
target_metadata = schema_sa.metadata


def _url_de_connexion() -> str:
    """`TESTPILOT_DB_URL` si définie, sinon le chemin SQLite ACTUEL de l'application.

    Le repli garantit qu'un poste qui n'a jamais entendu parler de cette fondation obtient
    exactement la base qu'il utilise déjà (`testpilot.config.DB_PATH`) — jamais une base neuve
    ailleurs, jamais une erreur de configuration silencieuse.
    """
    depuis_env = os.environ.get("TESTPILOT_DB_URL")
    if depuis_env:
        return depuis_env
    # `as_posix()` : SQLAlchemy attend des slashes, y compris sur Windows, dans une URL sqlite:///.
    return f"sqlite:///{testpilot_config.DB_PATH.as_posix()}"


def run_migrations_offline() -> None:
    """Génère le SQL sans connexion (``alembic upgrade --sql``)."""
    context.configure(
        url=_url_de_connexion(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Applique les migrations via une vraie connexion (le cas courant)."""
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _url_de_connexion()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
