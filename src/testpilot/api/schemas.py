"""DTO Pydantic de l'API — modèle à DEUX AXES exposé tel quel, jamais fusionné.

Les repos renvoient des dicts SQLite ; ces mappers projettent les champs voulus vers des
réponses stables. La séparation exécution/fonctionnel du §5 est préservée jusqu'au client.
"""

from __future__ import annotations

import json

from pydantic import BaseModel

from testpilot.verdict import defect_taxonomy as _dt


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
class GroupSummary(BaseModel):
    """Spécification (case_group) — conteneur d'affichage : id, module, titre, nb de cas."""
    id: int
    module_id: int
    title: str
    case_count: int = 0


class CaseSummary(BaseModel):
    id: int
    title: str
    module: str  # nom métier lisible du module (jamais le slug technique)
    module_id: int | None = None
    project_id: int | None = None
    # Spécification (case_group) propriétaire + angle testé — séparation 2026-07-19. `angle` est
    # une étiquette LIBRE (nominal/erreur/limite/autre/legacy), affichée en libellé métier côté UI.
    group_id: int | None = None
    group_title: str | None = None
    angle: str = ""
    # Métadonnées non versionnées (décision 0022 n°3b) : elles ne changent pas ce que le test
    # vérifie. `refs` = tickets externes ; `estimate` alimentera le burndown.
    refs: str = ""
    estimate: str = ""
    validation_status: str
    priority: str = "medium"  # étiquette de lecture — aucun ordre d'exécution promis
    last_execution_status: str | None = None
    last_functional_status: str | None = None
    last_executed_at: str | None = None
    # Version qui a produit le dernier verdict, et divergence éventuelle avec la version
    # COURANTE (décision 0016, option (iii)). Une tentative de réparation non adoptée écrit
    # quand même les `last_*` du cas : le verdict peut donc décrire une version rembobinée.
    # On le rend VISIBLE — jamais silencieux, et jamais « corrigé » en masquant un run réel.
    last_verdict_version_id: int | None = None
    verdict_from_other_version: bool = False


class VersionOut(BaseModel):
    id: int
    version_number: int
    # Contenu MÉTIER figé dans cette version (décision 0022 n°10) — c'est ce que l'écran affiche
    # et ce que l'historique diffe. `test_steps` est une liste JSON sérialisée.
    title: str = ""
    preconditions: str = ""
    test_steps: str = ""
    expected_result: str = ""
    angle: str = ""
    feature_content: str = ""
    steps_content: str = ""
    spec_hash: str = ""
    # D'où vient cette version, et ce qui a changé (décision 0014). Sans ça, une réparation
    # serait une boîte noire : l'humain verrait « v2 » sans savoir ce qui a bougé, donc sans
    # pouvoir ratifier en connaissance de cause.
    change_summary: str = ""
    created_by: str = ""
    created_at: str = ""


class ReviewOut(BaseModel):
    id: int
    version_id: int
    decision: str
    reviewer: str = ""
    comment: str = ""
    decided_at: str = ""


class LintWarning(BaseModel):
    step: str
    line: int
    kind: str
    message: str


class GateOut(BaseModel):
    allowed: bool
    needs_review: bool
    reason: str
    # Réparations autorisées par la relecture en cours (0014). 0 si non relue ou interdite.
    repair_budget: int = 0
    # Le défaut proposé au relecteur qui n'a pas d'avis — affiché, jamais imposé.
    repair_budget_default: int = 0
    # Avertissements NON-bloquants sur les assertions générées (décision 0008). N'affectent
    # jamais `allowed` : ils informent le relecteur, le gate reste souverain.
    lint_warnings: list[LintWarning] = []


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
    # Replis « libellé → nom technique » tracés pendant le run (décision 0007, phase B+).
    # Informatif et NON-bloquant, à l'image des `lint_warnings` du gate : signale soit un step
    # mal paramétré, soit un champ réellement renommé côté application. Présent même sur un run
    # vert — c'est là que le repli serait autrement invisible.
    field_fallbacks: list[str] = []
    # Raison d'un plantage AVANT tout scénario (migration 11). Vide sur un run normal : un
    # échec de scénario s'explique par ses `scenario_results`, pas par ce champ.
    error_message: str = ""
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


class RepairOut(BaseModel):
    """Un diagnostic soumis à l'arbitrage humain (décision 0013).

    Expose CÔTE À CÔTE ce que la machine a déduit (`defect_origin`) et ce que l'humain a tranché
    (`human_verdict`/`human_origin`) — jamais l'un à la place de l'autre : c'est l'écart entre
    les deux qui rend la taxonomie mesurable.
    """

    id: int
    execution_id: int
    test_case_id: int | None = None
    case_title: str | None = None
    module_id: int | None = None
    module_name: str | None = None
    project_id: int | None = None
    project_name: str | None = None
    executed_at: str = ""
    # Les DEUX axes du run concerné — informatifs ici : un arbitrage ne les recalcule JAMAIS
    # (§4.2 : un statut est la conséquence d'une exécution réelle, pas d'un avis).
    execution_status: str = ""
    functional_status: str = ""
    # Ce que la MACHINE a déduit.
    cause_category: str = ""
    # Libellé lisible de la cause, rendu CÔTÉ SERVEUR via `defect_taxonomy.LABELS` — même source
    # que le rapport (`report.py`), plutôt qu'un second vocabulaire dans `status.ts` qui
    # divergerait. Jamais d'enum brute à l'écran (§4.7).
    cause_label: str = ""
    defect_origin: str = ""
    confirmation_status: str = ""
    failure_signature: str = ""
    # Ce que l'HUMAIN a tranché (vide tant que non arbitré).
    human_verdict: str = ""
    human_origin: str = ""
    human_comment: str = ""
    confirmed_by: str | None = None
    confirmed_at: str | None = None


class RepairVerdictIn(BaseModel):
    """Arbitrage humain. `origin` est requis si `verdict='overturned'` (validé côté repo)."""

    verdict: str          # confirmed | overturned
    origin: str = ""      # test_a_reparer | vrai_bug | indetermine — si infirmé
    comment: str = ""
    reviewer: str = ""    # champ LIBRE : aucune authentification (cohérent avec le gate)


class ReorderCasesIn(BaseModel):
    """Nouvel ordre d'AFFICHAGE des cas d'un module (décision 0009).

    En LOT, pas un PATCH par cas : un glissement change N positions, et N appels laisseraient un
    ordre incohérent si l'un échouait. Le serveur recalcule les positions — la liste dit le
    RANG, pas l'index.
    """

    case_ids: list[int]


class ScenarioResultOut(BaseModel):
    scenario_name: str
    execution_status: str
    functional_status: str
    cause_category: str = ""
    failure_type: str = ""
    error_summary: str = ""
    # Exposé pour rendre `cause_category` AUDITABLE (décision 0015) : sans le step en échec,
    # relire un classement passé demandait d'ouvrir la base à la main.
    step_text: str = ""


class ExecutionDetail(ExecutionSummary):
    scenarios: list[ScenarioResultOut] = []


# ── Actions ───────────────────────────────────────────────────────────────────
class RunResponse(BaseModel):
    execution_id: int
    status: str  # "running"


class ModuleDetail(BaseModel):
    module: ModuleSummary
    project: ProjectRef


class CasePatch(BaseModel):
    priority: str  # low | medium | high


class CaseMetierIn(BaseModel):
    """Édition du contenu MÉTIER d'un cas (décision `0022`). Chaque champ est optionnel : seul ce
    qui est fourni change. Une modification d'un champ VERSIONNÉ crée une nouvelle version — jamais
    un écrasement (n°10). `refs`/`estimate` sont des métadonnées et n'en créent pas."""
    title: str | None = None
    preconditions: str | None = None
    test_steps: str | None = None      # liste JSON sérialisée
    expected_result: str | None = None
    angle: str | None = None
    refs: str | None = None
    estimate: str | None = None
    editor: str = "ui"


class CaseMetierOut(BaseModel):
    case: CaseSummary
    version_id: int | None = None      # None = rien de versionné n'a changé
    version_created: bool = False


class AddCaseIn(BaseModel):
    """Ajout d'un cas = fournir une SPEC (jamais une coquille vide — décision 0006)."""
    spec_content: str = ""
    spec_path: str = ""
    title: str = ""
    author: str = "ui"


class MetierDraftOut(BaseModel):
    """Le document métier proposé par l'IA — à valider ou corriger avant l'écriture du Gherkin."""
    title: str = ""
    preconditions: str = ""
    steps: list[str] = []
    expected_result: str = ""
    angle: str = ""


class GenerationJobOut(BaseModel):
    job_id: str
    # running | awaiting_metier | done | failed
    # ⚠️ `awaiting_metier` n'est PAS un état d'attente technique : le job est arrêté et n'ira
    # nulle part tant qu'un humain n'aura pas validé le document métier (décision `0022` n°5).
    status: str
    case_id: int | None = None
    error: str = ""
    # Rempli uniquement en `awaiting_metier`.
    metier: MetierDraftOut | None = None


class MetierValidationIn(BaseModel):
    """Le document métier tel que l'humain le valide — corrections comprises.

    C'est CE contenu qui fera foi pour l'écriture du Gherkin, pas la proposition de l'IA :
    l'humain peut tout réécrire, c'est l'intérêt de la pause.
    """
    title: str
    preconditions: str = ""
    steps: list[str]
    expected_result: str
    angle: str = ""


class ProjectIn(BaseModel):
    name: str
    description: str = ""
    connector_type: str = "odoo"
    base_url: str = ""
    database: str = ""
    username: str = ""
    password: str = ""  # secret : accepté en entrée, jamais relu en sortie


class ProjectPatch(BaseModel):
    """Édition d'un projet, connexion COMPRISE (décision `0005`).

    ⚠️ Défauts à `None`, pas à `""` — contrairement à `ProjectIn`. Sur un PATCH, `""` veut dire
    « vide ce champ » et `None` « n'y touche pas » : les confondre ferait effacer la connexion
    d'un projet à chaque renommage. C'est vital pour `password`, que l'API ne renvoie jamais —
    un écran d'édition l'affiche donc toujours vide, et le réenvoyer tel quel détruirait le
    secret enregistré.
    """
    name: str | None = None
    description: str | None = None
    connector_type: str | None = None
    base_url: str | None = None
    database: str | None = None
    username: str | None = None
    password: str | None = None  # secret : accepté en entrée, jamais relu en sortie


class ExplorationOut(BaseModel):
    """L'état de la cartographie d'un projet — ce que l'écran montre avant/après exploration.

    ⚠️ `mesure_le` est affiché systématiquement : la cartographie est une PHOTO qui vieillit, et
    tout ce qui la consomme doit dire de quand elle date (cf. `domain_model`).
    """
    explored: bool = False
    running: bool = False
    job_id: str = ""
    mesure_le: str = ""
    pages: int = 0
    transitions: int = 0
    champs: int = 0
    resume: str = ""
    error: str = ""


class QualityDayOut(BaseModel):
    jour: str
    success: int = 0
    technical_error: int = 0
    not_executed: int = 0


class QualityOut(BaseModel):
    """Santé technique de la génération, dans le temps — le suivi de l'évolution de l'outil.

    Axe EXÉCUTION uniquement (un test qui tourne et trouve un bug est un succès technique).
    `ran_rate` = None quand aucune mesure : « rien mesuré » ≠ « 0 % de réussite ».
    """
    total: int = 0
    ran: int = 0
    technical_error: int = 0
    not_executed: int = 0
    ran_rate: float | None = None
    by_day: list[QualityDayOut] = []


class ManualCaseIn(BaseModel):
    """Création d'un cas À LA MAIN (bouton « Ajouter un cas de test », sans IA).

    Titre + étapes + résultat attendu obligatoires (décision `0022` n°3.c) — un cas sans eux ne
    décrit rien. `test_steps` = liste JSON, comme partout ailleurs.
    """
    title: str
    preconditions: str = ""
    test_steps: list[str] = []
    expected_result: str = ""
    angle: str = ""


class SpecExtractOut(BaseModel):
    """Texte extrait d'un fichier téléversé, pour pré-remplir la zone de génération."""
    text: str
    filename: str = ""


class ModuleIn(BaseModel):
    name: str
    description: str = ""


class GroupIn(BaseModel):
    """Création d'une Spécification. `spec_content` est LE DOCUMENT source (décision `0022`).

    ⚠️ Pas de `spec_hash` : l'empreinte est recalculée par le repo depuis le document, jamais
    reçue de l'appelant — sinon elle pourrait mentir sur ce qu'elle référence.
    """
    title: str
    description: str = ""
    spec_content: str = ""


class GroupPatch(BaseModel):
    """Édition partielle : `None` = « ne touche pas à ce champ » (≠ « vide-le »)."""
    title: str | None = None
    description: str | None = None
    spec_content: str | None = None


class GroupDetail(BaseModel):
    """La Spécification AVEC son document — la vue de l'écran d'édition.

    `GroupSummary` (sans le document) reste la vue des listes et de l'arbre : une liste de
    spécifications n'a pas à charger N documents complets.
    """
    id: int
    module_id: int
    title: str
    description: str = ""
    spec_content: str = ""
    spec_hash: str = ""
    case_count: int = 0
    created_at: str = ""
    updated_at: str = ""


def group_detail(row: dict) -> GroupDetail:
    return GroupDetail(
        id=row["id"], module_id=row["module_id"], title=row["title"],
        description=row.get("description", ""), spec_content=row.get("spec_content", ""),
        spec_hash=row.get("spec_hash", ""), case_count=row.get("case_count", 0),
        created_at=row.get("created_at", ""), updated_at=row.get("updated_at", ""))


class ReviewIn(BaseModel):
    approved: bool
    reviewer: str = "ui"
    comment: str = ""
    # Tentatives de réparation que cette approbation autorise (décision 0014, option C).
    # None → le défaut de configuration. 0 → réparation interdite pour cette version.
    # Réparer exige d'exécuter, et §4.3 exige le gate avant toute exécution : c'est donc le
    # gate qui autorise, explicitement — il n'est pas contourné par la boucle.
    repair_budget: int | None = None


class ReviewResponse(BaseModel):
    decision: str
    validation_status: str
    gate: GateOut
    # Ce que l'approbation a réellement autorisé — renvoyé pour que l'UI montre la valeur
    # RETENUE, pas celle envoyée (elles diffèrent si le champ était vide).
    repair_budget: int = 0


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
        group_id=row.get("group_id"), group_title=row.get("group_title"),
        angle=row.get("angle", "") or "",
        refs=row.get("refs", "") or "", estimate=row.get("estimate", "") or "",
        validation_status=row["validation_status"],
        priority=row.get("priority", "medium"),
        last_execution_status=row.get("last_execution_status"),
        last_functional_status=row.get("last_functional_status"),
        last_executed_at=row.get("last_executed_at"),
        last_verdict_version_id=row.get("last_verdict_version_id"),
        # Divergence seulement si les DEUX sont connues : un cas jamais exécuté, ou sans version
        # courante, ne « diverge » de rien — le dire serait une alerte inventée.
        verdict_from_other_version=bool(
            row.get("last_verdict_version_id")
            and row.get("current_version_id")
            and row["last_verdict_version_id"] != row["current_version_id"]),
    )


def version_out(row: dict) -> VersionOut:
    return VersionOut(
        id=row["id"], version_number=row["version_number"],
        feature_content=row.get("feature_content", ""),
        steps_content=row.get("steps_content", ""),
        spec_hash=row.get("spec_hash", ""), created_at=row.get("created_at", ""),
        change_summary=row.get("change_summary", "") or "",
        created_by=row.get("created_by", "") or "",
        title=row.get("title", "") or "",
        preconditions=row.get("preconditions", "") or "",
        test_steps=row.get("test_steps", "") or "",
        expected_result=row.get("expected_result", "") or "",
        angle=row.get("angle", "") or "",
    )


def review_out(row: dict) -> ReviewOut:
    return ReviewOut(
        id=row["id"], version_id=row["version_id"], decision=row["decision"],
        reviewer=row.get("reviewer", ""), comment=row.get("comment", ""),
        decided_at=row.get("decided_at", ""),
    )


def _field_fallbacks(raw) -> list[str]:
    """Décode la liste JSON des replis (0007 B+). Vide si absente ou illisible.

    Un contenu illisible ne doit jamais casser l'affichage d'une exécution : le repli est une
    information de confort, le verdict à deux axes reste la donnée souveraine.
    """
    if not raw:
        return []
    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return [str(item) for item in decoded] if isinstance(decoded, list) else []


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
        field_fallbacks=_field_fallbacks(row.get("field_fallbacks")),
        error_message=row.get("error_message", "") or "",
        case_title=row.get("case_title"), module_name=row.get("module_name"),
        suite_name=row.get("suite_name"),
    )


def scenario_result_out(row: dict) -> ScenarioResultOut:
    return ScenarioResultOut(
        scenario_name=row["scenario_name"], execution_status=row["execution_status"],
        functional_status=row["functional_status"], cause_category=row.get("cause_category", ""),
        failure_type=row.get("failure_type", ""), error_summary=row.get("error_summary", ""),
        step_text=row.get("step_text", ""),
    )


def repair_out(row: dict) -> RepairOut:
    return RepairOut(
        id=row["id"], execution_id=row["execution_id"],
        test_case_id=row.get("test_case_id"), case_title=row.get("case_title"),
        module_id=row.get("module_id"), module_name=row.get("module_name"),
        project_id=row.get("project_id"), project_name=row.get("project_name"),
        executed_at=row.get("executed_at") or "",
        execution_status=row.get("execution_status") or "",
        functional_status=row.get("functional_status") or "",
        cause_category=row.get("cause_category", ""),
        cause_label=_dt.LABELS.get(row.get("cause_category", ""), ""),
        defect_origin=row.get("defect_origin", ""),
        confirmation_status=row.get("confirmation_status", ""),
        failure_signature=row.get("failure_signature", ""),
        human_verdict=row.get("human_verdict", ""),
        human_origin=row.get("human_origin", ""),
        human_comment=row.get("human_comment", ""),
        confirmed_by=row.get("confirmed_by"), confirmed_at=row.get("confirmed_at"),
    )
