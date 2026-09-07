"""Diffusion en temps réel des changements d'un projet (SSE, audit 2026-09-07 — « vrai temps
réel », suite du garde-fou anti-édition-concurrente de `CaseRepo.update_metier`).

**Pourquoi en mémoire, pas Redis.** Le déploiement cible tourne à UN SEUL worker uvicorn
(`compose.production.yml`) : toute la concurrence se joue dans ce même process, donc un simple
registre en mémoire suffit à prévenir tous les abonnés — pas besoin d'un relais externe pour
qu'une instance sache ce qu'une autre vient de publier, puisqu'il n'y en a qu'une. **Si
l'architecture passe un jour à plusieurs workers/process**, cette diffusion ne suffira plus :
chaque process aurait ses propres abonnés, sourds aux publications faites depuis un autre — il
faudra alors un pub/sub partagé (Redis).

**Pourquoi `queue.Queue`, pas `asyncio.Queue`.** Les routes qui PUBLIENT (`update_case_metier`,
`create_manual_case`…) sont des `def` synchrones — FastAPI les exécute dans un thread du pool,
PAS sur la boucle asyncio. `asyncio.Queue` n'est pas thread-safe : y écrire depuis ce thread sans
passer par `call_soon_threadsafe` corromprait son état. `queue.Queue` (stdlib, thread-safe par
construction) évite ce piège entièrement — la route SSE, elle, la consomme via
`asyncio.to_thread` (voir `routes/projects.py`).
"""

from __future__ import annotations

import queue
import threading

# Une file par ABONNÉ (un onglet de navigateur ouvert sur un projet), regroupées par projet —
# jamais l'inverse : publier un événement pour le projet 3 ne doit toucher AUCUN abonné d'un
# autre projet, cohérent avec l'isolation par projet du reste de l'application.
_ABONNES: dict[int, list["queue.Queue[dict]"]] = {}
_VERROU = threading.Lock()

# Au-delà, un abonné qui ne consomme plus (onglet en arrière-plan, throttle navigateur) perd ses
# plus vieux événements plutôt que de grossir indéfiniment ou de bloquer l'appelant — qui est,
# lui, un vrai enregistrement utilisateur en train de répondre à sa requête HTTP.
_TAILLE_FILE_MAX = 50


def abonner(project_id: int) -> "queue.Queue[dict]":
    """Ouvre un nouvel abonnement pour ce projet. Rendu au caller pour être passé à
    `desabonner` quand la connexion SSE se ferme (déconnexion du navigateur, fin de requête)."""
    q: "queue.Queue[dict]" = queue.Queue(maxsize=_TAILLE_FILE_MAX)
    with _VERROU:
        _ABONNES.setdefault(project_id, []).append(q)
    return q


def desabonner(project_id: int, q: "queue.Queue[dict]") -> None:
    with _VERROU:
        abonnes = _ABONNES.get(project_id)
        if not abonnes:
            return
        try:
            abonnes.remove(q)
        except ValueError:
            pass
        if not abonnes:
            _ABONNES.pop(project_id, None)


def publier(project_id: int, event: dict) -> None:
    """Best-effort : ne lève jamais. Un abonné en panne ou une file pleine ne doit jamais faire
    échouer l'enregistrement réel qui déclenche cette notification — la notification est un
    confort pour les écrans ouverts ailleurs, pas la source de vérité (qui reste la base)."""
    with _VERROU:
        abonnes = list(_ABONNES.get(project_id, ()))
    for q in abonnes:
        try:
            q.put_nowait(event)
        except queue.Full:
            try:
                q.get_nowait()   # perd le plus ancien pour faire de la place au plus récent
                q.put_nowait(event)
            except (queue.Empty, queue.Full):
                pass


def nombre_abonnes(project_id: int) -> int:
    """Pour les tests et l'observabilité — jamais utilisé pour décider quoi que ce soit métier."""
    with _VERROU:
        return len(_ABONNES.get(project_id, ()))
