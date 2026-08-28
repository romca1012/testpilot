"""Plafond de tâches de fond simultanées (§6 addendum charge machine).

**Le problème mesuré** : `automate_case`, `start_run` (`api/routes/cases.py`), `launch_run`
(`api/routes/runs.py`), `start_exploration` (`api/routes/projects.py`), `add_case` et
`validate_metier` (`api/routes/modules.py`) partent tous via `BackgroundTasks.add_task(...)`,
SANS AUCUNE limite de combien peuvent tourner à la fois. Un job de génération ou d'exécution
ouvre un navigateur Playwright réel (CPU/mémoire non négligeables) et souvent un appel à l'API
Anthropic (coût, débit). Dix clics simultanés sur « Lancer » démarraient dix navigateurs et dix
appels LLM en parallèle — jamais rejeté, jamais mis en attente, jamais visible.

**Le choix fait ici** : un admission-control EN MÉMOIRE — sémaphore borné + file FIFO — et non
une file externe (Celery/Redis). Même logique que l'anti-brute-force du login
(`api/routes/auth.py`, `_echecs_connexion` : un dict + `threading.Lock`, pas de table) : un
plafond de parallélisme n'a besoin que d'un compteur du PROCESSUS, pas d'un état qui doit
survivre à un redémarrage. Introduire une file externe n'est justifié que si ce plafond simple
s'avère insuffisant, MESURÉ — pas supposé à l'avance.

**Limite assumée et non cachée** : une tâche en attente vit uniquement dans ce module, EN
MÉMOIRE. Si le serveur redémarre pendant qu'une tâche patiente dans la file (jamais démarrée),
elle est PERDUE — exactement comme n'importe quelle `BackgroundTasks` de FastAPI aujourd'hui
(rien de nouveau n'est perdu ici ; la limite préexistait, elle n'est simplement pas comblée par
ce lot). Sur plusieurs machines/processus (aucun aujourd'hui), chaque processus aurait SON PROPRE
plafond, non partagé — un vrai frein multi-instance nécessiterait un état partagé (Redis...),
hors périmètre ici.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass

from testpilot import config

logger = logging.getLogger(__name__)


@dataclass
class QueueStatus:
    """Photo de l'état courant de la file — ce qu'un appelant a besoin de savoir."""
    max_concurrent: int
    running: int
    waiting: int


class JobQueue:
    """Admission-control FIFO : au plus `max_concurrent` tâches de fond ACTIVES en même temps.

    Le sémaphore ne suffit pas seul : un `threading.Semaphore` classique ne garantit ni l'ORDRE
    de réveil ni une POSITION consultable pendant l'attente. Ici, chaque appelant prend un ticket
    (son `label`, déjà unique — un `job_id` de génération, un `execution_id`, ...) et une
    `threading.Condition` réveille toujours le PREMIER ticket de la file dès qu'une place se
    libère : c'est ce qui rend `position()` fiable pendant l'attente, et ce qui garantit qu'une
    tâche en attente finit TOUJOURS par s'exécuter (jamais abandonnée, jamais doublée par une
    arrivée plus récente).
    """

    def __init__(self, max_concurrent: int | None = None):
        self.max_concurrent = config.MAX_CONCURRENT_JOBS if max_concurrent is None else max_concurrent
        if self.max_concurrent < 1:
            raise ValueError("max_concurrent doit être ≥ 1")
        self._condition = threading.Condition()
        self._running = 0
        self._waiting: deque[str] = deque()  # labels, ordre FIFO d'arrivée

    def status(self) -> QueueStatus:
        """Vue d'ensemble — c'est elle que la visibilité API expose (running / waiting)."""
        with self._condition:
            return QueueStatus(
                max_concurrent=self.max_concurrent,
                running=self._running,
                waiting=len(self._waiting),
            )

    def position(self, label: str) -> int | None:
        """Position 1-indexée de `label` dans la file d'ATTENTE, ou `None` s'il est déjà admis
        (en cours d'exécution) ou inconnu. Ne distingue pas les deux cas : ce module ne garde
        aucune trace d'un job une fois admis, seul l'appelant (job en base) sait s'il a terminé."""
        with self._condition:
            try:
                return self._waiting.index(label) + 1
            except ValueError:
                return None

    def _acquire(self, label: str) -> None:
        """Bloque l'appelant jusqu'à ce qu'une place se libère ET que ce soit son tour (FIFO)."""
        with self._condition:
            self._waiting.append(label)
            try:
                while self._running >= self.max_concurrent or self._waiting[0] != label:
                    self._condition.wait()
                self._waiting.popleft()
            except BaseException:
                # Interruption pendant l'attente (ex. arrêt du process) : retire proprement le
                # ticket plutôt que de laisser un fantôme bloquer la position 0 pour toujours.
                if label in self._waiting:
                    self._waiting.remove(label)
                raise
            self._running += 1

    def _release(self) -> None:
        with self._condition:
            self._running -= 1
            self._condition.notify_all()  # réveille tout le monde ; seul le nouveau 1er avance

    def run(self, fn, *args, queue_label: str = "", **kwargs):
        """Exécute `fn(*args, **kwargs)` une fois le tour venu.

        Conçu pour tourner DANS la tâche de fond elle-même (`background.add_task(queue.run, fn,
        ...)`) : c'est ce thread-là qui patiente, jamais la requête HTTP — la réponse est déjà
        partie avant que `run` ne soit même appelé (comportement `BackgroundTasks` inchangé).
        """
        label = queue_label or f"anonyme-{id(object())}"
        self._acquire(label)
        try:
            return fn(*args, **kwargs)
        finally:
            self._release()


# ── Instance partagée par tous les points d'appel (cases/modules/projects/runs) ──────────────
_lock_singleton = threading.Lock()
_queue: JobQueue | None = None


def get_queue() -> JobQueue:
    """File partagée du PROCESSUS courant — un seul plafond pour toutes les tâches de fond,
    pas un mécanisme par route (cf. tête de fichier)."""
    global _queue
    with _lock_singleton:
        if _queue is None:
            _queue = JobQueue()
        return _queue


def run_gated(fn, *args, queue_label: str = "", **kwargs):
    """Point d'entrée passé à `background.add_task(...)` à la place de `fn` directement.

    `background.add_task(concurrency.run_gated, generation_service.run_automation, job_id,
    queue_label=f"automation:{job_id}", **params)` — la tâche de fond attend son tour dans la
    file PARTAGÉE avant d'exécuter réellement `generation_service.run_automation`.
    """
    return get_queue().run(fn, *args, queue_label=queue_label, **kwargs)


def reset_default_queue_for_tests() -> None:
    """Réservé aux tests : force la prochaine `get_queue()` à recréer une file fraîche, pour ne
    pas faire fuiter l'état (compteurs, tickets) d'un test à l'autre."""
    global _queue
    with _lock_singleton:
        _queue = None
