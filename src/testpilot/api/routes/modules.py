"""Routes du module : détail (fil d'Ariane) et ajout d'un cas à partir d'une SPEC.

« Ajouter un cas » déclenche le flux spec → analyse → génération → gate (décision 0006) :
on ne crée jamais un cas sans version ni Gherkin. La génération étant longue et coûteuse,
elle tourne en tâche de fond (202 + polling du job), comme les exécutions.
"""

from __future__ import annotations

from pathlib import Path

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

from testpilot.api import access, schemas
from testpilot.api.deps import get_conn
from testpilot.api.services import generation_service, spec_extract
from testpilot.store.repositories import (
    CaseGroupRepo,
    CaseRepo,
    DuplicateName,
    ModuleRepo,
    ProjectRepo,
)

router = APIRouter(prefix="/api/modules", tags=["modules"])

# 409 pour `duplicate` : la requête est bien formée, c'est l'état du référentiel qui s'y oppose.
_ERROR_STATUS = {"not_found": 404, "invalid_spec": 422, "duplicate": 409,
                 "invalid_metier": 422, "invalid_state": 409, "no_connection": 409}


@router.get("/{module_id}", response_model=schemas.ModuleDetail)
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


@router.get("/{module_id}/groups", response_model=list[schemas.GroupSummary])
def list_groups(module_id: int, conn=Depends(get_conn)):
    """Les spécifications du module — la vue « module = liste de spécifications » (`0022`).

    Volontairement SANS le document (`GroupSummary`) : une liste n'a pas à charger N specs
    complètes. L'écran d'édition le récupère par `GET /api/groups/{id}`.
    """
    if ModuleRepo(conn).get(module_id) is None:
        raise HTTPException(status_code=404, detail=f"module {module_id} introuvable")
    return [schemas.GroupSummary(id=r["id"], module_id=r["module_id"], title=r["title"],
                                 case_count=r.get("case_count", 0))
            for r in CaseGroupRepo(conn).list_for_module(module_id)]


@router.post("/{module_id}/groups", response_model=schemas.GroupDetail, status_code=201)
def create_group(module_id: int, body: schemas.GroupIn, conn=Depends(get_conn)):
    """Crée une Spécification — un DOCUMENT nommé, et rien d'autre.

    ⚠️ Ne génère AUCUN cas et ne dépense RIEN : c'est l'étape 3 (« un angle par appel ») qui
    lira ce document, après que l'humain aura confirmé les angles voulus (§4bis du brief).
    Créer une spécification ne doit pas engager une dépense non demandée — même raison que le
    lancement explicite d'un run (`0022` n°8.c.1).

    Le document peut être vide à la création : on nomme la spécification d'abord, on la rédige
    ensuite. C'est la GÉNÉRATION qui exigera un document non vide, pas le conteneur.
    """
    if ModuleRepo(conn).get(module_id) is None:
        raise HTTPException(status_code=404, detail=f"module {module_id} introuvable")
    if not body.title.strip():
        raise HTTPException(status_code=422, detail="le titre de la spécification est requis")
    try:
        gid = CaseGroupRepo(conn).create(module_id=module_id, title=body.title.strip(),
                                         description=body.description)
    except DuplicateName as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    # Le document passe par `update()` : c'est LUI qui calcule `spec_hash`, en un seul endroit.
    if body.spec_content:
        CaseGroupRepo(conn).update(gid, spec_content=body.spec_content)
    return schemas.group_detail(CaseGroupRepo(conn).get(gid) | {"case_count": 0})


@router.patch("/{module_id}", response_model=schemas.ModuleSummary)
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
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    updated = ModuleRepo(conn).get(module_id)
    return schemas.module_summary(updated | {"case_count": _case_count(conn, module_id)})


@router.delete("/{module_id}", status_code=204)
def delete_module(module_id: int, conn=Depends(get_conn)):
    """Supprime un module et TOUTE sa descendance (spécifications, cas, versions, exécutions…).

    Cascade sur demande explicite (l'écran confirme en montrant ce qui partira). §2.10 interdit
    d'effacer un run *en silence*, pas sur une action claire de l'utilisateur.
    """
    if ModuleRepo(conn).get(module_id) is None:
        raise HTTPException(status_code=404, detail=f"module {module_id} introuvable")
    ModuleRepo(conn).delete(module_id)
    return Response(status_code=204)


@router.post("/{module_id}/cases/manual", response_model=schemas.CaseSummary, status_code=201)
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
            expected_result=body.expected_result.strip(), angle=body.angle,
            author=access.utilisateur_de(request) or "ui")
    except DuplicateName as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return schemas.case_summary(CaseRepo(conn).get(cid))


@router.post("/{module_id}/cases/extract", response_model=schemas.SpecExtractOut)
async def extract_spec(module_id: int, file: UploadFile = File(...), conn=Depends(get_conn)):
    """Extrait le TEXTE d'un fichier téléversé (.txt/.md/.docx) pour pré-remplir la génération.

    On ne devine pas le format à l'extension seule : `spec_extract` lève une erreur claire pour
    un type non géré (PDF nécessiterait une dépendance) — jamais un texte vide silencieux.
    """
    if ModuleRepo(conn).get(module_id) is None:
        raise HTTPException(status_code=404, detail=f"module {module_id} introuvable")
    data = await file.read()
    try:
        text = spec_extract.extract_text(file.filename or "", data)
    except spec_extract.UnsupportedFormat as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not text.strip():
        raise HTTPException(status_code=422,
                            detail="le fichier ne contient aucun texte exploitable")
    return schemas.SpecExtractOut(text=text, filename=file.filename or "")


@router.put("/{module_id}/cases/order", response_model=list[schemas.CaseSummary])
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


@router.post("/{module_id}/cases", response_model=schemas.GenerationJobOut, status_code=202)
def add_case(module_id: int, body: schemas.AddCaseIn, background: BackgroundTasks,
             request: Request, conn=Depends(get_conn)):
    spec = body.spec_content
    if not spec and body.spec_path:
        path = Path(body.spec_path)
        if not path.is_file():
            raise HTTPException(status_code=422, detail=f"spécification introuvable : {path}")
        spec = path.read_text(encoding="utf-8")

    try:
        # Le nom saisi à l'ouverture de session l'emporte sur le « ui » par défaut : sur un
        # serveur partagé, « qui a créé ce cas ? » doit avoir une réponse (2026-07-24).
        job_id, params = generation_service.start_generation(
            conn, module_id, spec_content=spec, title=body.title,
            author=access.utilisateur_de(request) or body.author)
    except generation_service.GenerationError as err:
        raise HTTPException(status_code=_ERROR_STATUS.get(err.code, 400), detail=err.detail)

    background.add_task(generation_service.run_generation, job_id, **params)
    return schemas.GenerationJobOut(job_id=job_id, status="running")


@router.get("/jobs/{job_id}", response_model=schemas.GenerationJobOut)
def get_job(job_id: str):
    job = generation_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job introuvable")
    metier = job.get("metier") if job["status"] == "awaiting_metier" else None
    return schemas.GenerationJobOut(
        job_id=job_id, status=job["status"], case_id=job["case_id"], error=job["error"],
        metier=schemas.MetierDraftOut(**metier) if metier else None)


@router.post("/jobs/{job_id}/metier", response_model=schemas.GenerationJobOut, status_code=202)
def validate_metier(job_id: str, body: schemas.MetierValidationIn, background: BackgroundTasks):
    """PASSE 4b — l'humain valide (ou corrige) le document métier ; le Gherkin est alors écrit.

    C'est le point de reprise de la pause voulue par `0022` n°5 : le technique n'est payé
    qu'après qu'un humain a signé l'intention. Le corps de la requête FAIT FOI — si le relecteur
    a réécrit les étapes, ce sont les siennes qui partent à la génération, pas celles de l'IA.
    """
    try:
        params = generation_service.validate_metier(job_id, body.model_dump())
    except generation_service.GenerationError as err:
        raise HTTPException(status_code=_ERROR_STATUS.get(err.code, 400), detail=err.detail)

    background.add_task(generation_service.resume_generation, job_id, **params)
    return schemas.GenerationJobOut(job_id=job_id, status="running")
