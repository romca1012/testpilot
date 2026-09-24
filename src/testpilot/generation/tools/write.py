"""Tools d'écriture des fichiers Behave, avec validation avant persistance.

Règles verrouillées (issues des erreurs récurrentes du prototype) :
  - guillemets ASCII uniquement (les typographiques cassent ``ast.parse``) ;
  - un fichier _steps.py ne redéfinit jamais un step de la bibliothèque partagée
    (sinon AmbiguousStep au run) — la liste réservée vient de ToolContext ;
  - un step généré ne réinvente pas son propre transport HTTP (décision 0003) : il passe
    par ``context.odoo`` (RPC) ou ``context.page`` (navigateur), jamais par ``requests``.
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from testpilot.generation import steps_library
from testpilot.generation.references import message_refus, verifier_references

if TYPE_CHECKING:
    from testpilot.generation.tools import ToolContext, ToolOutcome

_CURLY = "‘’“”"

# Bibliothèques d'accès réseau brut interdites dans un step généré. L'e2e a montré le
# problème : l'agent a écrit son propre helper `requests` vers /web/dataset/call_kw — une
# route interne, appelée hors session → 404, et 3 scénarios morts avant toute vérification.
_FORBIDDEN_IMPORTS = {"requests", "urllib", "urllib3", "httpx", "http", "aiohttp"}
# Endpoints internes d'Odoo : jamais appelés en direct par un test (c'est le rôle du RPC).
_FORBIDDEN_ENDPOINTS = ("/web/dataset", "/jsonrpc", "/xmlrpc")


def _outcome(observation: str, ok: bool = True, **kw):
    from testpilot.generation.tools import ToolOutcome
    return ToolOutcome(observation=observation, ok=ok, **kw)


def _forbidden_transport(tree: ast.AST, content: str) -> str:
    """Décrit le transport interdit trouvé dans un fichier de steps, sinon chaîne vide.

    Les imports sont détectés via l'AST (une regex confondrait un import réel avec une
    mention en commentaire ou en docstring) ; les endpoints internes le sont sur le texte.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in _FORBIDDEN_IMPORTS:
                    return f"import de `{alias.name}`"
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            if root in _FORBIDDEN_IMPORTS:
                return f"import depuis `{node.module}`"

    for endpoint in _FORBIDDEN_ENDPOINTS:
        if endpoint in content:
            return f"appel direct à l'endpoint interne `{endpoint}`"
    return ""


_LECTURES_RPC = {"search", "read", "search_read"}


def _touche_env(noeud: ast.AST, alias: frozenset = frozenset()) -> bool:
    return any((isinstance(n, ast.Attribute) and n.attr in {"env", "odoo"})
               or (isinstance(n, ast.Name) and (n.id in {"env", "odoo"} or n.id in alias))
               for n in ast.walk(noeud))


def _est_lecture_rpc(noeud: ast.AST, alias: frozenset = frozenset()) -> bool:
    return (isinstance(noeud, ast.Call) and isinstance(noeud.func, ast.Attribute)
            and noeud.func.attr in _LECTURES_RPC and _touche_env(noeud.func.value, alias))


def _forbidden_recount(tree: ast.AST) -> str:
    """Décrit un COMPTAGE écrit par l'agent (§F9, 2026-09-23), sinon chaîne vide.

    Un step généré qui recompte lui-même (`search_count`, ou `len()` d'un `search`/`read`
    RPC) contourne les helpers cloisonnés du lot 01 (`id > max_id`) et réintroduit le faux
    PASSED de F1 — dans le code GÉNÉRÉ, là où aucun test du dépôt ne le voit (mesuré en
    campagne réelle, cas 95, 23/09). Détection par AST : ni un commentaire ni une chaîne ne
    déclenchent, un `len()` sur une variable n'est vu que si elle vient d'une lecture RPC, et
    un alias local d'un modèle (`M = context.odoo.env['m']` puis `M.search_count([])`) est suivi.

    ⚠️ **Limites assumées — c'est un filet, pas une preuve d'absence de comptage** : ne sont PAS
    vus `getattr(m, 'search_count')`, un comptage indirect (`sum(1 for _ in m.search([]))`,
    `read_group`), un alias posé hors de la fonction (niveau module) ou passé en argument. Un
    agent déterminé les contourne ; ce garde ferme la forme littérale que l'agent produit
    réellement (mesuré : cas 95) et redirige vers le catalogue. Faux positif assumé : tout
    `len(search(...))` sur `env`/`odoo`, même légitime, est refusé.
    """
    portees = [n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))] or [tree]
    for portee in portees:
        affectations = [n for n in ast.walk(portee) if isinstance(n, ast.Assign)]
        alias = frozenset(
            c.id for n in affectations if isinstance(n.value, (ast.Subscript, ast.Attribute))
            and _touche_env(n.value) for c in n.targets if isinstance(c, ast.Name))
        issus_de_lecture = {
            c.id for n in affectations if _est_lecture_rpc(n.value, alias)
            for c in n.targets if isinstance(c, ast.Name)}
        for n in ast.walk(portee):
            if not isinstance(n, ast.Call):
                continue
            if (isinstance(n.func, ast.Attribute) and n.func.attr == "search_count"
                    and _touche_env(n.func.value, alias)):
                return "appel à `search_count` sur `context.odoo.env`"
            if isinstance(n.func, ast.Name) and n.func.id == "len" and n.args:
                arg = n.args[0]
                if _est_lecture_rpc(arg, alias) or (isinstance(arg, ast.Name)
                                                    and arg.id in issus_de_lecture):
                    return "`len()` d'une lecture `search`/`read` sur `context.odoo.env`"
    return ""


def write_feature_file(ctx: "ToolContext", content: str) -> "ToolOutcome":
    if not content.strip():
        return _outcome("[write_feature_file] contenu vide", ok=False)
    from behave.parser import ParserError, parse_feature
    try:
        feature = parse_feature(content, language="fr")
        scenarios = list(feature.walk_scenarios()) if feature else []
        outlines_vides = feature and any(
            hasattr(s, "examples") and not s.scenarios
            for s in feature.walk_scenarios(with_outlines=True))
    except ParserError as exc:
        return _outcome(f"[write_feature_file] GHERKIN_INVALIDE : {exc}", ok=False)
    if not scenarios or outlines_vides or any(not scenario.steps for scenario in scenarios):
        return _outcome(
            "[write_feature_file] SCENARIO_VIDE : fournis au moins un scénario avec des "
            "étapes ; chaque plan de scénario doit avoir des exemples exécutables.", ok=False)
    # Lot 12 (D11) : référence PROUVÉE inexistante → refus bloquant, là où la source fait autorité
    # (champ relationnel Odoo par `name_search` RPC ; `<select>` entièrement relevé).
    recherche = None
    if ctx.connector is not None:
        def recherche(modele, texte, limite):
            return ctx.connector.name_search(modele, texte, limite)
    refus = verifier_references(content, ctx.options_select, ctx.champs_relationnels, recherche)
    if refus:
        return _outcome(message_refus(refus), ok=False)
    path = ctx.generated_dir / f"{ctx.module_name}.feature"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return _outcome(
        f"[write_feature_file] OK — {path.name}, {len(scenarios)} scénario(s).",
        feature_content=content,
    )


def write_steps_file(ctx: "ToolContext", content: str) -> "ToolOutcome":
    # 1. Guillemets typographiques → ast.parse échouerait au run.
    curly = {c for c in content if c in _CURLY}
    if curly:
        return _outcome(
            "[write_steps_file] SYNTAX_ERROR : guillemets typographiques interdits "
            f"({''.join(sorted(curly))}). Utilise ' et \" ASCII, puis rappelle write_steps_file.",
            ok=False,
        )

    # 2. Syntaxe Python valide.
    try:
        tree = ast.parse(content)
    except SyntaxError as exc:
        return _outcome(f"[write_steps_file] SYNTAX_ERROR : {exc.msg} (ligne {exc.lineno})", ok=False)

    # 3. Aucun transport réinventé (décision 0003).
    forbidden = _forbidden_transport(tree, content)
    if forbidden:
        return _outcome(
            f"[write_steps_file] TRANSPORT_INTERDIT : {forbidden}. Un step ne fabrique pas ses "
            "propres appels HTTP — utilise `context.odoo` (lecture/écriture RPC) ou `context.page` "
            "(Playwright) pour agir dans le navigateur. Réutilise d'abord les steps partagés "
            "listés dans le prompt, puis rappelle write_steps_file.",
            ok=False,
        )

    # 3bis. Aucun comptage réécrit par l'agent (§F9) : régime BLOQUANT, comme le transport.
    recompte = _forbidden_recount(tree)
    if recompte:
        return _outcome(
            f"[write_steps_file] COMPTAGE_INTERDIT : {recompte}. Un step ne recompte pas les "
            "enregistrements lui-même (un tiers actif sur l'instance fausserait le verdict). "
            "Utilise les steps du catalogue : « le nombre d'enregistrements dans le modèle "
            "\"<modèle>\" est enregistré pour comparaison », puis « … augmente de 1 » ou "
            "« … n'a pas augmenté ». Si le besoin n'est pas couvert, dis-le dans ta réponse "
            "plutôt que de compter toi-même.",
            ok=False,
        )

    # 4. Aucune redéfinition d'un step de la bibliothèque partagée.
    declared = {step.label for step in steps_library.extract_steps(content)}
    clashing = sorted(declared & ctx.reserved_steps)
    if clashing:
        return _outcome(
            "[write_steps_file] AmbiguousStep : ces steps existent déjà dans la "
            f"bibliothèque partagée, ne les redéfinis pas : {clashing}.",
            ok=False,
        )

    path = ctx.generated_dir / f"{ctx.module_name}_steps.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return _outcome(
        f"[write_steps_file] OK — {path.name}, {len(declared)} step(s) déclaré(s).",
        steps_content=content,
    )
