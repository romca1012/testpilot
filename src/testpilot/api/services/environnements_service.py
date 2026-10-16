"""Environnements d'un projet au LANCEMENT d'une exécution (lot PT-04a, décisions A48 à A50 du porteur, 2026-10-16).

Trois moments :

1. **À la création** d'une exécution ou d'une planification (`environnements_demandes`) : les environnements choisis sont
   vérifiés — du projet, vivants, jamais « Production » (A48). Rien n'est créé sur un refus.
2. **Au lancement** (`figer_pour_la_campagne`) : l'environnement de la campagne est relu et FIGÉ (`test_run.environnement_fige`)
   — un environnement passé en « Production », mis à la corbeille ou introuvable entre-temps : la campagne n'est pas
   lancée, plutôt que jouée ailleurs que ce qui était annoncé.
3. **Pour jouer chaque cas** (`environnement_du_run`) : ce qui a été figé, lu par `run_service` pour taper la bonne
   application (`parametres/environnements.projet_sur`).

Un projet sans environnement ajouté suit exactement le chemin d'avant : rien n'est figé, rien n'est remplacé (règle R1).
"""

from __future__ import annotations

from testpilot.parametres import environnements as env
from testpilot.parametres.environnements import EnvironnementInvalide
from testpilot.store.repositories import ProjectEnvironmentRepo, ProjectRepo


def defaut_du_projet(projet: dict) -> dict:
    """L'environnement PAR DÉFAUT tel que l'écran le montre : le projet lui-même (son adresse n'est pas déplacée)."""
    oracle = projet.get("oracle_base_url", "") if (projet.get("oracle_type") or "").lower() == "http" else ""
    return {"id": env.DEFAUT, "nom": env.nom_affiche(projet.get("environnement_nom")), "base_url": projet.get("base_url", ""),
            "database": projet.get("database", ""), "connector_version": projet.get("connector_version", ""),
            "oracle_base_url": oracle, "nature": env.NATURE_TEST, "est_defaut": True}


def liste(conn, projet: dict) -> list[dict]:
    """Tous les environnements du projet, le défaut en tête."""
    ajoutes = [{**e, "est_defaut": False} for e in ProjectEnvironmentRepo(conn).liste(projet["id"])]
    return [defaut_du_projet(projet), *ajoutes]


def environnements_demandes(conn, project_id: int, ids: list[int]) -> list[dict | None]:
    """Les environnements choisis, vérifiés (None = par défaut). Vide : le défaut seul, comme avant. Lève
    `EnvironnementInvalide` avec un message à montrer tel quel — rien n'est créé."""
    demandes = list(dict.fromkeys(ids or [env.DEFAUT]))
    if len(demandes) > env.ENVIRONNEMENTS_MAX:
        raise EnvironnementInvalide(f"{env.ENVIRONNEMENTS_MAX} environnements au plus par lancement")
    depot = ProjectEnvironmentRepo(conn)
    choisis: list[dict | None] = []
    for environment_id in demandes:
        if environment_id == env.DEFAUT:
            choisis.append(None)
            continue
        trouve = depot.get(project_id, environment_id)
        if trouve is None:
            raise EnvironnementInvalide(f"environnement {environment_id} introuvable dans ce projet")
        if env.est_production(trouve):
            raise EnvironnementInvalide(f"« {trouve['nom']} » est un environnement de production : aucun test n'y est joué")
        choisis.append(trouve)
    return choisis


def nom_de(conn, projet: dict, environnement: dict | None) -> str:
    return environnement["nom"] if environnement else env.nom_affiche(projet.get("environnement_nom"))


def a_des_environnements(conn, project_id: int) -> bool:
    return bool(ProjectEnvironmentRepo(conn).liste(project_id))


def figer_pour_la_campagne(conn, run: dict) -> None:
    """Fige l'environnement de la campagne au lancement — une seule fois : une relance reprend ce qui est déjà figé.

    Lève `EnvironnementInvalide` si l'environnement choisi n'existe plus, est à la corbeille ou est devenu « Production ».
    L'environnement par défaut n'est figé (pour son NOM seulement, à l'affichage) que si le projet en a d'autres : un projet
    sans environnement ajouté ne voit rien changer."""
    deja = env.lire_fige(run.get("environnement_fige"))
    if deja is not None:
        # Revue du 2026-10-16 (bloquant) : une RELANCE revérifie l'environnement vivant — passé en « Production » ou mis à
        # la corbeille depuis le premier lancement, il ne joue plus (A48). Les valeurs jouées restent celles figées.
        _toujours_jouable(conn, run["project_id"], run.get("environment_id"), deja)
        return
    environment_id = run.get("environment_id")
    if environment_id is None:
        if not a_des_environnements(conn, run["project_id"]):
            return
        projet = ProjectRepo(conn).get(run["project_id"]) or {}
        fige = env.figer(defaut_du_projet(projet), environment_id=env.DEFAUT)
    else:
        trouve = ProjectEnvironmentRepo(conn).get(run["project_id"], environment_id)
        if trouve is None:
            raise EnvironnementInvalide("l'environnement de cette exécution n'est plus disponible (supprimé)")
        if env.est_production(trouve):
            raise EnvironnementInvalide(f"« {trouve['nom']} » est un environnement de production : aucun test n'y est joué")
        fige = env.figer(trouve, environment_id=environment_id)
    conn.execute("UPDATE test_run SET environnement_fige=? WHERE id=?", (fige, run["id"]))
    conn.commit()


def _toujours_jouable(conn, project_id: int, environment_id: int | None, fige: dict) -> None:
    """L'environnement figé est-il ENCORE jouable ? Celui de l'id figé doit être celui du run, vivant, et de nature « Test »
    — relu à chaque lancement et à chaque reprise d'une campagne (job durable relancé après un redémarrage)."""
    attendu = env.DEFAUT if environment_id is None else environment_id
    if fige.get("id") != attendu:
        raise EnvironnementInvalide("l'environnement figé de cette exécution ne correspond pas à celui choisi")
    if env.est_production(fige):
        raise EnvironnementInvalide(f"« {fige['nom']} » est un environnement de production : aucun test n'y est joué")
    if environment_id is None:
        return
    vivant = ProjectEnvironmentRepo(conn).get(project_id, environment_id)
    if vivant is None:
        raise EnvironnementInvalide("l'environnement de cette exécution n'est plus disponible (supprimé)")
    if env.est_production(vivant):
        raise EnvironnementInvalide(f"« {vivant['nom']} » est devenu un environnement de production : aucun test n'y est joué")


def environnement_du_run(conn, run_id: int) -> dict | None:
    """L'environnement AJOUTÉ figé pour cette campagne, ou None (l'environnement par défaut : le projet tel quel).

    Un run qui désigne un environnement ajouté sans l'avoir figé (lancé par un chemin qui ne fige pas) : `EnvironnementInvalide`
    — jamais l'environnement par défaut joué à sa place."""
    ligne = conn.execute("SELECT project_id, environment_id, environnement_fige FROM test_run WHERE id=?",
                         (run_id,)).fetchone()
    if ligne is None:
        return None
    fige = env.lire_fige(ligne["environnement_fige"])
    if fige is None:
        if ligne["environment_id"] is not None:
            raise EnvironnementInvalide("l'environnement de cette exécution n'a pas été figé au lancement")
        return None
    _toujours_jouable(conn, ligne["project_id"], ligne["environment_id"], fige)
    if fige["id"] == env.DEFAUT:
        return None
    return fige


def libelle_du_run(run: dict) -> str:
    """Le nom de l'environnement figé, pour l'écran — vide si rien n'a été figé (projet sans environnement ajouté)."""
    try:
        fige = env.lire_fige(run.get("environnement_fige"))
    except EnvironnementInvalide:
        return ""
    return (fige or {}).get("nom", "")
