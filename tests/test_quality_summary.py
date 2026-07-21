"""Santé technique de la génération — l'onglet « Qualité » et son agrégat.

LA question : un test fraîchement généré TOURNE-T-IL sans erreur technique ? Axe EXÉCUTION
(`execution_status`), jamais le fonctionnel — un test qui tourne et trouve un bug est un SUCCÈS
technique. C'est l'objectif « faire les tests sans erreur technique quel que soit le connecteur ».

Ce que ces tests figent :
- l'agrégat compte des exécutions RÉELLES, jamais un chiffre déclaré (§4.2) ;
- il ne regarde que le PREMIER JET (`first_run`) : réparations et rejeux mesurent autre chose ;
- « aucune mesure » (`ran_rate = None`) n'est PAS « 0 % de réussite » (§4.6) ;
- il ne mélange jamais les projets.
"""

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import app as app_mod
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import (
    CaseRepo,
    ExecutionRepo,
    VersionRepo,
    ensure_default_module,
)


@pytest.fixture
def conn(tmp_path):
    c = get_initialized_db(tmp_path / "q.db")
    yield c
    c.close()


_SEQ = [0]


def _cas(conn, module_id):
    _SEQ[0] += 1
    n = _SEQ[0]
    cid = CaseRepo(conn).create(title=f"Cas {n}", module_id=module_id, feature_slug=f"feat_{n}")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="s", spec_hash="h",
                                   feature_content="f", steps_content="s")
    return cid, vid


def _run(conn, cid, vid, *, execution_status, functional_status="indetermine",
         trigger="first_run"):
    eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid, trigger=trigger)
    ExecutionRepo(conn).finalize(eid, execution_status=execution_status,
                                 functional_status=functional_status,
                                 scenarios_total=1, scenarios_passed=0, scenarios_failed=0,
                                 duration_seconds=1.0, iterations=0, cost_usd=0.0)
    return eid


# ── L'agrégat ─────────────────────────────────────────────────────────────────

def test_le_taux_compte_ce_qui_a_TOURNE_pas_ce_qui_est_conforme(conn):
    """⚠️ Axe exécution, pas fonctionnel : un test non_conforme A TOURNÉ — c'est un succès
    technique. Les confondre ferait chuter le taux pour de vrais tests qui marchent."""
    mid = ensure_default_module(conn, "m")
    c1, v1 = _cas(conn, mid)
    c2, v2 = _cas(conn, mid)
    c3, v3 = _cas(conn, mid)
    _run(conn, c1, v1, execution_status="success", functional_status="conforme")
    _run(conn, c2, v2, execution_status="success", functional_status="non_conforme")  # a tourné !
    _run(conn, c3, v3, execution_status="technical_error")

    s = ExecutionRepo(conn).quality_summary()

    assert s["total"] == 3
    assert s["ran"] == 2, "le non_conforme compte comme ayant tourné"
    assert s["technical_error"] == 1
    assert abs(s["ran_rate"] - 2 / 3) < 1e-9


def test_seul_le_PREMIER_JET_compte(conn):
    """Rejeux et réparations mesurent une re-exécution ou le filet, pas la qualité de génération.
    Les inclure gonflerait ou masquerait le vrai taux du premier jet.

    ⚠️ Dans ce projet, une réparation crée une exécution `trigger='rerun'` (le schéma n'admet que
    `first_run` et `rerun`) : filtrer sur `first_run` exclut donc BIEN les deux à la fois."""
    mid = ensure_default_module(conn, "m")
    c1, v1 = _cas(conn, mid)
    _run(conn, c1, v1, execution_status="technical_error", trigger="first_run")
    _run(conn, c1, v1, execution_status="success", trigger="rerun")    # ignoré (rejeu/réparation)
    _run(conn, c1, v1, execution_status="success", trigger="rerun")    # ignoré

    s = ExecutionRepo(conn).quality_summary()

    assert s["total"] == 1, "seul le first_run est compté"
    assert s["technical_error"] == 1
    assert s["ran"] == 0


def test_aucune_mesure_donne_None_et_JAMAIS_zero(conn):
    """« Rien mesuré » n'est pas « 0 % de réussite » — le repli silencieux qu'on refuse (§4.6).
    Un 0 % afficherait un outil catastrophique là où il n'y a simplement pas encore de donnée."""
    s = ExecutionRepo(conn).quality_summary()

    assert s["total"] == 0
    assert s["ran_rate"] is None


def test_les_interrompus_sont_distincts_des_erreurs(conn):
    """`not_executed` (arrêté avant de tourner) n'est pas `technical_error` (a essayé, n'a pas
    pu) : les fondre accuserait la génération d'un échec qui est une interruption."""
    mid = ensure_default_module(conn, "m")
    c1, v1 = _cas(conn, mid)
    _run(conn, c1, v1, execution_status="not_executed")

    s = ExecutionRepo(conn).quality_summary()

    assert s["not_executed"] == 1
    assert s["technical_error"] == 0


def test_evolution_groupee_par_jour(conn):
    mid = ensure_default_module(conn, "m")
    c1, v1 = _cas(conn, mid)
    _run(conn, c1, v1, execution_status="success")
    _run(conn, c1, v1, execution_status="technical_error")

    s = ExecutionRepo(conn).quality_summary()

    assert len(s["by_day"]) >= 1
    jour = s["by_day"][-1]
    assert jour["success"] + jour["technical_error"] == 2


def test_jamais_de_melange_inter_projets(conn):
    """Deux projets, deux santés distinctes — invariant §8, gardé partout ailleurs."""
    m1 = ensure_default_module(conn, "projet_a")
    from testpilot.store.repositories import ModuleRepo, ProjectRepo
    pid1 = ModuleRepo(conn).get(m1)["project_id"]
    pid2 = ProjectRepo(conn).create(name="Autre", base_url="")
    m2 = ModuleRepo(conn).create(project_id=pid2, name="mod2")

    ca, va = _cas(conn, m1)
    cb, vb = _cas(conn, m2)
    _run(conn, ca, va, execution_status="success")
    _run(conn, cb, vb, execution_status="technical_error")

    sa = ExecutionRepo(conn).quality_summary(project_id=pid1)
    sb = ExecutionRepo(conn).quality_summary(project_id=pid2)

    assert sa["ran"] == 1 and sa["technical_error"] == 0
    assert sb["ran"] == 0 and sb["technical_error"] == 1


# ── L'API ─────────────────────────────────────────────────────────────────────

def test_api_quality_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    client = TestClient(app_mod.app)
    conn = get_initialized_db(config.DB_PATH)
    mid = ensure_default_module(conn, "m")
    c1, v1 = _cas(conn, mid)
    _run(conn, c1, v1, execution_status="success", functional_status="conforme")
    conn.close()

    r = client.get("/api/executions/quality/summary")

    assert r.status_code == 200
    body = r.json()
    assert body["ran"] == 1
    assert body["ran_rate"] == 1.0
    # La route /quality/summary ne doit pas être avalée par /{execution_id}.
    assert "by_day" in body


def test_api_quality_vide_rend_None(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api2.db")
    client = TestClient(app_mod.app)

    r = client.get("/api/executions/quality/summary")

    assert r.status_code == 200
    assert r.json()["ran_rate"] is None
    assert r.json()["total"] == 0
