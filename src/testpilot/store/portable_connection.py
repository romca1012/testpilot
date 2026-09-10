"""Compatibilité DB-API minimale pour exécuter les repositories sur PostgreSQL.

Les repositories historiques utilisent le contrat simple de ``sqlite3`` (SQL à paramètres
``?``, lignes indexables par nom et ``cursor.lastrowid``). Cette couche conserve ce contrat tout
en s'appuyant sur psycopg. Elle évite une réécriture risquée des règles métier et permet de faire
tourner exactement les mêmes repositories sur les deux moteurs.
"""

from __future__ import annotations

import re
import threading
from collections.abc import Iterable, Iterator, Sequence
from typing import Any

import psycopg
from psycopg.rows import dict_row

_TABLES_AVEC_ID = {
    "access_audit", "case_group", "cost_ledger", "execution",
    "module", "project", "repair_attempt", "review_decision", "scenario_result", "test_case",
    "test_case_version", "test_result", "test_run", "user",
    "user_group", "result_attachment",
    # Plans de test et planifications récurrentes (migration 43, 2026-09-10) : `PlanRepo.create`
    # et `ScheduledRunRepo.create` utilisent `.lastrowid` comme toutes les tables ci-dessus.
    "test_plan", "scheduled_run",
}
# Vérifié contre le VRAI schéma (`schema_sa.metadata`), pas retapé à l'œil (2026-09-03) :
# `generation_attempt`/`test_scenario_result` ne correspondaient à AUCUNE table réelle (noms
# fantômes) et `scenario_result` — la vraie table, remplie à chaque scénario Behave exécuté —
# en était absente : `int(cursor.lastrowid)` aurait levé `TypeError` sur PostgreSQL au premier
# vrai run. `generation_job` reste absente à raison : sa clé primaire est un TEXT (UUID) fourni
# par l'appelant, jamais un entier généré par la base — `.lastrowid` n'y a jamais de sens.
_INSERT = re.compile(r"^\s*INSERT\s+INTO\s+[\"']?([a-zA-Z_][a-zA-Z0-9_]*)", re.IGNORECASE)
ALEMBIC_HEAD = "41fbce28312f"
_urls_verifiees: set[str] = set()
_verrou_verification = threading.Lock()


def _qmark_vers_psycopg(sql: str) -> str:
    """Convertit les placeholders hors chaînes littérales, jamais les ``?`` du texte SQL."""
    resultat: list[str] = []
    quote: str | None = None
    i = 0
    while i < len(sql):
        char = sql[i]
        if quote:
            resultat.append(char)
            if char == quote:
                if i + 1 < len(sql) and sql[i + 1] == quote:
                    resultat.append(sql[i + 1])
                    i += 1
                else:
                    quote = None
        elif char in ("'", '"'):
            quote = char
            resultat.append(char)
        elif char == "?":
            resultat.append("%s")
        else:
            resultat.append(char)
        i += 1
    return "".join(resultat)


def _adapter_sql(sql: str) -> tuple[str, bool]:
    # ``user`` est un mot réservé/fonction spéciale PostgreSQL. SQLAlchemy crée donc la table
    # historique sous le nom cité ``"user"`` ; les requêtes SQLite existantes ne la citaient pas.
    sql = re.sub(r'(?<![\w"])user(?![\w"])', '"user"', sql, flags=re.IGNORECASE)
    ignore = bool(re.match(r"^\s*INSERT\s+OR\s+IGNORE\s+INTO\s+", sql, re.IGNORECASE))
    if ignore:
        sql = re.sub(r"^(\s*)INSERT\s+OR\s+IGNORE\s+INTO\s+", r"\1INSERT INTO ", sql,
                     count=1, flags=re.IGNORECASE)
        sql = sql.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"

    sql = _qmark_vers_psycopg(sql)
    match = _INSERT.match(sql)
    retour_id = bool(match and match.group(1).lower() in _TABLES_AVEC_ID
                     and " RETURNING " not in sql.upper() and not ignore)
    if retour_id:
        sql = sql.rstrip().rstrip(";") + " RETURNING id"
    return sql, retour_id


class PortableCursor:
    def __init__(self, cursor, *, lastrowid: int | None = None):
        self._cursor = cursor
        self.lastrowid = lastrowid

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def __iter__(self) -> Iterator[dict[str, Any]]:
        return iter(self._cursor)


class PostgresConnection:
    """Petit adaptateur exposant le sous-ensemble ``sqlite3.Connection`` réellement utilisé."""

    dialect = "postgresql"

    def __init__(self, url: str):
        # SQLAlchemy utilise ``postgresql+psycopg://`` ; psycopg attend ``postgresql://``.
        dsn = url.replace("postgresql+psycopg://", "postgresql://", 1)
        self._conn = psycopg.connect(dsn, row_factory=dict_row)
        if url not in _urls_verifiees:
            with _verrou_verification:
                if url not in _urls_verifiees:
                    try:
                        row = self._conn.execute(
                            "SELECT version_num FROM alembic_version").fetchone()
                    except Exception:
                        self._conn.close()
                        raise RuntimeError(
                            "schéma PostgreSQL absent : exécutez `alembic upgrade head`") from None
                    version = row["version_num"] if row else None
                    if version != ALEMBIC_HEAD:
                        self._conn.close()
                        raise RuntimeError(
                            f"schéma PostgreSQL {version!r}, attendu {ALEMBIC_HEAD!r}; "
                            "exécutez `alembic upgrade head`")
                    self._conn.commit()
                    _urls_verifiees.add(url)

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> PortableCursor:
        sql_adapte, retour_id = _adapter_sql(sql)
        cursor = self._conn.execute(sql_adapte, tuple(params or ()))
        lastrowid = None
        if retour_id:
            ligne = cursor.fetchone()
            lastrowid = int(ligne["id"]) if ligne else None
        return PortableCursor(cursor, lastrowid=lastrowid)

    def executemany(self, sql: str, params_seq: Iterable[Sequence[Any]]) -> PortableCursor:
        sql_adapte, _ = _adapter_sql(sql)
        cursor = self._conn.cursor()
        cursor.executemany(sql_adapte, params_seq)
        return PortableCursor(cursor)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()
