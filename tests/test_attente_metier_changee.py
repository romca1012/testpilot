"""D31 (validée par le porteur le 2026-10-09) — changer ce qu'un cas doit prouver n'est jamais approuvé d'office.

Avant : éditer le résultat attendu ou les étapes d'un cas gardait l'ancien test, approuvé d'office (amendement §4.3), et le
cas continuait d'afficher « Réussi ». Exemple : « remise de 10 % » devient « 15 % » ; le test vérifie toujours 10 %,
l'application applique 10 %, le cas reste vert — le bug est invisible. Ici :
- la nouvelle version reste à relire (régénérer, ou approuver si le test convient encore), avec un point de vigilance ;
- le cas affiche « Retest » jusqu'à un run sur la nouvelle attente (le run précédent garde son verdict) ;
- titre et préconditions : approbation d'office conservée.
"""

from __future__ import annotations

import itertools
import sqlite3
from types import SimpleNamespace

import pytest

from testpilot import config
from testpilot.api import schemas
from testpilot.api.routes import cases as route
from testpilot.api.services import generation_service, run_service
from testpilot.execution.behave_result import BehaveResult, BehaveScenario
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, ExecutionRepo, ModuleRepo, ProjectRepo, ReviewRepo, VersionRepo
from testpilot.verdict import review_gate
from testpilot.verdict import status as st

# ── La règle d'affichage, en Python et en SQL ─────────────────────────────────────────────────────────────


def test_un_reussi_obtenu_contre_une_autre_attente_se_lit_retest():
    assert st.statut_du_cas(st.EXEC_SUCCESS, st.FUNC_CONFORME, attente_changee=True) == st.STATUT_RETEST
    assert st.statut_du_cas(st.EXEC_SUCCESS, st.FUNC_CONFORME, attente_changee=False) == st.STATUT_PASSED
    # Un échec reste un échec : D31 ne vise que le faux vert.
    assert st.statut_du_cas(st.EXEC_SUCCESS, st.FUNC_NON_CONFORME, attente_changee=True) == st.STATUT_FAILED


def test_les_formes_python_et_sql_ne_divergent_sur_aucune_combinaison():
    executions = [st.EXEC_SUCCESS, st.EXEC_TECHNICAL_ERROR, st.EXEC_BLOCKED, st.EXEC_NOT_EXECUTED, None]
    fonctionnels = [st.FUNC_CONFORME, st.FUNC_NON_CONFORME, st.FUNC_INDETERMINE, st.FUNC_NOT_EVALUATED,
                    st.FUNC_DONNEE_INVALIDE, None]
    base = sqlite3.connect(":memory:")
    base.execute("CREATE TABLE t (ex TEXT, fo TEXT, ch INTEGER)")
    base.executemany("INSERT INTO t VALUES (?,?,?)", itertools.product(executions, fonctionnels, [0, 1]))
    ecarts = [(ex, fo, ch) for ex, fo, ch, sql in base.execute(
        f"SELECT ex, fo, ch, {st.sql_statut_du_cas('ex', 'fo', 'ch = 1')} FROM t")
        if sql != st.statut_du_cas(ex, fo, attente_changee=bool(ch))]
    base.close()

    assert not ecarts


# ── Bout en bout ──────────────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(run_service, "_expliquer", lambda *a, **k: "")
    monkeypatch.setattr(run_service, "_joindre_captures", lambda *a, **k: None)
    c = get_initialized_db(tmp_path / "d31.db")
    yield c
    c.close()


def _cas_vert(conn, *, feature: str = "# language: fr\nFonctionnalité: Remise\n") -> int:
    """Un cas automatisé, relu, dont le dernier run est vert : « remise de 10 % »."""
    pid = ProjectRepo(conn).create(name="P")
    mid = ModuleRepo(conn).create(project_id=pid, name="M")
    cid = CaseRepo(conn).create(title="Remise", module_id=mid, feature_slug="remise")
    v1 = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="", feature_content=feature,
                                  steps_content="# steps", title="Remise", test_steps="Valider le panier",
                                  expected_result="Remise de 10 %")
    CaseRepo(conn).set_current_version(cid, v1)
    ReviewRepo(conn).create(test_case_id=cid, version_id=v1, decision="approved", reviewer="humain", repair_budget=2)
    _run_vert(conn, cid, v1)
    return cid


def _run_vert(conn, cid: int, version_id: int) -> None:
    resultat = BehaveResult(success=True, returncode=0, dry_run=False)
    resultat.scenarios = [BehaveScenario(name="S", status="passed", duration=1.0)]
    resultat.passed = 1
    outcome = SimpleNamespace(real_run=resultat, dry_run_passed=True, retried=False, error=None, attempts=[])
    verdict = st.derive_verdict(outcome, connector_type="web")
    run_service._persist(conn, ExecutionRepo(conn).create(test_case_id=cid, version_id=version_id), cid, verdict,
                         outcome, 0.1)


def _statut(conn, cid: int) -> str:
    return schemas.case_summary(CaseRepo(conn).get(cid)).statut


def _ids(conn, statut: str) -> set[int]:
    lignes, _, _ = CaseRepo(conn).page(statut=statut)
    return {ligne["id"] for ligne in lignes}


def _editer(conn, cid: int, **champs) -> int:
    return route.update_case_metier(cid, schemas.CaseMetierIn(**champs), conn=conn).version_id


def _points(conn, cid: int) -> set[str]:
    cas = CaseRepo(conn).get(cid)
    return {p["kind"] for p in generation_service.lint_warnings_for_version(
        conn, cas, VersionRepo(conn).list_for_case(cid), cas["current_version_id"])}


def test_falsifiable_changer_le_resultat_attendu_ne_laisse_pas_le_cas_reussi(conn):
    cid = _cas_vert(conn)
    assert _statut(conn, cid) == st.STATUT_PASSED

    v2 = _editer(conn, cid, expected_result="Remise de 15 %")

    assert review_gate.evaluate_gate(ReviewRepo(conn), v2).allowed is False
    assert generation_service.ATTENTE_METIER_CHANGEE in _points(conn, cid)
    assert _statut(conn, cid) == st.STATUT_RETEST
    assert cid in _ids(conn, st.STATUT_RETEST) and cid not in _ids(conn, st.STATUT_PASSED)
    # Le run lui-même garde son verdict (décision 0016 (iii) : aucun run masqué).
    assert CaseRepo(conn).get(cid)["last_functional_status"] == st.FUNC_CONFORME


def test_falsifiable_changer_les_etapes_aussi(conn):
    cid = _cas_vert(conn)

    v2 = _editer(conn, cid, test_steps="Valider le panier avec le code PROMO15")

    assert review_gate.evaluate_gate(ReviewRepo(conn), v2).allowed is False
    assert _statut(conn, cid) == st.STATUT_RETEST


def test_corriger_le_titre_reste_approuve_d_office_et_vert(conn):
    cid = _cas_vert(conn)

    v2 = _editer(conn, cid, title="Remise fidélité")

    assert review_gate.evaluate_gate(ReviewRepo(conn), v2).allowed is True
    assert _statut(conn, cid) == st.STATUT_PASSED
    assert generation_service.ATTENTE_METIER_CHANGEE not in _points(conn, cid)


def test_confirmer_retire_le_signal_et_seul_un_run_rend_le_vert(conn):
    cid = _cas_vert(conn)
    v2 = _editer(conn, cid, expected_result="Remise de 15 %")

    ReviewRepo(conn).create(test_case_id=cid, version_id=v2, decision="approved", reviewer="humain", repair_budget=2)

    assert generation_service.ATTENTE_METIER_CHANGEE not in _points(conn, cid)
    assert _statut(conn, cid) == st.STATUT_RETEST, "approuver ne prouve rien : seul un run sur la nouvelle attente le peut"
    _run_vert(conn, cid, v2)
    assert _statut(conn, cid) == st.STATUT_PASSED


def test_un_cas_manuel_sans_test_reste_approuve_d_office(conn):
    cid = _cas_vert(conn, feature="")

    v2 = _editer(conn, cid, expected_result="Remise de 15 %")

    assert review_gate.evaluate_gate(ReviewRepo(conn), v2).allowed is True
