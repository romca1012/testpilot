"""Interrupteurs d'environnement du chantier « qualité des agents » (lot Q3-a).

⚠️ **Pourquoi des interrupteurs.** Tout ce qui change ce que l'API Anthropic REÇOIT (définitions
d'outils, prompt système) change le comportement de l'agent, donc doit pouvoir être MESURÉ avant
d'être activé (docs/SOURCES-DE-REFERENCE-AGENTS.md §4.3, banc du lot Q2). Chaque interrupteur est :

- **désactivé par défaut** : sans variable, ce que l'API reçoit est strictement identique, octet
  pour octet, à ce qui était envoyé avant Q3-a (garde : `tests/test_tools_strict_q3a.py`) ;
- **lu à chaque appel** (jamais figé à l'import) : un banc peut comparer deux configurations dans
  le même processus, un test peut le basculer sans recharger de module.

Module PUR : aucune I/O hors lecture de `os.environ`.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

ENV_TOOLS_STRICT = "TESTPILOT_TOOLS_STRICT"
ENV_PROMPT_HYPOTHESES = "TESTPILOT_PROMPT_HYPOTHESES"
ENV_TOOLS_DESCRIPTIONS_V2 = "TESTPILOT_TOOLS_DESCRIPTIONS_V2"
ENV_REGLES_CONNECTEUR = "TESTPILOT_REGLES_CONNECTEUR"
ENV_STEP_NOMBRE = "TESTPILOT_STEP_NOMBRE"
ENV_VARIABLES_DE_TEST = "TESTPILOT_VARIABLES_DE_TEST"
ENV_CAS_DIT_SES_DONNEES = "TESTPILOT_CAS_DIT_SES_DONNEES"

_VRAI = frozenset({"1", "true", "yes", "oui", "on"})


def _actif(nom: str, env: Mapping[str, str] | None) -> bool:
    source = os.environ if env is None else env
    return str(source.get(nom, "")).strip().lower() in _VRAI


def tools_strict_actif(env: Mapping[str, str] | None = None) -> bool:
    """Mode strict de l'API (`strict: true`) sur les outils critiques + `input_examples`."""
    return _actif(ENV_TOOLS_STRICT, env)


def prompt_hypotheses_actif(env: Mapping[str, str] | None = None) -> bool:
    """Phrase du PILIER 4 qui demande `hypotheses_non_verifiees` — et exposition du champ à l'API."""
    return _actif(ENV_PROMPT_HYPOTHESES, env)


def descriptions_v2_actif(env: Mapping[str, str] | None = None) -> bool:
    """Descriptions d'outils réécrites au standard Anthropic (quoi, quand, quand non, limites)."""
    return _actif(ENV_TOOLS_DESCRIPTIONS_V2, env)


def regles_connecteur_actif(env: Mapping[str, str] | None = None) -> bool:
    """Règles par connecteur (`Connector.rules()`) et section « comptes » dès le compte principal (lot Q3, D20)."""
    return _actif(ENV_REGLES_CONNECTEUR, env)


def variables_de_test_actif(env: Mapping[str, str] | None = None) -> bool:
    """Lot PT-02d : l'agent reçoit les NOMS des variables du projet et peut les écrire (`generation/variables_de_test.py`)."""
    return _actif(ENV_VARIABLES_DE_TEST, env)


def cas_dit_ses_donnees_actif(env: Mapping[str, str] | None = None) -> bool:
    """Lot PT-02f (étape E2, A39) : l'IA écrit `{{nom}}` dans le texte des cas qu'elle propose ; le test technique reprend
    EXACTEMENT les variables que le cas cite (`generation/variables_de_test.du_cas`). N'a d'effet qu'avec PT-02d allumé :
    sans lui l'agent technique ne voit aucune variable, et un cas citant `{{client}}` aurait un test qui ne l'emploie pas
    (revue du 2026-10-15, bloquant)."""
    return _actif(ENV_CAS_DIT_SES_DONNEES, env) and variables_de_test_actif(env)


def allume(nom: str, env: Mapping[str, str] | None = None) -> bool:
    """L'interrupteur `nom` est-il allumé ? Pour un step marqué `@derriere_interrupteur("<nom>")` dans la bibliothèque."""
    return _actif(nom, env)
