"""Déclenchement automatique des campagnes planifiées (migration 43).

`tick()` est appelée périodiquement par une boucle de fond (voir `app.py::lifespan`) — JAMAIS
par une requête HTTP. Elle réutilise EXACTEMENT le moteur d'exécution existant
(`campaign_service.start_campaign` + `durable_jobs`) : rien de nouveau côté exécution, seul le
DÉCLENCHEUR change (une horloge plutôt qu'un clic).

⚠️ **Une planification est TOUJOURS automatique.** `MODE_AUTOMATIQUE` est forcé ici, jamais lu
depuis une entrée utilisateur — `ScheduledRunRepo` ne connaît même pas de champ `mode` (voir sa
docstring). Le garde-fou de `campaign_service.start_campaign` (code d'erreur `"manual"`) reste un
second filet, jamais désactivé : personne n'est présent à 2h du matin pour saisir un résultat
manuel, donc ce choix n'a structurellement pas sa place ici.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from testpilot.api.services import campaign_service, donnees_de_test_service, environnements_service
from testpilot.parametres import environnements as envs
from testpilot.guardrails import durable_jobs
from testpilot.store.repositories import DonneeDeTestInvalide, PlanRepo, RunRepo, ScheduledRunRepo, TestDataRepo
from testpilot.verdict.status import MODE_AUTOMATIQUE

logger = logging.getLogger(__name__)


def _est_due(planif: dict, maintenant: datetime) -> bool:
    """Une planification quotidienne se déclenche une fois par jour, à l'heure dite ou juste
    après ; une hebdomadaire, en plus, seulement le bon jour (`weekday`, 0=lundi comme
    `datetime.weekday()`). `last_triggered_at` empêche un second déclenchement le même jour si
    `tick()` tourne plusieurs fois après l'heure cible (ex. le serveur redémarre entre-temps)."""
    if planif["frequency"] == "weekly" and maintenant.weekday() != planif["weekday"]:
        return False
    heure_due = maintenant.replace(hour=planif["hour"], minute=planif["minute"],
                                   second=0, microsecond=0)
    if maintenant < heure_due:
        return False
    dernier = planif.get("last_triggered_at") or ""
    if dernier and dernier[:10] == maintenant.date().isoformat():
        return False  # déjà déclenchée aujourd'hui — pas une seconde fois
    return True


def _declencher(conn, repo: ScheduledRunRepo, planif: dict, maintenant: datetime) -> int:
    """Crée une campagne fraîche et la lance, exactement comme `POST /runs` puis
    `POST /runs/{id}/launch` — la seule différence avec un geste humain est QUI l'a demandé
    (`triggered_by`), jamais COMMENT elle s'exécute.

    ⚠️ **`maintenant` partout, jamais `datetime.now()` ici** (bug trouvé en CI le 2026-09-11,
    invisible en local car l'horloge locale coïncidait par hasard avec les dates simulées des
    tests) : `_est_due()` compare `last_triggered_at` à `maintenant` reçu de `tick()` (réel en
    production, figé dans un test) — si `mark_triggered` timbrait avec l'horloge RÉELLE au lieu
    de ce même `maintenant`, les deux dates ne coïncidaient plus dès que le jour changeait entre
    l'écriture du test et son exécution, et la déduplication « pas deux fois le même jour »
    cessait de fonctionner silencieusement."""
    case_ids = repo.case_ids(planif["id"])
    nom = f"{planif['name']} — {maintenant.date().isoformat()}"
    champs = dict(
        selection_mode=planif["selection_mode"],
        mode=MODE_AUTOMATIQUE,  # ⚠️ TOUJOURS — jamais une valeur lue de `planif`
        case_ids=case_ids if planif["selection_mode"] == "frozen" else None,
    )
    acteur = f"scheduler:{planif['name']}"
    jeux = _jeux_du_declenchement(conn, planif)
    environnements = _environnements_du_declenchement(conn, planif)
    # A52 : une exécution par environnement, toutes les lignes dedans (une itération par ligne) — exactement comme à la main.
    plan_id, premier, run_ids = donnees_de_test_service.creer_les_executions(
        conn, project_id=planif["project_id"], nom=nom, jeux=jeux, created_by=acteur, environnements=environnements,
        nommer_le_jeu=True, **champs)
    try:
        _lancer(conn, premier, acteur)
    except Exception:
        # La première ne part pas (connexion, campagne vide…) : rien ne part. Les brouillons créés sont retirés, sinon
        # chaque passage de l'horloge en laisserait de plus ce jour-là.
        for run_id in run_ids:
            RunRepo(conn).supprimer_brouillon(run_id)
        if plan_id is not None:
            PlanRepo(conn).delete(plan_id)
        raise
    # La première est partie : la planification est déclenchée pour aujourd'hui, QUOI QU'IL ARRIVE aux suivantes — sinon
    # une erreur sur l'une d'elles relancerait une nouvelle première à chaque passage de l'horloge (revue du 2026-10-14).
    repo.mark_triggered(planif["id"], premier, at=maintenant.isoformat())
    for run_id in run_ids[1:]:
        try:
            _lancer(conn, run_id, acteur)
        except Exception:   # le brouillon reste dans le plan : c'est le signal visible qu'un environnement n'a pas été joué
            logger.exception("[scheduler] planification %s : exécution %s non lancée", planif["id"], run_id)
    return premier


def _lancer(conn, run_id: int, acteur: str) -> None:
    params = campaign_service.start_campaign(conn, run_id, triggered_by=acteur)
    durable_jobs.submit_immediat(conn, kind="campaign", kwargs=params,
                                 queue_label=f"campaign:{run_id}")


def _jeux_du_declenchement(conn, planif: dict) -> list[dict]:
    """Les jeux de la planification. Décision du porteur (2026-10-14, A36) : si UN SEUL de ses jeux est à la corbeille, la
    planification ne joue RIEN — ni les autres jeux, ni « Par défaut » à sa place — tant qu'on ne l'a pas corrigée
    (restaurer le jeu, ou recréer la planification). La liste des planifications le montre."""
    ids = donnees_de_test_service.ids_des_jeux(planif.get("dataset_ids"), strict=True)
    depot = TestDataRepo(conn)
    jeux = [j for j in (depot.jeu(planif["project_id"], i) for i in ids) if j is not None]
    if len(jeux) < len(ids):
        raise DonneeDeTestInvalide(f"{len(ids) - len(jeux)} jeu(x) de données de cette planification à la corbeille : "
                                   "rien n'est joué tant qu'elle n'est pas corrigée")
    return jeux


def _environnements_du_declenchement(conn, planif: dict) -> list[dict | None]:
    """Les environnements de la planification (None = par défaut). Même règle que les jeux (A36) : un seul à la corbeille,
    devenu « Production » ou illisible, et rien n'est joué — jamais un autre environnement à sa place."""
    ids = envs.ids_lus(planif.get("environment_ids"), strict=True)
    try:
        return environnements_service.environnements_demandes(conn, planif["project_id"], ids)
    except envs.EnvironnementInvalide as exc:
        raise envs.EnvironnementInvalide(f"{exc} : rien n'est joué tant que la planification n'est pas corrigée") from exc


def tick(conn, *, now: datetime | None = None) -> list[int]:
    """Déclenche chaque planification due. Rend les ids de `test_run` créés (utile aux tests).

    Best-effort PAR PLANIFICATION : une planification en échec (campagne vide, connexion
    incomplète...) ne doit jamais empêcher les autres de se déclencher — même philosophie que
    `campaign_service.run_campaign`, où un cas en échec ne bloque pas les suivants."""
    maintenant = now or datetime.now(timezone.utc)
    repo = ScheduledRunRepo(conn)
    declenches = []
    for planif in repo.list_active():
        if not _est_due(planif, maintenant):
            continue
        try:
            declenches.append(_declencher(conn, repo, planif, maintenant))
        except Exception:
            logger.exception("[scheduler] planification %s (%s) : déclenchement en échec",
                             planif["id"], planif["name"])
    return declenches
