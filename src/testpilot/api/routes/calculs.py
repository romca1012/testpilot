"""Vérifier une fiche de calcul sans rien enregistrer (étape 7, A110) — pour l'écran de validation des cas.

La personne voit, pendant qu'elle choisit ou corrige une fiche, ce qui manque (« sa source manque », « date de vérification »)
et si chaque exemple est retrouvé, avec le détail du calcul. C'est le MÊME calculateur que la validation et l'exécution
(`parametres/calcul.py`) : l'écran ne refait aucun calcul de son côté, il ne pourrait pas dire autre chose que le serveur.
Aucune I/O, aucun appel à l'IA.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from testpilot.api import access, schemas
from testpilot.parametres import calcul

router = APIRouter(prefix="/api/calculs", tags=["calculs"])


@router.post("/verifier", response_model=schemas.VerificationFicheOut,
             dependencies=[Depends(access.require_role(access.ROLE_TESTEUR))])
def verifier_une_fiche(body: schemas.VerificationFicheIn):
    try:
        fiche = calcul.valider_fiche(body.fiche, proposition=body.proposition)
    except calcul.FicheInvalide as exc:
        return schemas.VerificationFicheOut(utilisable=False, erreur=str(exc))
    if not fiche["exemples"]:
        return schemas.VerificationFicheOut(utilisable=False, entrees=calcul.entrees_attendues(fiche),
                                            erreur="aucun exemple chiffré à retrouver : ajoutez-en un")
    exemples = []
    for numero, exemple in enumerate(fiche["exemples"], start=1):
        try:
            resultat = calcul.calculer(fiche, exemple["entrees"])
            obtenu, detail = format(resultat.resultat, "f").replace(".", ","), resultat.detail
        except calcul.CalculImpossible as exc:
            obtenu, detail = f"incalculable : {exc}", []
        retrouve = not obtenu.startswith("incalculable") and calcul.verifier_exemples(
            {**fiche, "exemples": [exemple]}) == []
        exemples.append(schemas.ExempleVerifieOut(numero=numero, attendu=exemple["attendu"], obtenu=obtenu,
                                                   retrouve=retrouve, detail=detail))
    return schemas.VerificationFicheOut(
        utilisable=all(e.retrouve for e in exemples) and not body.proposition, entrees=calcul.entrees_attendues(fiche),
        exemples=exemples, a_confirmer=fiche.get("a_confirmer") or [])
