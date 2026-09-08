"""Migration 28 — Sous-sections (`case_group.parent_group_id`).

⚠️ **Le défaut RÉEL que ce fichier empêche de revenir** (mesuré le 2026-08-06, en démarrant le
vrai serveur contre la vraie base) : `schema.sql` portait un `CREATE INDEX ... ON
case_group(parent_group_id)` INCONDITIONNEL. Ce fichier s'exécute AVANT les migrations
(`init_db` = `executescript(schema.sql)` PUIS `_run_migrations`), via `CREATE TABLE IF NOT
EXISTS` — un NO-OP sur une base EXISTANTE, qui ne porte donc pas encore la colonne. Le serveur
plantait au tout premier démarrage contre la vraie base : `sqlite3.OperationalError: no such
column: parent_group_id`.

⚠️ **Pourquoi les tests de migration existants (`test_migration_27.py`) ne l'auraient PAS
attrapé** : ils construisent leur fixture « pré-migration » en SQL brut et appellent la fonction
de migration DIRECTEMENT — ils ne passent jamais par `init_db()`, donc jamais par `schema.sql`.
Un bug NÉ dans `schema.sql` leur est invisible par construction. Ce fichier corrige l'angle mort :
il copie la VRAIE base de production (encore en version 27 au moment d'écrire ceci) et appelle
`get_initialized_db` — le même chemin EXACT qu'emprunte le serveur réel au démarrage.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from testpilot.store.db import _SCHEMA_VERSION, get_initialized_db

_VRAIE_BASE = Path(__file__).resolve().parent.parent / "data" / "testpilot.db"


@pytest.mark.skipif(not _VRAIE_BASE.exists(), reason="pas de base réelle sur ce poste")
def test_la_migration_28_ne_plante_PAS_sur_la_vraie_base_de_production(tmp_path, monkeypatch):
    """LE test du défaut : passe par `init_db()` en entier (schema.sql PUIS migrations), sur
    une copie de la vraie base — jamais une fixture SQL reconstruite à la main, qui aurait été
    aveugle à un bug né dans `schema.sql` lui-même."""
    from testpilot import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    copie = tmp_path / "production_copie.db"
    shutil.copy2(_VRAIE_BASE, copie)

    conn = get_initialized_db(copie)   # ⚠️ LE chemin réel : executescript(schema.sql) + migrations
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == _SCHEMA_VERSION
        colonnes = {r["name"] for r in conn.execute("PRAGMA table_info(case_group)")}
        assert "parent_group_id" in colonnes
        index = {r["name"] for r in
                conn.execute("SELECT name FROM sqlite_master WHERE type='index'"
                             " AND tbl_name='case_group'")}
        assert "idx_case_group_parent" in index
    finally:
        conn.close()


def test_une_base_toute_neuve_traverse_aussi_init_db_sans_erreur(tmp_path, monkeypatch):
    """Le pendant sur une base NEUVE (schema.sql seul, sans migration à jouer) — pour s'assurer
    que le correctif n'a pas cassé le chemin inverse."""
    from testpilot import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    conn = get_initialized_db(tmp_path / "neuve.db")
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == _SCHEMA_VERSION
        colonnes = {r["name"] for r in conn.execute("PRAGMA table_info(case_group)")}
        assert "parent_group_id" in colonnes
    finally:
        conn.close()
