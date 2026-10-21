"""Les lignes propres à un cas (décisions A57 et A58 du porteur, 2026-10-19) : ses classes de valeurs et le résultat attendu
de chacune, jouées en itérations quand on lance ce cas.

Le tableau du PROJET garde ce qui est partagé par plusieurs cas ; celui-ci, ce qui n'a de sens que pour CE cas (« 17 ans →
Accès refusé »). Les colonnes sont des variables du projet : un nom est déclaré une fois, une case vide reprend la valeur du
projet. Droits : ceux de la fiche du cas — tout membre lit, testeurs et plus modifient. Une valeur est déclarée par une
PERSONNE (A53 : l'IA pourra en proposer, une personne les valide).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from testpilot.api import access, schemas
from testpilot.api.deps import get_conn
from testpilot.api.services.donnees_de_test_service import ecart_lignes_test
from testpilot.parametres import resolution
from testpilot.store.repositories import (CaseDataRepo, CaseRepo, DonneeDeTestInvalide, ProjectAccountRepo, TestDataRepo,
                                          VersionRepo)

router = APIRouter(prefix="/api/cases/{case_id}/donnees-de-test", tags=["donnees-de-test"])

_ACCES_AU_CAS = [Depends(access.require_project_access_depuis("case_id", access.project_id_depuis_case))]


def _projet_du_cas(conn, case_id: int) -> int:
    cas = CaseRepo(conn).get(case_id)
    if cas is None or cas.get("project_id") is None:
        raise HTTPException(status_code=404, detail=f"cas {case_id} introuvable")
    return int(cas["project_id"])


def _tableau(conn, case_id: int, project_id: int) -> schemas.DonneesDuCasOut:
    cas = CaseRepo(conn).get(case_id) or {}
    version = VersionRepo(conn).get(cas["current_version_id"]) if cas.get("current_version_id") else None
    lignes = CaseDataRepo(conn).variables_des_lignes(case_id)
    comptes = {c["id"]: c["label"] for c in ProjectAccountRepo(conn).liste(project_id)}
    du_cas = comptes.get((version or {}).get("compte_id"), "compte supprimé") if (version or {}).get(
        "compte_id") is not None else "principal"
    lignes_du_cas = CaseDataRepo(conn).lignes(case_id)
    # Revue : la colonne reste montrée dès qu'une ligne a son compte — même s'il ne reste que le principal — sinon la moindre
    # modification effaçait ce choix en silence (et une ligne « compte supprimé » se jouait avec le compte du cas).
    avec_colonne = bool(comptes) or any(l["compte_choisi"] for l in lignes_du_cas)

    def compte_joue(ligne: dict) -> str:
        """A91 : le compte avec lequel la ligne SERA jouée, dit à l'écran."""
        if not ligne["compte_choisi"]:
            return f"{du_cas} (compte du cas)"
        if ligne["compte_id"] is None:
            return "principal"
        return comptes.get(ligne["compte_id"], "compte supprimé")

    return schemas.DonneesDuCasOut(
        ecarts=ecart_lignes_test((version or {}).get("feature_content") or "", lignes) if lignes else [],
        variables=[schemas.VariableOut(**v) for v in TestDataRepo(conn).variables(project_id)],
        lignes=[schemas.LigneDuCasOut(id=l["id"], nom=l["nom"], valeurs={str(k): v for k, v in l["valeurs"].items()},
                                      compte_choisi=bool(l["compte_choisi"]), compte_id=l["compte_id"],
                                      compte_joue=compte_joue(l) if avec_colonne else "")
                for l in lignes_du_cas],
        comptes=([schemas.CompteChoixOut(id=None, libelle="principal")]
                 + [schemas.CompteChoixOut(id=cid, libelle=lib) for cid, lib in comptes.items()]) if avec_colonne else [])


@router.get("", response_model=schemas.DonneesDuCasOut, dependencies=_ACCES_AU_CAS)
def lire_les_lignes_du_cas(case_id: int, conn=Depends(get_conn)):
    return _tableau(conn, case_id, _projet_du_cas(conn, case_id))


@router.put("", response_model=schemas.DonneesDuCasOut, dependencies=_ACCES_AU_CAS)
def ecrire_les_lignes_du_cas(case_id: int, body: schemas.LignesDuCasIn, conn=Depends(get_conn)):
    """Remplace toutes les lignes du cas (ce que montre l'écran). Tout est validé AVANT d'écrire : rien n'est enregistré à
    moitié. Une case vide n'est pas enregistrée : elle reprend la valeur du projet."""
    project_id = _projet_du_cas(conn, case_id)
    lignes = []
    try:
        for ligne in body.lignes:
            if not all(cle.isascii() and cle.isdigit() and not cle.startswith("0") for cle in ligne.valeurs):
                raise ValueError("chaque case est désignée par l'identifiant de sa variable, écrit une seule fois")
            lignes.append({"id": ligne.id, "nom": ligne.nom, "valeurs": {int(cle): resolution.valider_valeur(valeur)
                                                        for cle, valeur in ligne.valeurs.items()},
                           "compte_choisi": ligne.compte_choisi, "compte_id": ligne.compte_id})
        CaseDataRepo(conn).remplacer(case_id, project_id, lignes)
    except (resolution.ValeurInvalide, DonneeDeTestInvalide, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _tableau(conn, case_id, project_id)
