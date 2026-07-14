"""Collaborateurs injectés du pilier generation (typage structurel, zéro couplage).

Le pilier ne dépend d'aucune implémentation concrète : il reçoit un ``Connector`` (pour
l'exploration) et un ``DryRunner`` (validation de parsing). Les implémentations réelles
(``connectors/odoo.py``, ``execution/behave_runner.py``) sont bâties à leurs piliers et
satisfont ces contrats par duck-typing.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from testpilot.connectors.base import Connector

__all__ = ["Connector", "DryRunResult", "DryRunner"]


@runtime_checkable
class DryRunResult(Protocol):
    """Résultat d'un ``behave --dry-run`` (validation de parsing, sans exécution réelle)."""
    success: bool
    undefined_steps: list[str]
    ambiguous_steps: list[str]


@runtime_checkable
class DryRunner(Protocol):
    def dry_run(self, module_name: str) -> DryRunResult:
        """Valide le parsing/résolution des steps d'un module. N'exécute rien."""
        ...
