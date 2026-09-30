"""Rayon d'explosion d'une réparation : quels steps ont changé, et lesquels n'y étaient pour rien.

`0017`, garde **détective** (arbitrage du porteur, 2026-07-17) — elle **informe le relecteur au
gate**, elle ne bloque jamais. Même régime que le lint d'assertions de `0008` C : bloquer
automatiquement demanderait d'abord de mesurer le taux de faux positifs, et c'est précisément
cette mesure que cette garde produit.

────────────────────────────────────────────────────────────────────────────────────
POURQUOI
────────────────────────────────────────────────────────────────────────────────────
`write_steps_file` REMPLACE le fichier, et le contrat l'exige (correctif du bug 2 de `0014`).
L'agent réécrit donc ~14 000 caractères **de code qui marchait** pour corriger un step. Mesuré le
2026-07-17 sur le cas 1 : l'échec était dans un step de **baseline RPC** ; l'agent a corrigé le
`HTTPError 404` (le garde-fou transport de `0003` l'y forçait) **et** réécrit au passage
l'**authentification**, avec un `fill()` nu là où le step partagé gère un champ non visible
(`force=True`) → `TimeoutError`. Deux réparations perdues, la troisième (`v9`) avait réussi
uniquement parce qu'elle **déléguait** l'auth au step partagé.

Rien ne voyait ce rayon d'explosion : `reserved_steps` bloque la **collision de libellés**, pas la
**réécriture** d'un step voisin sous le même nom.

────────────────────────────────────────────────────────────────────────────────────
CE QU'ELLE NE FAIT PAS, ET POURQUOI
────────────────────────────────────────────────────────────────────────────────────
Elle ne cherche PAS à savoir quel step Python correspond au step Gherkin en échec. Mesuré :
**14 des 20** steps réels du cas 1 portent des paramètres (`'le ticket a l'equipe "{team_name}"
id {team_id:d}'`) — les relier au texte d'un échec exigerait un matcher de motifs, c'est-à-dire
un **second** matcher à côté de celui de Behave. S'il divergeait, on accuserait le mauvais step
(docs/PRINCIPES.md, principe 4).

Pour une garde détective, ce raffinement n'achète rien : le relecteur voit déjà à l'écran quel
step a échoué. Lui dire « 8 steps modifiés pour 1 échec » suffit à déclencher son jugement.

Module PUR : AST uniquement, aucun réseau, aucun LLM, aucune exécution. Coût nul.
"""

from __future__ import annotations

import ast

from testpilot.generation import steps_library

# Types de warnings (miroir de `assertion_lint` : même contrat de sortie pour le même bandeau).
BODY_CHANGED = "step_modifie"
STEP_REMOVED = "step_supprime"
# Lot 09 (C9) — ce que `blast_radius` (steps.py) ne voit PAS : un changement du `.feature`
# lui-même (jamais gelé pour l'agent de CORRECTION, contrairement à l'agent de RÉPARATION dont le
# `.feature` est « gelé, sauf deux exceptions » par son propre prompt — voir `repair_prompt.md`).
SCENARIO_SUPPRIME = "scenario_supprime"
ASSERTION_MODIFIEE = "assertion_modifiee"
EXEMPLE_MODIFIE = "exemple_modifie"
# `@then` spécifiquement (sous-ensemble de BODY_CHANGED, plus grave) : le CODE d'une assertion a
# changé, pas seulement un step technique — voir `blast_radius_then`.
THEN_BODY_CHANGED = "assertion_code_modifiee"


def _corps_par_label(source: str) -> dict[str, str]:
    """Corps (normalisé) de chaque step déclaré, indexé par libellé.

    On compare le CODE, pas le texte : `ast.dump` neutralise les commentaires, l'indentation et
    les blancs. Renommer une variable reste un changement — c'en est un.
    """
    return {label: corps for label, (_kw, corps) in _corps_et_mot_cle_par_label(source).items()}


def _corps_et_mot_cle_par_label(source: str) -> dict[str, tuple[str, str]]:
    """`{libellé: (mot-clé Gherkin, corps normalisé)}` — le mot-clé permet à `blast_radius` de
    distinguer un `@then` réécrit (une ASSERTION a changé, plus grave) d'un `@given`/`@when`
    réécrit (une étape technique)."""
    try:
        tree = ast.parse(source or "")
    except SyntaxError:
        return {}

    resultat: dict[str, tuple[str, str]] = {}
    for step in steps_library.extract_steps(source or ""):
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if step.label not in {_label_de(deco) for deco in node.decorator_list}:
                continue
            resultat[step.label] = (
                step.keyword, ast.dump(ast.Module(body=node.body, type_ignores=[])))
    return resultat


def _label_de(deco) -> str:
    """Libellé porté par un décorateur `@given("…")`. Chaîne vide si ce n'en est pas un."""
    if isinstance(deco, ast.Call) and deco.args:
        arg = deco.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return arg.value
    return ""


def blast_radius(avant: str, apres: str) -> list[dict]:
    """Steps dont le CORPS a changé (ou qui ont disparu) entre deux versions.

    Rend une liste de warnings au même format que `assertion_lint.lint_steps` — c'est le même
    bandeau, non bloquant, qui les affiche. Vide s'il n'y a rien à signaler.

    ⚠️ **Un `@then` réécrit porte un `kind` DISTINCT** (`THEN_BODY_CHANGED`, pas `BODY_CHANGED`) —
    lot 09 (C9) : le corps d'un `@then` EST l'assertion elle-même (`constater(...)`), pas une
    étape technique. Le rayon d'explosion du cas 1 (2026-07-17, docstring du module) touchait un
    `@given` ; un `@then` réécrit est la faute que `repair_prompt.md` interdit explicitement
    (« RÈGLE ABSOLUE — ne jamais maquiller ») — ce module la rend VÉRIFIABLE après coup, pas
    seulement demandée au texte de l'agent (décision 0015 : le texte de l'agent n'est jamais une
    source de vérité).
    """
    avec_mot_cle_avant = _corps_et_mot_cle_par_label(avant)
    corps_apres = _corps_par_label(apres)
    if not avec_mot_cle_avant:
        return []   # rien à comparer : première version, ou code d'avant illisible

    warnings: list[dict] = []
    for label, (mot_cle, corps) in avec_mot_cle_avant.items():
        if label not in corps_apres:
            warnings.append({
                "step": label, "line": 0, "kind": STEP_REMOVED,
                "message": (f"Le step « {label} » existait avant la réparation et a DISPARU. "
                            "Si le scénario qui l'utilisait a été retiré, la couverture a reculé "
                            "sans que rien n'échoue."),
            })
        elif corps_apres[label] != corps:
            if mot_cle == "then":
                warnings.append({
                    "step": label, "line": 0, "kind": THEN_BODY_CHANGED,
                    "message": (f"Le CODE de l'assertion « {label} » (un `@then`) a été réécrit. "
                                "Une assertion modifiée peut changer ce qu'elle prouve, pas "
                                "seulement comment — vérifiez qu'elle affirme toujours la même "
                                "chose avant d'approuver."),
                })
            else:
                warnings.append({
                    "step": label, "line": 0, "kind": BODY_CHANGED,
                    "message": (f"Le code du step « {label} » a été réécrit par la réparation. "
                                "Vérifiez qu'il devait l'être : l'agent réécrit le fichier entier, "
                                "donc il peut abîmer un step qui marchait."),
                })
    return warnings


# ── Ce que `blast_radius` ne voit JAMAIS : le `.feature` lui-même (lot 09, C9) ──────────────────
#
# `blast_radius` compare `_steps.py` (le CODE) ; il ne dit rien d'un scénario supprimé, d'une
# ligne `Alors`/`Et` réécrite ou d'une valeur de table `Examples` changée — trois façons de
# « maquiller » un test SANS toucher un seul `@then` Python (ex. retirer le scénario qui échoue,
# ou changer la valeur attendue dans le `.feature` plutôt que dans le step). `repair_prompt.md`
# l'interdit déjà en texte (« RÈGLE ABSOLUE ») ; ceci le rend VÉRIFIABLE, pas seulement demandé.

def _scenarios_et_exemples(feature_content: str) -> dict[str, dict]:
    """`{nom du scénario/plan: {alors, exemples}}` — jamais les scénarios EXPANSÉS par ligne
    d'Examples (behave les suffixe `-- @N.M`, pas des déclarations distinctes du texte). Vide si
    le contenu ne parse pas (jamais une exception : un `.feature` cassé est déjà rattrapé par
    `write_feature_file`, cette fonction ne fait qu'observer)."""
    from behave.parser import ParserError, parse_feature
    try:
        feature = parse_feature(feature_content or "", language="fr")
    except ParserError:
        return {}
    if not feature:
        return {}

    resultat: dict[str, dict] = {}
    for scenario in feature.walk_scenarios(with_outlines=True):
        if " -- @" in scenario.name:
            continue
        alors: list[str] = []
        vu_alors = False
        for step in scenario.steps:
            if step.keyword.strip() in ("Alors", "Donc"):
                vu_alors = True
            if vu_alors:
                alors.append(f"{step.keyword.strip()} {step.name}")
        exemples = [
            (tuple(ex.table.headings), tuple(tuple(row) for row in ex.table.rows))
            for ex in (getattr(scenario, "examples", None) or [])
        ]
        resultat[scenario.name] = {"alors": alors, "exemples": exemples}
    return resultat


def diff_feature(avant: str, apres: str) -> list[dict]:
    """Ce qu'une réparation/correction a changé dans le `.feature` — scénario supprimé, constats
    (`Alors`/`Et`) réécrits, valeurs de la table `Examples` changées. Même contrat de sortie que
    `blast_radius` (même bandeau) ; vide si rien à signaler ou si `avant` ne parse pas."""
    avant_map = _scenarios_et_exemples(avant)
    if not avant_map:
        return []
    apres_map = _scenarios_et_exemples(apres)

    warnings: list[dict] = []
    for nom, info in avant_map.items():
        if nom not in apres_map:
            warnings.append({
                "step": nom, "line": 0, "kind": SCENARIO_SUPPRIME,
                "message": (f"Le scénario « {nom} » existait avant et a DISPARU du `.feature`. "
                            "Une réparation/correction ne doit jamais retirer un scénario (§5 du "
                            "brief : jamais de masquage d'échec par perte de couverture)."),
            })
            continue
        if info["alors"] != apres_map[nom]["alors"]:
            warnings.append({
                "step": nom, "line": 0, "kind": ASSERTION_MODIFIEE,
                "message": (f"Les constats (Alors/Et) du scénario « {nom} » ont changé. Ça ne "
                            "doit jamais arriver en réparant COMMENT le test agit — vérifiez que "
                            "l'intention d'origine (ce que le scénario prouve) est intacte."),
            })
        if info["exemples"] != apres_map[nom]["exemples"]:
            warnings.append({
                "step": nom, "line": 0, "kind": EXEMPLE_MODIFIE,
                "message": (f"La table Examples du scénario « {nom} » a changé de valeurs. Une "
                            "valeur d'exemple modifiée peut déguiser un cas qui échouait en cas "
                            "qui passe — vérifiez qu'elle teste toujours ce qui était prévu."),
            })
    return warnings


def resume(avant: str, apres: str) -> str:
    """Une phrase pour un humain pressé. Vide si aucun step n'a bougé."""
    warnings = blast_radius(avant, apres)
    if not warnings:
        return ""
    modifies = sum(1 for w in warnings if w["kind"] in (BODY_CHANGED, THEN_BODY_CHANGED))
    supprimes = sum(1 for w in warnings if w["kind"] == STEP_REMOVED)
    total = len(_corps_par_label(avant))
    morceaux = []
    if modifies:
        morceaux.append(f"{modifies} step(s) réécrit(s)")
    if supprimes:
        morceaux.append(f"{supprimes} step(s) supprimé(s)")
    return f"Réparation : {' et '.join(morceaux)} sur {total} — rayon d'explosion à vérifier."
