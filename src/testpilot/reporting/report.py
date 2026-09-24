"""Assemblage et rendu du rapport de test à DEUX AXES (§5).

Le rapport ne fusionne JAMAIS les deux statuts : l'axe EXÉCUTION (le test a-t-il pu
tourner ?) et l'axe FONCTIONNEL (l'app est-elle conforme ?) sont présentés séparément, au
niveau du cas et de chaque scénario. Il porte aussi la cause racine, le coût avec sa
PROVENANCE (estimated / anthropic_api — cf. guardrails/cost_source) et les drapeaux de
confirmation humaine en attente (asymétrie §5).

Module de logique pure : il assemble des objets déjà produits par les autres piliers,
sérialise en JSON et rend un HTML autonome (Jinja2, CSS inline). Aucun réseau, sorties
déterministes hors horodatage/chemins.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from testpilot import config
from testpilot.verdict import defect_taxonomy as dt
from testpilot.verdict.status import CaseVerdict, ScenarioVerdict

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_TEMPLATE_NAME = "report.html.j2"

# Libellés lisibles des axes (le JSON garde les codes bruts ; l'HTML affiche ces libellés).
EXEC_LABELS = {
    "success": "Exécuté",
    "technical_error": "Erreur technique",
    "blocked": "Bloqué (prérequis non rempli)",
    "not_executed": "Non exécuté",
}
FUNC_LABELS = {
    "conforme": "Conforme",
    "non_conforme": "Non conforme",
    "indetermine": "Indéterminé",
    "not_evaluated": "Non évalué",
}


@dataclass
class ScenarioLine:
    name: str
    execution_status: str
    functional_status: str
    cause_category: str = ""
    cause_label: str = ""
    failure_type: str = ""
    error: str = ""


@dataclass
class RepairLine:
    """Une tentative de réparation vue par le rapport (origine + régime de confirmation)."""
    cause_category: str
    cause_label: str
    defect_origin: str
    confirmation_status: str
    requires_human_confirmation: bool
    # Ce que l'agent DIT avoir changé (décision 0014). La colonne existait et était vide
    # partout : sans elle, une réparation serait une boîte noire — l'humain verrait « v2 » sans
    # savoir ce qui a bougé, donc sans pouvoir ratifier en connaissance de cause.
    what_was_tried: str = ""


@dataclass
class TestReport:
    module_name: str
    title: str
    version_number: int
    # Les deux axes — codes bruts + libellés, jamais fusionnés.
    execution_status: str
    functional_status: str
    execution_label: str
    functional_label: str
    scenarios_total: int
    scenarios_passed: int
    scenarios_failed: int
    scenarios: list[ScenarioLine] = field(default_factory=list)
    repairs: list[RepairLine] = field(default_factory=list)
    cost_usd: float = 0.0
    cost_source: str = "estimated"
    iterations: int = 0
    duration_seconds: float = 0.0
    generated_at: str = ""
    # Observation seule (budget mensuel = suivi, ne bloque rien en Inc. 0).
    monthly_cost_usd: float | None = None
    # CONTRE QUOI ce verdict a été rendu (2026-07-24). Un rapport qui ne nomme pas l'application
    # qu'il a jugée ne prouve rien : « conforme » n'a de sens que rapporté à une cible. Vide sur
    # les exécutions antérieures à la migration 20 — et l'affichage le dit, plutôt que de laisser
    # croire que le champ n'existe pas. **Jamais le mot de passe.**
    target_url: str = ""
    target_database: str = ""
    target_username: str = ""

    @property
    def needs_human_confirmation(self) -> bool:
        return any(r.requires_human_confirmation for r in self.repairs)

    def to_dict(self) -> dict:
        return asdict(self) | {"needs_human_confirmation": self.needs_human_confirmation}


def _scenario_line(v: ScenarioVerdict) -> ScenarioLine:
    return ScenarioLine(
        name=v.name,
        execution_status=v.execution_status,
        functional_status=v.functional_status,
        cause_category=v.cause_category,
        cause_label=dt.LABELS.get(v.cause_category, "") if v.cause_category else "",
        failure_type=v.failure_type,
        error=(v.error or "")[:500],
    )


def build_report(verdict: CaseVerdict, *, module_name: str, title: str = "",
                 version_number: int = 1, cost_usd: float = 0.0,
                 cost_source: str = "estimated", iterations: int = 0,
                 duration_seconds: float = 0.0, repairs: list | None = None,
                 monthly_cost_usd: float | None = None,
                 generated_at: str | None = None,
                 target_url: str = "", target_database: str = "",
                 target_username: str = "") -> TestReport:
    """Construit un ``TestReport`` depuis un ``CaseVerdict`` et les métadonnées du run.

    ``repairs`` : tentatives dont on veut tracer l'origine et l'éventuelle confirmation en
    attente. Tout objet portant les champs d'un ``DefectVerdict`` convient ; `what_was_tried`
    est lu s'il existe (duck typing) — `DefectVerdict` est un verdict d'ORIGINE, pas une
    tentative : lui ajouter ce champ mélangerait deux domaines.
    """
    repair_lines = [
        RepairLine(
            cause_category=r.cause_category,
            cause_label=dt.LABELS.get(r.cause_category, ""),
            defect_origin=r.defect_origin,
            confirmation_status=r.confirmation_status,
            requires_human_confirmation=r.requires_human_confirmation,
            what_was_tried=getattr(r, "what_was_tried", "") or "",
        )
        for r in (repairs or [])
    ]
    return TestReport(
        module_name=module_name,
        title=title or module_name,
        version_number=version_number,
        execution_status=verdict.execution_status,
        functional_status=verdict.functional_status,
        execution_label=EXEC_LABELS.get(verdict.execution_status, verdict.execution_status),
        functional_label=FUNC_LABELS.get(verdict.functional_status, verdict.functional_status),
        scenarios_total=len(verdict.scenarios),
        scenarios_passed=verdict.scenarios_passed,
        scenarios_failed=verdict.scenarios_failed,
        scenarios=[_scenario_line(v) for v in verdict.scenarios],
        repairs=repair_lines,
        cost_usd=round(cost_usd, 6),
        cost_source=cost_source,
        iterations=iterations,
        duration_seconds=round(duration_seconds, 3),
        generated_at=generated_at or datetime.now(timezone.utc).isoformat(),
        monthly_cost_usd=(round(monthly_cost_usd, 6) if monthly_cost_usd is not None else None),
        target_url=target_url, target_database=target_database, target_username=target_username,
    )


def render_json(report: TestReport, *, indent: int = 2) -> str:
    return json.dumps(report.to_dict(), ensure_ascii=False, indent=indent)


def _environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_html(report: TestReport) -> str:
    template = _environment().get_template(_TEMPLATE_NAME)
    return template.render(
        r=report,
        exec_labels=EXEC_LABELS,
        func_labels=FUNC_LABELS,
    )


def write_report(report: TestReport, reports_dir: Path | str | None = None) -> tuple[Path, Path]:
    """Écrit le rapport JSON + HTML et renvoie leurs chemins. Crée le dossier si besoin."""
    out_dir = Path(reports_dir) if reports_dir else config.REPORTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{report.module_name}_v{report.version_number}"
    json_path = out_dir / f"{stem}.json"
    html_path = out_dir / f"{stem}.html"
    json_path.write_text(render_json(report), encoding="utf-8")
    html_path.write_text(render_html(report), encoding="utf-8")
    return json_path, html_path
