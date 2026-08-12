"""Routes des cas de test : liste, détail (Gherkin + versions + relectures + exécutions),
déclenchement d'exécution, et action de relecture (gate actionnable depuis l'UI)."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response

from testpilot import config
from testpilot.api import erreurs, access, schemas
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


_CURSEUR_SEP = ":"


def _decoder_curseur(curseur: str | None) -> tuple | None:
    """Le curseur opaque redevient le triplet de tri. Un curseur illisible est traité comme
    ABSENT plutôt que comme une erreur : on repart du début, ce qui est visible et récupérable —
    là où un 422 laisserait l'écran bloqué sur une liste vide."""
    if not curseur:
        return None
    try:
        a, b, c = curseur.split(_CURSEUR_SEP)
        return int(a), int(b), int(c)
    except (ValueError, AttributeError):
        return None


@router.get("", response_model=schemas.PageCas)
def list_cases(project_id: int | None = None, module_id: int | None = None,
               group_id: int | None = None, q: str = "", statut: str = "",
               cursor: str | None = None, limit: int = 100, conn=Depends(get_conn)):
    """Les cas, PAGE PAR PAGE.

    ⚠️ Cette route rendait auparavant **tous** les cas du projet. À la cible du produit (de
    l'ordre du millier), c'était une réponse de plusieurs mégaoctets à chaque affichage — et un
    navigateur qui rame sur une liste que personne ne lit en entier.

    Recherche (`q`) et filtre (`statut`) sont traités **ici** : appliqués côté navigateur, ils ne
    porteraient que sur la page chargée, et chercher un cas absent de celle-ci répondrait
    « aucun résultat ». Un filtre qui ment sur l'absence est pire que pas de filtre.
    """
    limite = max(1, min(limit, 500))
    lignes, suivant, total = CaseRepo(conn).page(
        project_id=project_id, module_id=module_id, group_id=group_id,
        recherche=q, statut=statut, apres=_decoder_curseur(cursor), limite=limite)
    return schemas.PageCas(
        items=[schemas.case_summary(r) for r in lignes],
        next_cursor=_CURSEUR_SEP.join(str(x) for x in suivant) if suivant else None,
        total=total)


# ── Actions en LOT (lot C, 2026-07-24) ───────────────────────────────────────────────────────
# ⚠️ Ces routes sont déclarées AVANT `/{case_id}` : sinon FastAPI ferait correspondre « lot » au
# paramètre `case_id`, la conversion en entier échouerait, et l'écran recevrait une erreur de
# validation incompréhensible au lieu de son action.

_LOT_MAX = 500


def _ids_valides(case_ids: list[int]) -> list[int]:
    """Dédoublonne, borne, et refuse une demande vide.

    La borne n'est pas décorative : une requête sans limite deviendrait, sur un référentiel de
    plusieurs milliers de cas, une transaction longue qui bloque la base pour tout le monde.
    """
    uniques = list(dict.fromkeys(case_ids))
    if not uniques:
        raise erreurs.ErreurMetier("requete_invalide", "aucun cas sélectionné")
    if len(uniques) > _LOT_MAX:
        raise erreurs.ErreurMetier(
            "requete_invalide",
            f"{len(uniques)} cas sélectionnés — le maximum est {_LOT_MAX} par action")
    return uniques


def _acces_suffisant(conn, request: Request, project_id: int | None) -> bool:
    """Un accès EFFECTIF au moins Testeur sur le projet du cas (2026-08-11) — un cas dont le
    projet vient de passer en `no_access`, ou d'être forcé sous Testeur, doit être ignoré du lot
    EXACTEMENT comme un cas disparu entre l'affichage et le clic : jamais un 403 qui laisserait
    échouer les 19 autres pour un seul cas devenu inaccessible entre-temps, jamais une fuite sur
    quel projet le cas appartient.

    `project_id=None` (un cas SANS module — « hors arbre », voir `CaseRepo.create`) est TOUJOURS
    accessible : rien ne le rattache à un projet, donc rien à quoi comparer un rôle effectif.
    Même correctif que `access.require_project_access_depuis` (trouvé en vérifiant la suite
    complète : un cas de test créé sans module se voyait exclu du lot à tort)."""
    utilisateur = getattr(request.state, "user", None)
    if utilisateur is None:
        return False
    if project_id is None:
        return True
    role = access.role_effectif_projet(conn, utilisateur, project_id)
    return access.role_suffisant(role, access.ROLE_TESTEUR)


@router.patch("/lot", response_model=schemas.LotOut)
def priorite_en_lot(body: schemas.LotPrioriteIn, request: Request, conn=Depends(get_conn)):
    """Change la priorité de N cas en UNE requête.

    ⚠️ **Les cas introuvables OU DEVENUS INACCESSIBLES sont IGNORÉS, pas fatals** — et comptés à
    part. Entre l'affichage de la liste et le clic, un cas a pu être supprimé par quelqu'un
    d'autre, ou son projet passé hors d'accès : refuser toute l'action pour un élément disparu
    ferait perdre les 19 autres. Le compte rendu dit ce qui s'est réellement passé.
    """
    if body.priority not in ("low", "medium", "high"):
        raise erreurs.ErreurMetier("requete_invalide", "priorité invalide (low | medium | high)")
    cases = CaseRepo(conn)
    traites = 0
    for cid in _ids_valides(body.case_ids):
        cas = cases.get(cid)
        if cas is None or not _acces_suffisant(conn, request, cas.get("project_id")):
            continue
        cases.set_priority(cid, body.priority)
        traites += 1
    return schemas.LotOut(traites=traites, ignores=len(set(body.case_ids)) - traites)


@router.post("/lot/suppression", response_model=schemas.LotOut)
def supprimer_en_lot(body: schemas.LotCasIn, request: Request, conn=Depends(get_conn)):
    """Met N cas à la corbeille en UNE requête. Rien n'est détruit (§7) — tout est restaurable."""
    cases = CaseRepo(conn)
    par = access.utilisateur_de(request)
    traites = 0
    for cid in _ids_valides(body.case_ids):
        cas = cases.get(cid)
        if cas is None or not _acces_suffisant(conn, request, cas.get("project_id")):
            continue
        cases.delete(cid, par=par)
        traites += 1
    return schemas.LotOut(traites=traites, ignores=len(set(body.case_ids)) - traites)


@router.post("/{case_id}/automate", response_model=schemas.GenerationJobOut, status_code=202,
            dependencies=[Depends(access.require_project_access_depuis(
                "case_id", access.project_id_depuis_case))])
def automate_case(case_id: int, background: BackgroundTasks, request: Request,
                  conn=Depends(get_conn)):
    """AUTOMATISER un cas manuel : générer son test technique DEPUIS son métier (décision `0022`
    n°6). L'IA lit le titre/préconditions/étapes/résultat déjà saisis et écrit le Gherkin.

    Tâche de fond (LLM, quelques minutes), suivie via `GET /api/modules/jobs/{id}` — comme la
    génération. Le front ne propose ce bouton que pour un cas SANS test technique.
    """
    # ⚠️ Résolu SYNCHRONE, avant `background.add_task` (migration 32) — une fois en tâche de
    # fond, il n'y a plus de `Request` à lire.
    try:
        job_id, params = generation_service.start_automation(
            conn, case_id, author=access.utilisateur_de(request))
    except generation_service.GenerationError as err:
        raise erreurs.depuis_service(err.code, err.detail)
    background.add_task(generation_service.run_automation, job_id, **params)
    return schemas.GenerationJobOut(job_id=job_id, status="running")


@router.delete("/{case_id}", status_code=204,
              dependencies=[Depends(access.require_project_access_depuis(
                  "case_id", access.project_id_depuis_case))])
def delete_case(case_id: int, request: Request, conn=Depends(get_conn)):
    """Supprime un cas et toute sa descendance (versions, exécutions, résultats, coûts).

    Sur demande explicite de l'utilisateur (§2.10 interdit d'effacer un run *en silence*, pas de
    l'effacer quand on le demande). L'écran confirme d'abord.
    """
    if CaseRepo(conn).get(case_id) is None:
        raise HTTPException(status_code=404, detail=f"cas {case_id} introuvable")
    CaseRepo(conn).delete(case_id, par=access.utilisateur_de(request))
    return Response(status_code=204)


@router.post("/{case_id}/deplacer", response_model=schemas.CaseMoveOut,
            dependencies=[Depends(access.require_project_access_depuis(
                "case_id", access.project_id_depuis_case))])
def deplacer_case(case_id: int, body: schemas.CaseMoveIn, conn=Depends(get_conn)):
    """Déplace un cas vers une autre Section — même `id`, aucun historique touché
    (étape 2, migration 28)."""
    try:
        CaseRepo(conn).deplacer(case_id, body.group_id)
    # ⚠️ `DuplicateName` hérite de `ValueError` — ce `except` DOIT rester avant le générique,
    # sinon il est avalé par lui et une collision de titre rend 404 au lieu de 409 (mesuré).
    except DuplicateName as exc:
        raise erreurs.ErreurMetier("nom_deja_pris", str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return schemas.CaseMoveOut(id=case_id)


@router.post("/{case_id}/copier", response_model=schemas.CaseMoveOut, status_code=201,
            dependencies=[Depends(access.require_project_access_depuis(
                "case_id", access.project_id_depuis_case))])
def copier_case(case_id: int, body: schemas.CaseMoveIn, request: Request, conn=Depends(get_conn)):
    """Copie un cas dans une autre Section — un cas RÉELLEMENT NEUF, sans historique partagé
    (étape 2, migration 28)."""
    try:
        nouveau_id = CaseRepo(conn).copier(case_id, body.group_id,
                                           author=access.utilisateur_de(request))
    # ⚠️ `DuplicateName` hérite de `ValueError` — voir la note dans `deplacer_case` ci-dessus.
    except DuplicateName as exc:
        raise erreurs.ErreurMetier("nom_deja_pris", str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return schemas.CaseMoveOut(id=nouveau_id)


@router.get("/{case_id}", response_model=schemas.CaseDetail,
           dependencies=[Depends(access.require_project_access_depuis(
               "case_id", access.project_id_depuis_case))])
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


# Les trois métadonnées de lecture et leur vocabulaire — déclarés UNE fois, ici, plutôt que
# répétés dans autant de `if` qu'il y a de champs (c'était le cas avec la seule priorité, et ça
# se serait dupliqué à chaque champ ajouté).
_VOCABULAIRES = {
    "priority": schemas.PRIORITES_CAS,
    "type": schemas.TYPES_CAS,
    "etat": schemas.ETATS_CAS,
}


@router.patch("/{case_id}", response_model=schemas.CaseSummary,
             dependencies=[Depends(access.require_project_access_depuis(
                 "case_id", access.project_id_depuis_case))])
def update_case(case_id: int, body: schemas.CasePatch, conn=Depends(get_conn)):
    """Met à jour les métadonnées de LECTURE d'un cas : priorité, Type, État.

    ⚠️ **Modifier l'État n'a AUCUN effet de bord** : ce n'est pas un statut dérivé, et rien ne
    le remettra à zéro derrière l'utilisateur (arbitré le 2026-08-04). Aucun de ces trois champs
    ne crée de version — ils ne changent pas ce que le test vérifie.
    """
    cases = CaseRepo(conn)
    if cases.get(case_id) is None:
        raise HTTPException(status_code=404, detail=f"cas {case_id} introuvable")

    champs = {nom: valeur for nom, valeur in
              (("priority", body.priority), ("type", body.type), ("etat", body.etat))
              if valeur is not None}
    for nom, valeur in champs.items():
        if valeur not in _VOCABULAIRES[nom]:
            raise HTTPException(
                status_code=422,
                detail=f"{nom} invalide ({' | '.join(_VOCABULAIRES[nom])})")
    if champs:
        cases.set_metadonnees(case_id, **champs)
    return schemas.case_summary(cases.get(case_id))


@router.patch("/{case_id}/metier", response_model=schemas.CaseMetierOut,
             dependencies=[Depends(access.require_project_access_depuis(
                 "case_id", access.project_id_depuis_case))])
def update_case_metier(case_id: int, body: schemas.CaseMetierIn, conn=Depends(get_conn)):
    """Édite le contenu MÉTIER d'un cas. Un champ versionné modifié → **nouvelle version**.

    Le contenu technique (Gherkin) est recopié tel quel : éditer le métier ne régénère rien
    (décision `0022` n°6). ⚠️ **Amendement §4.3 (2026-07-21)** : éditer et enregistrer le métier
    VAUT relecture — la nouvelle version est donc approuvée automatiquement (tracé), et non plus
    laissée « à relire ». Plus de gate humain séparé sur le Gherkin.
    """
    cases = CaseRepo(conn)
    if cases.get(case_id) is None:
        raise HTTPException(status_code=404, detail=f"cas {case_id} introuvable")
    try:
        version_id = cases.update_metier(
            case_id, title=body.title, preconditions=body.preconditions,
            test_steps=body.test_steps, expected_result=body.expected_result,
            refs=body.refs, estimate=body.estimate, editor=body.editor)
    except DuplicateName as exc:
        raise erreurs.ErreurMetier("nom_deja_pris", str(exc)) from exc
    if version_id is not None:
        review_gate.auto_approve_metier(ReviewRepo(conn), case_id=case_id, version_id=version_id,
                                        repair_budget=config.REPAIR_BUDGET_DEFAULT)
    return schemas.CaseMetierOut(case=schemas.case_summary(cases.get(case_id)),
                                 version_id=version_id, version_created=version_id is not None)


@router.patch("/{case_id}/script", response_model=schemas.CaseMetierOut,
             dependencies=[Depends(access.require_role(access.ROLE_DEV)),
                          Depends(access.require_project_access_depuis(
                              "case_id", access.project_id_depuis_case))])
def update_case_script(case_id: int, body: schemas.ScriptEditIn, conn=Depends(get_conn)):
    """Édite DIRECTEMENT le Gherkin/Python généré — réservé au rôle Dev.

    Pas d'auto-approbation (contrairement à `/metier`) : voir `CaseRepo.update_script`.
    """
    cases = CaseRepo(conn)
    if cases.get(case_id) is None:
        raise HTTPException(status_code=404, detail=f"cas {case_id} introuvable")
    version_id = cases.update_script(case_id, feature_content=body.feature_content,
                                     steps_content=body.steps_content, editor=body.editor)
    return schemas.CaseMetierOut(case=schemas.case_summary(cases.get(case_id)),
                                 version_id=version_id, version_created=version_id is not None)


@router.get("/{case_id}/scenarios", response_model=list[schemas.ScenarioResultOut],
           dependencies=[Depends(access.require_project_access_depuis(
               "case_id", access.project_id_depuis_case))])
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


@router.post("/{case_id}/runs", response_model=schemas.RunResponse, status_code=202,
            dependencies=[Depends(access.require_project_access_depuis(
                "case_id", access.project_id_depuis_case))])
def start_run(case_id: int, background: BackgroundTasks, request: Request, conn=Depends(get_conn)):
    # ⚠️ Résolu SYNCHRONE, avant `background.add_task` (migration 32) — même moment que pour
    # `author` dans `add_case` : une fois en tâche de fond, il n'y a plus de `Request` à lire.
    triggered_by = access.utilisateur_de(request)
    try:
        eid, module, cid, vid = run_service.trigger_run(conn, case_id, triggered_by=triggered_by)
    except run_service.RunError as err:
        # Le code du service TRAVERSE la frontière HTTP (lot B) : le client teste `code`,
        # jamais la phrase française de `detail`.
        raise erreurs.depuis_service(err.code, err.detail)
    background.add_task(run_service.run_execution, eid, module, cid, vid,
                        triggered_by=triggered_by)
    return schemas.RunResponse(execution_id=eid, status="running")


@router.post("/{case_id}/review", response_model=schemas.ReviewResponse,
            dependencies=[Depends(access.require_project_access_depuis(
                "case_id", access.project_id_depuis_case))])
def submit_review(case_id: int, body: schemas.ReviewIn, request: Request,
                  conn=Depends(get_conn)):
    case = CaseRepo(conn).get(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"cas {case_id} introuvable")
    version_id = case.get("current_version_id")
    if not version_id:
        raise HTTPException(status_code=409, detail="aucune version à relire pour ce cas")

    decision = run_service.submit_review(
        conn, case_id, version_id, approved=body.approved,
        # Une relecture signée « ui » ne dit pas qui a relu. Le nom de session prime (2026-07-24).
        reviewer=access.utilisateur_de(request) or body.reviewer,
        comment=body.comment, repair_budget=body.repair_budget)
    # ⚠️ Un rejet ne touche PLUS au cas : la décision vit sur la VERSION (`review_decision`),
    # c'est elle que le gate consulte. Le statut recopié sur le cas était une seconde réponse à
    # la même question — et l'État, lui, appartient à l'humain (migration 25).
    budget = ReviewRepo(conn).repair_budget_for_version(version_id)
    return schemas.ReviewResponse(
        decision="approved" if body.approved else "rejected",
        repair_budget=budget,
        gate=schemas.GateOut(allowed=decision.allowed, needs_review=decision.needs_review,
                             reason=decision.reason, repair_budget=budget,
                             repair_budget_default=config.REPAIR_BUDGET_DEFAULT),
    )
