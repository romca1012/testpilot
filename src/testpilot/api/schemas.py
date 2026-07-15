"""DTO Pydantic de l'API — modèle à DEUX AXES exposé tel quel, jamais fusionné.

Les repos renvoient des dicts SQLite ; ces mappers projettent les champs voulus vers des
réponses stables. La séparation exécution/fonctionnel du §5 est préservée jusqu'au client.
"""

from __future__ import annotations

from pydantic import BaseModel


# ── Projet / Module (hiérarchie §7) ───────────────────────────────────────────
class ProjectSummary(BaseModel):
    id: int
    name: str
    description: str = ""
    connector_type: str = "odoo"
    base_url: str = ""
    database: str = ""
    username: str = ""
    # password : jamais exposé par l'API (write-only, cf. décision 0005).
    module_count: int = 0
    case_count: int = 0


class ModuleSummary(BaseModel):
    id: int
    project_id: int
    name: str
    description: str = ""
    case_count: int = 0


class ProjectRef(BaseModel):
    id: int
    name: str


class ModuleRef(BaseModel):
    id: int
    name: str


# ── Cas ───────────────────────────────────────────────────────────────────────
class CaseSummary(BaseModel):
    id: int
    title: str
    module: str  # nom métier lisible du module (jamais le slug technique)
    module_id: int | None = None
    project_id: int | None = None
    validation_status: str
    last_execution_status: str | None = None
    last_functional_status: str | None = None
    last_executed_at: str | None = None


class VersionOut(BaseModel):
    id: int
    version_number: int
    feature_content: str = ""
    steps_content: str = ""
    spec_hash: str = ""
    created_at: str = ""


class ReviewOut(BaseModel):
    id: int
    version_id: int
    decision: str
    reviewer: str = ""
    comment: str = ""
    decided_at: str = ""


class GateOut(BaseModel):
    allowed: bool
    needs_review: bool
    reason: str


class ExecutionSummary(BaseModel):
    id: int
    test_case_id: int
    version_id: int
    execution_status: str
    functional_status: str
    scenarios_total: int = 0
    scenarios_passed: int = 0
    scenarios_failed: int = 0
    cost_usd: float = 0.0
    iterations: int = 0
    duration_seconds: float = 0.0
    started_at: str = ""
    running: bool = False
    # Contexte de ce qui a tourné (rempli sur la liste globale). ``suite_name`` est réservé
    # à l'Exécution nommée transverse (§7) — null tant qu'elle n'est pas implémentée.
    case_title: str | None = None
    module_name: str | None = None
    suite_name: str | None = None


class CaseDetail(BaseModel):
    case: CaseSummary
    project: ProjectRef | None = None   # fil d'Ariane Projet > Module > Cas
    module: ModuleRef | None = None
    current_version_id: int | None = None
    versions: list[VersionOut] = []
    reviews: list[ReviewOut] = []
    executions: list[ExecutionSummary] = []
    gate: GateOut | None = None


class ScenarioResultOut(BaseModel):
    scenario_name: str
    execution_status: str
    functional_status: str
    cause_category: str = ""
    failure_type: str = ""
    error_summary: str = ""


class ExecutionDetail(ExecutionSummary):
    scenarios: list[ScenarioResultOut] = []


# ── Actions ───────────────────────────────────────────────────────────────────
class RunResponse(BaseModel):
    execution_id: int
    status: str  # "running"


class ProjectIn(BaseModel):
    name: str
    description: str = ""
    connector_type: str = "odoo"
    base_url: str = ""
    database: str = ""
    username: str = ""
    password: str = ""  # secret : accepté en entrée, jamais relu en sortie


class ModuleIn(BaseModel):
    name: str
    description: str = ""


class ReviewIn(BaseModel):
    approved: bool
    reviewer: str = "ui"
    comment: str = ""


class ReviewResponse(BaseModel):
    decision: str
    validation_status: str
    gate: GateOut


# ── Mappers dict → DTO ─────────────────────────────────────────────────────────
def project_summary(row: dict) -> ProjectSummary:
    return ProjectSummary(
        id=row["id"], name=row["name"], description=row.get("description", ""),
        connector_type=row.get("connector_type", "odoo"), base_url=row.get("base_url", ""),
        database=row.get("database", ""), username=row.get("username", ""),
        module_count=row.get("module_count", 0), case_count=row.get("case_count", 0))


def module_summary(row: dict) -> ModuleSummary:
    return ModuleSummary(id=row["id"], project_id=row["project_id"], name=row["name"],
                         description=row.get("description", ""), case_count=row.get("case_count", 0))


def case_summary(row: dict) -> CaseSummary:
    return CaseSummary(
        id=row["id"], title=row["title"],
        # Nom métier du module (repli sur le slug technique si le cas n'est pas encore rattaché).
        module=row.get("module_name") or row.get("feature_slug") or "—",
        module_id=row.get("module_id"), project_id=row.get("project_id"),
        validation_status=row["validation_status"],
        last_execution_status=row.get("last_execution_status"),
        last_functional_status=row.get("last_functional_status"),
        last_executed_at=row.get("last_executed_at"),
    )


def version_out(row: dict) -> VersionOut:
    return VersionOut(
        id=row["id"], version_number=row["version_number"],
        feature_content=row.get("feature_content", ""),
        steps_content=row.get("steps_content", ""),
        spec_hash=row.get("spec_hash", ""), created_at=row.get("created_at", ""),
    )


def review_out(row: dict) -> ReviewOut:
    return ReviewOut(
        id=row["id"], version_id=row["version_id"], decision=row["decision"],
        reviewer=row.get("reviewer", ""), comment=row.get("comment", ""),
        decided_at=row.get("decided_at", ""),
    )


def execution_summary(row: dict, *, running: bool = False) -> ExecutionSummary:
    return ExecutionSummary(
        id=row["id"], test_case_id=row["test_case_id"], version_id=row["version_id"],
        execution_status=row["execution_status"], functional_status=row["functional_status"],
        scenarios_total=row.get("scenarios_total", 0),
        scenarios_passed=row.get("scenarios_passed", 0),
        scenarios_failed=row.get("scenarios_failed", 0),
        cost_usd=row.get("cost_usd", 0.0), iterations=row.get("iterations", 0),
        duration_seconds=row.get("duration_seconds", 0.0),
        started_at=row.get("started_at", ""), running=running,
        case_title=row.get("case_title"), module_name=row.get("module_name"),
        suite_name=row.get("suite_name"),
    )


def scenario_result_out(row: dict) -> ScenarioResultOut:
    return ScenarioResultOut(
        scenario_name=row["scenario_name"], execution_status=row["execution_status"],
        functional_status=row["functional_status"], cause_category=row.get("cause_category", ""),
        failure_type=row.get("failure_type", ""), error_summary=row.get("error_summary", ""),
    )
