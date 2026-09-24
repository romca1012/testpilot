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
import functools
from typing import TYPE_CHECKING

from testpilot import config
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


# ── Gardes de PLACEMENT des assertions (lot 03, D4 — régime BLOQUANT) ────────────────────────────
#
# Le runtime (D3) prouve qu'un scénario vert a exécuté au moins un constat ; ces gardes disent à
# l'agent, AVANT tout run, où l'écrire. Un refus déterministe coûte moins qu'un run réel raté.
# Dérogation au régime détectif de 0008 (`assertion_lint`, inchangé pour les tautologies) : la faute
# est mesurable au runtime, donc le refus n'est pas une hypothèse.

_CONSTATER = {"constater", "constater_visible", "constater_texte"}


def _nom_appele(noeud: ast.Call) -> str:
    cible = noeud.func
    if isinstance(cible, ast.Name):
        return cible.id
    if isinstance(cible, ast.Attribute):
        return cible.attr
    return ""


def _decorateurs(func) -> set[str]:
    noms = set()
    for deco in func.decorator_list:
        cible = deco.func if isinstance(deco, ast.Call) else deco
        if isinstance(cible, ast.Name):
            noms.add(cible.id)
        elif isinstance(cible, ast.Attribute):
            noms.add(cible.attr)
    return noms


@functools.lru_cache(maxsize=4)
def _noms_qui_constatent(chemin: str, mtime: float) -> frozenset[str]:
    """Les noms de la bibliothèque qui CONSIGNENT un constat : `constater*`, les fonctions décorées
    `@constat`, et — point fixe — toute fonction qui en appelle une. Lu dans `_base_helpers.py` par
    AST : le code reste la source de vérité, aucune liste à tenir à jour."""
    try:
        with open(chemin, encoding="utf-8") as handle:
            arbre = ast.parse(handle.read())
    except (OSError, SyntaxError):
        return frozenset(_CONSTATER)
    fonctions = {n.name: n for n in arbre.body if isinstance(n, ast.FunctionDef)}
    noms = set(_CONSTATER) | {nom for nom, f in fonctions.items() if "constat" in _decorateurs(f)}
    change = True
    while change:
        change = False
        for nom, f in fonctions.items():
            if nom in noms:
                continue
            if any(isinstance(n, ast.Call) and _nom_appele(n) in noms for n in ast.walk(f)):
                noms.add(nom)
                change = True
    return frozenset(noms)


def _helpers_qui_constatent() -> frozenset[str]:
    chemin = config.STEPS_LIBRARY_DIR / "_base_helpers.py"
    try:
        mtime = chemin.stat().st_mtime
    except OSError:
        mtime = 0.0
    return _noms_qui_constatent(str(chemin), mtime)


def _affirme(noeud: ast.AST) -> str:
    """Ce qui, dans ce nœud, est une ASSERTION écrite à la main ou un constat, sinon `""`."""
    if isinstance(noeud, ast.Assert):
        return "`assert`"
    if isinstance(noeud, ast.Raise) and noeud.exc is not None:
        cible = noeud.exc.func if isinstance(noeud.exc, ast.Call) else noeud.exc
        if isinstance(cible, ast.Name) and cible.id == "AssertionError":
            return "`raise AssertionError`"
    if isinstance(noeud, ast.Call):
        nom = _nom_appele(noeud)
        if nom == "expect":
            return "`expect(...)`"
        if nom in _CONSTATER:
            return f"`{nom}(...)`"
    return ""


def _avale_l_echec(handler: ast.ExceptHandler) -> bool:
    """Un `except` nu, `except Exception` ou `except BaseException` qui ne relève JAMAIS."""
    if handler.type is None:
        large = True
    else:
        cible = handler.type
        nom = cible.id if isinstance(cible, ast.Name) else getattr(cible, "attr", "")
        large = nom in {"Exception", "BaseException", "AssertionError"}
    return large and not any(isinstance(n, ast.Raise) for n in ast.walk(handler))


def _forbidden_assertion_placement(tree: ast.AST) -> str:
    """Décrit la première faute de placement d'assertion (D4), sinon chaîne vide.

    1. une assertion ou un constat dans une fonction `@given`/`@when`/`@step` (sans `@then`) : le type
       du step est un signal de structure — une assertion hors `Alors` est classée « prérequis non
       rempli » (`@given`) ou « test cassé » (`@when`), jamais comme un constat sur l'application ;
    2. une fonction `@then` qui n'appelle ni `constater*` ni un helper de la bibliothèque qui en
       appelle : elle ne peut consigner aucun constat, donc ne prouve rien ;
    3. dans une fonction `@then`, un `except` large dont le corps ne relève pas : il avale l'échec.

    ⚠️ **Filet, pas preuve** : une assertion posée dans un helper NON décoré défini dans le fichier
    et appelé depuis un `@given`/`@when` n'est pas vue ; le runtime (D3) attrape ce qui reste.
    """
    constatent = _helpers_qui_constatent()
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        decorateurs = _decorateurs(func)
        est_then = "then" in decorateurs
        est_contexte = bool(decorateurs & {"given", "when", "step"}) and not est_then
        if est_contexte:
            for n in ast.walk(func):
                trouve = _affirme(n)
                if trouve:
                    return (f"{trouve} dans le step `{func.name}` (`@given`/`@when`) : une assertion "
                            "n'a sa place que dans un `@then`. Dans un Soit/Quand, prépare ou agis ; "
                            "déplace la vérification dans un step « Alors »")
        if est_then:
            appels = {_nom_appele(n) for n in ast.walk(func) if isinstance(n, ast.Call)}
            if not (appels & constatent):
                return (f"le step `@then` `{func.name}` n'appelle ni `constater(...)` ni un helper de "
                        "la bibliothèque qui constate : il ne peut consigner aucun constat, donc ne "
                        "prouve rien. Écris `constater(condition, \"message\")` "
                        "(ou `constater_visible` / `constater_texte`)")
            for n in ast.walk(func):
                if isinstance(n, ast.ExceptHandler) and _avale_l_echec(n):
                    return (f"le step `@then` `{func.name}` contient un `except` large qui ne relève "
                            "pas : il avale l'échec de la vérification. Retire le `try/except`, ou "
                            "relève l'exception (`raise`)")
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

    # 5. Placement des assertions (lot 03, D4) : régime BLOQUANT, comme le transport et le comptage.
    faute = _forbidden_assertion_placement(tree)
    if faute:
        return _outcome(
            f"[write_steps_file] ASSERTION_MAL_PLACEE : {faute}. Les vérifications s'écrivent "
            "`constater(...)` UNIQUEMENT dans un step `@then`, puis rappelle write_steps_file.",
            ok=False,
        )

    path = ctx.generated_dir / f"{ctx.module_name}_steps.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return _outcome(
        f"[write_steps_file] OK — {path.name}, {len(declared)} step(s) déclaré(s).",
        steps_content=content,
    )
