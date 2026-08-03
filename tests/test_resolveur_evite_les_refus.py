"""Le résolveur ne reproduit plus une valeur que l'application a refusée (§5bis n°1).

C'est l'étape qui **livre** le mécanisme : jusqu'ici le refus était mesuré et rangé ; ici il
change ce que l'outil écrit dans le formulaire.

⚠️ **L'invariant qui compte autant que le mécanisme** : sans aucune règle apprise, la valeur
produite est **identique** à celle d'avant. Vérifié ici sur les 161 champs requis de l'annuaire
RÉEL — pas sur des exemples choisis. Un mécanisme qui améliore un cas en déplaçant dix autres
n'aurait rien amélioré.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from testpilot.generation import regles_apprises as ra
from testpilot.generation import valeur_conforme as vc

ANNUAIRE_REEL = Path(__file__).resolve().parents[1] / "data" / "domain" / "projet-1.json"


def _regle(**kw) -> ra.RegleApprise:
    base = dict(route="/fournisseur/creation", champ="tva_intracommunautaire",
                type_contrainte="patternMismatch", valeur_contrainte="",
                valeur_refusee="", origine="navigateur", preuve="")
    base.update(kw)
    return ra.RegleApprise(**base)


def _champ(**kw) -> dict:
    base = {"name": "un_champ", "tag": "input", "type": "text", "visible": True,
            "label": "", "contraintes": {}, "options": []}
    base.update(kw)
    return base


# ── L'invariant de non-régression, sur données RÉELLES ───────────────────────

def _champs_requis_reels():
    if not ANNUAIRE_REEL.exists():
        return []
    modele = json.loads(ANNUAIRE_REEL.read_text(encoding="utf-8"))
    champs = []
    for route, infos in (modele.get("pages") or {}).items():
        for c in (infos.get("champs") or []):
            if c.get("name") and c.get("required"):
                champs.append(pytest.param(
                    {"name": c["name"], "tag": c.get("tag", ""), "type": c.get("type", ""),
                     "visible": c.get("visible", True), "label": c.get("label", ""),
                     "contraintes": c.get("contraintes") or {},
                     "options": [v for v, _ in (c.get("options") or [])]},
                    id=f"{route}:{c['name']}"))
    return champs


@pytest.mark.parametrize("champ", _champs_requis_reels())
def test_INVARIANT_sans_regle_apprise_la_valeur_est_INCHANGEE(champ):
    """Le premier candidat proposé est EXACTEMENT la valeur historique.

    ⚠️ Paramétré sur l'annuaire réel, pas sur des exemples : c'est la seule forme qui prouve que
    l'apprentissage ne déplace rien ailleurs.
    """
    try:
        attendu = vc._premier_candidat(champ)
    except vc.ValeurNonSynthetisable:
        with pytest.raises(vc.ValeurNonSynthetisable):
            vc.valeur_pour(champ)
        return
    assert vc.valeur_pour(champ) == attendu


# ── Le mécanisme ─────────────────────────────────────────────────────────────

def test_GARDE_le_resolveur_ne_reproduit_pas_une_valeur_deja_refusee():
    """⚠️ Échoue sur le code d'avant : `valeur_pour` était purement déterministe et rendait
    éternellement la même valeur, quel que soit le nombre de fois où l'application l'avait
    refusée."""
    champ = _champ(name="code_client1", contraintes={"pattern": r"\d{7}"})
    historique = vc.valeur_pour(champ)

    champ_appris = ra.fusionner(champ, [_regle(champ="code_client1",
                                               valeur_refusee=historique,
                                               valeur_contrainte=r"\d{7}")])
    nouvelle = vc.valeur_pour(champ_appris)

    assert nouvelle != historique
    import re
    assert re.fullmatch(r"\d{7}", nouvelle), "la variante doit RESTER conforme au motif mesuré"


def test_GARDE_une_regle_JS_impose_un_format_absent_du_crawl():
    """Le cas `tva_intracommunautaire`, de bout en bout.

    Aucune contrainte HTML : le crawl ne voit rien, le résolveur écrivait « TestPilot », le
    navigateur le refusait — à chaque rejeu, indéfiniment. Le refus mesuré porte la phrase de
    l'application, et c'est elle qui donne la forme.

    ⚠️ Échoue sur le code d'avant, qui n'avait aucun moyen d'apprendre quoi que ce soit.
    """
    champ = _champ(name="tva_intracommunautaire")
    assert vc.valeur_pour(champ) == "TestPilot"

    regle = _regle(type_contrainte="customError", valeur_refusee="TestPilot",
                   preuve="Le numéro de TVA doit contenir uniquement des chiffres.")
    valeur = vc.valeur_pour(ra.fusionner(champ, [regle]))

    assert valeur.isdigit(), f"attendu des chiffres, obtenu {valeur!r}"
    assert valeur != "TestPilot"


def test_GARDE_un_filtre_de_saisie_appris_impose_sa_classe():
    """`FAC-TEST-001` mutilé en `001` ⇒ le champ ne garde que les chiffres."""
    champ = _champ(name="numero_facture1")
    regle = _regle(champ="numero_facture1", type_contrainte="filtre_saisie",
                   valeur_contrainte=r"\d", valeur_refusee="TestPilot",
                   origine="filtre_saisie")
    assert vc.valeur_pour(ra.fusionner(champ, [regle])).isdigit()


def test_la_longueur_annoncee_par_la_regle_est_respectee():
    champ = _champ(name="siret", contraintes={"regle_lisible": "Un numéro à 9 chiffres"})
    regle = _regle(champ="siret", type_contrainte="filtre_saisie",
                   valeur_contrainte=r"\d", valeur_refusee="TestPilot")
    valeur = vc.valeur_pour(ra.fusionner(champ, [regle]))
    assert valeur.isdigit() and len(valeur) == 9


def test_la_classe_apprise_n_outrepasse_pas_maxlength():
    champ = _champ(name="court", contraintes={"maxlength": "4"})
    regle = _regle(champ="court", type_contrainte="filtre_saisie",
                   valeur_contrainte=r"\d", valeur_refusee="Test")
    assert len(vc.valeur_pour(ra.fusionner(champ, [regle]))) <= 4


# ── Ce que le mécanisme ne doit JAMAIS faire ─────────────────────────────────

def test_GARDE_toutes_les_variantes_refusees_donne_ValeurNonSynthetisable():
    """Épuisement ⇒ `indetermine`, JAMAIS `non_conforme`.

    ⚠️ C'est la doctrine centrale du produit : quand l'outil ne sait plus produire une donnée
    recevable, il le DIT. Il n'accuse pas l'application d'un défaut qu'il n'a pas prouvé.
    `ValeurNonSynthetisable` remonte en `ResolveurIncompletError`, donc en verdict indéterminé.
    """
    champ = _champ(name="code_client1", contraintes={"pattern": r"\d{7}"})
    toutes = [vc.valeur_pour(champ)]
    for n in range(2, vc._MAX_VARIANTES + 2):
        toutes.append(str(n % 10) * 7)

    regles = [_regle(champ="code_client1", valeur_refusee=v) for v in set(toutes)]
    with pytest.raises(vc.ValeurNonSynthetisable):
        vc.valeur_pour(ra.fusionner(champ, regles))


def test_une_variante_ne_VIOLE_JAMAIS_le_motif_mesure():
    """Une variante non conforme n'est pas proposée : mieux vaut renoncer que produire un faux."""
    import re
    champ = _champ(name="c", contraintes={"pattern": r"\d{7}"})
    base = vc.valeur_pour(champ)
    for variante in vc._variantes(base, champ):
        assert re.fullmatch(r"\d{7}", variante)


def test_une_classe_illisible_n_interdit_RIEN():
    """Une classe qu'on ne sait pas lire ne doit pas bloquer le résolveur."""
    champ = _champ(name="c", contraintes={"classe_conservee": "[[[pas une regex"})
    assert vc.valeur_pour(champ) == "TestPilot"


def test_les_options_reelles_priment_TOUJOURS_sur_une_regle_apprise():
    """`0019` : on n'invente jamais une valeur de `<select>`. Une classe apprise ne peut pas
    faire produire une valeur qui n'est pas dans la liste."""
    champ = _champ(name="agence", tag="select", options=["A1", "B2"])
    regle = _regle(champ="agence", type_contrainte="filtre_saisie", valeur_contrainte=r"\d",
                   valeur_refusee="zzz")
    assert vc.valeur_pour(ra.fusionner(champ, [regle])) in ("A1", "B2")
