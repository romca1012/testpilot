"""La réparation d'un cas ne doit jamais écraser le verdict RÉEL déjà persisté.

`run_execution` persiste le verdict d'abord (`_execute_and_persist`), puis tente une réparation
(`_maybe_repair`) — un bonus après coup, pas une condition de validité du verdict. Avant ce
correctif, une exception PENDANT la réparation remontait telle quelle au `except` du bas, qui
appelait `_finalize_error` sur le MÊME `execution_id` : `ExecutionRepo.finalize` n'a aucune garde
contre un second appel, donc un verdict fonctionnel réel (potentiellement un vrai bug détecté par
le test) devenait « erreur technique », silencieusement — un commentaire qui décrit le vrai
résultat restait collé à un statut qui dit le contraire (le registre `test_result` n'est, lui, pas
réécrit — seule la ligne `execution`, lue en direct pour le statut affiché, l'était).

Audit du 2026-08-07, défaut classé bloquant (B1).
"""

from __future__ import annotations

import pytest

from testpilot.api.services import run_service
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, ExecutionRepo, VersionRepo


@pytest.fixture
def conn(tmp_path):
    c = get_initialized_db(tmp_path / "r.db")
    yield c
    c.close()


def _cas(conn):
    cid = CaseRepo(conn).create(title="Cas", feature_slug="cas")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="s", spec_hash="h",
                                   feature_content="# f", steps_content="# s")
    return cid, vid


class _OutcomeFactice:
    """Ce que `_execute_and_persist` renvoie normalement — `_maybe_repair` n'en lit que ce que
    le gate exploite ; ici, jamais atteint puisque la réparation plante avant."""


def test_un_plantage_de_la_reparation_ne_touche_pas_au_verdict_deja_ecrit(
        conn, tmp_path, monkeypatch):
    cid, vid = _cas(conn)
    eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid)
    # `run_execution` ouvre SA PROPRE connexion (`get_initialized_db(config.DB_PATH)`) — sans
    # ceci, elle pointerait vers la vraie base du poste, pas celle de ce test.
    monkeypatch.setattr(run_service.config, "DB_PATH", tmp_path / "r.db")

    def fake_execute_and_persist(c, execution_id, case_id, module_name, runner):
        # Un vrai run, un vrai refus métier — un bug RÉELLEMENT détecté dans l'application.
        ExecutionRepo(c).finalize(
            execution_id, execution_status="success", functional_status="non_conforme",
            scenarios_total=1, scenarios_passed=0, scenarios_failed=1, cost_usd=0.0,
            iterations=0, duration_seconds=1.0,
            comment="Un vrai refus métier a été constaté par le test.")
        return _OutcomeFactice()

    def fake_maybe_repair(*a, **k):
        raise RuntimeError("boom pendant la réparation (ex: LLM indisponible)")

    # Hors sujet de ce test (résolution de connexion projet) : neutralisé pour isoler le
    # comportement vérifié ici, la protection du verdict déjà écrit.
    monkeypatch.setattr(run_service, "resolve_connection", lambda c, case_id: {})
    monkeypatch.setattr(run_service, "_execute_and_persist", fake_execute_and_persist)
    monkeypatch.setattr(run_service, "_maybe_repair", fake_maybe_repair)

    run_service.run_execution(eid, "cas", cid, vid)

    execution = ExecutionRepo(conn).get(eid)
    # Le verdict RÉEL reste acquis — jamais remplacé par « erreur technique ».
    assert execution["execution_status"] == "success"
    assert execution["functional_status"] == "non_conforme"
    assert "refus métier" in execution["error_message"] or execution["error_message"] == ""
    assert eid not in run_service._RUNNING   # le filet ferme quand même proprement


def test_une_tentative_de_reparation_qui_plante_finalise_SA_PROPRE_ligne_pas_l_originale(
        conn, monkeypatch):
    """Le plantage survient à L'INTÉRIEUR d'une tentative rejouée (`run_once`), pas dans le
    circuit de décision — sa propre ligne d'exécution (déjà créée en base) doit être finalisée en
    erreur technique, pas laissée `not_executed` pour toujours (même piège que `_finalize_error`,
    §4.6 : l'absence de signal prise pour un signal positif)."""
    cid, vid = _cas(conn)
    eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid)
    ExecutionRepo(conn).finalize(
        eid, execution_status="technical_error", functional_status="indetermine",
        scenarios_total=0, scenarios_passed=0, scenarios_failed=0, cost_usd=0.0,
        iterations=0, duration_seconds=0.0, comment="")

    created_eids: list[int] = []

    def fake_run_repair_loop(c, *, case_id, version_id, module_name, outcome, run_once,
                             connector, dry_runner):
        run_once(version_id)   # une seule tentative, qui va planter
        raise AssertionError("ne doit jamais être atteint : run_once doit avoir levé")

    def fake_execute_and_persist(c, execution_id, case_id, module_name, runner):
        created_eids.append(execution_id)
        raise RuntimeError("Behave a planté pendant la tentative de réparation")

    monkeypatch.setattr(run_service.repair_service, "run_repair_loop", fake_run_repair_loop)
    monkeypatch.setattr(run_service, "_execute_and_persist", fake_execute_and_persist)

    with pytest.raises(RuntimeError, match="Behave a planté"):
        run_service._maybe_repair(conn, case_id=cid, version_id=vid, module_name="cas",
                                  outcome=_OutcomeFactice(), runner=object())

    assert len(created_eids) == 1
    retry_eid = created_eids[0]
    assert retry_eid != eid   # une ligne distincte de l'originale
    retry = ExecutionRepo(conn).get(retry_eid)
    assert retry["execution_status"] == "technical_error"   # jamais 'not_executed'
    assert "planté" in retry["error_message"]
    # L'exécution d'ORIGINE, elle, n'a pas bougé.
    assert ExecutionRepo(conn).get(eid)["execution_status"] == "technical_error"
