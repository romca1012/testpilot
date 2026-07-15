"""Traduction de la connexion d'un PROJET en variables d'environnement pour le runtime.

Le harnais Behave (``behave_runtime/environment.py``) lit sa connexion dans l'environnement
(``ODOO_URL``/``ODOO_DB``/…). Le projet portant désormais le connecteur et ses paramètres
(décision 0005), ce module fait le pont : projet → variables d'environnement du sous-processus.

Règles :
- le mapping dépend du ``connector_type`` (architecture multi-connecteurs, §8) ;
- une valeur vide n'est PAS propagée : le runtime retombe alors sur la config globale
  (compatibilité avec les projets sans connexion saisie) ;
- ``ODOO_ENV`` n'est jamais produit ici — le garde-fou anti-production reste intact.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# connector_type → {variable d'environnement: colonne du projet}
_MAPPINGS: dict[str, dict[str, str]] = {
    "odoo": {
        "ODOO_URL": "base_url",
        "ODOO_DB": "database",
        "ODOO_USER": "username",
        "ODOO_PASSWORD": "password",
    },
}


def project_env(project: dict | None) -> dict[str, str]:
    """Variables d'environnement de connexion déduites d'un projet. Vide si non applicable."""
    if not project:
        return {}
    connector = (project.get("connector_type") or "").lower()
    mapping = _MAPPINGS.get(connector)
    if mapping is None:
        logger.warning("[runtime] connecteur '%s' sans mapping d'environnement — "
                       "connexion globale utilisée", connector)
        return {}
    env = {}
    for var, column in mapping.items():
        value = project.get(column)
        if value:  # vide → on laisse la config globale s'appliquer
            env[var] = str(value)
    return env
