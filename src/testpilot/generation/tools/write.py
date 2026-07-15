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


def write_feature_file(ctx: "ToolContext", content: str) -> "ToolOutcome":
    if not content.strip():
        return _outcome("[write_feature_file] contenu vide", ok=False)
    path = ctx.generated_dir / f"{ctx.module_name}.feature"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    scenarios = content.count("Scénario:") + content.count("Scenario:")
    return _outcome(
        f"[write_feature_file] OK — {path.name}, {scenarios} scénario(s).",
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
            "propres appels HTTP — utilise `context.odoo` (lecture/écriture RPC, ex. "
            "`context.odoo.env['helpdesk.ticket'].search_count([])`) ou `context.page` "
            "(Playwright) pour agir dans le navigateur. Réutilise d'abord les steps partagés "
            "listés dans le prompt, puis rappelle write_steps_file.",
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
