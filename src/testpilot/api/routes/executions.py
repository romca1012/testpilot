"""Routes des exécutions : liste (onglet Exécution), détail à deux axes, et rapport
(JSON + rendu HTML réutilisant le pilier reporting)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse

from testpilot.api import schemas
from testpilot.api.deps import get_conn
from testpilot.api.services import report_service, run_service
from testpilot.reporting import report as report_mod
from testpilot.store.repositories import ExecutionRepo

router = APIRouter(prefix="/api/executions", tags=["executions"])


@router.get("", response_model=list[schemas.ExecutionSummary])
def list_executions(limit: int = 50, project_id: int | None = None, conn=Depends(get_conn)):
    rows = ExecutionRepo(conn).list_recent(limit, project_id=project_id)
    return [schemas.execution_summary(r, running=run_service.is_running(r["id"])) for r in rows]


@router.get("/quality/summary", response_model=schemas.QualityOut)
def quality_summary(project_id: int | None = None, conn=Depends(get_conn)):
    """Santé technique de la génération dans le temps — l'évolution de l'outil.

    Dérivé des VRAIES exécutions (premier jet), jamais fabriqué : le tableau de bord compte des
    runs réels. `/quality/summary` et non `/quality` pour ne pas heurter `/{execution_id}`.
    """
    return schemas.QualityOut(**ExecutionRepo(conn).quality_summary(project_id=project_id))


@router.get("/{execution_id}", response_model=schemas.ExecutionDetail)
def get_execution(execution_id: int, conn=Depends(get_conn)):
    execs = ExecutionRepo(conn)
    row = execs.get(execution_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"exécution {execution_id} introuvable")
    summary = schemas.execution_summary(row, running=run_service.is_running(execution_id))
    scenarios = [schemas.scenario_result_out(s) for s in execs.list_scenario_results(execution_id)]
    return schemas.ExecutionDetail(**summary.model_dump(), scenarios=scenarios)


@router.get("/{execution_id}/artifacts", response_model=schemas.ArtifactsOut)
def list_artifacts(execution_id: int, conn=Depends(get_conn)):
    """La trace BRUTE de cette exécution : ce que la machine a réellement vu.

    Sans elle, un verdict « erreur technique » ou « refus silencieux » ne laisse rien à
    instruire — l'utilisateur constate, il ne comprend pas. `available=False` avec sa raison
    plutôt qu'une liste vide : « aucun fichier » et « aucune trace n'a été conservée » ne
    veulent pas dire la même chose, et confondre les deux est le motif « absence de signal prise
    pour un signal » que ce projet traque partout.
    """
    row = ExecutionRepo(conn).get(execution_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"exécution {execution_id} introuvable")

    chemin = (row.get("artifacts_path") or "").strip()
    if not chemin:
        return schemas.ArtifactsOut(
            available=False,
            reason="Aucune trace conservée : cette exécution est antérieure à leur archivage.")
    dossier = Path(chemin)
    if not dossier.is_dir():
        return schemas.ArtifactsOut(
            available=False,
            reason="La trace a été archivée mais son dossier est introuvable — déplacé, purgé, "
                   "ou base restaurée sans le répertoire de données.")

    fichiers = [schemas.ArtifactOut(name=f.name, size=f.stat().st_size, label=_libelle(f.name))
                for f in sorted(dossier.iterdir()) if f.is_file()]
    if not fichiers:
        return schemas.ArtifactsOut(available=False, reason="Le dossier de trace est vide.")
    return schemas.ArtifactsOut(available=True, files=fichiers)


# Libellés MÉTIER : un QA ne doit pas avoir à deviner ce qu'est `execution.behave.json` (§8).
_LIBELLES_ARTEFACTS = {
    "execution.log": "Journal de l'exécution réelle",
    "dry-run.log": "Journal de la vérification préalable",
    "execution.behave.json": "Détail par scénario et par étape",
    "dry-run.behave.json": "Détail de la vérification préalable",
    "execution.replis-de-champ.json": "Champs trouvés par un libellé de repli",
    "dry-run.replis-de-champ.json": "Champs trouvés par un libellé de repli (vérification)",
}


def _libelle(nom: str) -> str:
    if nom in _LIBELLES_ARTEFACTS:
        return _LIBELLES_ARTEFACTS[nom]
    if nom.endswith(".feature"):
        return "Le test tel qu'il a été joué"
    if nom.endswith("_steps.py"):
        return "Les étapes techniques telles qu'elles ont été jouées"
    return nom


@router.get("/{execution_id}/artifacts/{nom}", response_class=PlainTextResponse)
def get_artifact(execution_id: int, nom: str, conn=Depends(get_conn)):
    """Le contenu d'un artefact.

    ⚠️ **Le nom demandé n'est jamais concaténé au chemin.** On liste le dossier et on cherche une
    correspondance EXACTE : un `nom` du genre `../../.env` ne peut donc pas désigner un fichier
    hors du dossier de l'exécution. C'est la seule façon sûre de servir un fichier dont le nom
    vient de l'extérieur — et ici l'outil tourne sur un serveur partagé, avec des secrets à côté.
    """
    row = ExecutionRepo(conn).get(execution_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"exécution {execution_id} introuvable")
    dossier = Path((row.get("artifacts_path") or "").strip() or ".")
    if not dossier.is_dir():
        raise HTTPException(status_code=404, detail="aucune trace conservée pour cette exécution")

    for f in dossier.iterdir():
        if f.is_file() and f.name == nom:
            return PlainTextResponse(f.read_text(encoding="utf-8", errors="replace"))
    raise HTTPException(status_code=404, detail=f"artefact « {nom} » introuvable")


@router.get("/{execution_id}/report")
def get_report_json(execution_id: int, conn=Depends(get_conn)):
    report = report_service.build_report_for_execution(conn, execution_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"exécution {execution_id} introuvable")
    return report.to_dict()


@router.get("/{execution_id}/report.html", response_class=HTMLResponse)
def get_report_html(execution_id: int, conn=Depends(get_conn)):
    report = report_service.build_report_for_execution(conn, execution_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"exécution {execution_id} introuvable")
    return HTMLResponse(content=report_mod.render_html(report))
