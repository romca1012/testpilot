"""Orchestration bout-en-bout (§4) : spec → génération → gate de relecture → exécution → rapport.

Une seule commande pour la preuve de concept : ``testpilot run <spec>``. La logique de
décision du gate reste dans ``verdict/review_gate`` (pure) ; ce module ne fait que
l'affichage, la saisie et le câblage des piliers.

Les collaborateurs (analyzer, agent, executor, connexion) sont injectés via ``PipelineDeps``
pour que ``run_pipeline`` soit testable hors-ligne (fakes) sans toucher au vrai LLM, au vrai
Behave ni à Odoo. ``build_default_deps`` assemble les implémentations réelles pour la prod.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from testpilot import config
from testpilot.execution.executor import ExecutionOutcome
from testpilot.reporting import report as report_mod
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import (
    CaseRepo,
    CostRepo,
    ExecutionRepo,
    RepairRepo,
    ReviewRepo,
    now_iso,
)
from testpilot.verdict import defect_origin as do
from testpilot.verdict import review_gate
from testpilot.verdict.status import EXEC_SUCCESS, CaseVerdict, derive_verdict

# Étapes d'arrêt possibles du pipeline (valeur de PipelineResult.stopped_stage).
STAGE_GENERATION = "generation_failed"
STAGE_REVIEW_REJECTED = "review_rejected"
STAGE_DONE = "done"


@dataclass
class PipelineDeps:
    analyzer: object   # .analyze_spec_file(path) -> TestPlan
    agent: object      # .generate(plan, case_id=None, title=, author=) -> GenerationResult
    executor: object   # .execute(module_name) -> ExecutionOutcome
    conn: object       # connexion sqlite3 initialisée


@dataclass
class PipelineResult:
    stopped_stage: str
    case_id: int | None = None
    version_id: int | None = None
    execution_id: int | None = None
    verdict: CaseVerdict | None = None
    report_json: Path | None = None
    report_html: Path | None = None
    message: str = ""


def _interactive_approve(feature_content: str, out: Callable[[str], None]) -> bool:
    out("\n--- Version générée (relecture obligatoire avant exécution) ---")
    out(feature_content or "(feature vide)")
    answer = input("Approuver cette version pour exécution ? [o/N] ").strip().lower()
    return answer in ("o", "oui", "y", "yes")


def _diagnose_repairs(outcome: ExecutionOutcome) -> list:
    """Origine du défaut du run (cause dominante). Liste vide si pas d'échec exploitable."""
    if outcome.real_run is None or not outcome.real_run.failures:
        return []
    verdict = do.diagnose(outcome.real_run.failures)
    return [verdict] if verdict is not None else []


def _persist_run(deps: PipelineDeps, *, case_id: int, version_id: int,
                 verdict: CaseVerdict, outcome: ExecutionOutcome, repairs: list,
                 gen_cost_usd: float, iterations: int, duration_seconds: float) -> int:
    """Persiste exécution + scénarios + tentative de réparation + coût. Renvoie l'execution_id."""
    execs = ExecutionRepo(deps.conn)
    eid = execs.create(test_case_id=case_id, version_id=version_id)

    for s in verdict.scenarios:
        execs.add_scenario_result(
            execution_id=eid, scenario_name=s.name,
            execution_status=s.execution_status, functional_status=s.functional_status,
            failure_type=s.failure_type, cause_category=s.cause_category,
            error_summary=(s.error or "")[:500],
        )

    if repairs and outcome.real_run is not None:
        from testpilot.guardrails.repair_circuit import failure_signature
        repairs_repo = RepairRepo(deps.conn)
        sig = failure_signature(outcome.real_run.failures)
        for i, dv in enumerate(repairs, start=1):
            repairs_repo.create(
                execution_id=eid, attempt_number=i, failure_signature=sig,
                cause_category=dv.cause_category, defect_origin=dv.defect_origin,
                confirmation_status=dv.confirmation_status,
            )

    # Coût de génération au ledger — source 'estimated' (barème tokens, cf. cost_source).
    CostRepo(deps.conn).add_entry(
        phase="generation", model=config.MODEL_GENERATION, cost_usd=gen_cost_usd,
        source="estimated", execution_id=eid,
    )

    execs.finalize(
        eid, execution_status=verdict.execution_status,
        functional_status=verdict.functional_status,
        scenarios_total=len(verdict.scenarios),
        scenarios_passed=verdict.scenarios_passed,
        scenarios_failed=verdict.scenarios_failed,
        cost_usd=gen_cost_usd, iterations=iterations, duration_seconds=duration_seconds,
    )

    cases = CaseRepo(deps.conn)
    prev = cases.get(case_id)
    new_validation = review_gate.validation_status_after_run(
        prev["validation_status"] if prev else "never_executed", verdict.execution_status)
    cases.set_validation_status(case_id, new_validation)
    cases.update_last_outcome(
        case_id, execution_status=verdict.execution_status,
        functional_status=verdict.functional_status, executed_at=now_iso())
    return eid


def run_pipeline(deps: PipelineDeps, spec_path: str | Path, *, author: str = "",
                 auto_approve: bool = False, prompt_fn: Callable[[str], bool] | None = None,
                 reviewer: str = "cli", reports_dir: Path | str | None = None,
                 out: Callable[[str], None] = print) -> PipelineResult:
    """Enchaîne le pipeline complet pour un fichier de spec et écrit le rapport à deux axes."""
    # 1. Analyse de la spec → plan.
    plan = deps.analyzer.analyze_spec_file(spec_path)
    out(f"[1/5] Analyse : module '{plan.module_name}', {len(plan.scenarios)} scénario(s).")

    # 2. Génération (persiste cas + version via l'agent).
    gen = deps.agent.generate(plan, title=plan.module_name, author=author)
    if not gen.success or gen.version_id is None:
        out(f"[2/5] Génération échouée ({gen.stopped_reason}). Arrêt avant exécution.")
        return PipelineResult(STAGE_GENERATION, case_id=gen.case_id, version_id=gen.version_id,
                              message=gen.error or gen.stopped_reason)
    out(f"[2/5] Génération OK (cas {gen.case_id}, version {gen.version_id}, "
        f"{gen.iterations} itér., ${gen.cost_usd:.4f}).")

    # 3. Gate de relecture — décision pure dans review_gate, I/O ici.
    reviews = ReviewRepo(deps.conn)
    decision = review_gate.evaluate_gate(reviews, gen.version_id)
    if not decision.allowed:
        approver = prompt_fn or (lambda fc: _interactive_approve(fc, out))
        approved = True if auto_approve else approver(gen.feature_content)
        decision = review_gate.submit_review(
            reviews, case_id=gen.case_id, version_id=gen.version_id,
            approved=approved, reviewer=reviewer,
            comment="auto-approuvé (--yes)" if auto_approve else "relecture CLI")
        if not approved:
            out("[3/5] Version rejetée en relecture. Arrêt sans exécution.")
            CaseRepo(deps.conn).set_validation_status(gen.case_id, "to_review")
            return PipelineResult(STAGE_REVIEW_REJECTED, case_id=gen.case_id,
                                  version_id=gen.version_id, message="rejeté en relecture")
    out("[3/5] Relecture approuvée — exécution autorisée.")

    # 4. Exécution réelle → outcome brut.
    started = time.perf_counter()
    outcome = deps.executor.execute(plan.module_name)
    duration = time.perf_counter() - started
    out(f"[4/5] Exécution terminée en {duration:.1f}s (dry-run "
        f"{'OK' if outcome.dry_run_passed else 'ÉCHEC'}).")

    # 5. Verdict à deux axes + rapport.
    verdict = derive_verdict(outcome)
    repairs = _diagnose_repairs(outcome)
    eid = _persist_run(deps, case_id=gen.case_id, version_id=gen.version_id, verdict=verdict,
                       outcome=outcome, repairs=repairs, gen_cost_usd=gen.cost_usd,
                       iterations=gen.iterations, duration_seconds=duration)

    monthly = CostRepo(deps.conn).monthly_total_usd()
    report = report_mod.build_report(
        verdict, module_name=plan.module_name, title=plan.module_name,
        version_number=1, cost_usd=gen.cost_usd, cost_source="estimated",
        iterations=gen.iterations, duration_seconds=duration, repairs=repairs,
        monthly_cost_usd=monthly)
    json_path, html_path = report_mod.write_report(report, reports_dir)

    out(f"[5/5] Verdict — exécution : {report.execution_label} | "
        f"fonctionnel : {report.functional_label}. Rapport : {html_path}")
    if report.needs_human_confirmation:
        out("      ⚠ Confirmation humaine requise sur au moins une origine de défaut.")

    return PipelineResult(STAGE_DONE, case_id=gen.case_id, version_id=gen.version_id,
                          execution_id=eid, verdict=verdict,
                          report_json=json_path, report_html=html_path)


def build_default_deps(conn) -> PipelineDeps:
    """Assemble les implémentations réelles des piliers (LLM, Behave, connecteur, store).

    Le connecteur Odoo est CONNECTÉ ici et injecté à l'agent : sans lui, la génération
    explorerait à l'aveugle (pas d'``inspect_form``/``get_schema``) — ce qui viderait de son
    sens la perception « boîte noire » du §6. ``main`` le déconnecte en fin de run.

    Génération ET exécution tapent la connexion du PROJET courant (le premier projet, même
    règle que le rattachement automatique) : sans ça, un cas serait rangé sous un projet mais
    joué contre une autre instance — l'incohérence exacte que l'outil doit éliminer.
    """
    from testpilot.analysis.spec_analyzer import SpecAnalyzer
    from testpilot.connectors.odoo import OdooConnector
    from testpilot.connectors.runtime_env import project_env
    from testpilot.execution.behave_runner import BehaveRunner
    from testpilot.execution.executor import Executor
    from testpilot.generation.agent import GenerationAgent
    from testpilot.store.repositories import CaseRepo as _Case
    from testpilot.store.repositories import ProjectRepo as _Project
    from testpilot.store.repositories import VersionRepo as _Version

    project = _Project(conn).first()  # None → config globale (le projet sera créé depuis elle)
    connector = OdooConnector.from_project(project)
    connector.connect()
    runner = BehaveRunner(connection=project_env(project))
    agent = GenerationAgent(dry_runner=runner, connector=connector,
                            case_repo=_Case(conn), version_repo=_Version(conn))
    return PipelineDeps(analyzer=SpecAnalyzer(), agent=agent,
                        executor=Executor(runner), conn=conn)


def main(argv: list[str] | None = None) -> int:
    # Sur Windows, la console/redirection est en cp1252 : forcer utf-8 pour ne pas planter
    # sur les caractères non-latin1 (accents, symboles) de la sortie du pipeline.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = argparse.ArgumentParser(prog="testpilot", description="TestPilot — pipeline de test IA")
    sub = parser.add_subparsers(dest="command", required=True)
    runp = sub.add_parser("run", help="spec → génération → relecture → exécution → rapport")
    runp.add_argument("spec", help="chemin du fichier de spécification")
    runp.add_argument("--author", default="", help="auteur du cas généré")
    runp.add_argument("--yes", action="store_true",
                      help="auto-approuve le gate de relecture (exécution non interactive)")
    runp.add_argument("--db", default=None, help="chemin de la base (défaut : config)")
    args = parser.parse_args(argv)

    if args.command == "run":
        config.ensure_dirs()
        conn = get_initialized_db(args.db)
        connector = None
        try:
            deps = build_default_deps(conn)
            connector = getattr(deps.agent, "connector", None)
            result = run_pipeline(deps, args.spec, author=args.author, auto_approve=args.yes)
        finally:
            if connector is not None:
                try:
                    connector.disconnect()
                except Exception:
                    pass
            conn.close()
        return 0 if result.stopped_stage == STAGE_DONE else 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
