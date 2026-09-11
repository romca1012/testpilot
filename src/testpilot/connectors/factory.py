"""Fabrique de connecteur — LE point unique qui choisit l'implémentation selon le projet.

⚠️ **Bug corrigé (2026-09-11, SauceDemo sur /dev).** L'audit multi-connecteurs (2026-09-08)
avait branché l'EXPLORATION (`exploration_service._crawl`) sur `connector_type`, mais pas la
GÉNÉRATION technique ni la réparation : `generation_service.py` (``run_automation``,
``resume_generation``) et `run_service._connector_for` construisaient chacun un
``OdooConnector`` EN DUR, quel que soit le connecteur réel du projet. Un projet `web` (SauceDemo)
pouvait donc s'explorer, mais la génération technique tentait `odoorpc.ODOO(...)` contre un site
qui n'a évidemment aucun endpoint JSON-RPC Odoo — 405 « Method Not Allowed » avant même d'écrire
le premier test, l'exploration ayant pourtant réussi.

Cette fabrique centralise le choix : un seul endroit à faire évoluer le jour où un troisième
connecteur arrive, au lieu de trois branches `if connector_type == "odoo"` à tenir synchronisées.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from testpilot.connectors.base import Connector


def build_connector(project: dict | None, **overrides) -> Connector:
    """Le connecteur du PROJET (décision 0005), selon son `connector_type` réel.

    `odoo` (ou absent — un projet créé avant le multi-connecteurs n'a pas cette colonne) →
    ``OdooConnector`` : comportement HISTORIQUE inchangé. Tout autre type (`web`, …) →
    ``GenericWebConnector``, qui assume l'absence de modèle de données interrogeable (§ sa
    propre docstring) — même choix que `exploration_service._crawl`.
    """
    from testpilot.connectors.generic_web import GenericWebConnector
    from testpilot.connectors.odoo import OdooConnector

    connector_type = ((project or {}).get("connector_type") or "odoo").lower()
    if connector_type == "odoo":
        return OdooConnector.from_project(project, **overrides)
    return GenericWebConnector.from_project(project, **overrides)
