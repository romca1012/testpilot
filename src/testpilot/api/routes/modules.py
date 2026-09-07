"""Routes du module : détail (fil d'Ariane) et ajout d'un cas à partir d'une SPEC.

« Ajouter un cas » déclenche le flux spec → analyse → génération → gate (décision 0006) :
on ne crée jamais un cas sans version ni Gherkin. La génération étant longue et coûteuse,
elle tourne en tâche de fond (202 + polling du job), comme les exécutions.
"""

from __future__ import annotations

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Request,
    Response,
    UploadFile,
)

from testpilot import config
from testpilot.analysis import spec_analyzer
from testpilot.api import access, erreurs, schemas
from testpilot.api.deps import get_conn
from testpilot.api.services import events_bus, generation_service, spec_extract
from testpilot.guardrails import concurrency, durable_jobs
from testpilot.store.repositories import (
    CaseGroupRepo,
    CaseRepo,
    DuplicateName,
    ModuleRepo,
    ProfondeurInvalide,
    ProjectRepo,
)

router = APIRouter(prefix="/api/modules", tags=["modules"])

@router.get("/{module_id}", response_model=schemas.ModuleDetail,
           dependencies=[Depends(access.require_project_access_depuis(
               "module_id", access.project_id_depuis_module))])
def get_module(module_id: int, conn=Depends(get_conn)):
    module = ModuleRepo(conn).get(module_id)
    if module is None:
        raise HTTPException(status_code=404, detail=f"module {module_id} introuvable")
    project = ProjectRepo(conn).get(module["project_id"])
    return schemas.ModuleDetail(
        module=schemas.module_summary(module | {"case_count": _case_count(conn, module_id)}),
        project=schemas.ProjectRef(id=project["id"], name=project["name"]),
    )


def _case_count(conn, module_id: int) -> int:
    return conn.execute("SELECT COUNT(*) AS n FROM test_case WHERE module_id=?",
                        (module_id,)).fetchone()["n"]


@router.post("/{module_id}/groups", response_model=schemas.GroupDetail, status_code=201,
            dependencies=[Depends(access.require_project_access_depuis(
                "module_id", access.project_id_depuis_module))])
def create_group(module_id: int, body: schemas.GroupIn, conn=Depends(get_conn)):
    """Crée une Spécification — un DOCUMENT nommé, et rien d'autre.

    ⚠️ Ne génère AUCUN cas et ne dépense RIEN : c'est la génération qui lira ce document,
    après que l'humain aura confirmé ce qu'il veut couvrir (§4bis du brief).
    Créer une spécification ne doit pas engager une dépense non demandée — même raison que le
    lancement explicite d'un run (`0022` n°8.c.1).

    Le document peut être vide à la création : on nomme la spécification d'abord, on la rédige
    ensuite. C'est la GÉNÉRATION qui exigera un document non vide, pas le conteneur.

    `body.parent_group_id` (migration 28) : crée une SOUS-section sous une Section existante.
    """
    if ModuleRepo(conn).get(module_id) is None:
        raise HTTPException(status_code=404, detail=f"module {module_id} introuvable")
    if not body.title.strip():
        raise HTTPException(status_code=422, detail="le titre de la spécification est requis")
    try:
        gid = CaseGroupRepo(conn).create(module_id=module_id, title=body.title.strip(),
                                         description=body.description,
                                         parent_group_id=body.parent_group_id)
    except DuplicateName as exc:
        raise erreurs.ErreurMetier("nom_deja_pris", str(exc)) from exc
    except ProfondeurInvalide as exc:
        raise erreurs.ErreurMetier("profondeur_invalide", str(exc)) from exc
    # Le document passe par `update()` : c'est LUI qui calcule `spec_hash`, en un seul endroit.
    if body.spec_content:
        CaseGroupRepo(conn).update(gid, spec_content=body.spec_content)
    return schemas.group_detail(CaseGroupRepo(conn).get(gid) | {"case_count": 0})


@router.patch("/{module_id}", response_model=schemas.ModuleSummary,
             dependencies=[Depends(access.require_project_access_depuis(
                 "module_id", access.project_id_depuis_module))])
def rename_module(module_id: int, body: schemas.ModuleIn, conn=Depends(get_conn)):
    """Renomme un module (« Éditer la section »). Nom unique par projet (409 sinon)."""
    module = ModuleRepo(conn).get(module_id)
    if module is None:
        raise HTTPException(status_code=404, detail=f"module {module_id} introuvable")
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="le nom du module est requis")
    try:
        ModuleRepo(conn).rename(module_id, name=body.name.strip(), description=body.description)
    except DuplicateName as exc:
        raise erreurs.ErreurMetier("nom_deja_pris", str(exc)) from exc
    updated = ModuleRepo(conn).get(module_id)
    return schemas.module_summary(updated | {"case_count": _case_count(conn, module_id)})


@router.delete("/{module_id}", status_code=204,
              dependencies=[Depends(access.require_project_role_depuis(
                  "module_id", access.project_id_depuis_module, access.ROLE_ADMIN))])
def delete_module(module_id: int, request: Request, conn=Depends(get_conn)):
    """Supprime un module et TOUTE sa descendance (spécifications, cas, versions, exécutions…).

    Cascade sur demande explicite (l'écran confirme en montrant ce qui partira). §2.10 interdit
    d'effacer un run *en silence*, pas sur une action claire de l'utilisateur.
    """
    if ModuleRepo(conn).get(module_id) is None:
        raise HTTPException(status_code=404, detail=f"module {module_id} introuvable")
    ModuleRepo(conn).delete(module_id, par=access.utilisateur_de(request))
    return Response(status_code=204)


@router.post("/{module_id}/cases/manual", response_model=schemas.CaseSummary, status_code=201,
            dependencies=[Depends(access.require_project_access_depuis(
                "module_id", access.project_id_depuis_module))])
def create_manual_case(module_id: int, body: schemas.ManualCaseIn, request: Request,
                       conn=Depends(get_conn)):
    """Crée un cas À LA MAIN — le bouton « Ajouter un cas de test », SANS IA (décision `0022`).

    Le cas naît avec son document métier (titre, préconditions, étapes, résultat attendu) mais
    sans Gherkin : il n'est pas exécutable tant qu'un test technique n'a pas été généré. C'est
    l'inverse du bouton « Générer », qui lance l'IA.
    """
    if ModuleRepo(conn).get(module_id) is None:
        raise HTTPException(status_code=404, detail=f"module {module_id} introuvable")
    steps = [s.strip() for s in body.test_steps if s.strip()]
    if not (body.title.strip() and steps and body.expected_result.strip()):
        raise HTTPException(status_code=422,
                            detail="titre, étapes et résultat attendu sont obligatoires")
    import json
    try:
        cid = CaseRepo(conn).create_manual(
            module_id=module_id, title=body.title.strip(),
            preconditions=body.preconditions, test_steps=json.dumps(steps, ensure_ascii=False),
            expected_result=body.expected_result.strip(),
            author=access.utilisateur_de(request) or "ui")
    except DuplicateName as exc:
        raise erreurs.ErreurMetier("nom_deja_pris", str(exc)) from exc
    nouveau_cas = CaseRepo(conn).get(cid)
    projet_id = nouveau_cas.get("project_id") if nouveau_cas else None
    if projet_id is not None:
        events_bus.publier(projet_id, {"kind": "case_created", "case_id": cid})
    return schemas.case_summary(nouveau_cas)


@router.post("/{module_id}/cases/extract", response_model=schemas.SpecExtractOut,
            dependencies=[Depends(access.require_project_access_depuis(
                "module_id", access.project_id_depuis_module))])
async def extract_spec(module_id: int, file: UploadFile = File(...), conn=Depends(get_conn)):
    """Extrait le TEXTE d'un fichier téléversé (.txt/.md/.docx/.pdf) pour pré-remplir la
    génération, et conserve l'ORIGINAL sur disque pour une version plus évoluée.

    On ne devine pas le format à l'extension seule : `spec_extract` lève une erreur claire pour
    un type non géré, ou pour un PDF sans texte extractible — jamais un texte vide silencieux.
    La lecture est bornée (`SPEC_MAX_BYTES`) et vérifiée PENDANT la lecture, comme les pièces
    jointes d'un résultat : un envoi qui ment sur sa taille n'est jamais chargé en entier.
    """
    if ModuleRepo(conn).get(module_id) is None:
        raise HTTPException(status_code=404, detail=f"module {module_id} introuvable")
    data = await spec_extract.lire_borne(file, config.SPEC_MAX_BYTES)
    try:
        text = spec_extract.extract_text(file.filename or "", data)
    except spec_extract.UnsupportedFormat as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not text.strip():
        raise HTTPException(status_code=422,
                            detail="le fichier ne contient aucun texte exploitable")
    # Le fichier original, adressé par le hash du texte qu'il a produit — pas par son nom, qui
    # peut se répéter d'un téléversement à l'autre sans désigner le même document.
    spec_extract.conserver_original(spec_analyzer.spec_hash(text), file.filename or "", data)
    return schemas.SpecExtractOut(text=text, filename=file.filename or "")


@router.put("/{module_id}/cases/order", response_model=list[schemas.CaseSummary],
           dependencies=[Depends(access.require_project_access_depuis(
               "module_id", access.project_id_depuis_module))])
def reorder_cases(module_id: int, body: schemas.ReorderCasesIn, conn=Depends(get_conn)):
    """Fixe l'ordre d'AFFICHAGE des cas du module (décision 0009).

    ⚠️ Ordre de LECTURE, jamais d'exécution : celle-ci suit l'ordre des scénarios du `.feature`.
    Cet endpoint n'écrit que `position`, lu par le seul affichage.

    En LOT et transactionnel : un glissement change N positions ; N appels laisseraient un ordre
    incohérent si l'un échouait. La liste doit décrire exactement les cas du module (409 sinon) —
    une liste partielle laisserait des cas à une position périmée.
    """
    if ModuleRepo(conn).get(module_id) is None:
        raise HTTPException(status_code=404, detail=f"module {module_id} introuvable")
    try:
        CaseRepo(conn).reorder(module_id, body.case_ids)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return [schemas.case_summary(r) for r in CaseRepo(conn).list_all(module_id=module_id)]


@router.post("/{module_id}/cases", response_model=schemas.GenerationJobOut, status_code=202,
            dependencies=[Depends(access.require_project_role_depuis(
                "module_id", access.project_id_depuis_module, access.ROLE_DEV))])
def add_case(module_id: int, body: schemas.AddCaseIn, background: BackgroundTasks,
             request: Request, conn=Depends(get_conn)):
    spec = body.spec_content

    try:
        # Le nom saisi à l'ouverture de session l'emporte sur le « ui » par défaut : sur un
        # serveur partagé, « qui a créé ce cas ? » doit avoir une réponse (2026-07-24).
        job_id, params = generation_service.start_generation(
            conn, module_id, spec_content=spec, title=body.title,
            author=access.utilisateur_de(request) or body.author, group_id=body.group_id)
    except generation_service.GenerationError as err:
        raise erreurs.depuis_service(err.code, err.detail)

    # Plafonné (guardrails/concurrency.py) : la tâche de fond attend son tour dans la file
    # partagée avant de lancer réellement la génération (appels LLM) — le 202 répond, lui, tout
    # de suite.
    durable_jobs.submit(conn, background, kind="generation", args=[job_id], kwargs=params,
                        queue_label=f"generation:{job_id}")
    return schemas.GenerationJobOut(job_id=job_id, status="running")


@router.get("/jobs/queue/status", response_model=schemas.ConcurrencyQueueOut)
def get_queue_status():
    """État courant du plafond de tâches de fond PARTAGÉ (génération, exécution, exploration —
    `guardrails/concurrency.py`) : pas seulement la génération, malgré le préfixe `/modules/jobs`
    — c'est l'endpoint « job » déjà existant le plus proche, étendu plutôt que dupliqué (aucun
    autre écran de suivi de job n'existe aujourd'hui pour y accrocher cette visibilité).
    Placé AVANT `/jobs/{job_id}` : chemins à 3 segments, aucune ambiguïté de routage, mais l'ordre
    de lecture suit la logique « vue d'ensemble avant le détail d'un job ».
    """
    status = concurrency.get_queue().status()
    return schemas.ConcurrencyQueueOut(max_concurrent=status.max_concurrent,
                                       running=status.running, waiting=status.waiting)


@router.get("/jobs/{job_id}", response_model=schemas.GenerationJobOut,
           dependencies=[Depends(access.require_project_access_depuis(
               "job_id", access.project_id_depuis_job))])
def get_job(job_id: str, conn=Depends(get_conn)):
    """⚠️ Le job est lu EN BASE (migration 29, 2026-08-07) — jamais un dict en mémoire, qui
    disparaissait d'un coup si le serveur redémarrait pendant une génération en cours. Un job
    "running" resté bloqué trop longtemps est automatiquement réinterprété en échec
    (`GenerationJobRepo.get`), avec un message qui le dit clairement plutôt qu'un blocage muet."""
    job = generation_service.get_job(conn, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job introuvable")
    cases = job.get("cases") if job["status"] == "awaiting_metier" else None
    return schemas.GenerationJobOut(
        job_id=job_id, status=job["status"], case_ids=job.get("case_ids") or [],
        error=job["error"],
        cases=[schemas.MetierDraftOut(**c) for c in cases] if cases else None)


@router.post("/jobs/{job_id}/metier", response_model=schemas.GenerationJobOut, status_code=202,
            dependencies=[Depends(access.require_project_role_depuis(
                "job_id", access.project_id_depuis_job, access.ROLE_DEV))])
def validate_metier(job_id: str, body: schemas.MetierValidationIn, background: BackgroundTasks,
                    conn=Depends(get_conn)):
    """PASSE 4b — l'humain valide (ou corrige, ou réduit) l'ensemble des cas proposés, chacun avec
    la Section qu'il a choisie (ou aucune) ; le Gherkin de chaque cas retenu est alors écrit.

    C'est le point de reprise de la pause voulue par `0022` n°5, étendue au §9, puis mise à plat
    à l'étape 3 (2026-08-07) : le technique n'est payé qu'après qu'un humain a signé l'intention.
    Le corps de la requête FAIT FOI — si le relecteur a réécrit des étapes, supprimé un cas ou
    changé sa Section, c'est ce qu'il a validé qui part à la génération, pas la proposition de
    l'IA.
    """
    try:
        cases = [c.model_dump() for c in body.cases]
        params = generation_service.validate_metier(conn, job_id, cases)
    except generation_service.GenerationError as err:
        raise erreurs.depuis_service(err.code, err.detail)

    # Même `job_id` que `start_generation` : la position dans la file reprend l'identité du job,
    # pas une nouvelle file par appel (guardrails/concurrency.py).
    durable_jobs.submit(conn, background, kind="generation_resume", args=[job_id], kwargs=params,
                        queue_label=f"generation:{job_id}")
    return schemas.GenerationJobOut(job_id=job_id, status="running")
