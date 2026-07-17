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


def _corps_par_label(source: str) -> dict[str, str]:
    """Corps (normalisé) de chaque step déclaré, indexé par libellé.

    On compare le CODE, pas le texte : `ast.dump` neutralise les commentaires, l'indentation et
    les blancs. Renommer une variable reste un changement — c'en est un.
    """
    try:
        tree = ast.parse(source or "")
    except SyntaxError:
        return {}

    corps: dict[str, str] = {}
    for step in steps_library.extract_steps(source or ""):
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if step.label not in {_label_de(deco) for deco in node.decorator_list}:
                continue
            corps[step.label] = ast.dump(ast.Module(body=node.body, type_ignores=[]))
    return corps


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
    """
    corps_avant = _corps_par_label(avant)
    corps_apres = _corps_par_label(apres)
    if not corps_avant:
        return []   # rien à comparer : première version, ou code d'avant illisible

    warnings: list[dict] = []
    for label, corps in corps_avant.items():
        if label not in corps_apres:
            warnings.append({
                "step": label, "line": 0, "kind": STEP_REMOVED,
                "message": (f"Le step « {label} » existait avant la réparation et a DISPARU. "
                            "Si le scénario qui l'utilisait a été retiré, la couverture a reculé "
                            "sans que rien n'échoue."),
            })
        elif corps_apres[label] != corps:
            warnings.append({
                "step": label, "line": 0, "kind": BODY_CHANGED,
                "message": (f"Le code du step « {label} » a été réécrit par la réparation. "
                            "Vérifiez qu'il devait l'être : l'agent réécrit le fichier entier, "
                            "donc il peut abîmer un step qui marchait."),
            })
    return warnings


def resume(avant: str, apres: str) -> str:
    """Une phrase pour un humain pressé. Vide si aucun step n'a bougé."""
    warnings = blast_radius(avant, apres)
    if not warnings:
        return ""
    modifies = sum(1 for w in warnings if w["kind"] == BODY_CHANGED)
    supprimes = sum(1 for w in warnings if w["kind"] == STEP_REMOVED)
    total = len(_corps_par_label(avant))
    morceaux = []
    if modifies:
        morceaux.append(f"{modifies} step(s) réécrit(s)")
    if supprimes:
        morceaux.append(f"{supprimes} step(s) supprimé(s)")
    return f"Réparation : {' et '.join(morceaux)} sur {total} — rayon d'explosion à vérifier."
