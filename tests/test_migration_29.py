"""Migration 29 — `generation_job`, le job de génération PERSISTÉ (2026-08-07, incident réel).

Ce que ces tests figent :
- la table existe après migration, sur une base réelle ET sur une base neuve ;
- migration 28 (parité) l'a appris à la dure : toujours vérifier via `init_db()` en entier
  (schema.sql PUIS migrations), jamais une fixture SQL reconstruite à la main — ce fichier suit
  le même patron.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from testpilot.store.db import _SCHEMA_VERSION, get_initialized_db

_VRAIE_BASE = Path(__file__).resolve().parent.parent / "data" / "testpilot.db"


@pytest.mark.skipif(not _VRAIE_BASE.exists(), reason="pas de base réelle sur ce poste")
def test_la_migration_29_ne_plante_PAS_sur_la_vraie_base_de_production(tmp_path, monkeypatch):
    from testpilot import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    copie = tmp_path / "production_copie.db"
    shutil.copy2(_VRAIE_BASE, copie)

    conn = get_initialized_db(copie)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == _SCHEMA_VERSION
        colonnes = {r["name"] for r in conn.execute("PRAGMA table_info(generation_job)")}
        assert colonnes == {"id", "status", "error", "case_ids", "module_id", "payload",
                            "cost_usd", "created_at", "updated_at"}
    finally:
        conn.close()


def test_une_base_toute_neuve_traverse_aussi_init_db_sans_erreur(tmp_path, monkeypatch):
    from testpilot import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    conn = get_initialized_db(tmp_path / "neuve.db")
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == _SCHEMA_VERSION
        colonnes = {r["name"] for r in conn.execute("PRAGMA table_info(generation_job)")}
        assert "id" in colonnes and "payload" in colonnes
    finally:
        conn.close()


def test_rejouer_la_migration_est_SANS_EFFET(tmp_path, monkeypatch):
    """Idempotence : rouvrir une base déjà migrée ne doit ni planter ni dupliquer quoi que ce
    soit (même discipline que toute migration de ce dépôt)."""
    from testpilot import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    chemin = tmp_path / "deux_fois.db"
    get_initialized_db(chemin).close()
    conn = get_initialized_db(chemin)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == _SCHEMA_VERSION
    finally:
        conn.close()
