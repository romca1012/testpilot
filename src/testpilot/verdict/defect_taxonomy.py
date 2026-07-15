"""Taxonomie causale des échecs : projette un SYMPTÔME technique sur une CAUSE RACINE.

Le parser behave classe par symptôme (``ui_timeout``, ``assertion``, ``permission``,
``odoo_data``, ``odoorpc``, ``unknown``). Cette taxonomie re-projette sur la cause racine
du pipeline spec→test — le seul niveau exploitable pour décider « test à réparer » vs
« vrai bug » (voir ``defect_origin``). Module PUR (sans réseau ni LLM).
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
WRONG_NAVIGATION = "wrong_navigation"
WRONG_FIELD_NAME = "wrong_field_name"
MISSING_ROLE = "missing_role"
ASSERTION_MISMATCH = "assertion_mismatch"
UNKNOWN = "unknown"

CATEGORIES = (
    MISSING_SERVER_CONTEXT, WRONG_NAVIGATION, WRONG_FIELD_NAME,
    MISSING_ROLE, ASSERTION_MISMATCH, UNKNOWN,
)

LABELS = {
    MISSING_SERVER_CONTEXT: "Contexte serveur manquant",
    WRONG_NAVIGATION: "Navigation erronée",
    WRONG_FIELD_NAME: "Champ/sélecteur introuvable",
    MISSING_ROLE: "Rôle/permission manquant",
    ASSERTION_MISMATCH: "Assertion métier en échec",
    UNKNOWN: "Indéterminé",
}

_KEYWORDS: dict[str, tuple[str, ...]] = {
    MISSING_SERVER_CONTEXT: (
        "hidden_field_empty", "server_injected", "champ cache", "champ caché",
        "team_id", "reste vide", "resté vide", "many2one", "valeur injectee", "valeur injectée",
    ),
    WRONG_NAVIGATION: (
        "method not allowed", "route", "get direct", "post-only", "post only",
        "navigation", "page introuvable", "redirect", "mauvaise url", "parcours",
        # Erreur HTTP sur une route (404/405/5xx). NB : ``normalize_error`` remplace les
        # nombres par <n> et les URLs par <url> — on matche donc le texte, jamais le code.
        # Ces motifs doivent primer sur le « not found » de WRONG_FIELD_NAME (un 404 est un
        # problème de parcours, pas de sélecteur) : WRONG_NAVIGATION précède déjà
        # WRONG_FIELD_NAME dans CATEGORIES.
        "httperror", "client error", "server error", "not found for url",
    ),
    WRONG_FIELD_NAME: (
        "timeouterror", "timeout", "locator", "no element", "aucun element",
        "aucun élément", "not found", "selector", "selecteur", "sélecteur",
        "get_by_role", "has-text", "introuvable",
    ),
    MISSING_ROLE: (
        "accesserror", "access denied", "forbidden", "permission", "droit",
        "group_", "non autorise", "non autorisé", "unauthorized",
    ),
    ASSERTION_MISMATCH: (
        "assertionerror", "expected", "attendu", "assert", "ne vaut pas",
        "different de", "différent de", "mismatch",
    ),
}

# Projection symptôme→cause quand aucun mot-clé plus fort ne ressort.
_TYPE_FALLBACK = {
    "permission": MISSING_ROLE,
    "ui_timeout": WRONG_FIELD_NAME,
    "assertion": ASSERTION_MISMATCH,
    "odoo_data": MISSING_SERVER_CONTEXT,
    "odoorpc": WRONG_NAVIGATION,
    "http_error": WRONG_NAVIGATION,  # route inexistante / méthode refusée → parcours
}


def _failure_text(failure) -> str:
    step = getattr(failure, "step_text", "") or ""
    tb = getattr(failure, "traceback_summary", "") or ""
    raw = getattr(failure, "raw", "") or ""
    return normalize_error(f"{step} {tb} {raw}")


def classify_failure(failure) -> str:
    """Cause racine d'un échec : mots-clés d'abord (priorité), puis repli sur le symptôme."""
    text = _failure_text(failure)
    if text:
        for category in CATEGORIES:
            for kw in _KEYWORDS.get(category, ()):
                if kw in text:
                    return category
    ftype = (getattr(failure, "failure_type", "") or "").lower()
    return _TYPE_FALLBACK.get(ftype, UNKNOWN)


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
