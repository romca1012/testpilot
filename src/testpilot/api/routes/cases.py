"""Routes des cas de test : liste, détail (Gherkin + versions + relectures + exécutions),
déclenchement d'exécution, et action de relecture (gate actionnable depuis l'UI)."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response

from testpilot import config
from testpilot.api import schemas
from testpilot.api.deps import get_conn
from testpilot.api.services import generation_service, run_service
from testpilot.generation import assertion_lint, domain_model, repair_diff, smoke_check
from testpilot.store.repositories import (
    CaseRepo,
    DuplicateName,
    ExecutionRepo,
    ProjectRepo,
    ReviewRepo,
    VersionRepo,
)
from testpilot.verdict import review_gate

router = APIRouter(prefix="/api/cases", tags=["cases"])

_RUN_ERROR_STATUS = {"not_found": 404, "no_version": 409, "needs_review": 409}

# Auteur des versions produites par la boucle de réparation (0014). Une version signée ainsi a
# forcément un « avant » : celle qu'elle tentait de corriger.
_AUTEUR_REPARATION = "repair-agent"


def _lint_reparation(current: dict | None, version_rows: list[dict]) -> list[dict]:
    """Rayon d'explosion d'une réparation, comparé à la version qui la précède (0017).

    Rend une liste vide dès que la comparaison n'aurait pas de sens — première version, version
    écrite par la génération ou par un humain, ou prédécesseur introuvable. **Signaler dans ces
    cas-là serait une alerte inventée**, aussi nuisible qu'une alerte tue.
    """
    if not current or current.get("created_by") != _AUTEUR_REPARATION:
        return []
    precedentes = [v for v in version_rows if v["id"] < current["id"]]
    if not precedentes:
        return []
    avant = max(precedentes, key=lambda v: v["id"])
    return repair_diff.blast_radius(avant.get("steps_content") or "",
                                    current.get("steps_content") or "")


def _smoke_check_domaine(conn, case: dict, current: dict | None) -> list[dict]:
    """Le Gherkin référence-t-il des champs/valeurs qui existent ? (étape 4 du chantier `0021`).

    Le modèle vit **par connecteur** (`data/domain/odoo.json`) : le domaine d'Odoo n'est pas celui
    du prochain ERP (§8 — architecture multi-connecteurs dès le départ).

    Rend `[]` dès qu'il n'y a rien à comparer — pas de version, pas de projet, pas de modèle.
    ⚠️ **Ce silence ne vaut pas validation** : il signifie « je n'ai pas regardé », pas « c'est
    bon ». Le distinguer d'un vrai « rien à signaler » demanderait de le dire au relecteur — ce
    que le bandeau ne fait pas encore, et c'est une limite assumée de cette étape.

    Best-effort : un modèle absent ou illisible ne doit **jamais** casser l'affichage d'un cas —
    ce module informe, il ne gouverne rien.
    """
    if not current or not case.get("project_id"):
        return []
    projet = ProjectRepo(conn).get(case["project_id"])
    if not projet:
        return []
    # L'annuaire est propre au PROJET (son instance), plus au type de connecteur.
    modele = domain_model.charger_modele(projet)
    if not modele:
        return []
    return smoke_check.smoke_check(current.get("feature_content") or "",
                                   current.get("steps_content") or "", modele=modele)


@router.get("", response_model=list[schemas.CaseSummary])
def list_cases(project_id: int | None = None, module_id: int | None = None, conn=Depends(get_conn)):
    rows = CaseRepo(conn).list_all(project_id=project_id, module_id=module_id)
    return [schemas.case_summary(r) for r in rows]


@router.post("/{case_id}/automate", response_model=schemas.GenerationJobOut, status_code=202)
def automate_case(case_id: int, background: BackgroundTasks, conn=Depends(get_conn)):
    """AUTOMATISER un cas manuel : générer son test technique DEPUIS son métier (décision `0022`
    n°6). L'IA lit le titre/préconditions/étapes/résultat déjà saisis et écrit le Gherkin.

    Tâche de fond (LLM, quelques minutes), suivie via `GET /api/modules/jobs/{id}` — comme la
    génération. Le front ne propose ce bouton que pour un cas SANS test technique.
    """
    try:
        job_id, params = generation_service.start_automation(conn, case_id)
    except generation_service.GenerationError as err:
        code = {"not_found": 404, "invalid_metier": 422}.get(err.code, 400)
        raise HTTPException(status_code=code, detail=err.detail)
    background.add_task(generation_service.run_automation, job_id, **params)
    return schemas.GenerationJobOut(job_id=job_id, status="running")


@router.delete("/{case_id}", status_code=204)
def delete_case(case_id: int, conn=Depends(get_conn)):
    """Supprime un cas et toute sa descendance (versions, exécutions, résultats, coûts).

    Sur demande explicite de l'utilisateur (§2.10 interdit d'effacer un run *en silence*, pas de
    l'effacer quand on le demande). L'écran confirme d'abord.
    """
    if CaseRepo(conn).get(case_id) is None:
        raise HTTPException(status_code=404, detail=f"cas {case_id} introuvable")
    CaseRepo(conn).delete(case_id)
    return Response(status_code=204)


@router.get("/{case_id}", response_model=schemas.CaseDetail)
def get_case(case_id: int, conn=Depends(get_conn)):
    case = CaseRepo(conn).get(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"cas {case_id} introuvable")

    # Fil d'Ariane Projet > Module > Cas.
    project = module = None
    if case.get("project_id"):
        project = schemas.ProjectRef(id=case["project_id"], name=case.get("project_name") or "—")
    if case.get("module_id"):
        module = schemas.ModuleRef(id=case["module_id"], name=case.get("module_name") or "—")

    version_rows = VersionRepo(conn).list_for_case(case_id)
    version_id = case.get("current_version_id")
    gate = None
    if version_id:
        decision = review_gate.evaluate_gate(ReviewRepo(conn), version_id)
        # Lint non-bloquant des assertions de la version courante (décision 0008) : informe le
        # relecteur sans jamais changer `allowed` — le gate reste souverain.
        current = next((v for v in version_rows if v["id"] == version_id), None)
        warnings = assertion_lint.lint_steps(current.get("steps_content", "") if current else "")
        # Rayon d'explosion d'une RÉPARATION (0017) : l'agent réécrit le fichier entier, donc il
        # peut abîmer un step qui marchait — c'est ce qui a coûté deux tentatives au cas 1 le
        # 2026-07-17. Détective, jamais bloquant : `allowed` n'est pas touché. On ne compare que
        # si la version courante vient de l'agent de réparation ; une version écrite par un
        # humain ou par la génération n'a pas de « avant » à quoi se mesurer.
        warnings += _lint_reparation(current, version_rows)
        # Le test référence-t-il des champs/valeurs qui EXISTENT ? (étape 4 du chantier `0021`).
        # Lu dans le modèle du domaine VERSIONNÉ (`data/domain/{connecteur}.json`, crawl
        # déterministe relu par un humain) — aucun LLM, aucune I/O réseau, coût nul.
        # Détective comme les deux précédents : `allowed` n'est jamais touché. Le faux positif est
        # RÉEL (champ apparaissant après interaction, select peuplé en JS, scénario `[ERREUR]` qui
        # vise volontairement un id invalide) — d'où le §6 du brief et la borne du principe 2.
        warnings += _smoke_check_domaine(conn, case, current)
        gate = schemas.GateOut(allowed=decision.allowed, needs_review=decision.needs_review,
                               reason=decision.reason,
                               repair_budget=ReviewRepo(conn).repair_budget_for_version(version_id),
                               repair_budget_default=config.REPAIR_BUDGET_DEFAULT,
                               lint_warnings=[schemas.LintWarning(**w) for w in warnings])
    executions = [
        schemas.execution_summary(r, running=run_service.is_running(r["id"]))
        for r in ExecutionRepo(conn).list_for_case(case_id)
    ]
    return schemas.CaseDetail(
        case=schemas.case_summary(case),
        project=project,
        module=module,
        current_version_id=version_id,
        versions=[schemas.version_out(v) for v in version_rows],
        reviews=[schemas.review_out(r) for r in ReviewRepo(conn).list_for_case(case_id)],
        executions=executions,
        gate=gate,
    )


@router.patch("/{case_id}", response_model=schemas.CaseSummary)
def update_case(case_id: int, body: schemas.CasePatch, conn=Depends(get_conn)):
    """Met à jour la priorité de LECTURE d'un cas (étiquette — aucun ordre d'exécution)."""
    cases = CaseRepo(conn)
    if cases.get(case_id) is None:
        raise HTTPException(status_code=404, detail=f"cas {case_id} introuvable")
    if body.priority not in ("low", "medium", "high"):
        raise HTTPException(status_code=422, detail="priorité invalide (low | medium | high)")
    cases.set_priority(case_id, body.priority)
    return schemas.case_summary(cases.get(case_id))


@router.patch("/{case_id}/metier", response_model=schemas.CaseMetierOut)
def update_case_metier(case_id: int, body: schemas.CaseMetierIn, conn=Depends(get_conn)):
    """Édite le contenu MÉTIER d'un cas. Un champ versionné modifié → **nouvelle version**.

    Le contenu technique (Gherkin) est recopié tel quel : éditer le métier ne régénère rien
    (décision `0022` n°6). Conséquence voulue : la nouvelle version n'étant pas approuvée, le gate
    bloque l'exécution jusqu'à relecture — l'invariant §4.3 s'applique sans règle supplémentaire.
    """
    cases = CaseRepo(conn)
    if cases.get(case_id) is None:
        raise HTTPException(status_code=404, detail=f"cas {case_id} introuvable")
    try:
        version_id = cases.update_metier(
            case_id, title=body.title, preconditions=body.preconditions,
            test_steps=body.test_steps, expected_result=body.expected_result,
            angle=body.angle, refs=body.refs, estimate=body.estimate, editor=body.editor)
    except DuplicateName as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return schemas.CaseMetierOut(case=schemas.case_summary(cases.get(case_id)),
                                 version_id=version_id, version_created=version_id is not None)


@router.get("/{case_id}/scenarios", response_model=list[schemas.ScenarioResultOut])
def get_case_scenarios(case_id: int, conn=Depends(get_conn)):
    """Scénarios du DERNIER run du cas (dépliage) — vide si jamais exécuté.

    Le scénario n'est pas une entité de premier rang : il n'existe qu'au travers d'une
    exécution. On expose donc la granularité fine là où elle existe réellement.
    """
    execs = ExecutionRepo(conn)
    runs = execs.list_for_case(case_id)
    if not runs:
        return []
    last = max(runs, key=lambda r: r["id"])
    return [schemas.scenario_result_out(s) for s in execs.list_scenario_results(last["id"])]


@router.post("/{case_id}/runs", response_model=schemas.RunResponse, status_code=202)
def start_run(case_id: int, background: BackgroundTasks, conn=Depends(get_conn)):
    try:
        eid, module, cid, vid = run_service.trigger_run(conn, case_id)
    except run_service.RunError as err:
        raise HTTPException(status_code=_RUN_ERROR_STATUS.get(err.code, 400), detail=err.detail)
    background.add_task(run_service.run_execution, eid, module, cid, vid)
    return schemas.RunResponse(execution_id=eid, status="running")


@router.post("/{case_id}/review", response_model=schemas.ReviewResponse)
def submit_review(case_id: int, body: schemas.ReviewIn, conn=Depends(get_conn)):
    case = CaseRepo(conn).get(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"cas {case_id} introuvable")
    version_id = case.get("current_version_id")
    if not version_id:
        raise HTTPException(status_code=409, detail="aucune version à relire pour ce cas")

    decision = run_service.submit_review(
        conn, case_id, version_id, approved=body.approved,
        reviewer=body.reviewer, comment=body.comment, repair_budget=body.repair_budget)
    # Un rejet repositionne le cas « à relire » ; l'approbation n'ouvre que le gate.
    if not body.approved:
        CaseRepo(conn).set_validation_status(case_id, "to_review")
    refreshed = CaseRepo(conn).get(case_id)
    budget = ReviewRepo(conn).repair_budget_for_version(version_id)
    return schemas.ReviewResponse(
        decision="approved" if body.approved else "rejected",
        validation_status=refreshed["validation_status"],
        repair_budget=budget,
        gate=schemas.GateOut(allowed=decision.allowed, needs_review=decision.needs_review,
                             reason=decision.reason, repair_budget=budget,
                             repair_budget_default=config.REPAIR_BUDGET_DEFAULT),
    )
