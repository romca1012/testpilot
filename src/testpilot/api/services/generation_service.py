"""Ajout d'un cas à un module : spec → analyse → génération → gate (décision 0006).

« Ajouter un cas » NE crée PAS une coquille vide. Le parcours cible du brief part toujours
d'une **spécification** : on enchaîne donc le flux existant (analyse → génération → relecture),
en imposant simplement le module d'accueil. Un cas sans version ni Gherkin ne doit jamais
exister dans le référentiel — il afficherait un cas qui ne teste rien (§3).

La génération est longue et coûteuse (LLM) : elle tourne en tâche de fond, avec un job suivi
en mémoire — même schéma que les exécutions (202 + polling).
"""

from __future__ import annotations

import logging
import re
import uuid

from testpilot import config
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, ModuleRepo

logger = logging.getLogger(__name__)

# job_id → {status: running|done|failed, case_id, error}
_JOBS: dict[str, dict] = {}


class GenerationError(Exception):
    """Erreur métier de déclenchement (traduite en HTTP par la route)."""

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code  # not_found | invalid_spec
        self.detail = detail


def get_job(job_id: str) -> dict | None:
    return _JOBS.get(job_id)


def slugify(text: str) -> str:
    """Titre → slug de fichier .feature (ascii, minuscules, underscores)."""
    import unicodedata
    text = unicodedata.normalize("NFKD", text or "")
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or "cas"


def unique_feature_slug(conn, base: str) -> str:
    """Slug libre : un slug = un fichier ``.feature`` sur disque, donc unique GLOBALEMENT.

    Deux cas d'un même module ne peuvent pas partager de slug, sinon leurs .feature
    s'écraseraient l'un l'autre.
    """
    cases = CaseRepo(conn)
    slug = base
    suffix = 2
    while cases.feature_slug_taken(slug):
        slug = f"{base}_{suffix}"
        suffix += 1
    return slug


def start_generation(conn, module_id: int, *, spec_content: str, title: str = "",
                     author: str = "") -> tuple[str, dict]:
    """Valide la demande et prépare le job. Renvoie (job_id, paramètres de la tâche de fond)."""
    module = ModuleRepo(conn).get(module_id)
    if module is None:
        raise GenerationError("not_found", f"module {module_id} introuvable")
    if not (spec_content or "").strip():
        raise GenerationError("invalid_spec", "la spécification est vide")

    label = (title or "").strip() or f"Cas {module['name']}"
    slug = unique_feature_slug(conn, slugify(label))

    job_id = uuid.uuid4().hex
    _JOBS[job_id] = {"status": "running", "case_id": None, "error": "", "module_id": module_id}
    return job_id, {"module_id": module_id, "slug": slug, "title": label,
                    "spec_content": spec_content, "author": author}


def run_generation(job_id: str, *, module_id: int, slug: str, title: str,
                   spec_content: str, author: str) -> None:
    """Tâche de fond : analyse la spec puis génère le cas DANS le module demandé."""
    from testpilot.analysis.spec_analyzer import SpecAnalyzer
    from testpilot.connectors.odoo import OdooConnector
    from testpilot.connectors.runtime_env import project_env
    from testpilot.execution.behave_runner import BehaveRunner
    from testpilot.generation.agent import GenerationAgent
    from testpilot.store.repositories import ProjectRepo, VersionRepo

    conn = get_initialized_db(config.DB_PATH)
    connector = None
    try:
        module = ModuleRepo(conn).get(module_id)
        project = ProjectRepo(conn).get(module["project_id"]) if module else None

        # Génération ET dry-run tapent l'application DU PROJET du module (décision 0005).
        connector = OdooConnector.from_project(project)
        connector.connect()
        runner = BehaveRunner(connection=project_env(project))

        plan = SpecAnalyzer().analyze_spec_content(slug, spec_content)
        agent = GenerationAgent(dry_runner=runner, connector=connector,
                                case_repo=CaseRepo(conn), version_repo=VersionRepo(conn))
        result = agent.generate(plan, title=title, author=author, module_id=module_id)

        if result.success and result.case_id:
            _JOBS[job_id].update(status="done", case_id=result.case_id)
        else:
            _JOBS[job_id].update(status="failed",
                                 error=result.error or result.stopped_reason or "génération échouée")
    except Exception as exc:  # jamais laisser un job « en cours » sur un plantage
        logger.exception("[generation] job %s en échec : %s", job_id, exc)
        _JOBS[job_id].update(status="failed", error=str(exc)[:300])
    finally:
        if connector is not None:
            try:
                connector.disconnect()
            except Exception:
                pass
        conn.close()
