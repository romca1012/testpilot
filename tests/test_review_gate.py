"""INVARIANT CRITIQUE §4 — le gate de relecture bloque la première exécution.

Un cas généré par l'IA ne peut être exécuté qu'après approbation humaine de sa version
courante ; un ré-run de la même version approuvée ne redemande rien ; une nouvelle version
(re-génération) repasse par le gate.
"""

import pytest

from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, ReviewRepo, VersionRepo
from testpilot.verdict import review_gate as gate


@pytest.fixture
def repos(tmp_path, monkeypatch):
    from testpilot import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    conn = get_initialized_db(tmp_path / "t.db")
    yield CaseRepo(conn), VersionRepo(conn), ReviewRepo(conn)
    conn.close()


def _generated_case(cases, versions):
    cid = cases.create(title="Demande de matériel", feature_slug="demande_materiel")
    vid = versions.create(test_case_id=cid, spec_content="spec", spec_hash="h1",
                          feature_content="# language: fr", steps_content="from behave import *")
    cases.set_current_version(cid, vid)
    return cid, vid


def test_fresh_version_is_blocked_until_review(repos):
    cases, versions, reviews = repos
    _, vid = _generated_case(cases, versions)
    decision = gate.evaluate_gate(reviews, vid)
    assert decision.allowed is False
    assert decision.needs_review is True


def test_approval_unlocks_execution(repos):
    cases, versions, reviews = repos
    cid, vid = _generated_case(cases, versions)
    decision = gate.submit_review(reviews, case_id=cid, version_id=vid, approved=True, reviewer="lead")
    assert decision.allowed is True
    assert gate.evaluate_gate(reviews, vid).allowed is True


def test_rerun_of_approved_version_needs_no_new_review(repos):
    cases, versions, reviews = repos
    cid, vid = _generated_case(cases, versions)
    gate.submit_review(reviews, case_id=cid, version_id=vid, approved=True, reviewer="lead")
    # Deuxième passage (ré-exécution) : toujours autorisé, sans relecture supplémentaire.
    again = gate.evaluate_gate(reviews, vid)
    assert again.allowed is True and again.needs_review is False


def test_new_version_after_regeneration_is_blocked_again(repos):
    cases, versions, reviews = repos
    cid, vid1 = _generated_case(cases, versions)
    gate.submit_review(reviews, case_id=cid, version_id=vid1, approved=True, reviewer="lead")
    # Spec évoluée → nouvelle version → repasse par le gate.
    vid2 = versions.create(test_case_id=cid, spec_content="spec v2", spec_hash="h2",
                           feature_content="x", steps_content="y")
    cases.set_current_version(cid, vid2)
    assert gate.evaluate_gate(reviews, vid2).allowed is False


def test_rejected_version_is_blocked(repos):
    cases, versions, reviews = repos
    cid, vid = _generated_case(cases, versions)
    decision = gate.submit_review(reviews, case_id=cid, version_id=vid, approved=False,
                                  reviewer="lead", comment="Gherkin faux")
    assert decision.allowed is False
    assert "rejet" in decision.reason.lower()


def test_le_gate_ne_calcule_plus_aucun_statut_de_cas():
    """⚠️ `validation_status_after_run` a été SUPPRIMÉE avec la migration 25.

    Elle dérivait un « statut de validation » de l'exécution, que cinq appelants recopiaient sur
    le cas. Ce champ se présentait comme un cycle de vie sans en être un — aucun humain ne
    pouvait le poser — et `test_case.etat` le remplace, écrit par l'humain seul. Ce test garde la
    trace de la suppression : le gate décide d'AUTORISER une exécution, il n'étiquette pas les cas.
    """
    assert not hasattr(gate, "validation_status_after_run")
