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


# ── Revue du lot VH-03 ────────────────────────────────────────────────────────────────────────────────────


def _cas_avec_reparation_non_relue(conn):
    """v1 approuvée, puis v2 réécrite par l'agent de réparation, adoptée comme version courante, jamais relue."""
    pid = ProjectRepo(conn).create(name="P")
    mid = ModuleRepo(conn).create(project_id=pid, name="M")
    cid = CaseRepo(conn).create(title="C", module_id=mid, feature_slug="c")
    v1 = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="", feature_content="# f",
                                  steps_content="# v1")
    ReviewRepo(conn).create(test_case_id=cid, version_id=v1, decision="approved", reviewer="humain", repair_budget=2)
    v2 = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="", feature_content="# f",
                                  steps_content="# v2 réparée", created_by="repair-agent")
    CaseRepo(conn).set_current_version(cid, v2)
    return cid, v2


def test_falsifiable_editer_le_metier_ne_blanchit_pas_un_code_repare_non_relu(conn):
    """Bloquant de la revue : corriger une coquille du titre recopiait le code réparé non relu ET l'approuvait d'office."""
    from testpilot.api import schemas
    from testpilot.api.routes import cases as route
    from testpilot.verdict import review_gate

    cid, v2 = _cas_avec_reparation_non_relue(conn)

    sortie = route.update_case_metier(cid, schemas.CaseMetierIn(title="C (coquille corrigée)"), conn=conn)

    v3 = sortie.version_id
    assert v3 is not None and VersionRepo(conn).get(v3)["steps_content"] == "# v2 réparée"
    assert review_gate.evaluate_gate(ReviewRepo(conn), v3).allowed is False


def test_editer_le_metier_d_un_code_relu_reste_approuve_d_office(conn):
    """Sens inverse : l'amendement §4.3 (éditer le métier vaut relecture) reste vrai pour un code déjà relu."""
    from testpilot.api import schemas
    from testpilot.api.routes import cases as route
    from testpilot.verdict import review_gate

    cid, _ = _cas(conn, auteur="", approuvee=True)

    sortie = route.update_case_metier(cid, schemas.CaseMetierIn(title="C2"), conn=conn)

    assert review_gate.evaluate_gate(ReviewRepo(conn), sortie.version_id).allowed is True


def test_falsifiable_une_tentative_de_reparation_qui_plante_ne_remplace_pas_le_resultat(conn):
    cid, v2 = _cas_avec_reparation_non_relue(conn)
    eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=v2)

    assert run_service._ecrire_erreur(conn, eid, cid, "boom") is True

    assert CaseRepo(conn).get(cid)["last_execution_status"] in (None, "", "not_executed")


def test_reprise_d_une_vraie_base_ou_la_table_est_nommee_entre_guillemets(tmp_path):
    """SQLite écrit `CREATE TABLE "execution"` après un renommage : la reconstruction doit le reconnaître."""
    base = sqlite3.connect(str(tmp_path / "guillemets.db"))
    base.row_factory = sqlite3.Row
    base.executescript(_SCHEMA_PRE_59.replace("CREATE TABLE execution", 'CREATE TABLE "execution"'))
    base.execute("INSERT INTO test_case (id, title) VALUES (1, 'Cas')")
    base.execute("INSERT INTO execution (id, test_case_id) VALUES (10, 1)")
    base.commit()

    _migrate_59_confiance_apres_reparation(base)

    base.execute("INSERT INTO execution (test_case_id, confiance) VALUES (1, 'apres_reparation')")
    assert base.execute("SELECT count(*) FROM execution").fetchone()[0] == 2
    base.close()
