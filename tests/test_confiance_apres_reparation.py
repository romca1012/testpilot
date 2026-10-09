"""Lot VH-03 (V4, D28) — le run d'une version RÉPARÉE par l'agent et pas encore relue n'est jamais le résultat du cas.

Avant (audit du 2026-10-08) : le vert d'une version réécrite par l'agent de réparation était écrit dans `test_case.last_*`,
avec une confiance « nominale » — la liste affichait « Réussi » pour un test qu'aucun humain n'avait relu, et le gardait même
quand la réparation était ensuite refusée. Ici : migration 59 (nouvelle valeur `apres_reparation`, SQLite + Alembic +
`schema_sa`), et `run_service._persist` trace le run sans toucher au résultat du cas.
"""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest

from testpilot import config
from testpilot.api.services import run_service
from testpilot.execution.behave_result import BehaveResult, BehaveScenario
from testpilot.store.db import _migrate_59_confiance_apres_reparation, get_initialized_db
from testpilot.store.repositories import CaseRepo, ExecutionRepo, ModuleRepo, ProjectRepo, ReviewRepo, VersionRepo
from testpilot.verdict import status as st


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    c = get_initialized_db(tmp_path / "r.db")
    yield c
    c.close()


# ── Migration 59 ──────────────────────────────────────────────────────────────────────────────────────────


def test_base_neuve_accepte_la_nouvelle_confiance(conn):
    sql = conn.execute("SELECT sql FROM sqlite_master WHERE name='execution'").fetchone()[0]

    assert "'apres_reparation'" in sql


_SCHEMA_PRE_59 = """
CREATE TABLE test_case (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL);
CREATE TABLE execution (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_case_id INTEGER NOT NULL,
    confiance TEXT NOT NULL DEFAULT 'nominale' CHECK (confiance IN ('nominale', 'auto_resolue', 'apres_retry')),
    FOREIGN KEY (test_case_id) REFERENCES test_case(id)
);
CREATE INDEX idx_execution_case ON execution(test_case_id);
"""


def test_falsifiable_reprise_d_une_base_pre_59(tmp_path):
    """Avant migration la valeur est REFUSÉE (le CHECK mord vraiment) ; après, acceptée, données et index préservés."""
    base = sqlite3.connect(str(tmp_path / "vieille.db"))
    base.row_factory = sqlite3.Row
    base.executescript(_SCHEMA_PRE_59)
    base.execute("INSERT INTO test_case (id, title) VALUES (1, 'Cas')")
    base.execute("INSERT INTO execution (id, test_case_id, confiance) VALUES (10, 1, 'apres_retry')")
    base.commit()
    with pytest.raises(sqlite3.IntegrityError):
        base.execute("INSERT INTO execution (test_case_id, confiance) VALUES (1, 'apres_reparation')")
    base.rollback()

    _migrate_59_confiance_apres_reparation(base)
    _migrate_59_confiance_apres_reparation(base)  # idempotente

    base.execute("INSERT INTO execution (test_case_id, confiance) VALUES (1, 'apres_reparation')")
    assert base.execute("SELECT confiance FROM execution WHERE id=10").fetchone()[0] == "apres_retry"
    assert base.execute("SELECT name FROM sqlite_master WHERE name='idx_execution_case'").fetchone()
    with pytest.raises(sqlite3.IntegrityError):
        base.execute("INSERT INTO execution (test_case_id, confiance) VALUES (1, 'inventee')")
    base.close()


# ── Persistance ───────────────────────────────────────────────────────────────────────────────────────────


def _cas(conn, *, auteur: str, approuvee: bool):
    pid = ProjectRepo(conn).create(name="P")
    mid = ModuleRepo(conn).create(project_id=pid, name="M")
    cid = CaseRepo(conn).create(title="C", module_id=mid, feature_slug="c")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="", feature_content="# f",
                                   steps_content="# s", created_by=auteur)
    if approuvee:
        ReviewRepo(conn).create(test_case_id=cid, version_id=vid, decision="approved", reviewer="humain", comment="", repair_budget=2)
    eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid)
    return cid, eid


def _vert():
    resultat = BehaveResult(success=True, returncode=0, dry_run=False)
    resultat.scenarios = [BehaveScenario(name="S", status="passed", duration=1.0)]
    resultat.passed = 1
    outcome = SimpleNamespace(real_run=resultat, retried=False)
    return st.derive_verdict(SimpleNamespace(real_run=resultat, dry_run_passed=True, retried=False, error=None,
                                             attempts=[]), connector_type="web"), outcome


def _persister(conn, cid, eid, monkeypatch):
    monkeypatch.setattr(run_service, "_expliquer", lambda *a, **k: "")
    monkeypatch.setattr(run_service, "_joindre_captures", lambda *a, **k: None)
    verdict, outcome = _vert()
    run_service._persist(conn, eid, cid, verdict, outcome, 0.1)


def test_falsifiable_le_vert_d_une_version_reparee_non_relue_n_est_pas_le_resultat_du_cas(conn, monkeypatch):
    cid, eid = _cas(conn, auteur="repair-agent", approuvee=False)

    _persister(conn, cid, eid, monkeypatch)

    cas = CaseRepo(conn).get(cid)
    assert cas["last_execution_status"] in (None, "", "not_executed")
    assert conn.execute("SELECT confiance FROM execution WHERE id=?", (eid,)).fetchone()[0] == "apres_reparation"


def test_une_version_reparee_puis_relue_redevient_un_resultat(conn, monkeypatch):
    cid, eid = _cas(conn, auteur="repair-agent", approuvee=True)

    _persister(conn, cid, eid, monkeypatch)

    assert CaseRepo(conn).get(cid)["last_execution_status"] == "success"
    assert conn.execute("SELECT confiance FROM execution WHERE id=?", (eid,)).fetchone()[0] == "nominale"


def test_une_version_ordinaire_ne_change_pas(conn, monkeypatch):
    cid, eid = _cas(conn, auteur="", approuvee=False)

    _persister(conn, cid, eid, monkeypatch)

    assert CaseRepo(conn).get(cid)["last_execution_status"] == "success"


def test_la_nouvelle_confiance_est_a_confirmer_et_libellee():
    assert st.a_confirmer("passed", st.CONFIANCE_APRES_REPARATION) is True
    assert st.LIBELLES_CONFIANCE[st.CONFIANCE_APRES_REPARATION] == "Après réparation, non relue"
