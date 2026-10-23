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
from testpilot.parametres import calcul_au_lancement
from testpilot.parametres import iterations as iterations_mod
from testpilot.parametres import resolution
from testpilot.store.repositories import (
    CaseDataRepo,
    CaseRepo,
    DonneeDeTestInvalide,
    PlanRepo,
    RunRepo,
    TestDataRepo,
    VersionRepo,
)


@dataclass
class Script:
    dossier: Path | None = None          # où lire le test à jouer ; None = le chemin d'aujourd'hui
    parametres_joues: dict = field(default_factory=dict)
    comptes_par_iteration: bool = False  # étape 4, morceau 7 : le serveur a écrit la colonne `tp_compte` (le harnais y obéit)
    blocage: str = ""                    # non vide : le cas n'est pas joué, il sort « bloqué » avec ce message


def figer_pour_la_campagne(conn, run: dict) -> None:
    """Fige les valeurs de la campagne au lancement — une seule fois : une relance reprend ce qui est déjà figé.

    Lève `DonneeDeTestInvalide` si le jeu choisi n'existe plus (à la corbeille) : la campagne n'est alors pas lancée, plutôt
    que jouée avec d'autres valeurs que celles annoncées. Un projet sans variable et sans jeu choisi : rien n'est figé.
    A57/A58 : les lignes propres à chaque cas de la campagne sont figées avec le reste (`lignes_des_cas`), et la liste des
    cas présents au lancement (`cas_figes`). Une seule écriture (revue du 2026-10-19 : en deux, une erreur entre les deux
    laissait une campagne figée sans les lignes de ses cas, à jamais)."""
    if (run.get("parametres_figes") or "").strip():
        return
    figes = _figes_du_projet(conn, run)
    if figes is None:   # projet sans variable : rien à figer, comme avant (R1) — une ligne de cas n'y porte aucune valeur
        return
    # Étape 6 (IT-4, interrupteur éteint) : les colonnes dont la source est l'application, relevées MAINTENANT sur l'application
    # de l'environnement de la campagne, et figées avec le reste (A29) — un cas n'en est multiplié qu'au moment de le jouer, si
    # son test les emploie (`_avec_les_colonnes_de_l_application`). Une colonne vide ou illisible : rien n'est lancé.
    from testpilot.generation import interrupteurs
    if interrupteurs.colonne_depuis_l_application_actif():
        from testpilot.api.services import colonnes_application_service, environnements_service
        from testpilot.parametres.environnements import projet_sur
        from testpilot.store.repositories import ProjectRepo
        projet = projet_sur(ProjectRepo(conn).get(run["project_id"]),
                            environnements_service.environnement_du_run(conn, run["id"]))
        colonnes = colonnes_application_service.relever_les_colonnes(conn, projet)
        if colonnes:
            figes["colonnes_de_l_application"] = colonnes
    lignes, cas = _lignes_des_cas_de_la_campagne(conn, run)
    figes["cas_figes"] = cas
    if lignes:
        figes["lignes_des_cas"] = lignes
    conn.execute("UPDATE test_run SET parametres_figes=? WHERE id=?", (json.dumps(figes, ensure_ascii=False), run["id"]))
    conn.commit()


class PlageIncomplete(ValueError):
    """A107 : la plage de lignes choisie n'existe pas EXACTEMENT dans un cas de la campagne — rien n'est lancé."""


def cas_hors_plage(conn, project_id: int, case_ids, fin: int) -> list[str]:
    """A107 (porteur, 2026-10-23 : « la plage doit être exactement celle qui existe ») : les titres des cas qui ont leurs
    propres lignes mais pas la ligne `fin`. Un cas SANS lignes propres n'est pas concerné : il se joue une fois, avec les
    valeurs du projet, comme avec « la première seulement »."""
    depot = CaseDataRepo(conn)
    avec_lignes = set(depot.cas_avec_lignes(project_id))
    titres = []
    for case_id in dict.fromkeys(case_ids or []):
        if case_id in avec_lignes and len(depot.lignes(case_id)) < fin:
            titres.append((CaseRepo(conn).get(case_id) or {}).get("title") or f"cas {case_id}")
    return titres


def message_hors_plage(titres: list[str], debut: int, fin: int) -> str:
    return (f"la plage « de la ligne {debut} à {fin} » n'existe pas dans : " + ", ".join(f"« {t} »" for t in titres)
            + " — choisissez une plage que tous ces cas ont, ou ajoutez-leur des lignes")


def _lignes_des_cas_de_la_campagne(conn, run: dict) -> tuple[dict[str, list[dict]], list[int]]:
    """({case_id: [{jeu, valeurs: {nom: {valeur, origine}}}]} pour les cas qui ont leurs propres lignes — toutes, la
    première seulement (`test_run.lignes_des_cas`, A58), ou de la ligne X à Y (`ligne_debut`/`ligne_fin`, A107) ; les cas
    de la campagne à cet instant). Une plage qu'un cas n'a pas en entier : `PlageIncomplete`, jamais une plage raccourcie
    en silence (l'écran annoncerait des lignes jamais jouées)."""
    depot = CaseDataRepo(conn)
    avec_lignes = set(depot.cas_avec_lignes(run["project_id"]))
    premiere = (run.get("lignes_des_cas") or "toutes") == "premiere"
    debut, fin = run.get("ligne_debut"), run.get("ligne_fin")
    cas = list(RunRepo(conn).case_ids(run["id"]))
    if debut is not None and fin is not None:
        manquants = cas_hors_plage(conn, run["project_id"], cas, fin)
        if manquants:
            raise PlageIncomplete(message_hors_plage(manquants, debut, fin))
    figees = {}
    for case_id in cas:
        if case_id not in avec_lignes:
            continue
        niveaux = depot.niveaux(case_id)
        comptes = _comptes_des_lignes(conn, case_id, run["project_id"])
        if premiere:
            niveaux = niveaux[:1]
        elif debut is not None and fin is not None:
            # Les comptes suivent les lignes rang pour rang : découpés de la même façon (sinon la ligne 2 prendrait le
            # compte de la ligne 1).
            niveaux, comptes = niveaux[debut - 1:fin], comptes[debut - 1:fin]
        if niveaux:
            # Étape 4, morceau 7 : le compte de chaque ligne, figé au lancement avec ses valeurs (A29).
            figees[str(case_id)] = _lignes_jouables(niveaux, comptes)
    return figees, cas


def _lignes_jouables(niveaux: list[tuple[str, dict[str, str]]], comptes: list[dict] | None = None) -> list[dict]:
    """`comptes` (étape 4, morceau 7) : `[{libelle}]` dans le même ordre — `libelle` None : la ligne reprend le compte du cas ;
    `"compte supprimé"` est un blocage (A92). Absent : les lignes d'avant, sans compte."""
    lignes = [{"jeu": nom, "valeurs": {n: {"valeur": v, "origine": nom} for n, v in valeurs.items()}} for nom, valeurs in niveaux]
    for ligne, compte in zip(lignes, comptes or []):
        if compte.get("choisi"):
            ligne["compte"] = compte.get("libelle")
            # Revue : figé par IDENTIFIANT — un compte supprimé ou renommé après le lancement se relit au moment de jouer (A92).
            ligne["compte_id"] = compte.get("compte_id")
    return lignes


COMPTE_SUPPRIME = "\x00compte supprimé"   # jamais un libellé saisissable : un blocage, pas un compte


def _comptes_des_lignes(conn, case_id: int, project_id: int | None) -> list[dict]:
    """`[{choisi, libelle}]` des lignes du cas (A90) — le libellé du compte choisi, « principal », ou le marqueur d'un compte
    supprimé depuis (A92 : le test ne sera pas joué, jamais le principal à sa place)."""
    from testpilot.store.repositories import ProjectAccountRepo

    lignes = CaseDataRepo(conn).comptes_des_lignes(case_id)
    if not any(l["choisi"] for l in lignes):
        return []
    comptes = {c["id"]: c["label"] for c in ProjectAccountRepo(conn).liste(project_id)} if project_id is not None else {}
    return [{"choisi": l["choisi"], "compte_id": l["compte_id"],
             "libelle": ("principal" if l["compte_id"] is None else comptes.get(l["compte_id"], COMPTE_SUPPRIME))
             if l["choisi"] else None} for l in lignes]


def _ecart_des_lignes_figees(conn, case_id: int, version: dict, jeux: list, *, campagne: bool = False) -> str:
    """Le compte EFFECTIF de chaque ligne jouée (la sienne, figée ; sinon celui du cas) doit être un compte pour lequel le test a
    été écrit (`ecrit_pour.comptes_des_lignes`, sinon le seul compte de l'écriture). Rend le blocage, ou "" ."""
    from testpilot.api.services.modele_du_cas import ecrit_pour_de_la_version

    if not (version.get("feature_content") or "").strip():
        return ""
    ecrit = ecrit_pour_de_la_version(VersionRepo(conn).list_for_case(case_id), version)
    ecrits = set(ecrit.get("comptes_des_lignes") or [ecrit.get("compte_id") or 0])
    du_cas = _compte_du_cas(conn, version, _project_id_du_cas(conn, case_id))
    for ligne in jeux:
        if not isinstance(ligne, dict):
            continue
        a_son_compte = "compte" in ligne
        # Le compte_id figé s'il existe (données figées anciennes : sinon le libellé « principal » vaut 0).
        effectif = (ligne["compte_id"] if "compte_id" in ligne else None if a_son_compte else version.get("compte_id")) or 0
        if effectif not in ecrits:
            libelle = ligne.get("compte") if a_son_compte else du_cas
            suite = (" Cette exécution garde les comptes figés à son lancement : corrigez la fiche, puis créez une nouvelle "
                     "exécution." if campagne else "")
            return (f"Données de test : la ligne « {ligne.get('jeu') or 'Par défaut'} » est jouée en tant que « {libelle} », le "
                    "test n'a pas été écrit pour ce compte — régénérez le test, ou remettez cette ligne sur le compte pour "
                    f"lequel il a été écrit. Le test n'a pas été joué.{suite}")
    return ""


def _compte_du_cas(conn, version: dict, project_id: int | None) -> str:
    """Le libellé du compte « Joué en tant que » de la version — ce que reprend une ligne sans compte (A91)."""
    from testpilot.store.repositories import ProjectAccountRepo

    compte_id = (version or {}).get("compte_id")
    if compte_id is None or project_id is None:
        return "principal"
    compte = ProjectAccountRepo(conn).lire(project_id, compte_id)
    return compte["label"] if compte else COMPTE_SUPPRIME


def _avec_les_colonnes_de_l_application(figes: dict, feature: str, lignes_du_cas) -> dict | str:
    """Étape 6 (IT-4) : les valeurs figées de CE cas, une itération par valeur relevée des colonnes que SON test emploie et
    qu'aucune de ses lignes ne fixe — ou le message de blocage. Revue du 2026-10-22 : (B1) un test qui n'emploie pas la
    variable n'est pas multiplié (trois clients annoncés, un seul joué) ; (B2) une variable relevée dans un « Alors » est
    refusée — le test comparerait l'application à elle-même et sortirait « conforme » sur un défaut."""
    from testpilot.generation.variables_de_test import refus_preparation_dans_les_alors
    from testpilot.parametres import colonne_application as ca

    colonnes = ca.colonnes_a_jouer(figes, feature, _variables_des_lignes(lignes_du_cas or []))
    if not colonnes:
        return figes
    dans_un_alors = refus_preparation_dans_les_alors(feature, set(colonnes))
    if dans_un_alors:
        return ("Données de test : " + ", ".join("{{" + n + "}}" for n in sorted(colonnes)) + " vient de l'application — "
                "elle sert à préparer le test, jamais à vérifier (un « Alors » qui l'emploie comparerait l'application à "
                "elle-même). Retirez-la de l'« Alors », ou retirez sa source. Le test n'a pas été joué.")
    try:
        return ca.etendre_les_figes(figes, colonnes, JEUX_PAR_LANCEMENT_MAX)
    except ca.ColonneImpossible as exc:
        return f"Données de test : {exc}. Le test n'a pas été joué."


def _avec_les_lignes_du_cas(figes: dict, lignes: list[dict]) -> dict:
    """A57/A58 : chaque ligne propre au cas, posée PAR-DESSUS chaque ligne du projet jouée — la valeur du cas l'emporte, une
    case vide du cas reprend celle du projet. Par défaut seule « Par défaut » est jouée : le cas joue alors exactement ses
    lignes."""
    bases = figes["jeux"] if isinstance(figes.get("jeux"), list) else [{"jeu": figes.get("jeu") or "",
                                                                        "valeurs": figes.get("valeurs") or {}}]
    jeux = []
    for base in bases:
        for ligne in lignes:
            nom = ligne["jeu"] if len(bases) == 1 else f"{base.get('jeu') or 'Par défaut'} · {ligne['jeu']}"
            jeux.append({"jeu": nom, "valeurs": {**(base.get("valeurs") or {}), **ligne["valeurs"]},
                         **({"compte": ligne["compte"], "compte_id": ligne.get("compte_id")} if "compte" in ligne else {})})
    return {"jeu": figes.get("jeu") or "", "jeux": jeux, "connues": figes.get("connues") or []}


def _variables_des_lignes(lignes: list[dict]) -> set[str]:
    return {n for ligne in lignes for n in (ligne.get("valeurs") or {})}


def ecart_lignes_test(feature: str, variables_des_lignes) -> list[str]:
    """Revue du 2026-10-19 (bloquant) : les variables que les lignes du cas font varier et que son test n'emploie pas. Le
    test écrit alors la valeur en dur : ses lignes fusionneraient en UNE itération, jouée avec cette seule valeur, et
    l'écran annoncerait toutes les classes jouées — un « conforme » sur des valeurs jamais posées. Non vide : le test ne se
    joue pas (A59, porteur, 2026-10-19 ; même règle qu'A42). Rien sans test technique."""
    if not (feature or "").strip():
        return []
    employees = set(resolution.references(feature))
    return [f"les lignes du cas donnent « {{{{{nom}}}}} », le test ne l'emploie pas"
            for nom in sorted(set(variables_des_lignes)) if nom not in employees]


def _figes_du_projet(conn, run: dict) -> dict | None:
    """Les valeurs du tableau du PROJET (jeu choisi, ou lignes choisies) — `None` : rien à figer."""
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
        return {"jeu": ", ".join(j["jeu"] for j in jeux), "jeux": jeux, "connues": noms}
    noms, niveaux = TestDataRepo(conn).niveaux(run["project_id"], run.get("dataset_id"))
    # « Rien à figer » seulement pour un projet qui n'a JAMAIS déclaré de variable (aucun jeu, pas même « Par défaut », qui
    # naît avec la première et ne se supprime pas). Un projet dont toutes les variables sont à la corbeille fige un tableau
    # VIDE : ses tests qui écrivent `{{nom}}` sortiront « bloqué » (A31) — revue du 2026-10-14, ils étaient joués tels quels.
    if not noms and not niveaux and run.get("dataset_id") is None:
        return None
    valeurs = resolution.resoudre(niveaux, noms)
    return {"jeu": niveaux[-1][0] if niveaux else "", "dataset_id": run.get("dataset_id"), "connues": noms,
            "valeurs": {n: {"valeur": v.valeur, "origine": v.origine} for n, v in valeurs.items()}}


def _figes_de_l_execution(conn, execution_id: int) -> dict | None:
    ligne = conn.execute("SELECT r.parametres_figes FROM execution e JOIN test_run r ON r.id = e.run_id WHERE e.id=?",
                         (execution_id,)).fetchone()
    texte = (ligne["parametres_figes"] if ligne else "") or ""
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
    return ligne["project_id"] if ligne else None


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
    # A57 (revue du 2026-10-19) : un cas qui a ses propres lignes est joué avec elles — l'aperçu montre la PREMIÈRE, posée
    # par-dessus le projet, et dit l'écart qui bloquerait l'exécution.
    du_cas = CaseDataRepo(conn).niveaux(case_id)
    ecart = ecart_lignes_test(feature, {n for _, v in du_cas for n in v}) if du_cas else []
    niveaux = niveaux + du_cas[:1]
    rendu = resolution.remplacer(feature, resolution.resoudre(niveaux, noms), noms)
    return {"jeu": niveaux[-1][0] if niveaux else "", "texte": rendu.texte,
            "manques": ecart + ([] if rendu.complet else _manques(conn, project_id, rendu)),
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
        if not noms and not niveaux and not calcul_au_lancement.noms_appeles(feature):
            return Script()   # un projet qui n'a jamais déclaré de variable : le chemin d'aujourd'hui, octet pour octet
        figes = {"jeu": niveaux[-1][0] if niveaux else "", "connues": noms,
                 "valeurs": {n: {"valeur": v.valeur, "origine": v.origine} for n, v in resolution.resoudre(niveaux, noms).items()}}
        lignes_du_cas = _lignes_jouables(CaseDataRepo(conn).niveaux(case_id),
                                         _comptes_des_lignes(conn, case_id, _project_id_du_cas(conn, case_id)))
    else:
        lignes_du_cas = (figes.get("lignes_des_cas") or {}).get(str(case_id)) if isinstance(
            figes.get("lignes_des_cas"), dict) else None
        cas_figes = figes.get("cas_figes")
        if isinstance(cas_figes, list) and case_id not in cas_figes and CaseDataRepo(conn).lignes(case_id):
            # Revue du 2026-10-19 : un cas entré dans la campagne APRÈS son lancement (sélection « tous les cas ») n'a pas
            # de lignes figées. Joué avec les valeurs du projet, ses classes de valeurs ne le seraient jamais, sans un mot ;
            # les figer maintenant contournerait A29.
            return Script(blocage="Données de test : ce cas a ses propres lignes, ajouté à la campagne après son lancement "
                                  "— elles n'ont pas été figées. Créez une nouvelle exécution. Le test n'a pas été joué.")
    if campagne and figes.get("colonnes_de_l_application"):
        refus = _avec_les_colonnes_de_l_application(figes, feature, lignes_du_cas)
        if isinstance(refus, str):
            return Script(blocage=refus)
        figes = refus
    if lignes_du_cas:
        # A57/A58 : les lignes propres au cas, chacune une itération — figées au lancement avec le reste (A29).
        ecart = ecart_lignes_test(feature, _variables_des_lignes(lignes_du_cas))
        if ecart:
            # A59 (porteur, 2026-10-19). Régénérer seul ne suffit pas : l'IA écrit `{{nom}}` quand le CAS la cite (A39).
            return Script(blocage="Données de test : " + " ; ".join(ecart) + ". Citez-la dans les étapes ou le résultat "
                                  "attendu du cas puis régénérez le test, ou retirez cette colonne des lignes du cas. Le test "
                                  "n'a pas été joué.")
        figes = _avec_les_lignes_du_cas(figes, lignes_du_cas)
        if len(figes["jeux"]) > JEUX_PAR_LANCEMENT_MAX:
            return Script(blocage=f"Données de test : {len(figes['jeux'])} itérations pour ce cas, {JEUX_PAR_LANCEMENT_MAX} au "
                                  "plus. Cochez moins de lignes du projet, ou réduisez les lignes du cas. Le test n'a pas été "
                                  "joué.")
    # Étape 7 (A108, A110) : les calculs appelés par le test, calculés MAINTENANT pour chaque itération avec la fiche retenue
    # en vigueur (D41) ; l'appel devient une variable réservée qui reçoit la valeur. Impossible : le test n'est pas joué.
    avec_calculs = _avec_les_calculs(conn, case_id, feature, figes)
    if isinstance(avec_calculs, str):
        return Script(blocage=avec_calculs)
    feature, figes = avec_calculs
    version = {**version, "feature_content": feature}
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


def _avec_les_calculs(conn, case_id: int, feature: str, figes: dict) -> tuple[str, dict] | str:
    """Étape 7 : (test réécrit, valeurs figées complétées des valeurs calculées) — ou le message du blocage. Rien à faire si
    le test n'appelle aucun calcul (le chemin d'avant, octet pour octet)."""
    from testpilot.parametres import calcul
    from testpilot.store.repositories import FicheDeCalculRepo

    noms = calcul_au_lancement.noms_appeles(feature)
    if not noms:
        return feature, figes
    fin = " Le test n'a pas été joué."
    fiches = {}
    for retenue in FicheDeCalculRepo(conn).retenues(case_id):
        try:
            fiches[retenue["nom"]] = calcul.valider_fiche(retenue["contenu"])
        except calcul.FicheInvalide as exc:
            return f"Calcul « {retenue['nom']} » : {exc}.{fin}"
    par_nom = calcul_au_lancement.variables(noms)
    figes = json.loads(json.dumps(figes or {}))   # une copie : les valeurs figées en base ne portent jamais un calcul
    connues = list(figes.get("connues") or [])
    reservees = sorted(set(par_nom.values()) & set(connues))
    if reservees:
        return (f"Données de test : la variable « {reservees[0]} » porte un nom réservé aux calculs de TestPilot — "
                f"renommez-la.{fin}")
    lignes = figes["jeux"] if isinstance(figes.get("jeux"), list) else [figes]
    for ligne in lignes:
        if not isinstance(ligne, dict):
            continue
        valeurs = ligne.setdefault("valeurs", {})
        brutes = {n: str(v.get("valeur", "")) for n, v in valeurs.items() if isinstance(v, dict)}
        try:
            calculees = calcul_au_lancement.valeurs(fiches, par_nom, brutes)
        except calcul_au_lancement.CalculNonJouable as exc:
            jeu = ligne.get("jeu") or "Par défaut"
            return f"Données de test (ligne « {jeu} ») : {exc}.{fin}"
        for variable, (texte, origine, _detail) in calculees.items():
            valeurs[variable] = {"valeur": texte, "origine": origine}
    figes["connues"] = connues + list(par_nom.values())
    return calcul_au_lancement.reecrire(feature, par_nom), figes


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
    # Étape 4, morceau 7 (A90-A92) : une ligne au moins a son propre compte — chaque itération porte le sien (colonne
    # réservée des Exemples) ; une ligne sans compte reprend « Joué en tant que » du cas (A91).
    par_compte = any("compte" in ligne for ligne in figes["jeux"] if isinstance(ligne, dict))
    du_cas = _compte_du_cas(conn, version, _project_id_du_cas(conn, case_id)) if par_compte else None
    if par_compte and iterations_mod.COLONNE_COMPTE in connues:
        # Revue : une variable « tp_compte » créée avant que le nom soit réservé — sa valeur serait écrasée par le compte.
        return Script(blocage=f"Données de test : la variable « {iterations_mod.COLONNE_COMPTE} » porte un nom réservé à "
                              "TestPilot — renommez-la pour jouer les lignes avec leur compte. Le test n'a pas été joué.")
    if par_compte:
        from testpilot.store.repositories import ProjectAccountRepo
        project_id = _project_id_du_cas(conn, case_id)
        actuels = {c["id"]: c["label"] for c in ProjectAccountRepo(conn).liste(project_id)} if project_id is not None else {}
        for ligne in figes["jeux"]:
            if isinstance(ligne, dict) and "compte" in ligne and ligne.get("compte") not in (None, COMPTE_SUPPRIME):
                # Revue (A92) : relu MAINTENANT par son identifiant — supprimé depuis le lancement : bloqué ; renommé : son
                # nom d'aujourd'hui (celui que le harnais connaît).
                if ligne.get("compte_id") is not None:
                    ligne["compte"] = actuels.get(ligne["compte_id"], COMPTE_SUPPRIME)
        for ligne in figes["jeux"]:
            compte = ligne.get("compte") if isinstance(ligne, dict) else None
            if (compte or du_cas) == COMPTE_SUPPRIME:
                return Script(blocage=f"Données de test : la ligne « {ligne.get('jeu') or 'Par défaut'} » est jouée avec un "
                                      "compte supprimé — choisissez-en un autre. Le test n'a pas été joué.")
    # Revue finale (bloquant) : « écrit pour » se vérifie sur les lignes FIGÉES, celles que ce run joue — la porte relit la
    # base, où la ligne a pu être remise au compte du cas depuis le lancement (même double contrôle qu'A59).
    ecart = _ecart_des_lignes_figees(conn, case_id, version, figes["jeux"], campagne=campagne)
    if ecart:
        return Script(blocage=ecart)
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
        rendus.append((str(ligne.get("jeu") or ""), rendu, (ligne.get("compte") or du_cas) if par_compte else None))
    # Même réduction que `iterations_mod.iterations` (deux lignes aux mêmes valeurs ne font qu'une itération), en gardant
    # pour chacune l'origine de ses valeurs (« Par défaut » hérité ou non), montrée dans le rapport. Le compte en fait partie :
    # deux lignes qui ne diffèrent que par leur compte sont deux itérations (sinon la ligne « Lecteur » ne serait jamais jouée).
    groupes: dict[tuple, tuple[list[str], resolution.Remplacement, str | None]] = {}
    for nom, rendu, compte in rendus:
        cle = (compte, tuple(sorted((n, v.valeur) for n, v in rendu.jouees.items())))
        groupes.setdefault(cle, ([], rendu, compte))[0].append(nom)
    detail = [(" / ".join(noms), rendu, compte) for noms, rendu, compte in groupes.values()]
    colonne = iterations_mod.COLONNE_COMPTE
    iters = [(nom, {**{n: v.valeur for n, v in rendu.jouees.items()},
                    **({colonne: (compte or "").replace("|", "\\|")} if par_compte else {})})   # « | » échappé (Behave)
             for nom, rendu, compte in detail]
    if len(detail) > 1 or par_compte:
        joues = {"jeu": figes.get("jeu") or "",
                 "iterations": [{"jeu": nom, "valeurs": {n: {"valeur": v.valeur, "origine": v.origine}
                                                         for n, v in rendu.jouees.items()},
                                 **({"compte": compte} if par_compte else {})} for nom, rendu, compte in detail],
                 "valeurs": {}}
    else:   # une seule itération (mêmes valeurs pour ce test, ou aucune variable) : consignée comme un jeu seul
        nom, rendu, _ = detail[0]
        joues = {"jeu": nom, "valeurs": {n: {"valeur": v.valeur, "origine": v.origine} for n, v in rendu.jouees.items()}}
    conn.execute("UPDATE execution SET parametres_joues=? WHERE id=?", (json.dumps(joues, ensure_ascii=False), execution_id))
    conn.commit()
    if not rendus[0][1].jouees and not par_compte:
        return Script(parametres_joues=joues)   # aucune variable dans ce test : une seule itération, il se joue tel quel
    if len(iters) == 1 and not par_compte:
        texte = rendus[0][1].texte
    else:
        try:
            texte = iterations_mod.en_plan_de_scenario(feature, iters, connues,
                                                       toujours=(colonne,) if par_compte else ())
        except iterations_mod.IterationsImpossibles as exc:
            return Script(blocage=f"Itérations : {exc}. Le test n'a pas été joué.")
        # Revue du 2026-10-18 : le rattachement d'un résultat à son itération se décide ICI, sur le texte écrit par le
        # serveur, avant l'exécution — jamais sur ce que le run rend (`run_service._persist` lit cette table).
        joues["rangs_par_ligne"] = {str(ligne): rangs for ligne, rangs in iterations_mod.rangs_par_ligne(texte).items()}
        conn.execute("UPDATE execution SET parametres_joues=? WHERE id=?", (json.dumps(joues, ensure_ascii=False), execution_id))
        conn.commit()
    dossier = Path(config.DATA_DIR) / "executions" / str(execution_id) / "script"
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / f"{module_name}.feature").write_text(texte, encoding="utf-8")
    (dossier / f"{module_name}_steps.py").write_text(version.get("steps_content") or "", encoding="utf-8")
    return Script(dossier=dossier, parametres_joues=joues, comptes_par_iteration=par_compte)


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


# ── Étape 6 (IT-3d, A58 point 5) : les lignes d'un cas devenues fausses ─────────────────────────────────────────────────

LIGNES_A_RELIRE = ("Le texte du cas a changé depuis l'enregistrement de ses lignes : relisez-les (valeurs limites, résultat "
                   "attendu de chaque ligne), puis enregistrez-les.")


def lignes_a_relire(conn, case_id: int) -> str:
    """Le message à montrer quand le texte du cas (préconditions, étapes, résultat attendu) a changé depuis l'enregistrement de
    ses lignes — « moins de 18 ans » devenu « moins de 21 ans » : la ligne « 20 ans → Bienvenue » est devenue fausse. Vide :
    pas de ligne, lignes d'avant la migration 75 (aucune empreinte : jamais signalées sans preuve), ou texte inchangé.
    Signal, pas un blocage (décision du porteur proposée : A106)."""
    from testpilot.store.repositories import CaseRepo, empreinte_du_texte_du_cas

    depot = CaseDataRepo(conn)
    ecrites_pour = depot.lignes_ecrites_pour(case_id)
    if not ecrites_pour or not depot.lignes(case_id):
        return ""
    cas = CaseRepo(conn).get(case_id) or {}
    version = VersionRepo(conn).get(cas["current_version_id"]) if cas.get("current_version_id") else None
    return LIGNES_A_RELIRE if empreinte_du_texte_du_cas(version) != ecrites_pour else ""


class PropositionImpossible(ValueError):
    """Les nouvelles lignes ne peuvent pas être proposées (interrupteur éteint, cas sans texte, aucune variable)."""


def proposer_les_lignes(conn, case_id: int, *, llm=None, cost_tracker=None) -> list[dict]:
    """IT-3d : l'IA qui rédige les cas PROPOSE les lignes du cas pour son texte d'AUJOURD'HUI (même passe qu'IT-3c, A53, A60 :
    seulement les variables déclarées). Rien n'est enregistré : une personne relit, corrige et enregistre (A53). Derrière
    `TESTPILOT_LIGNES_PROPOSEES` (éteint) comme IT-3c — un appel au modèle de langage, payant."""
    import json as _json

    from testpilot.analysis.plan import TestPlan
    from testpilot.generation import interrupteurs, metier_writer
    from testpilot.store.repositories import CaseRepo

    if not interrupteurs.lignes_proposees_actif():
        raise PropositionImpossible("la proposition des lignes par l'IA n'est pas activée")
    cas = CaseRepo(conn).get(case_id) or {}
    version = VersionRepo(conn).get(cas["current_version_id"]) if cas.get("current_version_id") else None
    if not version:
        raise PropositionImpossible("ce cas n'a pas de texte")
    variables = [{"nom": v["nom"], "description": v["description"]}
                 for v in TestDataRepo(conn).variables(cas.get("project_id"))] if cas.get("project_id") else []
    if not variables:
        raise PropositionImpossible("le projet ne déclare aucune variable : il n'y a pas de ligne à proposer")
    try:
        etapes = _json.loads(version.get("test_steps") or "[]")
    except ValueError:
        etapes = []
    texte = "\n".join([str(version.get("preconditions") or ""), *(str(e) for e in etapes if e),
                       str(version.get("expected_result") or "")])
    # Revue (C6) : seulement le texte du cas d'AUJOURD'HUI — la spécification du groupe peut être l'ancienne (18 ans), et
    # l'IA la suivrait à côté du texte corrigé (21 ans).
    plan = TestPlan(module_name=cas.get("feature_slug") or "cas", models=[], scenarios=[], personas=[], portal_routes=[],
                    risks=[], raw_spec=texte)
    brouillon = metier_writer.propose_metier(plan, llm=llm, cost_tracker=cost_tracker, variables=variables,
                                             proposer_lignes=True,
                                             brief="Propose les lignes de ce cas tel qu'il est écrit ci-dessus (il fait foi).")
    if not brouillon.lignes:
        raise PropositionImpossible("l'IA n'a proposé aucune ligne exploitable pour ce cas")
    return brouillon.lignes
