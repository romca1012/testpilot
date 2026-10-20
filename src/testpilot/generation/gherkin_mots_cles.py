"""Les mots-clés de structure du Gherkin (scénario, plan, contexte, règle), tirés de Behave lui-même — jamais une liste écrite
à la main dans chaque contrôle.

Étape 2 du plan unique (A61, 2026-10-20) : `Exemple:` est un mot-clé de scénario du Gherkin français (mesuré :
`behave.i18n.languages['fr']['scenario'] == ['Exemple', 'Scénario']`) ; quatre contrôles ne connaissaient que `Scénario:`.
Sur un test écrit avec `Exemple:`, la page du scénario précédent restait la page courante (fausse alerte « champ sans
preuve »), et un `Contexte` ne se refermait jamais. Le deux-points est exigé : `Exemples:` (le tableau d'un plan) n'ouvre
pas un scénario.

Module pur : aucune I/O.
"""
from __future__ import annotations

import re

from behave.i18n import languages

_LANGUES = ("fr", "en")   # le dépôt écrit en français ; l'anglais reste accepté comme avant (`Scenario:`, `Background:`)


def _motif(*cles: str) -> re.Pattern[str]:
    mots = {m.strip() for langue in _LANGUES for cle in cles for m in languages[langue][cle] if m.strip() != "*"}
    alternatives = "|".join(re.escape(m) for m in sorted(mots, key=len, reverse=True))
    return re.compile(rf"^\s*(?:{alternatives})\s*:")


DEBUT_SCENARIO = _motif("scenario", "scenario_outline")
DEBUT_CONTEXTE = _motif("background")
DEBUT_REGLE = _motif("rule")
