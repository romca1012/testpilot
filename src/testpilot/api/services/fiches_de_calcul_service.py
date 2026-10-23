"""Les fiches de calcul choisies sur l'écran de validation des cas (étape 7, décisions A108 et A110 du porteur, 2026-10-23).

Après « Générer », chaque cas qui attend une valeur calculée porte « Calcul détecté ». La personne choisit : la fiche proposée
par l'IA, un calcul qu'elle fournit elle-même, ou pas de calcul — le choix par DÉFAUT si elle valide sans rien faire. Choisir
une fiche vaut validation par cette personne (V10) : elle est enregistrée `retenue`, avec son nom et la date.

Une fiche n'est retenue que si elle est bien formée ET retrouve EXACTEMENT ses exemples (`parametres/calcul.py`) : sinon le
cas est refusé à la validation, avec l'écart, plutôt que d'écrire un test qui comparerait l'application à un calcul faux.
"""

from __future__ import annotations

from testpilot.parametres import calcul
from testpilot.store.repositories import FicheDeCalculRepo

FICHES_PAR_CAS_MAX = 10   # au-delà, ce n'est plus « le total et la TVA » : un cas à découper


def fautes_des_fiches(cas: dict) -> list[str]:
    """Ce qui empêche de retenir les fiches choisies pour ce cas (vide : rien). Ne lit que ce que la personne a validé."""
    retenues = cas.get("fiches_retenues") or []
    if len(retenues) > FICHES_PAR_CAS_MAX:
        return [f"{len(retenues)} calculs retenus : {FICHES_PAR_CAS_MAX} au plus"]
    fautes, noms = [], set()
    for choisie in retenues:
        origine = str((choisie or {}).get("origine") or "")
        if origine not in FicheDeCalculRepo.ORIGINES:
            fautes.append("un calcul retenu ne dit pas s'il vient de l'IA ou d'une personne")
            continue
        try:
            fiche = calcul.valider_fiche((choisie or {}).get("contenu"))
        except calcul.FicheInvalide as exc:
            fautes.append(f"calcul « {((choisie or {}).get('contenu') or {}).get('nom') or '?'} » : {exc}")
            continue
        if fiche["nom"] in noms:
            fautes.append(f"deux calculs retenus s'appellent « {fiche['nom']} »")
        noms.add(fiche["nom"])
        for ecart in calcul.verifier_exemples(fiche):
            fautes.append(f"calcul « {fiche['nom']} » : l'exemple {ecart.numero} attend {ecart.attendu}, "
                          f"le calcul donne {ecart.obtenu}")
    return fautes


def transporter(cas: dict) -> dict:
    """Ce qui part avec le cas validé jusqu'à sa création : la raison du « Calcul détecté », les fiches RETENUES normalisées
    (avec leur origine) et les propositions de l'IA non choisies (gardées pour l'historique, jamais utilisées)."""
    sortie = {}
    if str(cas.get("calcul_detecte") or "").strip():
        sortie["calcul_detecte"] = str(cas["calcul_detecte"]).strip()[:500]
    retenues = [{"origine": c["origine"], "contenu": calcul.valider_fiche(c["contenu"])}
                for c in (cas.get("fiches_retenues") or [])]
    if retenues:
        sortie["fiches_retenues"] = retenues
    noms_retenus = {r["contenu"]["nom"] for r in retenues}
    proposees = []
    for brute in (cas.get("fiches_proposees") or [])[:FICHES_PAR_CAS_MAX]:
        try:
            fiche = calcul.valider_fiche(brute)
        except calcul.FicheInvalide:
            continue   # une proposition mal formée n'a rien à garder : elle n'a jamais pu être choisie
        if fiche["nom"] not in noms_retenus:
            proposees.append(fiche)
    if proposees:
        sortie["fiches_proposees"] = proposees
    return sortie


def enregistrer(conn, *, case_id: int, project_id: int | None, cas: dict, par: str) -> None:
    """Après la création du cas : sa raison de calcul et ses fiches. Une fiche retenue sans nom de personne est impossible
    (`FicheDeCalculRepo.creer` le refuse) — le choix vaut validation, il faut savoir qui l'a fait."""
    if not project_id:
        return
    if cas.get("calcul_detecte"):
        conn.execute("UPDATE test_case SET calcul_detecte=? WHERE id=?", (cas["calcul_detecte"], case_id))
        conn.commit()
    depot = FicheDeCalculRepo(conn)
    for retenue in cas.get("fiches_retenues") or []:
        depot.creer(project_id=project_id, case_id=case_id, contenu=retenue["contenu"], origine=retenue["origine"],
                    statut="retenue", auteur="IA" if retenue["origine"] == "ia" else par, retenue_par=par)
    for proposee in cas.get("fiches_proposees") or []:
        depot.creer(project_id=project_id, case_id=case_id, contenu=proposee, origine="ia", statut="proposee",
                    auteur="IA")
