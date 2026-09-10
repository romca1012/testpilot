"""File durable au-dessus du plafond de concurrence en mémoire.

Une requête écrit d'abord le travail en base, puis programme son exécution. Après un redémarrage,
les travaux encore ``queued`` sont rejoués. Un travail déjà ``running`` n'est jamais rejoué
aveuglément (les effets externes ne sont pas transactionnels) : il est clôturé explicitement en
échec et son objet métier est rendu relançable.
"""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timedelta, timezone

from testpilot import config
from testpilot.guardrails import concurrency
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import BackgroundJobRepo, GenerationJobRepo, RunRepo

logger = logging.getLogger(__name__)


def submit(conn, background, *, kind: str, args: list | tuple = (), kwargs: dict | None = None,
           queue_label: str) -> str:
    """Persiste avant de rendre la main, puis confie l'exécution à FastAPI."""
    job_id = uuid.uuid4().hex
    BackgroundJobRepo(conn).creer(
        job_id, kind=kind, queue_label=queue_label,
        payload={"args": list(args), "kwargs": kwargs or {}},
    )
    background.add_task(run_job, job_id)
    return job_id


def submit_immediat(conn, *, kind: str, args: list | tuple = (), kwargs: dict | None = None,
                    queue_label: str) -> str:
    """Comme `submit()`, pour un appelant SANS requête HTTP en cours (le scheduler — migration
    43 — tourne dans une boucle de fond, jamais dans un cycle requête/réponse) : pas de
    `BackgroundTasks` à qui confier l'exécution, donc un thread démarré directement — le même
    geste que `recover_at_startup()` ci-dessous pour les tâches reprises au redémarrage."""
    job_id = uuid.uuid4().hex
    BackgroundJobRepo(conn).creer(
        job_id, kind=kind, queue_label=queue_label,
        payload={"args": list(args), "kwargs": kwargs or {}},
    )
    threading.Thread(target=run_job, args=(job_id,), daemon=True,
                     name=f"testpilot-job-{job_id[:8]}").start()
    return job_id


def _call(kind: str, args: list, kwargs: dict) -> None:
    # Imports tardifs : ce module est chargé par les routes qui chargent déjà les services.
    from testpilot.api.services import (
        campaign_service,
        exploration_service,
        generation_service,
        run_service,
    )

    handlers = {
        "generation": generation_service.run_generation,
        "generation_resume": generation_service.resume_generation,
        "automation": generation_service.run_automation,
        "execution": run_service.run_execution,
        "campaign": campaign_service.run_campaign,
        "exploration": exploration_service.run_exploration,
    }
    try:
        handler = handlers[kind]
    except KeyError as exc:
        raise RuntimeError(f"type de tâche durable inconnu : {kind}") from exc
    handler(*args, **kwargs)


def run_job(job_id: str) -> None:
    """Attendre la capacité avant de réclamer le travail persistant."""
    concurrency.run_gated(_run_admitted_job, job_id, queue_label=f"durable:{job_id}")


def _run_admitted_job(job_id: str) -> None:
    """Réclame atomiquement une tâche ; une seule exécution gagne, même après un rejeu."""
    conn = get_initialized_db()
    try:
        repo = BackgroundJobRepo(conn)
        job = repo.get(job_id)
        if job is None or not repo.claim(job_id):
            return
        payload = job["payload"]
        kind = job["kind"]
        label = job["queue_label"]
    finally:
        conn.close()

    erreur = ""
    try:
        _call(kind, payload.get("args", []), payload.get("kwargs", {}))
    except Exception as exc:
        erreur = str(exc) or type(exc).__name__
        logger.exception("[durable-job] %s (%s) en échec", job_id, kind)
    finally:
        conn = get_initialized_db()
        try:
            BackgroundJobRepo(conn).terminer(job_id, erreur=erreur)
        finally:
            conn.close()


def _reconcilier_interrompu(conn, job: dict) -> None:
    """Rend visible et relançable une tâche active interrompue, sans la doubler."""
    payload = job.get("payload") or {}
    args = payload.get("args") or []
    kwargs = payload.get("kwargs") or {}
    kind = job.get("kind")
    message = "traitement interrompu par un redémarrage du serveur; relancez-le"
    if kind in {"generation", "generation_resume", "automation"} and args:
        GenerationJobRepo(conn).maj(str(args[0]), status="failed", error=message)
    elif kind == "execution" and len(args) >= 3:
        from testpilot.api.services.run_service import _finalize_error
        _finalize_error(conn, int(args[0]), int(args[2]), message)
    elif kind == "campaign":
        run_id = kwargs.get("run_id") or (args[0] if args else None)
        if run_id is not None:
            # Brouillon = relançable. Les exécutions déjà terminées restent historisées.
            conn.execute("UPDATE test_run SET status='draft' WHERE id=? AND status='running'",
                         (int(run_id),))
            conn.commit()


def recover_at_startup() -> int:
    """Clôt les actifs interrompus et rejoue les travaux qui n'avaient pas commencé."""
    conn = get_initialized_db()
    try:
        repo = BackgroundJobRepo(conn)
        for job in repo.interrompus():
            try:
                _reconcilier_interrompu(conn, job)
            except Exception:
                logger.exception("[durable-job] réconciliation impossible pour %s", job["id"])
        limite = datetime.now(timezone.utc) - timedelta(
            days=max(1, config.BACKGROUND_JOB_RETENTION_DAYS))
        repo.purger_termines(limite.isoformat())
        queued = repo.queued_ids()
    finally:
        conn.close()

    for job_id in queued:
        threading.Thread(target=run_job, args=(job_id,), daemon=True,
                         name=f"testpilot-job-{job_id[:8]}").start()
    if queued:
        logger.warning("[durable-job] %s tâche(s) en attente reprise(s) au démarrage", len(queued))
    return len(queued)
