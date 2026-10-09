"""Gel des vérifications : une réparation peut corriger OÙ un test lit l'application, jamais CE QU'IL AFFIRME (lot VH-03, V3).

Pourquoi. Audit du 2026-10-08 : le gel du `.feature` pendant une réparation n'existait que dans le prompt ; l'agent disposait de
`write_feature_file` et `write_steps_file`, et une réparation pouvait réécrire un `Alors`, une valeur attendue ou une table
d'Exemples — puis le test « réparé » passait. Un test qui cesse d'accuser l'application parce qu'on a changé ce qu'il vérifie,
c'est exactement un faux `conforme`.

Ce qui est gelé :
- dans le `.feature` : pour chaque scénario existant, la suite de ses steps `Alors` (type `then`, `Et`/`Mais` compris) et ses
  tables d'Exemples ; un scénario existant ne disparaît ni ne change de nom (ajouter un scénario reste possible) ;
- dans le `_steps.py` : chaque fonction `@then`, et chaque fonction du fichier qu'elle appelle, à l'ADRESSAGE près — les chaînes
  passées aux méthodes qui désignent un élément (`locator`, `get_by_role`…) et les délais (`timeout=`) peuvent changer ; tout le
  reste (comparaisons, valeurs attendues, appels à `constater`, structure) est figé.

Module PUR : aucune I/O, aucun LLM ; parsing Gherkin par Behave (déjà la référence de `write_feature_file`).
"""

from __future__ import annotations

import ast

_ADRESSAGE = frozenset({"locator", "get_by_role", "get_by_label", "get_by_text", "get_by_placeholder", "get_by_test_id",
                        "get_by_title", "get_by_alt_text", "query_selector", "query_selector_all", "wait_for_selector",
                        "frame_locator", "filter", "nth"})
_DELAIS = frozenset({"timeout", "delay"})


def _alors_et_exemples(feature: str) -> dict[str, tuple] | None:
    from behave.parser import ParserError, parse_feature

    try:
        parsed = parse_feature(feature, language="fr")
    except ParserError:
        return None
    if parsed is None:
        return {}
    gel: dict[str, tuple] = {}
    for scenario in parsed.walk_scenarios(with_outlines=True):
        alors = tuple(step.name for step in scenario.steps if step.step_type == "then")
        exemples = tuple(tuple(tuple(ligne.cells) for ligne in (ex.table.rows if ex.table else []))
                         for ex in getattr(scenario, "examples", []) or [])
        gel[scenario.name] = (alors, exemples)
    return gel


def feature_modifiee(reference: str, proposition: str) -> list[str]:
    """Ce que `proposition` change à ce que `reference` VÉRIFIE (liste vide si rien)."""
    avant, apres = _alors_et_exemples(reference), _alors_et_exemples(proposition)
    if avant is None or apres is None:
        return []  # un Gherkin illisible est refusé ailleurs (`write_feature_file`)
    ecarts = []
    for nom, (alors, exemples) in avant.items():
        if nom not in apres:
            ecarts.append(f"le scénario « {nom} » a disparu ou changé de nom")
            continue
        alors_apres, exemples_apres = apres[nom]
        if alors_apres != alors:
            ecarts.append(f"les vérifications « Alors » du scénario « {nom} » ont changé")
        if exemples_apres != exemples:
            ecarts.append(f"les Exemples du scénario « {nom} » ont changé")
    return ecarts


class _SansAdressage(ast.NodeTransformer):
    """Remplace les chaînes passées aux méthodes d'adressage et les délais par un repère neutre."""

    def visit_Call(self, noeud: ast.Call):
        self.generic_visit(noeud)
        if isinstance(noeud.func, ast.Attribute) and noeud.func.attr in _ADRESSAGE:
            noeud.args = [ast.Constant("<ADRESSE>") if isinstance(a, (ast.Constant, ast.JoinedStr)) else a
                          for a in noeud.args]
            for k in noeud.keywords:
                if isinstance(k.value, (ast.Constant, ast.JoinedStr)) and k.arg not in {None}:
                    k.value = ast.Constant("<ADRESSE>")
        for k in noeud.keywords:
            if k.arg in _DELAIS:
                k.value = ast.Constant("<DELAI>")
        return noeud


def _signature(fonction: ast.AST) -> str:
    copie = ast.parse(ast.unparse(fonction))
    corps = copie.body[0]
    if (corps.body and isinstance(corps.body[0], ast.Expr) and isinstance(corps.body[0].value, ast.Constant)
            and isinstance(corps.body[0].value.value, str)):
        corps.body = corps.body[1:]  # la docstring n'est pas une vérification
    return ast.dump(_SansAdressage().visit(copie), annotate_fields=False)


def _decores_then(fonction: ast.AST) -> bool:
    for deco in fonction.decorator_list:
        cible = deco.func if isinstance(deco, ast.Call) else deco
        if getattr(cible, "id", getattr(cible, "attr", "")) == "then":
            return True
    return False


def _fonctions_qui_verifient(arbre: ast.AST) -> dict[str, ast.AST]:
    """Les fonctions `@then` et, transitivement, les fonctions du fichier qu'elles appellent."""
    toutes = {n.name: n for n in arbre.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    retenues = {nom: f for nom, f in toutes.items() if _decores_then(f)}
    a_voir = list(retenues.values())
    while a_voir:
        f = a_voir.pop()
        for n in ast.walk(f):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in toutes \
                    and n.func.id not in retenues:
                retenues[n.func.id] = toutes[n.func.id]
                a_voir.append(toutes[n.func.id])
    return retenues


def steps_modifies(reference: str, proposition: str) -> list[str]:
    """Ce que `proposition` change aux fonctions qui VÉRIFIENT de `reference`, adressage mis à part."""
    try:
        avant, apres = ast.parse(reference), ast.parse(proposition)
    except SyntaxError:
        return []  # refusé ailleurs (`write_steps_file`)
    gelees = _fonctions_qui_verifient(avant)
    disponibles = {n.name: n for n in apres.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    ecarts = []
    for nom, fonction in gelees.items():
        if nom not in disponibles:
            ecarts.append(f"la fonction de vérification `{nom}` a disparu")
        elif _signature(disponibles[nom]) != _signature(fonction):
            ecarts.append(f"la fonction de vérification `{nom}` a changé au-delà de l'adressage (sélecteurs, délais)")
    return ecarts
