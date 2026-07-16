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

# Issue propre à cette boucle : le test n'a pas tourné du tout (le circuit, lui, ne connaît que
# des ÉCHECS — il n'a aucun moyen de distinguer « aucun échec » de « aucun run »).
RUN_FAILED = "run_failed"


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


def a_tourne(outcome) -> bool:
    """Le test s'est-il RÉELLEMENT exécuté ?

    ⚠️ **Distinction vitale, trouvée en run réel (étape 6).** Quand le dry-run échoue, Behave ne
    joue rien et `Executor` rend `real_run=None` → `_failures_of` donnait alors une liste vide,
    **exactement comme un test qui passe**. Le circuit concluait « plus aucun échec — réparation
    terminée » alors que **le test n'avait jamais tourné** : il adoptait une version cassée en
    proclamant sa victoire.

    C'est le **faux négatif** que §4.4 déclare inacceptable, et le motif déjà traqué en `0010`,
    `0011` et `0013` : **l'absence de signal prise pour un signal positif**. Mesuré : l'exécution
    13 (v7) avait 0 scénario et la réparation s'est déclarée réussie.
    """
    return outcome is not None and getattr(outcome, "real_run", None) is not None


def _failures_of(outcome) -> list:
    """Échecs du run. ⚠️ Vide ne veut RIEN dire sans `a_tourne()` : voir sa docstring."""
    return list(outcome.real_run.failures) if a_tourne(outcome) else []


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
        # ⚠️ AVANT toute évaluation : un test qui n'a pas tourné n'a pas « zéro échec », il n'a
        # pas de résultat. Laisser `evaluate` voir une liste vide lui ferait conclure
        # « résolu » — et la boucle adopterait une version cassée (bug trouvé en run réel).
        if not a_tourne(outcome):
            session.outcome = RUN_FAILED
            session.reason = (
                "le test n'a pas pu s'exécuter (dry-run en échec) — il ne parse plus. "
                "La réparation l'a cassé, ou la version de départ était déjà injouable."
            )
            logger.warning("[repair] cas %s : le test ne tourne plus après %s tentative(s) — "
                           "aucune adoption", case_id, session.attempts)
            break

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
            # Le fichier ACTUEL : `write_steps_file` le REMPLACE, l'agent doit donc partir de
            # son contenu et le rendre entier — sans lui, il réécrit de mémoire et tronque.
            steps_content=version["steps_content"] or "",
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

    _sync_disque(versions, session, version_id, current_version_id, module_name)

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


def _sync_disque(versions, session: RepairSession, version_id: int,
                 current_version_id: int, module_name: str) -> None:
    """Le DISQUE doit toujours refléter la version qui fait référence.

    ⚠️ Le runner lit les fichiers **sur disque** (`BehaveRunner._assemble` les recopie), pas la
    base. Or `write_steps_file` a écrit la tentative de l'agent sur ce disque. Si la réparation
    n'est PAS adoptée, la base dit « v1 » et le disque contient « v3 » : **le prochain run
    exécuterait v3 en prétendant v1** — un « affiché ≠ réel » (§4.6), et le pire genre : le
    verdict porterait sur un code que personne n'a approuvé.

    On réécrit donc systématiquement la version de référence après la boucle.
    """
    if not session.attempts:
        return   # rien n'a été écrit sur le disque
    reference = current_version_id if session.resolved else version_id
    version = versions.get(reference)
    if version is None:
        logger.error("[repair] version de référence %s introuvable — disque non resynchronisé",
                     reference)
        return
    try:
        config.GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        (config.GENERATED_DIR / f"{module_name}.feature").write_text(
            version["feature_content"] or "", encoding="utf-8")
        (config.GENERATED_DIR / f"{module_name}_steps.py").write_text(
            version["steps_content"] or "", encoding="utf-8")
        logger.info("[repair] disque resynchronisé sur la version de référence v%s", reference)
    except OSError:
        # Laisser un disque divergent serait pire que bruyant : un run futur mentirait.
        logger.exception("[repair] ÉCHEC de la resynchronisation du disque sur v%s — le prochain "
                         "run pourrait exécuter un code qui n'est pas celui de la version "
                         "courante", reference)


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
