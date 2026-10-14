"""Données de test au LANCEMENT d'une exécution (lot PT-02b, décisions A26 à A29).

Deux moments, et seulement ces deux-là :

1. **Au lancement d'une campagne** (`figer_pour_la_campagne`) : les valeurs du jeu choisi — ou du jeu « Par défaut » —
   sont résolues UNE FOIS et figées sur la campagne (`test_run.parametres_figes`, A29). Relancer la campagne reprend les
   mêmes ; modifier le tableau ensuite ne change rien à ce qui est joué.
2. **Juste avant de jouer un cas** (`preparer_le_script`) : les variables `{{nom}}` du test sont remplacées dans une COPIE
   propre à cette exécution (`data/executions/<id>/script/`) — jamais dans le fichier partagé du cas, que d'autres
   exécutions lisent au même moment. Ce que le test a réellement reçu est consigné sur l'exécution
   (`execution.parametres_joues`). Une variable inconnue, sans valeur, mal écrite ou mal placée : le cas n'est PAS joué, il
   sort « bloqué » avec la variable nommée — jamais une chaîne `{{nom}}` saisie telle quelle dans l'application.

Ce qui ne change pas (règle R1 du plan) : un projet sans variable, ou un cas joué hors campagne dont le projet n'en a pas,
suit exactement le chemin d'aujourd'hui — même fichier, octet pour octet.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from testpilot import config
from testpilot.parametres import resolution
from testpilot.store.repositories import DonneeDeTestInvalide, PlanRepo, RunRepo, TestDataRepo, VersionRepo


@dataclass
class Script:
    dossier: Path | None = None          # où lire le test à jouer ; None = le chemin d'aujourd'hui
    parametres_joues: dict = field(default_factory=dict)
    blocage: str = ""                    # non vide : le cas n'est pas joué, il sort « bloqué » avec ce message


def figer_pour_la_campagne(conn, run: dict) -> None:
    """Fige les valeurs de la campagne au lancement — une seule fois : une relance reprend ce qui est déjà figé.

    Lève `DonneeDeTestInvalide` si le jeu choisi n'existe plus (à la corbeille) : la campagne n'est alors pas lancée, plutôt
    que jouée avec d'autres valeurs que celles annoncées. Un projet sans variable et sans jeu choisi : rien n'est figé."""
    if (run.get("parametres_figes") or "").strip():
        return
    noms, niveaux = TestDataRepo(conn).niveaux(run["project_id"], run.get("dataset_id"))
    # « Rien à figer » seulement pour un projet qui n'a JAMAIS déclaré de variable (aucun jeu, pas même « Par défaut », qui
    # naît avec la première et ne se supprime pas). Un projet dont toutes les variables sont à la corbeille fige un tableau
    # VIDE : ses tests qui écrivent `{{nom}}` sortiront « bloqué » (A31) — revue du 2026-10-14, ils étaient joués tels quels.
    if not noms and not niveaux and run.get("dataset_id") is None:
        return
    valeurs = resolution.resoudre(niveaux, noms)
    figes = {"jeu": niveaux[-1][0] if niveaux else "", "dataset_id": run.get("dataset_id"), "connues": noms,
             "valeurs": {n: {"valeur": v.valeur, "origine": v.origine} for n, v in valeurs.items()}}
    conn.execute("UPDATE test_run SET parametres_figes=? WHERE id=?", (json.dumps(figes, ensure_ascii=False), run["id"]))
    conn.commit()


def _figes_de_l_execution(conn, execution_id: int) -> dict | None:
    ligne = conn.execute("SELECT r.parametres_figes FROM execution e JOIN test_run r ON r.id = e.run_id WHERE e.id=?",
                         (execution_id,)).fetchone()
    texte = (ligne[0] if ligne else "") or ""
    if not texte.strip():
        return None
    try:
        figes = json.loads(texte)
    except ValueError:
        return {"illisible": True}
    return figes if isinstance(figes, dict) else {"illisible": True}


def _project_id_du_cas(conn, case_id: int) -> int | None:
    ligne = conn.execute("SELECT m.project_id FROM test_case tc JOIN module m ON m.id = tc.module_id WHERE tc.id=?",
                         (case_id,)).fetchone()
    return ligne[0] if ligne else None


def preparer_le_script(conn, execution_id: int, case_id: int, version_id: int, module_name: str) -> Script:
    """Le test à jouer pour CETTE exécution. Voir la docstring du module."""
    version = VersionRepo(conn).get(version_id) or {}
    feature = version.get("feature_content") or ""
    figes = _figes_de_l_execution(conn, execution_id)
    campagne = figes is not None
    if figes is not None and figes.get("illisible"):
        return Script(blocage="Données de test : les valeurs figées de cette campagne sont illisibles. Créez une nouvelle "
                              "exécution.")
    if figes is None:
        # Hors campagne figée (un cas lancé seul) : le jeu « Par défaut » du moment, figé pour cette seule exécution.
        project_id = _project_id_du_cas(conn, case_id)
        noms, niveaux = TestDataRepo(conn).niveaux(project_id) if project_id is not None else ([], [])
        if not noms and not niveaux:
            return Script()   # un projet qui n'a jamais déclaré de variable : le chemin d'aujourd'hui, octet pour octet
        figes = {"jeu": niveaux[-1][0] if niveaux else "", "connues": noms,
                 "valeurs": {n: {"valeur": v.valeur, "origine": v.origine} for n, v in resolution.resoudre(niveaux, noms).items()}}
    valeurs = {n: resolution.Valeur(str(v.get("valeur", "")), str(v.get("origine", ""))) for n, v in (figes.get("valeurs") or {}).items()}
    rendu = resolution.remplacer(feature, valeurs, figes.get("connues") or [])
    if not rendu.complet:
        project_id = _project_id_du_cas(conn, case_id)
        a_la_corbeille = set(TestDataRepo(conn).variables_a_la_corbeille(project_id)) if project_id is not None else set()
        manques = [n if n.startswith("variable mal") else
                   f"variable à la corbeille « {n} »" if n in a_la_corbeille else f"variable inconnue « {n} »"
                   for n in rendu.inconnues]
        manques += [f"variable sans valeur « {n} »" for n in rendu.sans_valeur]
        # Une campagne garde les valeurs figées à SON lancement (A29) : la relancer rejouerait le même manque.
        suite = ("Complétez le tableau des données de test, puis créez une nouvelle exécution : celle-ci garde les valeurs "
                 "figées à son lancement." if campagne else "Complétez le tableau des données de test, puis relancez.")
        return Script(blocage=f"Données de test (jeu « {figes.get('jeu') or 'Par défaut'} ») : " + " ; ".join(manques)
                      + f". Le test n'a pas été joué. {suite}")
    joues = {"jeu": figes.get("jeu") or "", "valeurs": {n: {"valeur": v.valeur, "origine": v.origine} for n, v in rendu.jouees.items()}}
    if rendu.jouees or campagne:   # consigné dès qu'une valeur a été posée, ou que la campagne joue un jeu de données
        conn.execute("UPDATE execution SET parametres_joues=? WHERE id=?", (json.dumps(joues, ensure_ascii=False), execution_id))
        conn.commit()
    if rendu.texte == feature:
        return Script(parametres_joues=joues)   # aucune variable dans ce test : il se joue tel quel
    dossier = Path(config.DATA_DIR) / "executions" / str(execution_id) / "script"
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / f"{module_name}.feature").write_text(rendu.texte, encoding="utf-8")
    (dossier / f"{module_name}_steps.py").write_text(version.get("steps_content") or "", encoding="utf-8")
    return Script(dossier=dossier, parametres_joues=joues)


# ── Une exécution par jeu de données (A28, A35) — lancement à la main ET planification ────────────────────────────────────

JEUX_PAR_LANCEMENT_MAX = 50   # A28 : au-delà, un lancement par erreur créerait des dizaines d'exécutions


def jeux_demandes(conn, project_id: int, dataset_ids: list[int], *, maximum: int = JEUX_PAR_LANCEMENT_MAX) -> list[dict]:
    """Les jeux demandés, vérifiés : du projet, vivants, sans doublon, `maximum` au plus. Lève `DonneeDeTestInvalide` avec
    un message à montrer tel quel — rien n'est créé."""
    demandes = list(dict.fromkeys(dataset_ids))
    if len(demandes) > maximum:
        raise DonneeDeTestInvalide(f"{maximum} jeux de données au plus par lancement")
    depot = TestDataRepo(conn)
    jeux = []
    for dataset_id in demandes:
        jeu = depot.jeu(project_id, dataset_id)
        if jeu is None:
            raise DonneeDeTestInvalide(f"jeu de données {dataset_id} introuvable dans ce projet")
        jeux.append(jeu)
    return jeux


def creer_une_execution_par_jeu(conn, *, project_id: int, nom: str, jeux: list[dict], created_by: str = "",
                                description: str = "", refs: str = "", **champs) -> tuple[int, int, list[int]]:
    """Plusieurs jeux (A28) : une exécution PAR jeu, regroupées dans un plan qui porte `nom`. Rend (plan, première
    exécution, toutes les exécutions dans l'ordre). `champs` : ceux de `RunRepo.create` (sélection, mode, cas…).

    Décision A35 : la PREMIÈRE (le jeu « Par défaut » s'il est demandé) joue tous les tests ; les suivantes, la même
    sélection, mais seulement les tests qui écrivent des variables — un test sans variable rejoué à l'identique pour chaque
    jeu ne prouverait rien de plus. Ce tri se fait au LANCEMENT (`RunRepo.case_ids`), pas ici : figé à la création, il
    oubliait un test qui gagne une variable avant le lancement (revue du 2026-10-14)."""
    jeux = sorted(jeux, key=lambda j: not j["est_defaut"])
    plan_id = PlanRepo(conn).create(project_id=project_id, name=nom, description=description, refs=refs,
                                    created_by=created_by)
    run_ids = []
    for rang, jeu in enumerate(jeux):
        run_id = RunRepo(conn).create(project_id=project_id, name=f"{nom} — {jeu['nom']}", description=description,
                                      refs=refs, dataset_id=jeu["id"], seulement_variables=rang > 0, **champs)
        PlanRepo(conn).assign_run(plan_id, run_id)
        run_ids.append(run_id)
    return plan_id, run_ids[0], run_ids


def ids_des_jeux(texte: str | None, *, strict: bool = False) -> list[int]:
    """Les jeux d'une planification (`scheduled_run.dataset_ids`, liste JSON). Illisible : `[]` pour l'affichage ; avec
    `strict` (au déclenchement), `DonneeDeTestInvalide` — jamais le jeu « Par défaut » joué à la place de jeux illisibles."""
    if not (texte or "").strip():
        return []
    try:
        ids = json.loads(texte)
    except ValueError:
        ids = None
    if not isinstance(ids, list) or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids):
        if strict:
            raise DonneeDeTestInvalide("les jeux de données de la planification sont illisibles")
        return []
    return ids
