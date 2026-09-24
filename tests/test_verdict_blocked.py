"""Lot 02 (D1) — `blocked` : un prérequis d'environnement manquant est un statut d'EXÉCUTION.

Ce que ces tests fixent :

- un prérequis non rempli (step de Contexte, fixture/connexion en échec) → exécution `blocked`,
  fonctionnel `indetermine`, statut de lecture `blocked` — AUTOMATIQUEMENT ;
- une assertion en `Alors` reste `failed` (inchangé), un `TimeoutError` en `Quand` reste `retest` ;
- l'agrégation : `technical_error` > `blocked` > `success` sur l'axe exécution, et un
  `non_conforme` surface TOUJOURS (un constat sur l'application n'est jamais masqué) ;
- la valeur `blocked` traverse la PERSISTANCE (les CHECK de la base l'acceptent) — l'angle mort de la
  migration 19, qui avait fait planter un `donnee_invalide` correctement jugé.
"""

from __future__ import annotations

import pytest

from testpilot.execution.behave_result import (
    STEP_TYPE_HOOK,
    BehaveFailure,
    BehaveResult,
    BehaveScenario,
)
from testpilot.execution.executor import ExecutionOutcome
from testpilot.verdict import defect_taxonomy as dt
from testpilot.verdict import status as st


def _outcome(scenarios, failures, dry_ok=True, returncode=1):
    real = BehaveResult(success=(returncode == 0), returncode=returncode,
                        scenarios=scenarios, failures=failures)
    return ExecutionOutcome(module_name="m", dry_run_passed=dry_ok,
                            real_run=real if dry_ok else None)


def _echec(scenario, step_type, brut, ftype="assertion", libelle=""):
    return BehaveFailure(scenario, libelle, ftype, "", raw=brut, step_type=step_type)


# ── Les cas de la spec du lot ───────────────────────────────────────────────────────────────

def test_module_non_installe_dans_le_contexte_est_blocked():
    """Le cas 101 tirage 1 du lot 12 (F2) : `Soit le module Odoo "…" est installé` échoue."""
    scenarios = [BehaveScenario("[Limite] SIREN", "failed", error="Le module n'est pas installé")]
    failures = [_echec("[Limite] SIREN", "given", "ASSERT FAILED: Le module Odoo 'x' n'est pas installé.",
                       libelle='Soit le module Odoo "x" est installé')]

    v = st.derive_verdict(_outcome(scenarios, failures))

    assert (v.execution_status, v.functional_status) == (st.EXEC_BLOCKED, st.FUNC_INDETERMINE)
    assert v.scenarios[0].cause_category == dt.PRECONDITION_NON_REMPLIE
    assert st.statut_de_test(v.execution_status, v.functional_status) == st.STATUT_BLOCKED


def test_login_rpc_impossible_avant_tout_step_est_blocked():
    """Fixture (`before_scenario` : login RPC, navigateur) en échec avant le premier step."""
    scenarios = [BehaveScenario("[Nominal]", "failed", error="RuntimeError: login refusé")]
    failures = [_echec("[Nominal]", STEP_TYPE_HOOK, "RuntimeError: login refusé", ftype="hook")]

    v = st.derive_verdict(_outcome(scenarios, failures))

    assert (v.execution_status, v.functional_status) == (st.EXEC_BLOCKED, st.FUNC_INDETERMINE)
    assert st.statut_de_test(v.execution_status, v.functional_status) == st.STATUT_BLOCKED


def test_assertion_en_alors_reste_failed_inchange():
    scenarios = [BehaveScenario("[Erreur]", "failed", error="attendu 0")]
    failures = [_echec("[Erreur]", "then", "ASSERT FAILED: attendu 0, obtenu 5")]

    v = st.derive_verdict(_outcome(scenarios, failures))

    assert (v.execution_status, v.functional_status) == (st.EXEC_SUCCESS, st.FUNC_NON_CONFORME)
    assert st.statut_de_test(v.execution_status, v.functional_status) == st.STATUT_FAILED


def test_timeout_en_quand_reste_retest_inchange():
    scenarios = [BehaveScenario("[Nominal]", "failed", error="TimeoutError")]
    failures = [_echec("[Nominal]", "when", "TimeoutError: waiting for locator", ftype="ui_timeout")]

    v = st.derive_verdict(_outcome(scenarios, failures))

    assert (v.execution_status, v.functional_status) == (st.EXEC_TECHNICAL_ERROR, st.FUNC_INDETERMINE)
    assert st.statut_de_test(v.execution_status, v.functional_status) == st.STATUT_RETEST


def test_assertion_en_quand_est_un_test_casse_a_revérifier_jamais_un_bug_applicatif():
    """D2 : `broken_test_code` → technical_error / indetermine → retest, jamais failed."""
    scenarios = [BehaveScenario("[Nominal]", "failed", error="ASSERT FAILED: x")]
    failures = [_echec("[Nominal]", "when", "ASSERT FAILED: x")]

    v = st.derive_verdict(_outcome(scenarios, failures))

    assert v.scenarios[0].cause_category == dt.BROKEN_TEST_CODE
    assert (v.execution_status, v.functional_status) == (st.EXEC_TECHNICAL_ERROR, st.FUNC_INDETERMINE)
    assert st.statut_de_test(v.execution_status, v.functional_status) == st.STATUT_RETEST


# ── Agrégation : technical_error > blocked > success, et un constat surface toujours ────────

def _verdict(nom, ex, fo, cause=""):
    return st.ScenarioVerdict(nom, ex, fo, cause_category=cause)


def test_technical_error_prime_sur_blocked_qui_prime_sur_success():
    ok = _verdict("a", st.EXEC_SUCCESS, st.FUNC_CONFORME)
    bloque = _verdict("b", st.EXEC_BLOCKED, st.FUNC_INDETERMINE)
    panne = _verdict("c", st.EXEC_TECHNICAL_ERROR, st.FUNC_INDETERMINE)

    assert st.aggregate([ok, bloque]).execution_status == st.EXEC_BLOCKED
    assert st.aggregate([ok, panne]).execution_status == st.EXEC_TECHNICAL_ERROR
    assert st.aggregate([bloque, panne]).execution_status == st.EXEC_TECHNICAL_ERROR
    assert st.aggregate([ok]).execution_status == st.EXEC_SUCCESS


def test_un_non_conforme_surface_toujours_meme_avec_un_scenario_bloque():
    """Un constat sur l'application n'est jamais masqué par un prérequis manquant ailleurs."""
    constat = _verdict("a", st.EXEC_SUCCESS, st.FUNC_NON_CONFORME)
    bloque = _verdict("b", st.EXEC_BLOCKED, st.FUNC_INDETERMINE)

    v = st.aggregate([constat, bloque])

    assert v.functional_status == st.FUNC_NON_CONFORME
    assert v.execution_status == st.EXEC_BLOCKED
    assert st.statut_de_test(v.execution_status, v.functional_status) == st.STATUT_FAILED


def test_un_cas_partiellement_bloque_n_est_jamais_conforme():
    v = st.aggregate([_verdict("a", st.EXEC_SUCCESS, st.FUNC_CONFORME),
                      _verdict("b", st.EXEC_BLOCKED, st.FUNC_INDETERMINE)])

    assert v.functional_status == st.FUNC_INDETERMINE
    assert st.statut_de_test(v.execution_status, v.functional_status) == st.STATUT_BLOCKED


def test_blocked_prime_sur_la_regle_indetermine_donne_retest():
    assert st.statut_de_test(st.EXEC_BLOCKED, st.FUNC_INDETERMINE) == st.STATUT_BLOCKED
    assert st.statut_de_test(st.EXEC_TECHNICAL_ERROR, st.FUNC_INDETERMINE) == st.STATUT_RETEST
    assert "'blocked'" in st.sql_statut("ex", "fo")


# ── Persistance : les CHECK de la base acceptent `blocked` ───────────────────────────────────

def test_la_base_neuve_accepte_blocked_sur_les_trois_tables(tmp_path):
    from testpilot.store.db import get_initialized_db

    conn = get_initialized_db(tmp_path / "t.db")
    for table in ("execution", "test_case", "scenario_result"):
        sql = conn.execute("SELECT sql FROM sqlite_master WHERE name=?", (table,)).fetchone()[0]
        assert "'blocked'" in sql, f"le CHECK de {table} refuse `blocked`"


def test_un_verdict_blocked_se_persiste_de_bout_en_bout(tmp_path, monkeypatch):
    """Le chemin RÉEL de `run_service._persist` : scénario + exécution + dernier résultat du cas."""
    from testpilot.api.services import run_service
    from testpilot.store.db import get_initialized_db
    from testpilot.store.repositories import CaseRepo, ExecutionRepo

    conn = get_initialized_db(tmp_path / "t.db")
    monkeypatch.setattr(run_service, "_expliquer", lambda *a, **k: "")
    monkeypatch.setattr(run_service, "_joindre_captures", lambda *a, **k: None)
    case_id = _creer_cas(conn)
    execution_id = ExecutionRepo(conn).create(test_case_id=case_id,
                                              version_id=_version_du_cas(conn, case_id))
    scenarios = [BehaveScenario("[Nominal]", "failed", error="module absent")]
    failures = [_echec("[Nominal]", "given", "ASSERT FAILED: module absent")]
    outcome = _outcome(scenarios, failures)
    verdict = st.derive_verdict(outcome)

    run_service._persist(conn, execution_id, case_id, verdict, outcome, 1.0, "m")

    ligne = conn.execute("SELECT execution_status, functional_status FROM execution WHERE id=?",
                         (execution_id,)).fetchone()
    assert (ligne["execution_status"], ligne["functional_status"]) == ("blocked", "indetermine")
    sc = conn.execute("SELECT execution_status, cause_category FROM scenario_result "
                      "WHERE execution_id=?", (execution_id,)).fetchone()
    assert (sc["execution_status"], sc["cause_category"]) == ("blocked", dt.PRECONDITION_NON_REMPLIE)
    cas = CaseRepo(conn).get(case_id)
    assert cas["last_execution_status"] == "blocked"


def _creer_cas(conn) -> int:
    from testpilot.store.repositories import CaseRepo, ModuleRepo, ProjectRepo

    projet = ProjectRepo(conn).create(name="Portail")
    module = ModuleRepo(conn).create(project_id=projet, name="Demandes")
    return CaseRepo(conn).create(title="Nominal", module_id=module, feature_slug="nominal")


def _version_du_cas(conn, case_id: int) -> int:
    from testpilot.store.repositories import VersionRepo

    return VersionRepo(conn).create(test_case_id=case_id, spec_content="", spec_hash="",
                                    feature_content="# f", steps_content="# s")


@pytest.mark.parametrize("tables", [("execution", "test_case", "scenario_result")])
def test_l_alembic_head_accepte_blocked(tables, tmp_path):
    """Le schéma qu'un déploiement PostgreSQL reçoit (via Alembic) porte aussi `blocked`."""
    from testpilot.store import schema_sa

    for table in tables:
        checks = [c for c in schema_sa.metadata.tables[table].constraints
                  if getattr(c, "name", "") and "execution_status" in c.name]
        assert checks and all("'blocked'" in str(c.sqltext) for c in checks), table
