"""`connectors.factory.build_connector` — bug SauceDemo (2026-09-11).

⚠️ Le vrai bug qui a atteint `/dev` : l'audit multi-connecteurs (2026-09-08) avait branché
l'EXPLORATION sur `connector_type`, mais pas la génération technique ni la réparation —
`generation_service.py` et `run_service._connector_for` construisaient un `OdooConnector` EN DUR.
Résultat mesuré en conditions réelles : un projet `web` (SauceDemo) s'explorait très bien, mais la
génération technique tentait `odoorpc.ODOO(...)` contre un site sans aucun JSON-RPC Odoo — un
`urllib.error.HTTPError: HTTP Error 405: Method Not Allowed` avant même d'écrire un seul test.

Ces tests portent sur la fabrique elle-même (aucun réseau, aucun Playwright) : ils garantissent
que le CHOIX de classe suit `connector_type`, indépendamment de ce que chaque connecteur fait
ensuite avec sa connexion.
"""

from __future__ import annotations

from testpilot.connectors.factory import build_connector
from testpilot.connectors.generic_web import GenericWebConnector
from testpilot.connectors.odoo import OdooConnector


def test_connector_type_web_rend_le_connecteur_generique():
    """⚠️ Le cœur du bug : un projet `web` (SauceDemo) ne doit JAMAIS recevoir un OdooConnector —
    il tenterait du JSON-RPC contre un site qui n'en a pas, et plante en 405/404 avant tout test."""
    projet = {"connector_type": "web", "base_url": "https://www.saucedemo.com"}
    connecteur = build_connector(projet)
    assert isinstance(connecteur, GenericWebConnector)
    assert not isinstance(connecteur, OdooConnector)


def test_connector_type_odoo_rend_le_connecteur_odoo():
    """GARDE NÉGATIVE : le cas historique (Odoo, l'unique connecteur avant le multi-connecteurs)
    ne doit subir aucune régression."""
    projet = {"connector_type": "odoo", "base_url": "http://recette:8069",
             "database": "db", "username": "u", "password": "p"}
    connecteur = build_connector(projet)
    assert isinstance(connecteur, OdooConnector)


def test_connector_type_absent_retombe_sur_odoo():
    """GARDE NÉGATIVE : un projet créé AVANT le multi-connecteurs n'a pas cette colonne — le
    comportement historique (Odoo par défaut) doit rester intact, pas une régression silencieuse."""
    projet = {"base_url": "http://recette:8069", "database": "db"}
    assert isinstance(build_connector(projet), OdooConnector)


def test_projet_none_retombe_sur_odoo():
    """Même filet que les connecteurs eux-mêmes (`from_project(None)`) : jamais une exception
    juste parce qu'aucun projet n'a été résolu."""
    assert isinstance(build_connector(None), OdooConnector)


def test_connector_type_est_insensible_a_la_casse():
    projet = {"connector_type": "WEB", "base_url": "https://www.saucedemo.com"}
    assert isinstance(build_connector(projet), GenericWebConnector)


def test_les_overrides_atteignent_bien_le_connecteur_choisi():
    """`build_connector` doit transmettre `**overrides` comme le font déjà les `from_project` des
    deux connecteurs — sans ça, un appelant qui en dépend perdrait silencieusement ce réglage."""
    projet = {"connector_type": "web", "base_url": "https://www.saucedemo.com"}
    connecteur = build_connector(projet, headless=False)
    assert connecteur._headless is False
