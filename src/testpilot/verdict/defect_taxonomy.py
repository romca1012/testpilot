"""Taxonomie causale des échecs : projette un SYMPTÔME technique sur une CAUSE RACINE.

Le parser behave classe par symptôme (``ui_timeout``, ``assertion``, ``permission``,
``odoo_data``, ``odoorpc``, ``unknown``). Cette taxonomie re-projette sur la cause racine
du pipeline spec→test — le seul niveau exploitable pour décider « test à réparer » vs
« vrai bug » (voir ``defect_origin``). Module PUR (sans réseau ni LLM).

────────────────────────────────────────────────────────────────────────────────────
DÉCISION 0015 — ON CLASSE SUR LE SIGNAL, JAMAIS SUR LE TEXTE DE L'AGENT
────────────────────────────────────────────────────────────────────────────────────
Cette taxonomie lisait ``step_text`` — le libellé Gherkin **écrit par l'agent** — et le
message qui suit ``AssertionError:`` (idem), par mots-clés **prioritaires**. Elle jugeait donc
l'agent sur son propre texte. Mesuré : le **même** ``TypeError`` recevait **quatre** classements
selon le seul nom du step, et un **vrai bug** sur un step nommé ``…"team_id"…`` devenait
``test_a_reparer`` — la boucle de réparation (`0014`) aurait alors réparé un test **correct**
contre une application **cassée** : le faux négatif que §4.4 déclare inacceptable.

L'ordre est désormais :

1. **SIGNAL** — le TYPE d'exception, produit par Python/Playwright/odoorpc, **jamais** par
   l'agent. Décisif.
2. **SYMPTÔME** — le ``failure_type`` du parser (regex sur l'ERREUR, pas sur le step).
3. **INDICE** — mots-clés, **en dernier recours**, et **jamais** sur ``step_text``.

Les mots-clés de DOMAINE (``team_id``, ``many2one``, ``accesserror``, ``group_``) ont été
retirés : figés dans un module qui se déclare « connector-agnostic », ils étaient du code mort
une fois le signal prioritaire — et leur place est dans les règles du connecteur, pas ici.
"""

from __future__ import annotations

import re
from collections import Counter

_URL_RE = re.compile(r"https?://\S+")
_NUM_RE = re.compile(r"\d+")
_WS_RE = re.compile(r"\s+")


def normalize_error(text: str) -> str:
    """Neutralise URLs / nombres / espaces pour une correspondance stable."""
    t = (text or "").lower()
    t = _URL_RE.sub("<url>", t)
    t = _NUM_RE.sub("<n>", t)
    return _WS_RE.sub(" ", t).strip()


# Causes racines — ordre = priorité (sévérité décroissante), tranche les égalités.
MISSING_SERVER_CONTEXT = "missing_server_context"
BROKEN_TEST_CODE = "broken_test_code"
WRONG_NAVIGATION = "wrong_navigation"
WRONG_FIELD_NAME = "wrong_field_name"
MISSING_ROLE = "missing_role"
ASSERTION_MISMATCH = "assertion_mismatch"
UNKNOWN = "unknown"

CATEGORIES = (
    MISSING_SERVER_CONTEXT, BROKEN_TEST_CODE, WRONG_NAVIGATION, WRONG_FIELD_NAME,
    MISSING_ROLE, ASSERTION_MISMATCH, UNKNOWN,
)

LABELS = {
    MISSING_SERVER_CONTEXT: "Contexte serveur manquant",
    BROKEN_TEST_CODE: "Erreur dans le code du test",
    WRONG_NAVIGATION: "Navigation erronée",
    WRONG_FIELD_NAME: "Champ/sélecteur introuvable",
    MISSING_ROLE: "Rôle/permission manquant",
    ASSERTION_MISMATCH: "Assertion métier en échec",
    UNKNOWN: "Indéterminé",
}

# ── 1. SIGNAL : le type d'exception (décision 0015) ───────────────────────────
# Produit par le RUNTIME (Python, Playwright, odoorpc) — jamais par l'agent. C'est la seule
# donnée de ce module que le composant jugé ne fabrique pas.
_EXCEPTION_LINE_RE = re.compile(r"^\s*([\w.]+(?:Error|Exception|Timeout))\b", re.MULTILINE)

# ⚠️ Behave n'écrit JAMAIS « AssertionError ». Vérifié dans la source (behave 1.3.3,
# ``model.py:1888``) :
#
#     schema = u"ERROR: {e_classname}: {e}"
#     if isinstance(exception, AssertionError):
#         schema = u"ASSERT FAILED: {e}"          # ← le nom de la classe DISPARAÎT
#     ...
#     if use_traceback:                            # use_traceback = config.verbose
#         schema += u"\n{traceback}"               # ← pas de traceback hors mode verbose
#
# Conséquence mesurée sur nos données réelles : les 5 assertions en base portent
# « ASSERT FAILED: … », aucune ne porte « AssertionError ». La clé `AssertionError` de
# `_EXCEPTION_TO_CAUSE` était donc du **code mort en run réel** — le premier jet de 0015 ne
# classait les assertions que par MOTS-CLÉS, c'est-à-dire par le texte de l'agent : la porte du
# faux négatif restait ouverte, précisément là où la décision prétendait l'avoir fermée.
#
# Ce préfixe est écrit par BEHAVE, pas par l'agent : c'est un signal au même titre qu'un type
# d'exception. Seul le message qui SUIT est de l'agent — et il n'est pas lu.
_BEHAVE_ASSERT_RE = re.compile(r"^\s*ASSERT FAILED:", re.MULTILINE)

_EXCEPTION_TO_CAUSE = {
    # Playwright : l'élément attendu n'est jamais apparu.
    "TimeoutError": WRONG_FIELD_NAME,
    "PlaywrightTimeoutError": WRONG_FIELD_NAME,
    # Erreurs de PROGRAMMATION dans le code du step. L'application n'y est pour rien : c'est
    # notre code qui est faux, donc réparable par construction. C'était le trou le plus absurde
    # de l'ancienne version — un `TypeError` nu tombait en `unknown` → `indetermine`, et le
    # circuit refusait de réparer le cas le plus évidemment réparable qui soit.
    "TypeError": BROKEN_TEST_CODE,
    "AttributeError": BROKEN_TEST_CODE,
    "KeyError": BROKEN_TEST_CODE,
    "IndexError": BROKEN_TEST_CODE,
    "NameError": BROKEN_TEST_CODE,
    "UnboundLocalError": BROKEN_TEST_CODE,
    "ImportError": BROKEN_TEST_CODE,
    "ModuleNotFoundError": BROKEN_TEST_CODE,
    "ZeroDivisionError": BROKEN_TEST_CODE,
    "IndentationError": BROKEN_TEST_CODE,
    "SyntaxError": BROKEN_TEST_CODE,
    # Le test affirme, l'application répond autrement → jugement HUMAIN (§4.4). Le message qui
    # suit est écrit par l'agent : on ne le lit pas pour décider.
    # NB : en run réel via Behave, c'est `_BEHAVE_ASSERT_RE` qui attrape ce cas — Behave masque
    # le nom de la classe. Cette clé sert au mode verbose (traceback joint) et aux appels directs.
    "AssertionError": ASSERTION_MISMATCH,
    # Droit manquant — donnée d'ENVIRONNEMENT.
    "AccessError": MISSING_ROLE,
    "AccessDenied": MISSING_ROLE,
    # Route inexistante / méthode refusée → problème de PARCOURS.
    "HTTPError": WRONG_NAVIGATION,
}

# ⚠️ `ValueError` est volontairement ABSENT : il est ambigu (bug de code, mais aussi levé
# légitimement par odoorpc sur un enregistrement introuvable). Le laisser tomber au symptôme
# vaut mieux que de le classer à tort — un mauvais classement décide maintenant de la
# réparabilité (`0014`).


# ── 2. SYMPTÔME : projection du failure_type du parser ────────────────────────
# Regex sur l'ERREUR (behave_result.classify_failure), pas sur le step.
_TYPE_FALLBACK = {
    "permission": MISSING_ROLE,
    "ui_timeout": WRONG_FIELD_NAME,
    "assertion": ASSERTION_MISMATCH,
    "odoo_data": MISSING_SERVER_CONTEXT,
    "odoorpc": WRONG_NAVIGATION,
    "http_error": WRONG_NAVIGATION,  # route inexistante / méthode refusée → parcours
}


# ── 3. INDICE : mots-clés, DERNIER RECOURS ────────────────────────────────────
# ⚠️ Lus UNIQUEMENT sur le message d'erreur, JAMAIS sur `step_text` (décision 0015). Ils ne
# servent que lorsque ni le signal ni le symptôme n'ont parlé — c'est-à-dire presque jamais.
# Les mots-clés de DOMAINE ont été retirés (`team_id`, `many2one` → Odoo helpdesk ; `group_`,
# `accesserror` → Odoo/Sapian) : ce module se déclare « connector-agnostic », et les y laisser
# aurait été du code mort dans un module qui ment sur sa portée.
_KEYWORDS: dict[str, tuple[str, ...]] = {
    MISSING_SERVER_CONTEXT: (
        "hidden_field_empty", "server_injected", "champ cache", "champ caché",
        "reste vide", "resté vide", "valeur injectee", "valeur injectée",
    ),
    WRONG_NAVIGATION: (
        "method not allowed", "route", "get direct", "post-only", "post only",
        "navigation", "page introuvable", "redirect", "mauvaise url", "parcours",
        "httperror", "client error", "server error", "not found for url",
    ),
    WRONG_FIELD_NAME: (
        "timeouterror", "timeout", "locator", "no element", "aucun element",
        "aucun élément", "not found", "selector", "selecteur", "sélecteur",
        "get_by_role", "has-text", "introuvable",
    ),
    MISSING_ROLE: (
        "access denied", "forbidden", "permission", "droit", "non autorise",
        "non autorisé", "unauthorized",
    ),
    ASSERTION_MISMATCH: (
        "assertionerror", "expected", "attendu", "assert", "ne vaut pas",
        "different de", "différent de", "mismatch",
    ),
}


def exception_type(text: str) -> str:
    """Nom de la classe d'exception réellement levée. `''` si aucune n'est identifiable.

    On garde la DERNIÈRE ligne d'exception : dans une chaîne d'exceptions, Python met en
    dernier celle qui a effectivement interrompu le step. Le nom est réduit à son dernier
    segment (`playwright._impl._errors.TimeoutError` → `TimeoutError`).
    """
    matches = _EXCEPTION_LINE_RE.findall(text or "")
    return matches[-1].split(".")[-1] if matches else ""


def runtime_error_text(failure) -> str:
    """Le texte produit par le RUNTIME pour cet échec : `raw` + `traceback_summary`.

    Un seul endroit définit « ce qui compte comme le texte d'erreur » — `classify_failure` et
    `repair_circuit.failure_signature` s'en servent tous deux. Le dupliquer les ferait diverger,
    et la divergence serait à diagnostiquer plus tard (docs/PRINCIPES.md, principe 4).

    ⚠️ N'inclut PAS `step_text` : c'est le libellé écrit par l'agent (décision 0015).
    """
    return f"{getattr(failure, 'raw', '') or ''}\n{getattr(failure, 'traceback_summary', '') or ''}"


def _message_text(failure) -> str:
    """Le texte de l'ERREUR — sans `step_text`.

    ⚠️ `step_text` est le libellé Gherkin **écrit par l'agent** : le lire revenait à juger
    l'agent sur ce qu'il a lui-même rédigé (décision 0015). Il n'entre plus ici.
    """
    tb = getattr(failure, "traceback_summary", "") or ""
    raw = getattr(failure, "raw", "") or ""
    return normalize_error(f"{tb} {raw}")


def classify_failure(failure) -> str:
    """Cause racine : SIGNAL (rendu de Behave, type d'exception) → SYMPTÔME → INDICE.

    Le signal est décisif parce qu'il est le seul que le composant jugé ne produit pas.
    """
    brut = runtime_error_text(failure)

    # Le rendu d'assertion de Behave est testé D'ABORD : c'est la forme la plus extérieure et la
    # plus sûre. Sans lui, une assertion dont l'agent écrit « permission refusée » dans son
    # message serait classée `missing_role` → `test_a_reparer` par mots-clés — la boucle 0014
    # réparerait alors un test CORRECT contre une application cassée (§4.4, faux négatif).
    if _BEHAVE_ASSERT_RE.search(brut):
        return ASSERTION_MISMATCH

    cause = _EXCEPTION_TO_CAUSE.get(exception_type(brut))
    if cause:
        return cause

    ftype = (getattr(failure, "failure_type", "") or "").lower()
    if ftype in _TYPE_FALLBACK:
        return _TYPE_FALLBACK[ftype]

    text = _message_text(failure)
    if text:
        for category in CATEGORIES:
            for kw in _KEYWORDS.get(category, ()):
                if kw in text:
                    return category
    return UNKNOWN


def classify_failures(failures) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for f in failures or []:
        counts[classify_failure(f)] += 1
    return {cat: counts.get(cat, 0) for cat in CATEGORIES if counts.get(cat, 0)}


def dominant_category(failures) -> str | None:
    """Cause majoritaire (départage par priorité de CATEGORIES). None si aucun échec."""
    counts = classify_failures(failures)
    if not counts:
        return None
    top = max(counts.values())
    for cat in CATEGORIES:
        if counts.get(cat, 0) == top:
            return cat
    return None
