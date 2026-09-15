"""Migration 44 — `project.connector_type` gagne un CHECK (audit « Le pari Mabl/Testim »,
2026-09-15, item P2 avancé en Phase 0 du plan de consolidation).

Avant ce correctif, seul `'odoo'` était traité spécialement (`connectors/factory.py`) : tout le
reste — y compris une faute de frappe — tombait déjà, en silence, dans le connecteur générique.
Le CHECK ne change aucun comportement d'exécution ; il rend visible, dès l'écriture, ce qui était
déjà vrai à la lecture.
"""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from testpilot.store.db import (
    _SCHEMA_VERSION,
    _migrate_44_connector_type_valide,
    get_initialized_db,
)

_VRAIE_BASE = Path(__file__).resolve().parent.parent / "data" / "testpilot.db"

# Reprend le texte RÉEL de `schema.sql` pour `project`, tel qu'il existe aujourd'hui (avec
# `IF NOT EXISTS`) — pas une forme simplifiée : c'est exactement ce qu'une vraie base porte avant
# ce correctif (voir `test_migration_25.py`, dont la fixture pré-25 utilisait, elle, la forme SANS
# `IF NOT EXISTS` en vigueur à SON époque — le format stocké suit `schema.sql`, pas une convention
# fixe dans le temps).
_PRE_44 = """
CREATE TABLE IF NOT EXISTS project (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT    NOT NULL,
    description    TEXT    NOT NULL DEFAULT '',
    connector_type TEXT    NOT NULL DEFAULT 'odoo',
    connector_version TEXT NOT NULL DEFAULT '',
    base_url       TEXT    NOT NULL DEFAULT '',
    database       TEXT    NOT NULL DEFAULT '',
    username       TEXT    NOT NULL DEFAULT '',
    password       TEXT    NOT NULL DEFAULT '',
    deleted_at    TEXT    NOT NULL DEFAULT '',
    deleted_by    TEXT    NOT NULL DEFAULT '',
    created_at     TEXT    NOT NULL,
    default_access TEXT NOT NULL DEFAULT ''
);
CREATE UNIQUE INDEX uq_project_name ON project(name) WHERE deleted_at = '';

INSERT INTO project (id, name, connector_type, created_at) VALUES (1, 'Odoo', 'odoo', '2026-01-01');
INSERT INTO project (id, name, connector_type, created_at) VALUES (2, 'SauceDemo', 'web', '2026-01-01');
-- Une ligne qu'aucun code n'a jamais écrite intentionnellement, mais que rien n'a jamais refusée
-- non plus avant ce correctif — exactement le trou que la migration ferme.
INSERT INTO project (id, name, connector_type, created_at) VALUES (3, 'Faute de frappe', 'odooo', '2026-01-01');
"""


@pytest.fixture
def pre44(tmp_path):
    raw = sqlite3.connect(str(tmp_path / "pre44.db"))
    raw.row_factory = sqlite3.Row
    raw.executescript(_PRE_44)
    raw.commit()
    yield raw
    raw.close()


def _sql_project(conn) -> str:
    return conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='project'").fetchone()["sql"]


def test_le_check_est_installe(pre44):
    _migrate_44_connector_type_valide(pre44)
    assert "connector_type IN ('odoo', 'web')" in _sql_project(pre44)


def test_une_valeur_deja_invalide_est_normalisee_vers_web_avant_le_check(pre44):
    """Préserve le comportement déjà en vigueur (`build_connector` traite déjà tout ce qui n'est
    pas 'odoo' comme générique) plutôt que de faire échouer la migration sur une donnée que rien
    n'avait jamais rejetée."""
    _migrate_44_connector_type_valide(pre44)
    pre44.commit()
    ligne = pre44.execute("SELECT connector_type FROM project WHERE id=3").fetchone()
    assert ligne["connector_type"] == "web"


def test_les_valeurs_deja_valides_sont_preservees(pre44):
    avant = {r["id"]: dict(r) for r in pre44.execute("SELECT * FROM project ORDER BY id")}
    _migrate_44_connector_type_valide(pre44)
    pre44.commit()
    apres = {r["id"]: dict(r) for r in pre44.execute("SELECT * FROM project ORDER BY id")}
    for pid in (1, 2):
        assert apres[pid] == avant[pid]


def test_le_check_est_reellement_applique_apres_migration(pre44):
    _migrate_44_connector_type_valide(pre44)
    pre44.commit()
    with pytest.raises(sqlite3.IntegrityError):
        pre44.execute(
            "INSERT INTO project (name, connector_type, created_at) VALUES ('X', 'sap', '')")


def test_l_index_survit_a_la_reconstruction(pre44):
    _migrate_44_connector_type_valide(pre44)
    pre44.commit()
    index = {r["name"] for r in pre44.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='project'")}
    assert "uq_project_name" in index


def test_rejouer_la_migration_ne_duplique_ni_ne_casse_rien(pre44):
    _migrate_44_connector_type_valide(pre44)
    pre44.commit()
    _migrate_44_connector_type_valide(pre44)
    pre44.commit()
    assert pre44.execute("SELECT COUNT(*) AS n FROM project").fetchone()["n"] == 3
    assert _sql_project(pre44).count("connector_type IN") == 1


def test_une_table_deja_reconstruite_une_fois_se_reconstruit_encore(pre44):
    """Même défaut que celui documenté dans `test_migration_25.py` : `ALTER TABLE … RENAME TO`
    réécrit le schéma stocké avec des guillemets — une reconstruction suivante qui chercherait le
    nom SANS guillemets ne trouverait rien et casserait au démarrage."""
    pre44.execute("ALTER TABLE project RENAME TO project_tmp")
    pre44.execute("ALTER TABLE project_tmp RENAME TO project")
    pre44.commit()
    assert '"project"' in _sql_project(pre44)

    _migrate_44_connector_type_valide(pre44)
    pre44.commit()

    assert "connector_type IN ('odoo', 'web')" in _sql_project(pre44)
    assert pre44.execute("SELECT COUNT(*) AS n FROM project").fetchone()["n"] == 3


# ── Vu d'une base neuve ───────────────────────────────────────────────────────

def test_une_base_neuve_porte_deja_le_check(tmp_path, monkeypatch):
    from testpilot import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    conn = get_initialized_db(tmp_path / "neuve.db")
    assert "connector_type IN ('odoo', 'web')" in _sql_project(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO project (name, connector_type, created_at) VALUES ('X', 'sap', '')")
    conn.close()


# ── Le défaut RÉEL trouvé en rejouant cette migration sur la VRAIE base ─────────
#
# `PRAGMA foreign_key_check` SANS argument (le premier jet de cette migration, calqué sur la 19)
# vérifie TOUTE la base, pas seulement `project` — et la vraie base porte une ligne `project_member`
# orpheline (un `user` supprimé), un défaut de donnée préexistant et sans aucun rapport avec
# `connector_type`. Sans le correctif (`foreign_key_check(project)`, restreint aux clés SORTANTES
# de la seule table reconstruite), CETTE migration aurait empêché le serveur de démarrer sur un
# problème qu'elle n'a ni créé ni le pouvoir de corriger — trouvé exactement comme le décrit
# `test_migration_28.py` : jamais visible sur une fixture SQL reconstruite à la main.

@pytest.mark.skipif(not _VRAIE_BASE.exists(), reason="pas de base réelle sur ce poste")
def test_la_migration_44_ne_plante_pas_sur_la_vraie_base_de_production(tmp_path, monkeypatch):
    from testpilot import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    copie = tmp_path / "production_copie.db"
    shutil.copy2(_VRAIE_BASE, copie)

    conn = get_initialized_db(copie)  # LE chemin réel : executescript(schema.sql) + migrations
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == _SCHEMA_VERSION
        assert "connector_type IN ('odoo', 'web')" in _sql_project(conn)
    finally:
        conn.close()
