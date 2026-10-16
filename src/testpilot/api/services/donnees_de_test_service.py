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
from testpilot.parametres import iterations as iterations_mod
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
    lignes = ids_des_jeux(run.get("dataset_ids"), strict=True)
    if lignes:
        # A52 : plusieurs lignes — une itération par ligne. Chacune figée, dans l'ordre choisi ; une ligne à la corbeille :
        # rien n'est lancé (`DonneeDeTestInvalide`), comme pour un seul jeu.
        depot = TestDataRepo(conn)
        jeux, noms = [], []
        for dataset_id in lignes:
            noms, niveaux = depot.niveaux(run["project_id"], dataset_id)
            valeurs = resolution.resoudre(niveaux, noms)
            jeux.append({"jeu": niveaux[-1][0] if niveaux else "", "dataset_id": dataset_id,
                         "valeurs": {n: {"valeur": v.valeur, "origine": v.origine} for n, v in valeurs.items()}})
        figes = {"jeu": ", ".join(j["jeu"] for j in jeux), "jeux": jeux, "connues": noms}
        conn.execute("UPDATE test_run SET parametres_figes=? WHERE id=?", (json.dumps(figes, ensure_ascii=False), run["id"]))
        conn.commit()
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


def _manques(conn, project_id: int | None, rendu: resolution.Remplacement) -> list[str]:
    """Chaque valeur qui manque, nommée — le même message au lancement et dans l'aperçu de la fiche d'un test."""
    a_la_corbeille = set(TestDataRepo(conn).variables_a_la_corbeille(project_id)) if project_id is not None else set()
    manques = [n if n.startswith("variable mal") else
               f"variable à la corbeille « {n} »" if n in a_la_corbeille else f"variable inconnue « {n} »"
               for n in rendu.inconnues]
    return manques + [f"variable sans valeur « {n} »" for n in rendu.sans_valeur]


def apercu(conn, case_id: int, version_id: int, dataset_id: int | None = None) -> dict:
    """Ce test tel qu'il serait joué AUJOURD'HUI avec ce jeu (« Par défaut » si aucun) — fiche d'un test, lot PT-02c.

    Même calcul que `preparer_le_script` (mêmes niveaux, même remplacement, mêmes messages) : l'aperçu ne peut pas
    annoncer un test que l'exécution jouerait autrement. Il n'écrit rien. Lève `DonneeDeTestInvalide` pour un jeu qui
    n'est pas un jeu vivant du projet."""
    version = VersionRepo(conn).get(version_id) or {}
    feature = version.get("feature_content") or ""
    project_id = _project_id_du_cas(conn, case_id)
    depot = TestDataRepo(conn)
    if dataset_id is not None and (project_id is None or depot.jeu(project_id, dataset_id) is None):
        raise DonneeDeTestInvalide(f"jeu de données {dataset_id} introuvable dans ce projet")
    noms, niveaux = depot.niveaux(project_id, dataset_id) if project_id is not None else ([], [])
    if not noms and not niveaux:   # projet qui n'a jamais déclaré de variable : joué tel quel, comme `preparer_le_script`
        return {"jeu": "", "texte": feature, "manques": [], "valeurs": {}}
    rendu = resolution.remplacer(feature, resolution.resoudre(niveaux, noms), noms)
    return {"jeu": niveaux[-1][0] if niveaux else "", "texte": rendu.texte,
            "manques": [] if rendu.complet else _manques(conn, project_id, rendu),
            "valeurs": {n: {"valeur": v.valeur, "origine": v.origine} for n, v in rendu.jouees.items()}}


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
    if isinstance(figes.get("jeux"), list):
        return _preparer_les_iterations(conn, execution_id, case_id, module_name, version, figes, campagne)
    valeurs = {n: resolution.Valeur(str(v.get("valeur", "")), str(v.get("origine", ""))) for n, v in (figes.get("valeurs") or {}).items()}
    rendu = resolution.remplacer(feature, valeurs, figes.get("connues") or [])
    if not rendu.complet:
        manques = _manques(conn, _project_id_du_cas(conn, case_id), rendu)
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


def _preparer_les_iterations(conn, execution_id: int, case_id: int, module_name: str, version: dict, figes: dict,
                             campagne: bool) -> Script:
    """A52 : plusieurs lignes figées — le test est joué une fois par ligne, dans CETTE exécution (`parametres/iterations`).

    Chaque ligne est résolue avec les mêmes règles qu'un jeu seul ; une valeur qui manque dans une ligne : le test n'est pas
    joué (« bloqué », la ligne nommée). Les itérations sont les lignes réduites aux valeurs des variables du test : une seule
    restante, il est joué comme avec un jeu seul ; aucune variable, il se joue tel quel."""
    feature = version.get("feature_content") or ""
    connues = figes.get("connues") or []
    if not figes["jeux"]:
        return Script(blocage="Données de test : les valeurs figées de cette campagne sont illisibles. Créez une nouvelle "
                              "exécution.")
    rendus = []
    for ligne in figes["jeux"]:
        if not isinstance(ligne, dict) or not isinstance(ligne.get("valeurs"), dict):
            return Script(blocage="Données de test : les valeurs figées de cette campagne sont illisibles. Créez une nouvelle "
                                  "exécution.")
        valeurs = {n: resolution.Valeur(str(v.get("valeur", "")), str(v.get("origine", "")))
                   for n, v in ligne["valeurs"].items() if isinstance(v, dict)}
        rendu = resolution.remplacer(feature, valeurs, connues)
        if not rendu.complet:
            manques = _manques(conn, _project_id_du_cas(conn, case_id), rendu)
            suite = ("Complétez le tableau des données de test, puis créez une nouvelle exécution : celle-ci garde les "
                     "valeurs figées à son lancement." if campagne else "Complétez le tableau des données de test, puis relancez.")
            return Script(blocage=f"Données de test (ligne « {ligne.get('jeu') or 'Par défaut'} ») : " + " ; ".join(manques)
                          + f". Le test n'a pas été joué. {suite}")
        rendus.append((str(ligne.get("jeu") or ""), rendu))
    # Même réduction que `iterations_mod.iterations` (deux lignes aux mêmes valeurs ne font qu'une itération), en gardant
    # pour chacune l'origine de ses valeurs (« Par défaut » hérité ou non), montrée dans le rapport.
    groupes: dict[tuple, tuple[list[str], resolution.Remplacement]] = {}
    for nom, rendu in rendus:
        cle = tuple(sorted((n, v.valeur) for n, v in rendu.jouees.items()))
        groupes.setdefault(cle, ([], rendu))[0].append(nom)
    detail = [(" / ".join(noms), rendu) for noms, rendu in groupes.values()]
    iters = [(nom, {n: v.valeur for n, v in rendu.jouees.items()}) for nom, rendu in detail]
    if len(detail) > 1:
        joues = {"jeu": figes.get("jeu") or "",
                 "iterations": [{"jeu": nom, "valeurs": {n: {"valeur": v.valeur, "origine": v.origine}
                                                         for n, v in rendu.jouees.items()}} for nom, rendu in detail],
                 "valeurs": {}}
    else:   # une seule itération (mêmes valeurs pour ce test, ou aucune variable) : consignée comme un jeu seul
        nom, rendu = detail[0]
        joues = {"jeu": nom, "valeurs": {n: {"valeur": v.valeur, "origine": v.origine} for n, v in rendu.jouees.items()}}
    conn.execute("UPDATE execution SET parametres_joues=? WHERE id=?", (json.dumps(joues, ensure_ascii=False), execution_id))
    conn.commit()
    if not rendus[0][1].jouees:
        return Script(parametres_joues=joues)   # aucune variable dans ce test : une seule itération, il se joue tel quel
    if len(iters) == 1:
        texte = rendus[0][1].texte
    else:
        try:
            texte = iterations_mod.en_plan_de_scenario(feature, iters, connues)
        except iterations_mod.IterationsImpossibles as exc:
            return Script(blocage=f"Itérations : {exc}. Le test n'a pas été joué.")
    dossier = Path(config.DATA_DIR) / "executions" / str(execution_id) / "script"
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / f"{module_name}.feature").write_text(texte, encoding="utf-8")
    (dossier / f"{module_name}_steps.py").write_text(version.get("steps_content") or "", encoding="utf-8")
    return Script(dossier=dossier, parametres_joues=joues)


# ── Création des exécutions : une par environnement, toutes les lignes dedans (A52) ──────────────────────────────────────

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


def creer_les_executions(conn, *, project_id: int, nom: str, jeux: list[dict], created_by: str = "",
                         description: str = "", refs: str = "", environnements: list[dict | None] | None = None,
                         nommer_le_jeu: bool = False, **champs) -> tuple[int | None, int, list[int]]:
    """Décision A52 : UNE exécution par environnement (PT-04a), qui joue TOUTES les lignes choisies — une itération par ligne,
    jamais une exécution par ligne (remplace la règle d'A28 « une exécution par jeu, regroupées dans un plan »). Plusieurs
    environnements : leurs exécutions sont regroupées dans un plan qui porte `nom`. Rend (plan ou None, première exécution,
    toutes les exécutions). `champs` : ceux de `RunRepo.create` (sélection, mode, cas…).

    Un seul jeu : posé comme avant (`dataset_id`) ; plusieurs : `dataset_ids`, le jeu « Par défaut » en tête s'il est
    choisi."""
    from testpilot.api.services import environnements_service
    from testpilot.store.repositories import ProjectRepo

    jeux = sorted(jeux, key=lambda j: not j["est_defaut"])
    lignes = ({"dataset_id": jeux[0]["id"]} if len(jeux) == 1 else {"dataset_ids": [j["id"] for j in jeux]} if jeux else {})
    environnements = environnements or [None]
    if nommer_le_jeu and len(jeux) == 1 and len(environnements) == 1:
        nom = f"{nom} — {jeux[0]['nom']}"   # une planification à un seul jeu le nommait déjà ainsi (R1)
    if len(environnements) == 1:
        environnement = environnements[0]
        run_id = RunRepo(conn).create(project_id=project_id, name=nom, description=description, refs=refs,
                                      environment_id=environnement["id"] if environnement else None, **lignes, **champs)
        return None, run_id, [run_id]
    projet = ProjectRepo(conn).get(project_id) or {}
    plan_id = PlanRepo(conn).create(project_id=project_id, name=nom, description=description, refs=refs,
                                    created_by=created_by)
    run_ids = []
    for environnement in environnements:
        run_id = RunRepo(conn).create(project_id=project_id,
                                      name=f"{nom} — {environnements_service.nom_de(conn, projet, environnement)}",
                                      description=description, refs=refs,
                                      environment_id=environnement["id"] if environnement else None, **lignes, **champs)
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
