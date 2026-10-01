"""F26, point 1 (2026-10-01) — garde-fou au gate de relecture, COMPLÉMENTAIRE au contrôle amont
`metier_writer.verifier_dependance_inter_cas` (F26(b)) : celui-ci porte sur le MÉTIER déclaré par
le modèle, structurellement contraignable mais pas infaillible. Celui-ci porte sur le GHERKIN
produit — ce qui s'exécute réellement — et sert de filet pour tout ce qui échapperait au premier
contrôle.

Signal DÉTECTIF, jamais bloquant (même régime que 0008/0017/0021, D4) : un cas qui ouvre un
enregistrement réel en lecture seule n'est pas un problème en soi — mais le relecteur doit le
savoir avant d'approuver, impossible à manquer, distinct de l'avertissement générique.

Trois motifs mesurés sur C130-C137 (Portail Sapian - Integration, 2026-10-01) :
1. `j'ouvre l'enregistrement "X" du modèle "…"` après `je renseigne le champ "…" avec la valeur
   "X"` (C131/C133 corrigés).
2. Une valeur créée via une LIGNE DE TABLEAU (`j'ajoute une ligne à … avec :`, ex. `serial_no |
   BDD-TEST-SN-001` dans un assistant Odoo) — C136. ⚠️ Toutes les cellules ne sont pas des
   créations : un champ dont le nom finit par `_id` (convention Odoo many2one) est une RÉFÉRENCE
   vers un enregistrement EXISTANT, jamais une valeur créée — distinction mesurée directement sur
   C134 (`equipment_id | [CODE] …`, une référence, PAS une création) vs C136 (`serial_no | …`, une
   vraie création). Sans cette distinction, traiter toute cellule comme « créée » aurait fait
   disparaître le signal sur C134.
3. Une valeur au FORMAT D'AFFICHAGE ODOO (`"[CODE] Libellé"`) référencée n'importe où (y compris
   une cellule de tableau) sans avoir été créée — motif de C134 : l'équipement réel y est injecté
   dans une ligne de tableau (champ `equipment_id`, finit par `_id` → jamais traité comme créé),
   jamais ouvert via `j'ouvre l'enregistrement`. Portée volontairement étroite au format décoré
   plutôt qu'à « toute valeur citée » : une donnée de référence légitime (« AGENCE DE
   SAINT-ETIENNE », « Testpilot QA ») n'a pas ce format et ne déclenche pas le signal.

Portée délibérément étroite : un faux négatif ici tombe quand même, détective, sur un autre cas
mesuré plus tard — mieux vaut une portée précise et vérifiée (3 motifs réels) qu'une portée large
et non éprouvée.
"""
from __future__ import annotations

import re

_CREE_CHAMP = re.compile(r'je renseigne le champ "([^"]+)" avec la valeur "([^"]+)"')
_LIGNE_TABLEAU = re.compile(r'^\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|')
_OUVRE = re.compile(r"j'ouvre l'enregistrement \"([^\"]+)\" du modèle \"([^\"]+)\"")
_DEBUT_CONTEXTE = re.compile(r"^\s*(Contexte|Background)\s*:")
_DEBUT_SCENARIO = re.compile(r"^\s*(Scénario|Scenario|Plan du scénario)\s*:")
# Toute chaîne citée OU cellule de tableau au format décoré Odoo : "[CODE] Libellé".
_VALEUR_DECOREE = re.compile(r'(?:"(\[\S+\]\s[^"]+)"|\|\s*(\[\S+\]\s[^|]+?)\s*\|)')

KIND_ENREGISTREMENT_NON_CREE = "enregistrement_non_cree_par_le_scenario"


def _est_reference(champ: str) -> bool:
    """Convention Odoo : un champ qui finit par `_id` est une relation vers un enregistrement
    EXISTANT (many2one), jamais une valeur que CE scénario vient de créer."""
    return champ.strip().lower().endswith("_id")


def _cree_par(nom: str, noms_crees: set[str]) -> bool:
    """`nom` est couvert si un nom créé lui est identique, ou si `nom` le CONTIENT — tolère un
    affichage Odoo décoré (ex. `"[REF] Nom"` quand le scénario a créé `"Nom"`)."""
    return any(c == nom or c in nom for c in noms_crees)


def lint_enregistrements_non_crees(feature_content: str) -> list[dict]:
    """Points de vigilance structurels sur le `.feature` — jamais un jugement sur ce que ferait le
    test une fois exécuté. Voir le docstring du module pour les trois motifs couverts."""
    warnings: list[dict] = []
    noms_contexte: set[str] = set()
    noms_scenario: set[str] = set()
    vus_scenario: set[str] = set()  # valeurs décorées déjà signalées dans ce scénario
    dans_contexte = False

    for numero, ligne in enumerate(feature_content.splitlines(), 1):
        if _DEBUT_CONTEXTE.match(ligne):
            dans_contexte = True
            continue
        if _DEBUT_SCENARIO.match(ligne):
            dans_contexte = False
            noms_scenario = set(noms_contexte)
            vus_scenario = set()
            continue

        cible = noms_contexte if dans_contexte else noms_scenario

        cree = _CREE_CHAMP.search(ligne)
        if cree:
            champ, valeur = cree.group(1), cree.group(2)
            if not _est_reference(champ):
                cible.add(valeur)
            continue

        ligne_tableau = _LIGNE_TABLEAU.match(ligne)
        if ligne_tableau:
            champ, valeur = ligne_tableau.group(1).strip(), ligne_tableau.group(2).strip()
            if champ.lower() != "champ" and not _est_reference(champ):  # ignore l'en-tête
                cible.add(valeur)
            # pas de `continue` : une cellule peut AUSSI être une valeur décorée (motif 3, C134) —
            # les deux contrôles s'appliquent à la même ligne.

        noms_connus = noms_contexte if dans_contexte else (noms_contexte | noms_scenario)

        ouvre = _OUVRE.search(ligne)
        if ouvre:
            nom, modele = ouvre.group(1), ouvre.group(2)
            if not _cree_par(nom, noms_connus):
                warnings.append({
                    "kind": KIND_ENREGISTREMENT_NON_CREE, "line": numero,
                    "step": f'j\'ouvre l\'enregistrement "{nom}" du modèle "{modele}"',
                    "message": (f'Ce scénario ouvre « {nom} » (modèle « {modele} ») sans l\'avoir '
                               "créé lui-même : si cet enregistrement existe réellement, ce test "
                               "agit sur une donnée réelle, pas sur une donnée produite par ce "
                               "run. À vérifier avant d'approuver.")})
            continue

        for m in _VALEUR_DECOREE.finditer(ligne):
            valeur = (m.group(1) or m.group(2)).strip()
            if valeur in vus_scenario or _cree_par(valeur, noms_connus):
                continue
            vus_scenario.add(valeur)
            warnings.append({
                "kind": KIND_ENREGISTREMENT_NON_CREE, "line": numero,
                "step": valeur,
                "message": (f'La valeur « {valeur} » a le format d\'un enregistrement Odoo réel '
                           "(code entre crochets) et n'a jamais été créée par ce scénario : "
                           "probablement une donnée réelle de l'instance. À vérifier avant "
                           "d'approuver.")})
    return warnings


# ── Garde BLOQUANTE à l'écriture (F26(b), migration 58, 2026-10-01) ─────────────────────────────
#
# Complémentaire à `lint_enregistrements_non_crees` ci-dessus (détective, jamais bloquant, portée
# large) : celle-ci est volontairement BLOQUANTE, mais volontairement ÉTROITE — appelée par
# `tools/write.py::write_feature_file` UNIQUEMENT quand le métier du cas a déclaré
# `depend_dun_autre_cas_du_groupe` (ToolContext, migration 58). Hors de cette condition, elle
# n'est jamais invoquée : un cas qui n'a jamais annoncé cette dépendance (ex. un produit de
# catalogue fixe sur SauceDemo, référencé sans jamais être « créé ») reste hors de sa portée,
# exactement comme prévu — bloquer là aussi aurait réintroduit le faux positif mesuré sur
# `"Sauce Labs Backpack"` (1 cas sur 2 dans tout le corpus généré, 2026-10-01) lors du diagnostic
# du motif 4 ci-dessous.
#
# Un 4e motif rejoint ici les 3 de la fonction détective : `je clique sur "{libellé}" dans la
# ligne contenant "{texte}"` (C138, rejeu réel) — jamais ajouté à la fonction détective elle-même
# car il est trop large pour une portée non gated (confirmé par le faux positif SauceDemo).
_CLIC_LIGNE = re.compile(r'je clique sur "[^"]+" dans la ligne contenant "([^"]+)"')


def _message_refus_entite(valeur: str, ligne: int, step: str) -> str:
    return (
        f'[write_feature_file] ENTITE_NON_CREEE (ligne {ligne}) : « {step} » référence '
        f'« {valeur} » sans que CE scénario l\'ait créée lui-même. Le métier de ce cas a déclaré '
        "qu'il dépend d'un autre cas du groupe — mais chaque scénario Behave s'exécute isolément, "
        "sans jamais accéder à ce qu'un AUTRE scénario a fait, même de la même spécification. "
        "Ajoute, avant cette ligne, les steps qui CRÉENT cette entité toi-même (formulaire de "
        "création + enregistrement, ou une ligne de tableau), puis réutilise le nom ou "
        "l'identifiant que ton scénario vient lui-même de produire — jamais un enregistrement "
        "réel observé pendant l'exploration. Rappelle ensuite write_feature_file avec le contenu "
        ".feature complet."
    )


def verifier_entite_a_creer(feature_content: str) -> str | None:
    """`None` si chaque référence (motifs 1, 3 et 4) est couverte par une création antérieure DANS
    LE MÊME scénario (ou le Contexte partagé) ; sinon le message de refus pour la PREMIÈRE
    référence fautive rencontrée — un seul suffit à faire corriger l'agent, qui revoit tout le
    fichier au tour suivant (`write_feature_file` REMPLACE, jamais un patch partiel)."""
    noms_contexte: set[str] = set()
    noms_scenario: set[str] = set()
    dans_contexte = False

    for numero, ligne in enumerate(feature_content.splitlines(), 1):
        if _DEBUT_CONTEXTE.match(ligne):
            dans_contexte = True
            continue
        if _DEBUT_SCENARIO.match(ligne):
            dans_contexte = False
            noms_scenario = set(noms_contexte)
            continue

        cible = noms_contexte if dans_contexte else noms_scenario

        cree = _CREE_CHAMP.search(ligne)
        if cree:
            champ, valeur = cree.group(1), cree.group(2)
            if not _est_reference(champ):
                cible.add(valeur)
            continue

        ligne_tableau = _LIGNE_TABLEAU.match(ligne)
        if ligne_tableau:
            champ, valeur = ligne_tableau.group(1).strip(), ligne_tableau.group(2).strip()
            if champ.lower() != "champ" and not _est_reference(champ):
                cible.add(valeur)
            # pas de `continue` : une cellule peut AUSSI être une valeur décorée (motif 3).

        noms_connus = noms_contexte if dans_contexte else (noms_contexte | noms_scenario)

        ouvre = _OUVRE.search(ligne)
        if ouvre and not _cree_par(ouvre.group(1), noms_connus):
            return _message_refus_entite(ouvre.group(1), numero, ligne.strip())

        clic = _CLIC_LIGNE.search(ligne)
        if clic and not _cree_par(clic.group(1), noms_connus):
            return _message_refus_entite(clic.group(1), numero, ligne.strip())

        for m in _VALEUR_DECOREE.finditer(ligne):
            valeur = (m.group(1) or m.group(2)).strip()
            if not _cree_par(valeur, noms_connus):
                return _message_refus_entite(valeur, numero, ligne.strip())

    return None
