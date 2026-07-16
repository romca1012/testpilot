"""Décision 0014, étape 3 — L'ORCHESTRATEUR pilote la boucle, jamais l'agent.

Le design (b), arbitré : `repair_circuit.evaluate()` décide de continuer ou d'arrêter ; l'agent
ne fait que **proposer** une correction. Lui donner ce pouvoir remettrait le garde-fou dans les
mains du composant qu'il encadre — et `0012` a montré que le circuit lit un texte que l'agent
écrit lui-même.

Tests déterministes : ni Behave, ni Odoo, ni LLM. `run_once` et l'agent sont injectés.
"""

from dataclasses import dataclass, field

import pytest

from testpilot import config
from testpilot.api.services import repair_service
from testpilot.generation.repair_agent import RepairProposal
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import (
    CaseRepo,
    ExecutionRepo,
    RepairRepo,
    ReviewRepo,
    VersionRepo,
)


# ── Doublures ─────────────────────────────────────────────────────────────────

@dataclass
class _Failure:
    """Fidèle à l'échec RÉEL du cas 2 (exécutions 4 à 7) — le témoin de `0014`.

    ⚠️ Détail qui compte : la cause vient du mot `team_id` dans le **step_text**, pas de
    l'erreur. Un `TypeError` nu (sans mot-clé) tomberait en `unknown` → `indetermine` → le
    circuit s'arrêterait pour confirmation. La doublure doit donc porter le vrai libellé, sinon
    elle testerait un chemin que la réalité n'emprunte pas.
    """

    scenario_name: str = "[Nominal] — Raison de demande renseignée"
    step_text: str = 'Alors le dernier ticket créé a le champ "team_id" pointant vers "Matériel"'
    failure_type: str = "unknown"
    traceback_summary: str = ""
    raw: str = "TypeError: 'int' object is not subscriptable"


@dataclass
class _Scenario:
    name: str = "[Nominal]"
    status: str = "failed"


@dataclass
class _RealRun:
    failures: list = field(default_factory=list)
    scenarios: list = field(default_factory=lambda: [_Scenario()])


@dataclass
class _Outcome:
    real_run: _RealRun
    execution_id: int | None = None


def _echec(raw="TypeError: 'int' object is not subscriptable"):
    return _Outcome(real_run=_RealRun(failures=[_Failure(raw=raw)]))


def _succes():
    return _Outcome(real_run=_RealRun(failures=[], scenarios=[_Scenario(status="passed")]))


@pytest.fixture
def conn(tmp_path):
    c = get_initialized_db(tmp_path / "r.db")
    yield c
    c.close()


def _cas(conn, *, budget=2):
    cid = CaseRepo(conn).create(title="Cas", feature_slug="cas")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="spec", spec_hash="h",
                                   feature_content="# feature v1", steps_content="# steps v1")
    CaseRepo(conn).set_current_version(cid, vid)
    ReviewRepo(conn).create(test_case_id=cid, version_id=vid, decision="approved",
                            reviewer="qa", repair_budget=budget)
    eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid)
    return cid, vid, eid


def _agent(monkeypatch, *suites):
    """L'agent rend successivement les propositions données. Compte ses invocations."""
    appels = {"n": 0}
    sequence = list(suites)

    def faux_propose(**kwargs):
        appels["n"] += 1
        return sequence.pop(0) if sequence else RepairProposal(changed=False)

    monkeypatch.setattr(repair_service.repair_agent, "propose_fix", faux_propose)
    return appels


def _runner(conn, cid, resultats):
    """`run_once` injecté : crée une exécution et rend le résultat prévu."""
    suite = list(resultats)

    def run_once(version_id):
        eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=version_id, trigger="rerun")
        out = suite.pop(0) if suite else _echec()
        out.execution_id = eid
        return out

    return run_once


# ── Le chemin « répare » ──────────────────────────────────────────────────────

def test_une_reparation_qui_reussit_adopte_la_nouvelle_version(conn, monkeypatch):
    cid, vid, eid = _cas(conn, budget=2)
    _agent(monkeypatch, RepairProposal(changed=True, steps_content="# steps v2 corrigé",
                                       summary="search() rend des ids : browse() ajouté."))
    depart = _echec(); depart.execution_id = eid

    session = repair_service.run_repair_loop(
        conn, case_id=cid, version_id=vid, module_name="cas",
        outcome=depart, run_once=_runner(conn, cid, [_succes()]))

    assert session.attempts == 1
    assert session.outcome == "resolved" and session.resolved

    # Une tentative = une VERSION (trace honnête de ce qui a été tenté).
    versions = VersionRepo(conn).list_for_case(cid)
    assert len(versions) == 2
    v2 = [v for v in versions if v["id"] != vid][0]
    assert v2["steps_content"] == "# steps v2 corrigé"
    assert "browse()" in v2["change_summary"]      # ce que l'agent DIT avoir fait

    # La version réparée devient la référence…
    assert CaseRepo(conn).get(cid)["current_version_id"] == v2["id"]


def test_la_version_reparee_n_est_JAMAIS_approuvee_d_office(conn, monkeypatch):
    """LE test de l'option (i). Fabriquer une `review_decision` signée par l'IA serait
    l'auto-approbation écartée : une version que personne n'a relue n'est jamais approuvée,
    quelle que soit la justification."""
    cid, vid, eid = _cas(conn, budget=2)
    _agent(monkeypatch, RepairProposal(changed=True, steps_content="# v2", summary="corrigé"))
    depart = _echec(); depart.execution_id = eid

    repair_service.run_repair_loop(conn, case_id=cid, version_id=vid, module_name="cas",
                                   outcome=depart, run_once=_runner(conn, cid, [_succes()]))

    v2 = CaseRepo(conn).get(cid)["current_version_id"]
    # Aucune décision de relecture sur v2 — donc le gate la refuse pour tout run FUTUR.
    assert ReviewRepo(conn).latest_for_version(v2) is None
    assert ReviewRepo(conn).is_version_approved(v2) is False
    # …et le cas attend une ratification humaine.
    assert CaseRepo(conn).get(cid)["validation_status"] == "to_review"


def test_deux_tentatives_avant_de_reussir(conn, monkeypatch):
    cid, vid, eid = _cas(conn, budget=2)
    appels = _agent(monkeypatch,
                    RepairProposal(changed=True, steps_content="# v2", summary="essai 1"),
                    RepairProposal(changed=True, steps_content="# v3", summary="essai 2"))
    depart = _echec(); depart.execution_id = eid

    session = repair_service.run_repair_loop(
        conn, case_id=cid, version_id=vid, module_name="cas",
        outcome=depart, run_once=_runner(conn, cid, [_echec("autre erreur"), _succes()]))

    assert appels["n"] == 2 and session.attempts == 2
    assert session.resolved
    assert len(VersionRepo(conn).list_for_case(cid)) == 3      # v1 + 2 tentatives


# ── Le chemin « arrête » — le circuit décide ─────────────────────────────────

def test_budget_zero_n_appelle_meme_pas_l_agent(conn, monkeypatch):
    """budget=0 → `evaluate` coupe au premier tour (0 >= 0), sans cas particulier : le
    garde-fou existant fait le travail. Aucun appel LLM n'est engagé."""
    cid, vid, eid = _cas(conn, budget=0)
    appels = _agent(monkeypatch, RepairProposal(changed=True, steps_content="# v2"))
    depart = _echec(); depart.execution_id = eid

    session = repair_service.run_repair_loop(
        conn, case_id=cid, version_id=vid, module_name="cas",
        outcome=depart, run_once=_runner(conn, cid, [_succes()]))

    assert appels["n"] == 0
    assert session.attempts == 0
    assert session.outcome == "max_iterations"
    assert len(VersionRepo(conn).list_for_case(cid)) == 1     # aucune version créée


def test_version_non_relue_aucune_reparation(conn, monkeypatch):
    """§4.3 : pas de gate, pas d'exécution — donc pas de réparation."""
    cid = CaseRepo(conn).create(title="Cas", feature_slug="cas")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="",
                                   feature_content="", steps_content="")
    CaseRepo(conn).set_current_version(cid, vid)
    eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid)
    appels = _agent(monkeypatch, RepairProposal(changed=True, steps_content="# v2"))
    depart = _echec(); depart.execution_id = eid

    session = repair_service.run_repair_loop(
        conn, case_id=cid, version_id=vid, module_name="cas",
        outcome=depart, run_once=_runner(conn, cid, [_succes()]))
    assert appels["n"] == 0 and session.attempts == 0


def test_un_vrai_bug_arrete_la_boucle_immediatement(conn, monkeypatch):
    """Le signal métier prime : réparer un vrai bug n'a pas de sens, l'app répond faux.
    Arbitrage du porteur : on sur-arrête à tort plutôt que de laisser la réparation courir sur
    une vraie régression (§4.4). Le faux positif est infirmable depuis `0013`."""
    cid, vid, eid = _cas(conn, budget=2)
    appels = _agent(monkeypatch, RepairProposal(changed=True, steps_content="# v2"))
    # ⚠️ step_text SANS mot-clé : sinon `team_id` gagnerait — les catégories sont testées par
    # priorité, et le NOM DU STEP peut donc l'emporter sur l'erreur réelle (angle mort connu,
    # consigné au backlog). Ici « attendu » → ASSERTION_MISMATCH → vrai_bug.
    depart = _Outcome(real_run=_RealRun(failures=[_Failure(
        step_text="Alors le ticket est conforme",
        raw="AssertionError: attendu 26206, obtenu 26205")]))
    depart.execution_id = eid

    session = repair_service.run_repair_loop(
        conn, case_id=cid, version_id=vid, module_name="cas",
        outcome=depart, run_once=_runner(conn, cid, [_succes()]))

    assert appels["n"] == 0
    assert session.outcome == "real_bug"
    assert not session.resolved


def test_un_agent_qui_ne_sait_pas_reparer_arrete_la_boucle(conn, monkeypatch):
    """Un aveu utile vaut mieux qu'une tentative au hasard : insister brûlerait le budget."""
    cid, vid, eid = _cas(conn, budget=2)
    _agent(monkeypatch, RepairProposal(changed=False, summary="Le formulaire refuse un champ "
                                                              "requis que la spec ne cite pas."))
    depart = _echec(); depart.execution_id = eid

    session = repair_service.run_repair_loop(
        conn, case_id=cid, version_id=vid, module_name="cas",
        outcome=depart, run_once=_runner(conn, cid, [_succes()]))

    assert session.attempts == 0
    assert session.outcome == "agent_no_fix"
    assert "champ requis" in session.reason          # son aveu est conservé
    assert len(VersionRepo(conn).list_for_case(cid)) == 1


def test_une_reparation_ratee_ne_change_PAS_la_reference(conn, monkeypatch):
    """La référence reste la version qu'un HUMAIN a approuvée. Les versions tentées demeurent
    en historique — c'est la trace de ce qui a été essayé, pas une promotion."""
    cid, vid, eid = _cas(conn, budget=1)
    _agent(monkeypatch, RepairProposal(changed=True, steps_content="# v2 raté", summary="essai"))
    depart = _echec(); depart.execution_id = eid

    session = repair_service.run_repair_loop(
        conn, case_id=cid, version_id=vid, module_name="cas",
        outcome=depart, run_once=_runner(conn, cid, [_echec()]))

    assert session.attempts == 1 and not session.resolved
    assert CaseRepo(conn).get(cid)["current_version_id"] == vid     # v1 reste la référence
    assert len(VersionRepo(conn).list_for_case(cid)) == 2           # v2 existe en historique
    assert session.final_version_id == vid


# ── Modèle B : une exécution = un run ────────────────────────────────────────

def test_chaque_tentative_rejouee_cree_sa_propre_execution(conn, monkeypatch):
    """Modèle B : chaque ligne d'exécution reste vraie — une version, un verdict, un run.
    §4.2 tient littéralement, ligne par ligne."""
    cid, vid, eid = _cas(conn, budget=2)
    _agent(monkeypatch,
           RepairProposal(changed=True, steps_content="# v2", summary="a"),
           RepairProposal(changed=True, steps_content="# v3", summary="b"))
    depart = _echec(); depart.execution_id = eid

    repair_service.run_repair_loop(
        conn, case_id=cid, version_id=vid, module_name="cas",
        outcome=depart, run_once=_runner(conn, cid, [_echec("encore"), _succes()]))

    execs = ExecutionRepo(conn).list_for_case(cid)
    assert len(execs) == 3                                  # run initial + 2 rejeux
    versions_jouees = {e["version_id"] for e in execs}
    assert len(versions_jouees) == 3                        # chacune sur SA version


# ── what_was_tried : la colonne qui était vide partout ───────────────────────

def test_what_was_tried_est_renseigne(conn, monkeypatch):
    """La colonne existait et était vide partout : elle dit ce que l'agent a tenté.
    « J'ai corrigé » n'apprendrait rien — on stocke ce qu'il DIT avoir changé."""
    cid, vid, eid = _cas(conn, budget=1)
    RepairRepo(conn).create(execution_id=eid, attempt_number=1, failure_signature="sig",
                            cause_category="missing_server_context",
                            defect_origin="test_a_reparer", confirmation_status="pending_human")
    _agent(monkeypatch, RepairProposal(
        changed=True, steps_content="# v2",
        summary="search() rend des ids, pas des dicts : browse() ajouté avant .id"))
    depart = _echec(); depart.execution_id = eid

    repair_service.run_repair_loop(conn, case_id=cid, version_id=vid, module_name="cas",
                                   outcome=depart, run_once=_runner(conn, cid, [_succes()]))

    tente = RepairRepo(conn).list_for_execution(eid)[0]
    assert "browse()" in tente["what_was_tried"]
    assert tente["defect_origin"] == "test_a_reparer"   # le diagnostic machine reste intact
