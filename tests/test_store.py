"""Smoke test du socle de persistance : le schéma s'initialise et round-trip complet.

Verrouille que la structure de données validée (cas → versions → relecture → exécution
→ scénarios → réparations → coûts) fonctionne, et que les CHECK d'enum protègent bien
les statuts (base du §5 côté DB).
"""

import sqlite3

import pytest

from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import (
    CaseRepo,
    CostRepo,
    ExecutionRepo,
    RepairRepo,
    ReviewRepo,
    VersionRepo,
)


@pytest.fixture
def conn(tmp_path):
    connection = get_initialized_db(tmp_path / "testpilot.db")
    yield connection
    connection.close()


def test_case_version_review_execution_roundtrip(conn):
    cases, versions = CaseRepo(conn), VersionRepo(conn)
    reviews, execs = ReviewRepo(conn), ExecutionRepo(conn)

    cid = cases.create(title="Demande de matériel", feature_slug="demande_materiel", author="qa")
    assert cases.get(cid)["validation_status"] == "never_executed"

    vid1 = versions.create(test_case_id=cid, spec_content="spec", spec_hash="abc",
                           feature_content="# language: fr", steps_content="from behave import *")
    cases.set_current_version(cid, vid1)
    assert versions.latest_for_case(cid)["version_number"] == 1

    # Une seconde version s'incrémente automatiquement (historisation §7).
    vid2 = versions.create(test_case_id=cid, spec_content="spec v2", spec_hash="def",
                           feature_content="x", steps_content="y")
    assert versions.latest_for_case(cid)["version_number"] == 2
    assert len(versions.list_for_case(cid)) == 2

    # Gate de relecture : non approuvée tant qu'aucune décision.
    assert reviews.is_version_approved(vid2) is False
    reviews.create(test_case_id=cid, version_id=vid2, decision="approved", reviewer="lead")
    assert reviews.is_version_approved(vid2) is True

    # Exécution + deux axes de statut persistés indépendamment.
    eid = execs.create(test_case_id=cid, version_id=vid2, trigger="first_run")
    execs.add_scenario_result(execution_id=eid, scenario_name="[Nominal] ok",
                              execution_status="success", functional_status="conforme")
    execs.finalize(eid, execution_status="success", functional_status="conforme",
                   scenarios_total=1, scenarios_passed=1, scenarios_failed=0,
                   cost_usd=0.12, iterations=4, duration_seconds=30.0)
    row = execs.get(eid)
    assert row["execution_status"] == "success"
    assert row["functional_status"] == "conforme"
    assert len(execs.list_scenario_results(eid)) == 1


def test_repair_attempt_and_cost_ledger(conn):
    """La réparation auto (`0014`) crée une tentative et trace son coût. (Le confirmation humain
    `0013` a été retiré — plus de list_pending/confirm.)"""
    cases, versions, execs = CaseRepo(conn), VersionRepo(conn), ExecutionRepo(conn)
    repairs, costs = RepairRepo(conn), CostRepo(conn)

    cid = cases.create(title="t", feature_slug="m")
    vid = versions.create(test_case_id=cid, spec_content="", spec_hash="",
                          feature_content="", steps_content="")
    eid = execs.create(test_case_id=cid, version_id=vid)

    repairs.create(execution_id=eid, attempt_number=1, failure_signature="sig",
                   cause_category="wrong_navigation", defect_origin="test_a_reparer",
                   confirmation_status="not_required", what_was_tried="essai 1")
    assert len(repairs.list_for_execution(eid)) == 1

    costs.add_entry(phase="generation", model="claude-sonnet-4-6", cost_usd=0.5,
                    source="estimated", execution_id=eid)
    costs.add_entry(phase="repair", model="claude-haiku-4-5-20251001", cost_usd=0.1,
                    source="estimated", execution_id=eid)
    assert abs(costs.monthly_total_usd() - 0.6) < 1e-9


def test_enum_check_constraint_rejects_invalid_status(conn):
    cases = CaseRepo(conn)
    cid = cases.create(title="t", feature_slug="m")
    with pytest.raises(sqlite3.IntegrityError):
        cases.set_validation_status(cid, "bogus")
