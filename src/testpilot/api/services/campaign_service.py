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
from testpilot.api.services import notification_service, run_service
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import RunRepo
from testpilot.verdict.status import MODE_AUTOMATIQUE, MODE_MANUELLE

logger = logging.getLogger(__name__)


class CampaignError(Exception):
    """Erreur métier de lancement (traduite en HTTP par la route)."""

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code  # not_found | empty | already_running | archived | manual | no_connection | environment_refused
        self.detail = detail


def start_campaign(conn, run_id: int, *, triggered_by: str = "") -> dict:
    """Valide le lancement et passe le run « en cours ». Renvoie les paramètres de la tâche.

    `triggered_by` (migration 32) : le compte qui a demandé ce lancement — résolu par
    l'APPELANT, SYNCHRONE, avant toute mise en tâche de fond, reporté sur CHAQUE exécution que
    la campagne va créer.
    """
    repo = RunRepo(conn)
    run = repo.get(run_id)
    if run is None:
        raise CampaignError("not_found", f"exécution {run_id} introuvable")
    if run["status"] == "running":
        raise CampaignError("already_running", "cette exécution est déjà en cours")
    if run.get("is_archived"):
        # Garde CÔTÉ SERVEUR, pas seulement à l'écran (note fonctionnelle) : un run archivé est
        # en lecture seule, ses résultats sont figés. Le bloquer uniquement dans l'UI laisserait
        # l'API le relancer et réécrire un historique clos.
        raise CampaignError("archived",
                            "cette exécution est archivée (lecture seule) — rouvrez-la pour la relancer")
    if run.get("mode", MODE_AUTOMATIQUE) == MODE_MANUELLE:
        # ⚠️ Le MODE D'EXÉCUTION se choisit à la création (2026-08-04). Une campagne manuelle se
        # SAISIT, cas par cas ; la lancer produirait des résultats machine dans une campagne dont
        # tout l'historique est humain — et le trigger de la base les refuserait, une exécution
        # après l'autre, sans que personne ne comprenne pourquoi. On le dit ici, en clair.
        raise CampaignError("manual",
                            "cette campagne est manuelle : ses résultats se saisissent à la main, "
                            "cas par cas. Créez une campagne automatique pour la faire jouer.")
    case_ids = repo.case_ids(run_id)
    if not case_ids and run.get("seulement_variables") and repo.case_ids(run_id, tri_variables=False):
        # A35 : l'exécution d'un jeu autre que le premier ne joue que les tests qui écrivent des variables — aucun n'en écrit.
        raise CampaignError("empty", "aucun test de cette exécution n'utilise de donnée de test : rien à jouer avec ce jeu "
                                     "(les autres tests sont joués une fois, dans la première exécution du plan)")
    if not case_ids:
        # Lancer une campagne vide produirait un run « terminé » sans rien avoir testé — un
        # succès trompeur. On refuse et on le dit.
        # Une campagne automatique ne contient que les cas AUTOMATISÉS (2026-10-12) : vide, elle l'est le plus souvent
        # parce que les cas du projet ont été saisis à la main ou importés. On dit quoi faire.
        raise CampaignError("empty", "cette exécution ne contient aucun cas doté d'un test technique — faites automatiser des "
                                     "cas, ou créez une exécution manuelle pour jouer à la main ceux qui existent")

    # ⚠️ La connexion se vérifie UNE FOIS ici, et non cas par cas : un run lancé sans savoir
    # contre quelle application il tourne produirait N verdicts faux d'un coup. Vérifié AVANT de
    # passer le run « en cours », pour qu'un refus ne laisse pas une campagne bloquée en course —
    # et APRÈS le contrôle « campagne vide », qui est le diagnostic le plus précis quand les deux
    # sont vrais (dire « connexion incomplète » sur une campagne sans cas enverrait corriger la
    # mauvaise chose).
    from testpilot.connectors.runtime_env import ConnexionIncomplete, verifier_connexion
    from testpilot.store.repositories import ProjectRepo
    # Lot PT-04a (A48) : l'environnement de la campagne est vérifié et FIGÉ ici, avant la connexion — un environnement
    # « Production », supprimé ou illisible : la campagne n'est pas lancée, jamais jouée ailleurs que ce qui était annoncé.
    from testpilot.api.services import environnements_service
    from testpilot.parametres.environnements import EnvironnementInvalide, projet_sur
    try:
        environnements_service.figer_pour_la_campagne(conn, run)
        environnement = environnements_service.environnement_du_run(conn, run_id)
    except EnvironnementInvalide as err:
        raise CampaignError("environment_refused", str(err)) from err
    try:
        verifier_connexion(projet_sur(ProjectRepo(conn).get(run["project_id"]), environnement))
    except ConnexionIncomplete as err:
        raise CampaignError("no_connection", err.message()) from err

    # Lot PT-02b (A29) : les valeurs des données de test sont FIGÉES ici, au lancement, une fois pour toute la campagne. Un jeu
    # choisi qui n'existe plus (à la corbeille) : la campagne n'est pas lancée, plutôt que jouée avec d'autres valeurs.
    from testpilot.api.services import donnees_de_test_service
    from testpilot.parametres.colonne_application import ColonneImpossible
    from testpilot.store.repositories import DonneeDeTestInvalide
    try:
        donnees_de_test_service.figer_pour_la_campagne(conn, run)
    except donnees_de_test_service.PlageIncomplete as err:
        # A107 : la plage « de la ligne X à Y » n'existe pas en entier dans un cas (lignes retirées depuis la création) —
        # rien n'est lancé, plutôt que jouer moins de lignes que celles annoncées.
        raise CampaignError("range_missing", f"données de test : {err}") from err
    except DonneeDeTestInvalide as err:
        raise CampaignError("dataset_missing", f"le jeu de données de cette exécution n'est plus disponible : {err}") from err
    except ColonneImpossible as err:
        # Étape 6 (IT-4) : une colonne « depuis l'application » n'a pas pu être remplie — rien n'est lancé, plutôt que jouer
        # avec d'autres valeurs que celles annoncées.
        raise CampaignError("column_from_app", f"données de test : {err}") from err

    repo.set_status(run_id, "running", launched=True)
    # `strict` (lot 05, D5) : transmis à la tâche de fond comme le reste — un job durable relancé après un redémarrage
    # relit ces mêmes paramètres, et un job ancien (sans cette clé) retombe sur « non strict ».
    # D33 : `sans_repli` suit le même chemin ; un job ancien (sans cette clé) retombe sur la règle d'aujourd'hui (sans repli).
    return {"run_id": run_id, "case_ids": case_ids, "triggered_by": triggered_by,
            "strict": bool(run.get("strict")), "sans_repli": bool(run.get("sans_repli", 1))}


def run_campaign(run_id: int, case_ids: list[int], *, triggered_by: str = "", strict: bool = False,
                 sans_repli: bool = True) -> None:
    """Tâche de fond : exécute les cas du run EN SÉQUENCE, puis clôt la campagne.

    Chaque cas est joué par le circuit existant (`run_service`), qui persiste le verdict à deux
    axes et tente une réparation si elle est autorisée. On rattache l'exécution au run juste après
    sa création : c'est ce lien qui fait exister le « résultat du cas DANS ce run » (`0022` n°4).

    `triggered_by` (migration 32) : reporté sur CHAQUE exécution créée par cette campagne — c'est
    le même geste (« lancer CETTE campagne »), pas N déclenchements distincts.
    """
    conn = get_initialized_db()
    try:
        # Lot PT-04a : l'environnement FIGÉ au lancement (None = par défaut). Illisible ou jamais figé : aucun cas n'est joué
        # — `finally` clôt la campagne, chaque cas reste « non testé » plutôt que joué contre une autre application.
        from testpilot.api.services import environnements_service
        try:
            environnement = environnements_service.environnement_du_run(conn, run_id)
        except ValueError:
            logger.exception("[campagne %s] environnement illisible : aucun cas n'est joué", run_id)
            return
        for case_id in case_ids:
            if environnement is not None:
                # Revue du 2026-10-16 : passé en « Production » ou mis à la corbeille PENDANT la campagne, l'environnement
                # ne joue plus — les cas restants restent non testés, aucun n'est joué contre une production déclarée.
                try:
                    environnements_service.environnement_du_run(conn, run_id)
                except ValueError:
                    logger.warning("[campagne %s] environnement devenu injouable : les cas restants ne sont pas joués", run_id)
                    break
            try:
                eid, slug, cid, vid = run_service.trigger_run(conn, case_id,
                                                               triggered_by=triggered_by,
                                                               environnement=environnement)
            except run_service.RunError as err:
                # Un cas non exécutable (sans version, gate fermé) ne fait pas tomber la campagne :
                # les autres continuent. Mais rester au seul journal serveur (2026-09-15) laissait
                # le cas « Untested » sans explication à l'écran — `enregistrer_lancement_bloque`
                # rend le même verdict honnête qu'un plantage technique en cours de run, quand une
                # version existe pour le porter (`needs_review`/`no_test`/`no_connection`).
                logger.warning("[campagne %s] cas %s non lancé : %s", run_id, case_id, err.detail)
                run_service.enregistrer_lancement_bloque(
                    conn, case_id=case_id, code=err.code, message=err.detail, run_id=run_id,
                    triggered_by=triggered_by, environnement=environnement)
                continue
            # Le rattachement AVANT l'exécution : si le processus meurt en cours de route, la
            # ligne d'exécution reste reliée à sa campagne (sinon elle deviendrait orpheline).
            conn.execute("UPDATE execution SET run_id=? WHERE id=?", (run_id, eid))
            conn.commit()
            try:
                run_service.run_execution(eid, slug, cid, vid, triggered_by=triggered_by,
                                          **({"strict": True} if strict else {}),
                                          **({"sans_repli": True} if sans_repli else {}),
                                          **({"environnement": environnement} if environnement else {}))
            except Exception:
                # `run_execution` a son propre filet (statut technical_error) ; on protège quand
                # même la boucle pour que les cas suivants soient joués.
                logger.exception("[campagne %s] cas %s : exécution en échec", run_id, case_id)
    finally:
        try:
            RunRepo(conn).set_status(run_id, "completed", completed=True)
        except Exception:
            logger.exception("[campagne %s] clôture non enregistrée", run_id)
        # Best-effort ABSOLU (2026-08-12) : prévenir qui a lancé cette campagne ne doit jamais
        # empêcher sa clôture, déjà enregistrée juste au-dessus.
        try:
            notification_service.notifier_fin_de_campagne(conn, run_id, triggered_by=triggered_by)
        except Exception:
            logger.exception("[campagne %s] notification non envoyée", run_id)
        conn.close()
