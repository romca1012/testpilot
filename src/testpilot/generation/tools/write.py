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

from testpilot.generation import enregistrement_lint, litteraux_observes, steps_library
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
                if root in _FORBIDDEN_IMPORTS or root == "testpilot":
                    return f"import de `{alias.name}`"
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            # Lot 07e (D7, revue du 2026-09-28) : le paquet applicatif `testpilot` n'est JAMAIS
            # importé par un step généré (le prompt système n'enseigne que `_base_helpers`,
            # `features.environment`, `behave`) — bannir la RACINE entière, pas seulement un
            # sous-module précis, ferme aussi un contournement PAR ATTRIBUT (importer un paquet
            # PARENT puis nommer un sous-module sensible en pointillé dans le code, jamais dans une
            # clause `import`/`from` — donc invisible à une détection limitée à un sous-module précis).
            if root in _FORBIDDEN_IMPORTS or root == "testpilot":
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


def _forbidden_source_kwarg(tree: ast.AST) -> str:
    """Décrit un appel `constater(..., source=...)` LITTÉRAL (lot 07e, D7), sinon chaîne vide.

    ⚠️ **Message précoce, pas la garantie elle-même** (revue du 2026-09-28, 3e passe). La 2e revue a
    montré qu'une garde par AST limitée à cette forme se contourne par un 3e argument POSITIONNEL,
    un déballage `**{...}` ou un alias d'import (`from _base_helpers import constater as c`) — trois
    formes qu'aucune détection AST ne ferme EXHAUSTIVEMENT (un agent peut toujours renommer,
    déballer ou compter les positions). La VRAIE garantie tient désormais à la SIGNATURE de
    `constater(condition, message)` elle-même (`_base_helpers.py`, plus de paramètre `source`
    du tout) : un 3e argument, sous QUELQUE forme que ce soit, lève un `TypeError` au lieu de forger
    un signal. Ce garde-ci ne fait que transformer le cas le plus probable (le mot-clé littéral,
    celui qu'un agent écrirait naturellement après avoir vu `source` dans un message d'erreur ou une
    trace) en un refus déterministe AVANT le run, plutôt qu'en un crash runtime moins lisible.
    """
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and _nom_appele(node) == "constater"
                and any(kw.arg == "source" for kw in node.keywords)):
            return "argument `source=` d'un appel à `constater`"
    return ""


# Q1 (revue du 2026-10-07) : noms du MÉCANISME de preuve, réservés au socle. Un step généré qui s'en servirait
# pourrait se déclarer « non assertif » ou fausser le compteur pour masquer un `Alors` vide. Le refus est un message
# PRÉCOCE ; la garantie est STRUCTURELLE (`environment._est_exempte_non_assertive` n'exempte jamais une fonction du
# fichier généré) — même doctrine que `source=` (lot 07e) : un garde par forme de code ne ferme jamais la classe.
_RESERVES_AU_SOCLE = frozenset({
    "non_assertif", "_tp_non_assertif", "_COMPTEUR_CONSTATS", "nombre_de_constats_reussis",
    "consigner_alors_sans_constat", "_consigner_constat", "_SOURCE_CONSTAT", "_source_du_constat",
    "definir_etat_constat", "TP_GENERATED_STEPS_FILE",
    # Lot VH-02 (revue du 2026-10-08) : la garde des constats qui ne prouvent rien, et le fichier où les constats sont consignés.
    "_condition_toujours_vraie", "ConstatInvalideError", "TP_CONSTATS_FILE",
})


def _forbidden_reserve_au_socle(tree: ast.AST) -> str:
    """Décrit la première référence à un nom du mécanisme de preuve (`Name`, `Attribute`, import, ou chaîne
    littérale type `setattr(f, "_tp_non_assertif", True)`), sinon chaîne vide."""
    for node in ast.walk(tree):
        nom = ""
        if isinstance(node, ast.Name):
            nom = node.id
        elif isinstance(node, ast.Attribute):
            nom = node.attr
        elif isinstance(node, ast.alias):
            nom = node.name
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            nom = node.value
        if nom in _RESERVES_AU_SOCLE:
            return f"« {nom} » (mécanisme de preuve réservé à la bibliothèque)"
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


def _helpers_qui_constatent() -> frozenset[str]:
    """Délégué à `steps_library` (Q1 : source unique, partagée avec le catalogue). Bibliothèque
    illisible → au moins `constater*`, comme avant."""
    return steps_library.helpers_qui_constatent() or frozenset(_CONSTATER)


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
        # Lot VH-02 (V10) : `except (AssertionError, X):` contournait la garde, qui ne lisait qu'un nom seul.
        cibles = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
        noms = {c.id if isinstance(c, ast.Name) else getattr(c, "attr", "") for c in cibles}
        # `TypeError`/`ConstatInvalideError` : avaler le refus d'un constat qui ne prouve rien (revue VH-02).
        large = bool(noms & {"Exception", "BaseException", "AssertionError", "TypeError", "ConstatInvalideError"})
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


# ── Lot VH-02 (V1, V9) : un constat doit LIRE l'application ; une action ne se fait pas par RPC ; Python limité ──────────────
#
# Audit du 2026-10-08 : `constater(statut == attendu)` où les deux côtés viennent du Gherkin, `constater(True)`,
# `constater(page.url)` ou `constater(a == a)` passaient toutes les gardes et donnaient `conforme`. Et un `Quand je valide la
# commande` codé `context.odoo.env[m].write({"state": "done"})` suivi d'un `Alors l'état technique … est "done"` sortait
# `conforme` sans que l'interface ni la logique métier aient été exercées. Gardes de FORME (un filet, pas une preuve) : le
# runtime garde le dernier mot (`constater` refuse un objet qui ne prouve rien, un constat échoué avalé → `indetermine`).

# Ce que Behave pose sur `context` à partir du TEXTE du test (tableau, docstring, scénario…) : ce n'est pas l'application.
_CONTEXTE_DU_TEST = frozenset({"table", "text", "scenario", "feature", "config", "tags", "active_outline", "step"})
# Modules qu'un fichier de steps généré peut importer. Tout le reste est refusé : un import est le moyen le plus court de
# sortir du cadre (nouvelle connexion, réseau, système de fichiers, harnais).
_IMPORTS_AUTORISES = frozenset({
    "behave", "_base_helpers", "features", "playwright", "re", "json", "datetime", "decimal", "time", "math",
    "unicodedata", "string", "collections", "itertools", "functools", "typing", "uuid", "random",
})
_APPELS_INTERDITS = frozenset({"exec", "eval", "compile", "__import__", "open", "globals", "vars", "locals", "breakpoint"})
_ATTRIBUTS_INTERDITS = frozenset({"__dict__", "__globals__", "__builtins__", "__code__", "_runner", "__class__"})
_ECRITURES_RPC = frozenset({"create", "write", "unlink", "copy", "action_confirm", "action_post", "button_validate"})


def _lit_le_contexte_applicatif(noeud: ast.AST) -> bool:
    return (isinstance(noeud, ast.Attribute) and isinstance(noeud.value, ast.Name) and noeud.value.id == "context"
            and noeud.attr not in _CONTEXTE_DU_TEST)


def _cibles(cible: ast.AST) -> list[str]:
    if isinstance(cible, ast.Name):
        return [cible.id]
    if isinstance(cible, (ast.Tuple, ast.List)):
        return [n for c in cible.elts for n in _cibles(c)]
    if isinstance(cible, ast.Starred):
        return _cibles(cible.value)
    return []


def _noms_lus_de_l_application(func: ast.AST) -> set[str]:
    """Les variables locales dont la valeur vient de l'application (lecture de `context.page`, `context.odoo`, de l'oracle…),
    directement ou par d'autres variables — point fixe. Un helper NON décoré reçoit ses paramètres d'un step : ils comptent
    comme lus de l'application (provenance inconnue ; le runtime garde le dernier mot). Les paramètres d'un step décoré
    viennent du Gherkin : ils n'en sont pas."""
    lus: set[str] = set()
    if not _decorateurs(func):
        lus |= {a.arg for a in func.args.args + func.args.kwonlyargs if a.arg != "context"}

    def depend(expr: ast.AST | None) -> bool:
        return expr is not None and any(
            _lit_le_contexte_applicatif(n) or (isinstance(n, ast.Name) and n.id in lus) for n in ast.walk(expr))

    change = True
    while change:
        change = False
        for n in ast.walk(func):
            paires: list[tuple[list[str], ast.AST | None]] = []
            if isinstance(n, ast.Assign):
                paires = [(_cibles(t), n.value) for t in n.targets]
            elif isinstance(n, (ast.AugAssign, ast.AnnAssign)):
                paires = [(_cibles(n.target), n.value)]
            elif isinstance(n, (ast.For, ast.AsyncFor, ast.comprehension)):
                paires = [(_cibles(n.target), n.iter)]
            elif isinstance(n, ast.NamedExpr):
                paires = [(_cibles(n.target), n.value)]
            elif isinstance(n, ast.withitem) and n.optional_vars is not None:
                paires = [(_cibles(n.optional_vars), n.context_expr)]
            for noms, valeur in paires:
                if depend(valeur) and not set(noms) <= lus:
                    lus |= set(noms)
                    change = True
    return lus


def _constat_sans_lecture(tree: ast.AST) -> str:
    """Un `constater*` dont la condition ne lit rien de l'application, ou qui est une tautologie, ou un `constater` redéfini."""
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in _CONSTATER:
            return f"redéfinition de `{n.name}` : seule la bibliothèque définit les constats"
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in _CONSTATER for t in n.targets):
            return "réaffectation de `constater` : seule la bibliothèque définit les constats"
        if isinstance(n, ast.alias) and n.name in _CONSTATER and n.asname and n.asname != n.name:
            return f"`{n.name}` importé sous un autre nom (`{n.asname}`) : importe-le sous son nom"
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        lus = _noms_lus_de_l_application(func)
        for appel in ast.walk(func):
            if not (isinstance(appel, ast.Call) and _nom_appele(appel) in _CONSTATER and appel.args):
                continue
            condition = appel.args[0]
            if isinstance(condition, ast.Constant):
                return (f"`{_nom_appele(appel)}({ast.unparse(condition)}, …)` dans `{func.name}` : une condition constante "
                        "ne vérifie rien")
            if (isinstance(condition, ast.Compare) and len(condition.comparators) == 1
                    and ast.dump(condition.left) == ast.dump(condition.comparators[0])):
                return f"`{ast.unparse(condition)}` dans `{func.name}` : une comparaison d'une valeur à elle-même est toujours vraie"
            if not any(_lit_le_contexte_applicatif(x) or (isinstance(x, ast.Name) and x.id in lus)
                       for x in ast.walk(condition)):
                return (f"`{_nom_appele(appel)}({ast.unparse(condition)[:60]}, …)` dans `{func.name}` ne lit rien de "
                        "l'application : la condition ne dépend que de valeurs écrites dans le test. Lis la valeur à "
                        "l'écran (`context.page`), par RPC (`context.odoo`) ou par l'oracle, puis compare-la")
    return ""


def _forbidden_ecriture_rpc(tree: ast.AST) -> str:
    """Une écriture RPC (`create`/`write`/`unlink`…) dans un `@when`/`@then` : l'action testée ne se fait pas par RPC."""
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not (_decorateurs(func) & {"when", "then"}):
            continue
        for appel in ast.walk(func):
            if (isinstance(appel, ast.Call) and isinstance(appel.func, ast.Attribute)
                    and appel.func.attr in _ECRITURES_RPC and "odoo" in ast.unparse(appel.func.value)):
                return (f"`{ast.unparse(appel.func)[:70]}(…)` dans le step `{func.name}` : une action ou une vérification ne "
                        "s'écrit pas par RPC (elle contournerait l'interface et la logique testées). Prépare les données "
                        "dans un `@given`, agis par l'interface (`context.page`)")
    return ""


def _forbidden_python(tree: ast.AST) -> str:
    """Imports hors liste blanche, appels dynamiques (`exec`, `eval`, `open`…), introspection du harnais."""
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for alias in n.names:
                if alias.name.split(".")[0] not in _IMPORTS_AUTORISES:
                    return f"`import {alias.name}` : module non autorisé dans un fichier de steps"
        if isinstance(n, ast.ImportFrom) and (n.module or "").split(".")[0] not in _IMPORTS_AUTORISES:
            return f"`from {n.module} import …` : module non autorisé dans un fichier de steps"
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _APPELS_INTERDITS:
            return f"`{n.func.id}(…)` : appel interdit dans un fichier de steps"
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in {"getattr", "setattr", "delattr"}
                and (len(n.args) < 2 or not isinstance(n.args[1], ast.Constant))):
            return f"`{n.func.id}` avec un nom d'attribut calculé : écris l'attribut en clair"
        if isinstance(n, ast.Attribute) and n.attr in _ATTRIBUTS_INTERDITS:
            return f"`.{n.attr}` : introspection interdite dans un fichier de steps"
    return ""


def _message_litteraux(outil: str, ecarts) -> str:
    lignes = [f"[{outil}] LITTERAL_NON_OBSERVE : ce test cite ce qui n'a pas été observé sur l'application."]
    for e in ecarts[:8]:
        lignes.append(f"- {e.ou} : « {e.cite} » — {e.raison}" + (f" ; observé : « {e.observe} »" if e.observe else ""))
    lignes.append("Utilise le nom observé À L'IDENTIQUE (accents et casse compris), ou inspecte la page "
                  "(`inspect_page_snapshot` / `inspect_page_form`) pour le relever, puis réécris.")
    return "\n".join(lignes)


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
    # F26(b), migration 58 : question DIFFÉRENTE de `verifier_references` ci-dessus — pas « cette
    # entité existe-t-elle » (lot 12, D11) mais « CE scénario a-t-il lui-même créé l'entité que le
    # métier a désignée avant de la référencer ». Les deux contrôles coexistent, aucun ne remplace
    # l'autre. Gated : appelé seulement quand le métier a déclaré la dépendance (`ToolContext`,
    # jamais une heuristique générale sur la nature de la référence — cf. le faux positif
    # SauceDemo mesuré en diagnostic, qui a écarté une portée non gated).
    if ctx.depend_dun_autre_cas_du_groupe and ctx.etat_a_creer_par_ce_cas:
        refus_entite = enregistrement_lint.verifier_entite_a_creer(content)
        if refus_entite:
            return _outcome(refus_entite, ok=False)
    # Lot VH-05 (D24) : tout champ, bouton ou page cité existe À L'IDENTIQUE dans ce que l'exploration a observé. BLOQUANT.
    indications = ""
    if ctx.annuaire is not None:
        ecarts = litteraux_observes.controler_feature(content, ctx.annuaire)
        refus = [e for e in ecarts if e.bloquant]
        if refus:
            return _outcome(_message_litteraux("write_feature_file", refus), ok=False)
        indications = "".join(f" Attention ({e.ou}) : « {e.cite} » — {e.raison}." for e in ecarts)
    path = ctx.generated_dir / f"{ctx.module_name}.feature"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return _outcome(
        f"[write_feature_file] OK — {path.name}, {len(scenarios)} scénario(s).{indications}",
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

    # 3ter. Aucun `source=` forgé sur `constater(...)` (lot 07e, D7) : régime BLOQUANT, comme le
    # transport et le comptage — seuls les helpers internes de la bibliothèque le renseignent.
    source_forgee = _forbidden_source_kwarg(tree)
    if source_forgee:
        return _outcome(
            f"[write_steps_file] SOURCE_FORGEE : {source_forgee}. Un step ne revendique pas lui-même "
            "un recoupement contre l'oracle backend — utilise les steps du catalogue "
            "(« l'oracle \"<nom>\" renvoie <n> résultat(s) », « le champ \"<chemin>\" de l'oracle "
            "\"<nom>\" vaut \"<valeur>\" ») ; `constater(...)` s'appelle sans `source=`.",
            ok=False,
        )

    # 3quater. Aucune référence au mécanisme de preuve réservé au socle (Q1) : BLOQUANT, comme `source=`.
    reserve = _forbidden_reserve_au_socle(tree)
    if reserve:
        return _outcome(
            f"[write_steps_file] MECANISME_RESERVE : {reserve}. Un step ne déclare pas lui-même qu'il est "
            "« non assertif » et ne touche pas au compteur de constats : écris `constater(condition, "
            "\"message\")` dans un `@then`, ou utilise un step du catalogue.",
            ok=False,
        )

    # 3quinquies. Lot VH-02 (V1, V9) : Python limité, aucune action par RPC, un constat lit l'application. BLOQUANT.
    for code, faute, conseil in (
            ("PYTHON_INTERDIT", _forbidden_python(tree), "Utilise les steps du catalogue et `context.page`."),
            ("ACTION_PAR_RPC", _forbidden_ecriture_rpc(tree), ""),
            ("CONSTAT_SANS_LECTURE", _constat_sans_lecture(tree), "")):
        if faute:
            return _outcome(f"[write_steps_file] {code} : {faute}. {conseil}".rstrip() + " Puis rappelle write_steps_file.",
                            ok=False)

    # 3sexies. Lot VH-05 (D24) : réseau direct, `context.X` inventé ou secret (tous connecteurs) ; sélecteurs par texte libre et
    # libellés non observés (connecteur web avec annuaire). BLOQUANT.
    if ctx.attributs_contexte or ctx.annuaire is not None:
        from testpilot.generation.litteraux_observes import Annuaire
        ecarts = litteraux_observes.controler_steps(content, ctx.annuaire or Annuaire(),
                                                    set(ctx.attributs_contexte) or set())
        regles = {"reseau", "contexte"} | ({"selecteur", "libelle"} if ctx.annuaire is not None else set())
        if not ctx.attributs_contexte:
            regles.discard("contexte")
        refus = [e for e in ecarts if e.bloquant and e.regle in regles]
        if refus:
            return _outcome(_message_litteraux("write_steps_file", refus), ok=False)

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
