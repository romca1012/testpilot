"""Lancement d'un RUN (campagne) — incrément 1b de la décision `0022` n°8.

Créer une campagne ne lance rien (8.c.1) ; **lancer** est un geste explicite. Ce service exécute
les N cas du run **en séquence**, chacun produisant une `execution` rattachée (`run_id`).

⚠️ **Séquence et non parallèle**, délibérément : les tests pilotent un vrai navigateur contre une
vraie application, et créent des données (tickets). Les jouer en parallèle ferait s'entre-gêner
leurs comptages (« le nombre d'enregistrements a augmenté de 1 » devient faux si un autre
scénario crée en même temps) — c'est exactement la famille de faux négatifs que `0011` a traquée.

⚠️ **Un cas qui échoue n'arrête pas la campagne** : les autres cas continuent. Une campagne sert à
savoir *où* on en est sur l'ensemble ; s'arrêter au premier échec cacherait l'état des suivants.
"""

from __future__ import annotations

import logging

from testpilot import config
from testpilot.api.services import run_service
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import RunRepo

logger = logging.getLogger(__name__)


class CampaignError(Exception):
    """Erreur métier de lancement (traduite en HTTP par la route)."""

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code  # not_found | empty | already_running
        self.detail = detail


def start_campaign(conn, run_id: int) -> dict:
    """Valide le lancement et passe le run « en cours ». Renvoie les paramètres de la tâche."""
    repo = RunRepo(conn)
    run = repo.get(run_id)
    if run is None:
        raise CampaignError("not_found", f"exécution {run_id} introuvable")
    if run["status"] == "running":
        raise CampaignError("already_running", "cette exécution est déjà en cours")
    case_ids = repo.case_ids(run_id)
    if not case_ids:
        # Lancer une campagne vide produirait un run « terminé » sans rien avoir testé — un
        # succès trompeur. On refuse et on le dit.
        raise CampaignError("empty", "cette exécution ne contient aucun cas de test")

    repo.set_status(run_id, "running", launched=True)
    return {"run_id": run_id, "case_ids": case_ids}


def run_campaign(run_id: int, case_ids: list[int]) -> None:
    """Tâche de fond : exécute les cas du run EN SÉQUENCE, puis clôt la campagne.

    Chaque cas est joué par le circuit existant (`run_service`), qui persiste le verdict à deux
    axes et tente une réparation si elle est autorisée. On rattache l'exécution au run juste après
    sa création : c'est ce lien qui fait exister le « résultat du cas DANS ce run » (`0022` n°4).
    """
    conn = get_initialized_db(config.DB_PATH)
    try:
        for case_id in case_ids:
            try:
                eid, slug, cid, vid = run_service.trigger_run(conn, case_id)
            except run_service.RunError as err:
                # Un cas non exécutable (sans version, gate fermé) ne fait pas tomber la campagne :
                # il reste « non testé » dans le run, et on le journalise.
                logger.warning("[campagne %s] cas %s non lancé : %s", run_id, case_id, err.detail)
                continue
            # Le rattachement AVANT l'exécution : si le processus meurt en cours de route, la
            # ligne d'exécution reste reliée à sa campagne (sinon elle deviendrait orpheline).
            conn.execute("UPDATE execution SET run_id=? WHERE id=?", (run_id, eid))
            conn.commit()
            try:
                run_service.run_execution(eid, slug, cid, vid)
            except Exception:
                # `run_execution` a son propre filet (statut technical_error) ; on protège quand
                # même la boucle pour que les cas suivants soient joués.
                logger.exception("[campagne %s] cas %s : exécution en échec", run_id, case_id)
    finally:
        try:
            RunRepo(conn).set_status(run_id, "completed", completed=True)
        except Exception:
            logger.exception("[campagne %s] clôture non enregistrée", run_id)
        conn.close()
