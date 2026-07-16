"""Boucle de réparation — L'ORCHESTRATEUR PILOTE (décision 0014, étape 3).

    run vN → échec → circuit.evaluate() → l'agent propose → vN+1 → run vN+1 → …

⚠️ **Le circuit décide, jamais l'agent.** `repair_circuit.evaluate()` a été écrit pour ça : il
rend `should_continue`. L'agent, lui, ne fait que proposer une correction — il n'a aucun outil
pour exécuter (design (b) arbitré). Lui donner ce pouvoir remettrait le garde-fou dans les mains
du composant qu'il encadre, alors que `0012` a montré que le circuit lit un texte que l'agent
écrit lui-même.

**Modèle B** : une exécution = **un run réel d'une version**. Chaque ligne d'exécution reste
donc vraie (une version, un verdict, un run) et §4.2 tient littéralement, ligne par ligne. Le
prix est un historique plus fourni ; c'est la trace honnête.

**Le gate reste souverain** (§4.3) : le budget vient de la relecture (`0014` étape 2), et une
version réparée **n'est jamais approuvée d'office** — elle repasse « à relire » pour ratification
avant tout run futur. Fabriquer une `review_decision` signée par l'IA serait l'auto-approbation
qu'on a écartée.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from testpilot import config
from testpilot.generation import repair_agent
from testpilot.guardrails.repair_circuit import CircuitState, evaluate, failure_signature
from testpilot.store.repositories import CaseRepo, RepairRepo, ReviewRepo, VersionRepo

logger = logging.getLogger(__name__)


@dataclass
class RepairSession:
    """Ce que la boucle a fait — assez pour l'expliquer à un humain."""

    attempts: int = 0
    outcome: str = ""              # issue du circuit (resolved | real_bug | stalled | …)
    reason: str = ""
    resolved: bool = False
    final_version_id: int | None = None
    executions: list[int] = field(default_factory=list)
    cost_usd: float = 0.0


def _failures_of(outcome) -> list:
    return list(outcome.real_run.failures) if outcome and outcome.real_run else []


def _scenarios_of(outcome) -> list:
    return list(outcome.real_run.scenarios) if outcome and outcome.real_run else []


def run_repair_loop(conn, *, case_id: int, version_id: int, module_name: str,
                    outcome, run_once, connector=None) -> RepairSession:
    """Répare tant que le circuit l'autorise. `run_once(version_id) -> outcome` est injecté.

    `outcome` est le résultat du run initial (déjà persisté par l'appelant) : la boucle part de
    son échec. `run_once` crée une exécution et la persiste — la boucle ne sait pas comment,
    c'est ce qui la rend testable sans Behave ni Odoo.
    """
    session = RepairSession()
    budget = ReviewRepo(conn).repair_budget_for_version(version_id)

    # Le budget EST le plafond du circuit : budget=0 → `evaluate` coupe au premier tour
    # (0 >= 0) sans aucun cas particulier. Le garde-fou existant fait le travail.
    circuit = CircuitState(max_iterations=budget, stall_limit=config.REPAIR_STALL_LIMIT)

    versions = VersionRepo(conn)
    cases = CaseRepo(conn)
    current_version_id = version_id
    failures = _failures_of(outcome)

    while True:
        decision = evaluate(circuit, failures)
        session.outcome, session.reason = decision.outcome, decision.reason
        if not decision.should_continue:
            break

        version = versions.get(current_version_id)
        if version is None:
            session.outcome, session.reason = "error", "version courante introuvable"
            break

        # 1. L'agent propose — il ne décide de rien.
        proposal = repair_agent.propose_fix(
            module_name=module_name,
            scenarios=_scenarios_of(outcome),
            failures=failures,
            connector=connector,
        )
        session.cost_usd = round(session.cost_usd + proposal.cost_usd, 6)
        if not proposal.changed:
            # Aveu utile : l'agent n'a rien réécrit (il ne sait pas, ou il conclut à un bug de
            # l'application). Insister brûlerait le budget pour rien.
            session.outcome = "agent_no_fix"
            session.reason = proposal.summary or "l'agent n'a proposé aucune correction"
            break

        # 2. Une tentative = une VERSION (trace honnête de ce qui a été tenté).
        new_version_id = versions.create(
            test_case_id=case_id,
            spec_content=version["spec_content"], spec_hash=version["spec_hash"],
            feature_content=proposal.feature_content or version["feature_content"],
            steps_content=proposal.steps_content or version["steps_content"],
            change_summary=proposal.summary[:500] or "Réparation automatique",
            created_by="repair-agent",
        )
        session.attempts += 1
        circuit.record(failure_signature(failures))

        # 3. On rejoue — nouvelle EXÉCUTION (modèle B).
        _record_attempt(conn, outcome, failures, session.attempts, proposal.summary)
        outcome = run_once(new_version_id)
        session.executions.append(getattr(outcome, "execution_id", None))
        failures = _failures_of(outcome)
        current_version_id = new_version_id

    session.resolved = (session.outcome == "resolved")
    session.final_version_id = current_version_id

    if session.resolved and current_version_id != version_id:
        # La version réparée devient la référence — mais elle n'est PAS approuvée : personne ne
        # l'a relue. Le cas repasse « à relire » pour ratification (§4.3). C'est le prix de
        # l'option C : la réparation est invisible PENDANT la session, jamais après.
        cases.set_current_version(case_id, current_version_id)
        cases.set_validation_status(case_id, "to_review")
        logger.info("[repair] cas %s réparé en %s tentative(s) → v%s, à ratifier",
                    case_id, session.attempts, current_version_id)
    elif current_version_id != version_id:
        # Réparation ratée : la référence reste la version qu'un HUMAIN a approuvée. Les
        # versions tentées demeurent en historique — c'est la trace de ce qui a été essayé.
        session.final_version_id = version_id
        logger.info("[repair] cas %s non réparé (%s) — v%s reste la référence",
                    case_id, session.outcome, version_id)
    return session


def _record_attempt(conn, outcome, failures, attempt_number: int, what_was_tried: str) -> None:
    """Renseigne `what_was_tried` sur le diagnostic de l'exécution qui a échoué.

    La colonne existait et était **vide partout** : elle est faite pour dire ce que l'agent a
    tenté. « J'ai corrigé » n'apprendrait rien — on stocke ce qu'il DIT avoir changé, tel quel,
    et un humain le lira.
    """
    execution_id = getattr(outcome, "execution_id", None)
    if execution_id is None:
        return
    repairs = RepairRepo(conn)
    existing = repairs.list_for_execution(execution_id)
    if existing:
        conn.execute("UPDATE repair_attempt SET what_was_tried=?, attempt_number=? WHERE id=?",
                     (what_was_tried[:1000], attempt_number, existing[0]["id"]))
        conn.commit()
    elif failures:
        repairs.create(
            execution_id=execution_id, attempt_number=attempt_number,
            failure_signature=failure_signature(failures),
            cause_category="", defect_origin="test_a_reparer",
            confirmation_status="pending_human", what_was_tried=what_was_tried[:1000])
