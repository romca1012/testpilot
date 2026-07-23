"""Pilier 2 — génération des fichiers Behave depuis un TestPlan (boucle ReAct).

⚠️ **Imports PARESSEUX (PEP 562).** Importer `GenerationAgent` au chargement du package tirait
tout le pilier — anthropic, la boucle ReAct, ses dépendances — dès qu'on touchait
`testpilot.generation`. Or le **sous-processus Behave** (résolveur déterministe, §2bis) n'a besoin
que de modules PURS de ce package (`valeur_conforme`, `domain_model`) : lui imposer anthropic
serait un couplage inutile et lourd. Le `__getattr__` module-level ne charge `agent`/`state` que
si on y accède vraiment — `from testpilot.generation import GenerationAgent` continue de marcher.
"""

from __future__ import annotations

__all__ = ["GenerationAgent", "GenerationResult"]


def __getattr__(name: str):
    if name == "GenerationAgent":
        from testpilot.generation.agent import GenerationAgent
        return GenerationAgent
    if name == "GenerationResult":
        from testpilot.generation.state import GenerationResult
        return GenerationResult
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
