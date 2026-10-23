"""Migration 77 (étape 7, A108, A110) — les fiches de calcul d'un cas, et la raison d'un « Calcul détecté ».

Les quatre pièces d'une évolution de schéma (CLAUDE.md §6) : migration SQLite, révision Alembic chaînée sur la tête précédente,
`schema_sa` aligné, et ce test. Additive : un cas d'avant n'a rien de détecté et aucune fiche.
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import pytest

from testpilot.store import db, portable_connection, schema_sa
from testpilot.store.db import _migrate_77_fiches_de_calcul, get_initialized_db

RACINE = Path(__file__).resolve().parent.parent


def test_une_base_neuve_a_la_table_et_la_colonne(tmp_path):
    conn = get_initialized_db(tmp_path / "neuve.db")
    colonnes = {r["name"] for r in conn.execute("PRAGMA table_info(fiche_de_calcul)")}
    assert {"project_id", "case_id", "nom", "contenu", "origine", "statut", "retenue_par", "retenue_le"} <= colonnes
    assert "calcul_detecte" in {r["name"] for r in conn.execute("PRAGMA table_info(test_case)")}
    assert db._SCHEMA_VERSION >= 77
    conn.close()


def test_falsifiable_un_statut_ou_une_origine_inconnus_sont_refuses_par_la_base(tmp_path):
    conn = get_initialized_db(tmp_path / "neuve.db")
    conn.execute("INSERT INTO project (name, created_at) VALUES ('P', 'x')")
    pid = conn.execute("SELECT id FROM project").fetchone()[0]
    conn.execute("INSERT INTO module (project_id, name, created_at) VALUES (?, 'M', 'x')", (pid,))
    mid = conn.execute("SELECT id FROM module").fetchone()[0]
    conn.execute("INSERT INTO test_case (module_id, title, feature_slug, created_at, updated_at)"
                 " VALUES (?, 'C', 'c', 'x', 'x')", (mid,))
    cid = conn.execute("SELECT id FROM test_case").fetchone()[0]
    inserer = ("INSERT INTO fiche_de_calcul (project_id, case_id, nom, origine, statut, created_at, updated_at)"
               " VALUES (?, ?, 'Total', ?, ?, 'x', 'x')")
    conn.execute(inserer, (pid, cid, "ia", "proposee"))
    for origine, statut in (("devinee", "proposee"), ("ia", "validee")):
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(inserer, (pid, cid, origine, statut))
    conn.close()


def test_la_migration_77_est_idempotente_et_garde_les_cas_d_avant(tmp_path):
    base = sqlite3.connect(str(tmp_path / "vieille.db"))
    base.row_factory = sqlite3.Row
    base.execute("CREATE TABLE project (id INTEGER PRIMARY KEY)")
    base.execute("CREATE TABLE test_case (id INTEGER PRIMARY KEY, title TEXT)")
    base.execute("INSERT INTO test_case VALUES (7, 'Cas')")

    _migrate_77_fiches_de_calcul(base)
    _migrate_77_fiches_de_calcul(base)

    assert base.execute("SELECT calcul_detecte FROM test_case").fetchone()[0] == ""
    assert base.execute("SELECT COUNT(*) FROM fiche_de_calcul").fetchone()[0] == 0
    base.close()


def test_schema_sa_porte_la_table_et_la_colonne():
    table = schema_sa.metadata.tables["fiche_de_calcul"]
    assert {"ck_fiche_de_calcul_origine", "ck_fiche_de_calcul_statut"} <= {c.name for c in table.constraints}
    assert not schema_sa.metadata.tables["test_case"].c.calcul_detecte.nullable
    assert schema_sa.ALIGNED_WITH_SCHEMA_VERSION == db._SCHEMA_VERSION


def test_la_revision_alembic_est_chainee_sur_la_tete_precedente():
    chemin = RACINE / "alembic" / "versions" / "b8e2f4a6c193_fiches_de_calcul.py"
    spec = importlib.util.spec_from_file_location("revision_77", chemin)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)

    assert (revision.revision, revision.down_revision) == ("b8e2f4a6c193", "a7d3e9b2c418")
    assert portable_connection.ALEMBIC_HEAD == "b8e2f4a6c193"
