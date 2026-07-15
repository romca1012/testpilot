"""Lint statique des assertions générées — repère les assertions INFALSIFIABLES (décision 0008).

Module **PUR** (AST uniquement, aucune I/O). Il ne **bloque jamais** la génération : sa sortie
alimente un **avertissement non-bloquant** au gate de relecture (le gate reste souverain, §4.3).
Raison d'être : une tautologie **passe à l'exécution** (un `assert` toujours vrai réussit) — ni
le dry-run ni le run réel ne peuvent la voir. Seuls le statique (ici) ou l'œil humain le peuvent.

Trois motifs détectés :

1. **`always_true_constant`** — `assert <constante vraie>` ou `assert ... or <constante vraie>`
   (sous-ensemble trivial : l'assertion ne peut pas échouer).
2. **`tautology_negation_in_else`** — le motif exact de l'écart 2 : dans le `else` d'un
   `if <test>`, un `assert` dont un opérande est la **négation de ce même test** (`X not in Y`
   sous un `if X in Y`) — donc toujours vrai dans cette branche.
3. **`then_without_assertion`** — un step `@then` (assertion) dont le corps n'affirme rien : ni
   `assert`, ni `raise`, ni appel d'assertion. **Filtré par décorateur** : un `@when`/`@given`
   d'action n'affirme légitimement rien, il n'est jamais signalé.

Anti-faux-positif : la négation (motif 2) est reconnue par **égalité structurelle stricte**
(même opérande gauche, même comparateur, opérateur inverse) — un `assert foo or (c not in d)`
sans rapport avec le `if a in b` englobant n'est **pas** signalé.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass

# Opérateurs de comparaison et leur inverse booléen exact.
_INVERSE_CMP = {
    ast.In: ast.NotIn, ast.NotIn: ast.In,
    ast.Eq: ast.NotEq, ast.NotEq: ast.Eq,
    ast.Lt: ast.GtE, ast.GtE: ast.Lt,
    ast.Gt: ast.LtE, ast.LtE: ast.Gt,
    ast.Is: ast.IsNot, ast.IsNot: ast.Is,
}

# Un corps de `@then` « affirme » s'il appelle une fonction dont le nom évoque une vérification
# (helper d'assertion partagé) — évite de crier sur un step qui délègue son assertion.
_ASSERTION_CALL_RE = re.compile(r"(?i)(assert|verify|check|expect|ensure)")

ALWAYS_TRUE_CONSTANT = "always_true_constant"
TAUTOLOGY_NEGATION_IN_ELSE = "tautology_negation_in_else"
THEN_WITHOUT_ASSERTION = "then_without_assertion"


@dataclass(frozen=True)
class LintWarning:
    step: str      # libellé Gherkin du step (ou nom de fonction à défaut)
    line: int      # ligne 1-indexée dans le fichier de steps
    kind: str      # une des constantes ci-dessus
    message: str   # explication lisible pour le relecteur

    def as_dict(self) -> dict:
        return {"step": self.step, "line": self.line, "kind": self.kind, "message": self.message}


def lint_steps(content: str) -> list[dict]:
    """Analyse un fichier `_steps.py` et renvoie la liste des avertissements (dicts triés).

    Tolérant : un contenu vide ou non parsable renvoie une liste vide (le lint ne casse jamais
    la construction du gate).
    """
    if not content or not content.strip():
        return []
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []

    warnings: list[LintWarning] = []
    for func in _iter_functions(tree):
        label = _step_label(func)
        _lint_asserts(func.body, [], label, warnings)
        if _is_then(func) and not _has_assertion(func):
            warnings.append(LintWarning(
                step=label, line=func.lineno, kind=THEN_WITHOUT_ASSERTION,
                message="Ce step `@then` n'affirme rien (ni assert, ni raise) : il ne peut pas "
                        "échouer — c'est un test vide.",
            ))

    warnings.sort(key=lambda w: (w.line, w.kind))
    return [w.as_dict() for w in warnings]


# ── Parcours ──────────────────────────────────────────────────────────────────
def _iter_functions(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


def _lint_asserts(body, negated_tests, label, out) -> None:
    """Parcourt un bloc en gardant la pile des tests connus FAUX (branches `else` traversées)."""
    for stmt in body:
        if isinstance(stmt, ast.Assert):
            _check_assert(stmt, negated_tests, label, out)
        elif isinstance(stmt, ast.If):
            _lint_asserts(stmt.body, negated_tests, label, out)
            _lint_asserts(stmt.orelse, negated_tests + [stmt.test], label, out)
        elif isinstance(stmt, (ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith)):
            _lint_asserts(stmt.body, negated_tests, label, out)
            orelse = getattr(stmt, "orelse", [])
            if orelse:
                _lint_asserts(orelse, negated_tests, label, out)
        elif isinstance(stmt, ast.Try):
            for sub in (stmt.body, stmt.orelse, stmt.finalbody):
                _lint_asserts(sub, negated_tests, label, out)
            for handler in stmt.handlers:
                _lint_asserts(handler.body, negated_tests, label, out)
        # les FunctionDef imbriquées sont traitées par _iter_functions (walk global)


def _check_assert(node: ast.Assert, negated_tests, label, out) -> None:
    test = node.test

    # 1. Constante vraie, directement ou comme opérande d'un `or`.
    if _is_truthy_constant(test):
        out.append(_w(label, node.lineno, ALWAYS_TRUE_CONSTANT,
                      "Assertion sur une constante vraie : elle ne peut jamais échouer."))
        return
    or_values = test.values if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.Or) else []
    if any(_is_truthy_constant(v) for v in or_values):
        out.append(_w(label, node.lineno, ALWAYS_TRUE_CONSTANT,
                      "Un opérande du `or` est une constante vraie : l'assertion est toujours vraie."))
        return

    # 2. Motif contextuel écart 2 : un opérande (ou l'assert entier) = négation d'un `if` englobant.
    candidates = or_values or [test]
    for cand in candidates:
        if any(_is_negation_of(cand, t) for t in negated_tests):
            out.append(_w(label, node.lineno, TAUTOLOGY_NEGATION_IN_ELSE,
                          "Dans le `else` d'un `if`, cet opérande est la négation de la condition "
                          "du `if` — donc toujours vrai ici. L'assertion ne peut pas échouer."))
            return


# ── Prédicats AST ─────────────────────────────────────────────────────────────
def _is_truthy_constant(node) -> bool:
    return isinstance(node, ast.Constant) and bool(node.value) is True


def _is_negation_of(candidate, test) -> bool:
    """`candidate` est-il la négation booléenne EXACTE de `test` ? (comparaison structurelle)"""
    # not (test)
    if isinstance(candidate, ast.UnaryOp) and isinstance(candidate.op, ast.Not):
        return _same(candidate.operand, test)
    # Comparaison simple à opérateur inverse : `X in Y` ↔ `X not in Y`, `==` ↔ `!=`, etc.
    if (isinstance(candidate, ast.Compare) and isinstance(test, ast.Compare)
            and len(candidate.ops) == 1 and len(test.ops) == 1):
        inv = _INVERSE_CMP.get(type(test.ops[0]))
        if (inv is not None and isinstance(candidate.ops[0], inv)
                and _same(candidate.left, test.left)
                and _same(candidate.comparators[0], test.comparators[0])):
            return True
    return False


def _same(a, b) -> bool:
    """Égalité structurelle de deux nœuds (indépendante des positions de ligne)."""
    return ast.dump(a) == ast.dump(b)


# ── Décorateurs de steps ───────────────────────────────────────────────────────
def _step_label(func) -> str:
    for deco in func.decorator_list:
        if isinstance(deco, ast.Call) and deco.args and isinstance(deco.args[0], ast.Constant):
            return str(deco.args[0].value)
    return func.name


def _is_then(func) -> bool:
    return any(_deco_name(d) == "then" for d in func.decorator_list)


def _deco_name(deco) -> str:
    target = deco.func if isinstance(deco, ast.Call) else deco
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    return ""


def _has_assertion(func) -> bool:
    for node in ast.walk(func):
        if isinstance(node, (ast.Assert, ast.Raise)):
            return True
        if isinstance(node, ast.Call):
            name = _deco_name(node)  # réutilise l'extraction Name/Attribute
            if name and _ASSERTION_CALL_RE.search(name):
                return True
    return False


def _w(label, line, kind, message) -> LintWarning:
    return LintWarning(step=label, line=line, kind=kind, message=message)
