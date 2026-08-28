"""Plafond de tâches de fond simultanées (`guardrails/concurrency.py`).

Le problème mesuré : `automate_case`, `start_run`, `launch_run`, `start_exploration`, `add_case`
et `validate_metier` partent tous via `BackgroundTasks.add_task(...)` SANS AUCUNE limite — dix
clics simultanés démarreraient dix navigateurs Playwright et dix appels LLM en parallèle.

La preuve centrale de ce fichier n'est PAS unitaire (« la classe s'instancie ») mais
COMPORTEMENTALE : avec un plafond fixé à N, lancer N+2 tâches simultanées ne laisse JAMAIS plus
de N s'exécuter à la fois, et les 2 en attente finissent TOUJOURS par s'exécuter — jamais perdues,
jamais doublées. Les tâches simulées ici sont de simples fonctions Python (pas de vrai
navigateur) : ce qui est testé, c'est l'admission-control, pas Playwright.
"""

from __future__ import annotations

import threading
import time

import pytest

from testpilot import config
from testpilot.guardrails import concurrency


def _attendre(predicate, timeout: float = 2.0, pas: float = 0.005) -> bool:
    """Poll jusqu'à ce que `predicate()` soit vrai — évite un `sleep` fixe qui serait soit trop
    court (flaky sur une machine lente) soit trop long (test qui traîne inutilement)."""
    fin = time.monotonic() + timeout
    while time.monotonic() < fin:
        if predicate():
            return True
        time.sleep(pas)
    return predicate()


# --- Construction ------------------------------------------------------------------------

def test_max_concurrent_doit_etre_au_moins_un():
    with pytest.raises(ValueError):
        concurrency.JobQueue(max_concurrent=0)


def test_status_initial_vide():
    q = concurrency.JobQueue(max_concurrent=3)
    s = q.status()
    assert (s.max_concurrent, s.running, s.waiting) == (3, 0, 0)


# --- La preuve centrale : jamais plus de N actives, jamais rien de perdu -----------------

def test_jamais_plus_de_max_concurrent_taches_actives_a_la_fois():
    """N=2, on lance N+2=4 tâches en même temps. Chaque tâche, une fois ADMISE, s'annonce
    (compteur partagé) puis attend un signal commun avant de rendre la main — ça force les
    tâches admises à rester actives simultanément le temps qu'on observe le plafond, plutôt que
    de compter sur un `sleep` qui pourrait manquer le croisement."""
    N = 2
    q = concurrency.JobQueue(max_concurrent=N)
    verrou = threading.Lock()
    actives = 0
    pic_observe = 0
    signal_liberation = threading.Event()
    resultats: list[int] = []

    def travail(i: int) -> None:
        nonlocal actives, pic_observe
        with verrou:
            actives += 1
            pic_observe = max(pic_observe, actives)
        # Tient la place : force un vrai chevauchement le temps qu'on vérifie `status()`.
        signal_liberation.wait(timeout=5)
        with verrou:
            actives -= 1
        resultats.append(i)

    threads = [
        threading.Thread(target=lambda i=i: q.run(travail, i, queue_label=f"job-{i}"))
        for i in range(N + 2)
    ]
    for t in threads:
        t.start()

    # Les N premiers finissent par être admis et tenir la place ; les 2 autres patientent.
    assert _attendre(lambda: q.status().running == N and q.status().waiting == 2), (
        f"état inattendu après admission : {q.status()}")
    assert pic_observe <= N  # jamais dépassé, même un court instant

    # Libère tout d'un coup : les 2 en attente doivent être admis à leur tour, jamais abandonnés.
    signal_liberation.set()
    for t in threads:
        t.join(timeout=5)
        assert not t.is_alive(), "une tâche en attente n'a jamais été admise — perdue"

    assert pic_observe <= N
    assert sorted(resultats) == list(range(N + 2)), "toutes les tâches doivent avoir tourné, une fois"
    assert q.status() == concurrency.QueueStatus(max_concurrent=N, running=0, waiting=0)


# --- FIFO : position consultable pendant l'attente, jamais de resquillage ----------------

def test_position_reflete_lordre_darrivee_fifo():
    """Le plafond est saturé par 1 tâche qui bloque exprès ; deux autres arrivent ensuite, DANS
    UN ORDRE CONNU (on attend la mise en file de la première avant de lancer la seconde) — leur
    position doit refléter cet ordre, jamais l'inverse."""
    q = concurrency.JobQueue(max_concurrent=1)
    bloque_ici = threading.Event()
    laisser_partir = threading.Event()

    def occupe_la_place() -> None:
        bloque_ici.set()
        laisser_partir.wait(timeout=5)

    t0 = threading.Thread(target=lambda: q.run(occupe_la_place, queue_label="occupant"))
    t0.start()
    assert bloque_ici.wait(timeout=2), "la première tâche n'a jamais démarré"
    assert _attendre(lambda: q.status().running == 1)

    t1 = threading.Thread(target=lambda: q.run(lambda: None, queue_label="second"))
    t1.start()
    assert _attendre(lambda: q.position("second") == 1), "arrivé premier en file, doit être en tête"

    t2 = threading.Thread(target=lambda: q.run(lambda: None, queue_label="troisieme"))
    t2.start()
    assert _attendre(lambda: q.position("troisieme") == 2), "arrivé après, doit rester derrière"
    assert q.position("second") == 1  # toujours en tête, la nouvelle arrivée ne l'a pas doublé

    # Un job déjà ADMIS (ou inconnu) n'a plus de position en file — il n'attend plus.
    assert q.position("occupant") is None
    assert q.position("inconnu") is None

    laisser_partir.set()
    t0.join(timeout=5)
    t1.join(timeout=5)
    t2.join(timeout=5)
    assert q.status().waiting == 0


# --- run_gated / file partagée du processus -----------------------------------------------

def test_run_gated_utilise_la_file_partagee_du_processus(monkeypatch):
    """C'est CE point d'entrée qui est branché sur les 6 routes (`background.add_task(
    concurrency.run_gated, fn, ..., queue_label=...)`) : il doit bien passer par la file
    PARTAGÉE (`get_queue()`), pas une file neuve à chaque appel — sinon le plafond ne serait
    jamais réellement respecté entre deux routes différentes."""
    concurrency.reset_default_queue_for_tests()
    monkeypatch.setattr(config, "MAX_CONCURRENT_JOBS", 5)
    try:
        resultat = concurrency.run_gated(lambda x, *, y: x + y, 1, queue_label="t", y=2)
        assert resultat == 3
        assert concurrency.get_queue().max_concurrent == 5
        # Deux appels de suite doivent utiliser la MÊME instance (partagée), pas deux files isolées.
        assert concurrency.get_queue() is concurrency.get_queue()
    finally:
        concurrency.reset_default_queue_for_tests()


def test_max_concurrent_jobs_par_defaut_lu_depuis_la_config(monkeypatch):
    """Le défaut vient de `config.MAX_CONCURRENT_JOBS` (donc de la variable d'environnement
    `TESTPILOT_MAX_CONCURRENT_JOBS`) — pas d'une constante dupliquée dans `concurrency.py`."""
    monkeypatch.setattr(config, "MAX_CONCURRENT_JOBS", 7)
    q = concurrency.JobQueue()
    assert q.max_concurrent == 7


# --- Une exception dans la tâche ne bloque pas la file pour les suivantes -----------------

def test_une_tache_qui_leve_libere_quand_meme_sa_place():
    """Une génération/exécution qui échoue (exception) ne doit jamais garder la place occupée
    indéfiniment — sinon un seul job en échec suffirait à geler tout le plafond pour toujours."""
    q = concurrency.JobQueue(max_concurrent=1)

    def echoue() -> None:
        raise RuntimeError("panne simulée")

    with pytest.raises(RuntimeError, match="panne simulée"):
        q.run(echoue, queue_label="echec")

    assert q.status() == concurrency.QueueStatus(max_concurrent=1, running=0, waiting=0)
    # La place est bien redevenue disponible pour la tâche suivante.
    assert q.run(lambda: "ok", queue_label="suivante") == "ok"
