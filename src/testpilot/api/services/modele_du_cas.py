"""Étape 4, morceau 7 (A85-A88, porteur 2026-10-21) : avec quels écrans l'IA écrit le test d'un cas, et pour quel compte il
a été écrit.

C'est le SEUL point par lequel la génération lit la carte des comptes (`exploration_service.charger_carte`) — un test de
structure le garde (`tests/test_exploration_multi_comptes.py`). Interrupteur `TESTPILOT_GENERATION_PAR_COMPTE` éteint, ou cas
joué avec le principal : le modèle du principal, EXACTEMENT comme avant (l'annexe des comptes n'est même pas lue).

« Écrit pour » (A86-A88) : la provenance d'un test dit pour quel compte il a été écrit. Joué ensuite avec un autre compte sans
régénération, il est bloqué — une absence vraie pour un compte qui ne voit rien sortirait « Passé ». Indépendant de
l'interrupteur : ça ne change rien à ce que l'IA reçoit.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from testpilot.generation import carte_des_comptes, domain_model, interrupteurs

# Les métadonnées du modèle que le relevé d'un compte n'a pas (il ne porte que ce que le compte a VU) : reprises du principal.
_METADONNEES = ("connector_type", "projet", "project_id", "base_url", "mesure_le", "methode", "formes_oracle")


@dataclass
class ModeleDuCas:
    modele: dict | None
    compte: dict | None = None            # {id, libelle, empreinte} ; None = le principal
    vue: str = "principal"                # principal | compte | principal_faute_d_exploration
    avis: str = ""                        # A85 : ce que la fiche dira (écrit sans les écrans de ce compte)
    refus: str = ""                       # A85 : « Automatiser avec l'IA » refuse (compte en connexion impossible)
    ecrit_pour: dict = field(default_factory=dict)
    # A90-A91 : `[{nom, compte_id, libelle}]` — le compte EFFECTIF de chaque ligne du cas (la ligne, sinon le compte du cas),
    # vide si aucune ligne n'a son propre compte.
    comptes_des_lignes: list = field(default_factory=list)


def compte_de_la_version(conn, projet: dict | None, compte_id: int | None) -> dict | None:
    """`{id, libelle, empreinte}` du compte avec lequel la version est jouée ; `None` pour le principal ou un compte disparu
    (l'exécution le bloque déjà, morceau 5)."""
    from testpilot.connectors.runtime_env import empreinte_du_compte
    from testpilot.store.repositories import ProjectAccountRepo

    if compte_id is None or not projet:
        return None
    compte = ProjectAccountRepo(conn).lire(projet["id"], compte_id)
    if compte is None:
        return None
    return {"id": compte["id"], "libelle": compte["label"], "empreinte": empreinte_du_compte(compte),
            "business_role": compte.get("business_role") or ""}


def _vue_du_compte(conn, projet: dict, compte: dict, base: dict | None) -> tuple[dict | None, dict]:
    """`(modèle vu par ce compte, état de son exploration)` — le modèle est `None` si ce compte n'a pas été exploré en entier.
    Même forme que le modèle du principal : ses métadonnées (adresse, date, oracle) sont reprises du principal (A73 : l'oracle
    reste le sien)."""
    from testpilot.api.services import exploration_service

    etat = exploration_service.etat_des_comptes(conn, projet)["par_compte"].get(compte["id"]) or {}
    if etat.get("statut") != "explore" or base is None:
        return None, etat
    vue = carte_des_comptes.vue_du_compte(exploration_service.charger_carte(conn, projet) or {}, compte["libelle"])
    if vue is None:
        return None, etat
    for cle in ("menus_visibles", "absence_fiable"):
        vue.pop(cle, None)
    return {**{k: base[k] for k in _METADONNEES if k in base}, **vue}, etat


def comptes_effectifs_des_lignes(conn, projet: dict | None, case_id: int | None, compte_du_cas: int | None) -> list[dict]:
    """A91 : `[{nom, compte_id, libelle}]` — le compte avec lequel chaque ligne du cas SERA jouée. Vide si aucune ligne n'a son
    propre compte (les lignes se jouent alors avec le compte du cas, comme avant)."""
    from testpilot.store.repositories import CaseDataRepo, ProjectAccountRepo

    if not case_id or not projet:
        return []
    lignes = CaseDataRepo(conn).comptes_des_lignes(case_id)
    if not any(l["choisi"] for l in lignes):
        return []
    noms = {c["id"]: c["label"] for c in ProjectAccountRepo(conn).liste(projet["id"])}
    effectifs = []
    for ligne in lignes:
        compte_id = ligne["compte_id"] if ligne["choisi"] else compte_du_cas
        supprime = compte_id is not None and compte_id not in noms
        libelle = carte_des_comptes.PRINCIPAL if compte_id is None else noms.get(compte_id, "compte supprimé")
        effectifs.append({"nom": ligne["nom"], "compte_id": compte_id, "libelle": libelle, "supprime": supprime})
    return effectifs


def pour_la_generation(conn, projet: dict | None, compte_id: int | None, case_id: int | None = None) -> ModeleDuCas:
    """Le modèle que l'IA reçoit pour écrire ce test, et ce que la fiche en dira."""
    base = domain_model.charger_modele(projet) if projet else None
    compte = compte_de_la_version(conn, projet, compte_id)
    resultat = ModeleDuCas(modele=base, compte=compte)
    if compte is not None and interrupteurs.generation_par_compte_actif():
        vue, etat = _vue_du_compte(conn, projet, compte, base)
        statut = etat.get("statut", "a_actualiser")
        if vue is not None:
            resultat.modele, resultat.vue = vue, "compte"
        else:
            resultat.vue = "principal_faute_d_exploration"
            if statut == "connexion_impossible":
                resultat.refus = (f"{compte['libelle']} : connexion impossible à la dernière exploration — corrigez son mot "
                                  "de passe dans les réglages du projet, puis actualisez l'exploration.")
            raison = {"incomplet": "exploration incomplète", "echec": "son exploration a échoué",
                      "a_actualiser": etat.get("message") or "pas encore exploré"}.get(statut, "pas encore exploré")
            resultat.avis = (f"Écrit sans les écrans de {compte['libelle']} ({raison}) — actualisez l'exploration puis "
                             "régénérez")
    resultat.comptes_des_lignes = comptes_effectifs_des_lignes(conn, projet, case_id, compte_id)
    resultat.ecrit_pour = {"compte_id": compte["id"] if compte else None,
                           "libelle": compte["libelle"] if compte else carte_des_comptes.PRINCIPAL,
                           "empreinte": compte["empreinte"] if compte else "", "vue": resultat.vue,
                           **({"avis": resultat.avis} if resultat.avis else {}),
                           # A90 : les comptes des lignes pour lesquels ce test a été écrit (écart s'ils changent ensuite).
                           **({"comptes_des_lignes": sorted({l["compte_id"] or 0 for l in resultat.comptes_des_lignes})}
                              if resultat.comptes_des_lignes else {})}
    return resultat


def pour_la_relecture(conn, projet: dict | None, version_rows: list[dict], current: dict | None) -> tuple[dict | None, str]:
    """`(modèle, empreinte de la cible)` avec lesquels relire le test de `current` (points de vigilance, correction,
    réparation) : ceux avec lesquels il a été ÉCRIT. Sinon, un test écrit avec les écrans de Lecteur verrait toutes ses preuves
    jugées contre l'annuaire du principal (« champ non vu ») et le contrôle de fin d'écriture divergerait de la fiche.
    Écrit pour le principal (le cas de tous les tests d'avant) : exactement le calcul d'avant."""
    from testpilot.generation.provenance import target_fingerprint

    base = domain_model.charger_modele(projet) if projet else None
    ecrit = ecrit_pour_de_la_version(version_rows, current)
    if ecrit.get("vue") != "compte" or not projet:
        return base, target_fingerprint(projet)
    compte = compte_de_la_version(conn, projet, ecrit.get("compte_id"))
    vue = _vue_du_compte(conn, projet, compte, base)[0] if compte else None
    return (vue if vue is not None else base), target_fingerprint(projet, compte=ecrit.get("empreinte") or None)


def ecrit_pour_de_la_version(version_rows: list[dict], current: dict | None) -> dict:
    """Pour quel compte le test de `current` a été ÉCRIT — lu dans la provenance de la version qui l'a écrit, à travers les
    corrections et réparations (`origin`). A87 : une version d'avant le morceau 7 est réputée écrite pour le principal."""
    from testpilot.api.services.generation_service import _chaine_de_provenance, _ecriture_du_test

    from testpilot.api.services.generation_service import _versions_du_meme_test

    if not current:
        return {}
    # Revue : la version la plus PROCHE qui a écrit ce test (une génération porte `ecrit_pour` au premier niveau) — une
    # régénération au contenu identique, pour un autre compte, ne reste pas « écrite pour » le compte de la toute première.
    for version in [current, *_versions_du_meme_test(version_rows, current)]:
        try:
            provenance = json.loads(version.get("generation_provenance") or "{}")
        except ValueError:
            continue
        if isinstance(provenance, dict) and isinstance(provenance.get("ecrit_pour"), dict):
            return provenance["ecrit_pour"]
    for provenance in _chaine_de_provenance(_ecriture_du_test(version_rows, current)):
        if isinstance(provenance.get("ecrit_pour"), dict):
            return provenance["ecrit_pour"]
    return {"compte_id": None, "libelle": carte_des_comptes.PRINCIPAL, "vue": "principal", "avant_le_morceau_7": True}


def ecart_de_compte(conn, case: dict, version_rows: list[dict], current: dict | None) -> list[str]:
    """A86-A88 : le test a été écrit pour un compte et le cas est joué avec un autre — un écart bloquant (mécanisme d'A42),
    sans « Débloquer ». Rien pour une version sans test (cas manuel, pas encore écrit)."""
    from testpilot.store.repositories import ProjectAccountRepo

    if not current or not (current.get("feature_content") or "").strip():
        return []
    from testpilot.connectors.runtime_env import empreinte_du_compte

    ecrit = ecrit_pour_de_la_version(version_rows, current)
    joue_id = current.get("compte_id")
    compte = ProjectAccountRepo(conn).lire(case["project_id"], joue_id) if joue_id is not None and case.get(
        "project_id") else None
    pour = ecrit.get("libelle") or carte_des_comptes.PRINCIPAL
    if ecrit.get("compte_id") == joue_id:
        # Revue (bloquant) : même compte, mais identifiant de connexion changé depuis — c'est une autre personne (morceau 6).
        if compte is not None and ecrit.get("empreinte") and ecrit["empreinte"] != empreinte_du_compte(compte):
            return [f"le compte « {compte['label']} » a changé d'identifiant depuis l'écriture du test (régénérez le test)"]
        return _ecart_des_lignes(conn, case, ecrit, joue_id)
    joue = carte_des_comptes.PRINCIPAL
    if joue_id is not None:
        joue = compte["label"] if compte else "un compte supprimé"
    return [f"écrit pour « {pour} », joué en tant que « {joue} » (régénérez le test, ou remettez « Joué en tant que : "
            f"{pour} »)"]


def _ecart_des_lignes(conn, case: dict, ecrit: dict, joue_id: int | None) -> list[str]:
    """A90 (lien entre l'écriture et les lignes) : une ligne jouée avec un compte pour lequel le test n'a PAS été écrit — même
    raison qu'A86 (une absence vraie pour un compte qui ne voit rien sortirait « Passé ») : bloqué, la ligne nommée."""
    from testpilot.store.repositories import CaseDataRepo, ProjectRepo

    if not case.get("id") or not any(l["choisi"] for l in CaseDataRepo(conn).comptes_des_lignes(case["id"])):
        return []   # le cas le plus courant (aucune ligne à compte) : une seule requête
    projet = ProjectRepo(conn).get(case["project_id"]) if case.get("project_id") else None
    lignes = comptes_effectifs_des_lignes(conn, projet, case.get("id"), joue_id)
    if not lignes:
        return []
    ecrits = set(ecrit.get("comptes_des_lignes") or [ecrit.get("compte_id") or 0])
    # Un compte supprimé n'est pas un écart : A92 bloque déjà, avec le bon geste (« choisissez-en un autre »).
    return [f"la ligne « {l['nom']} » est jouée en tant que « {l['libelle']} », le test n'a pas été écrit pour ce compte "
            "(régénérez le test, ou remettez cette ligne sur le compte pour lequel il a été écrit)"
            for l in lignes if not l["supprime"] and (l["compte_id"] or 0) not in ecrits]
