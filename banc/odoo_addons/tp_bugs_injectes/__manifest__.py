# -*- coding: utf-8 -*-
{
    "name": "TestPilot — défauts injectés (banc de mesure)",
    "summary": "Défauts activables un par un, INACTIFS par défaut — uniquement pour le banc de mesure.",
    "description": """
Banc de mesure de la fiabilité du verdict (lot 04 du plan de fiabilité).

Chaque défaut s'active par le paramètre système `tp_bug.<code>` = `1` et n'existe que sur l'instance du
banc : ce module n'est JAMAIS installé sur une instance client. Sans paramètre, le comportement d'Odoo est
inchangé (les tests du module le vérifient, défaut par défaut).
""",
    "version": "1.0",
    "category": "Hidden",
    "license": "LGPL-3",
    "depends": ["sale_management", "sale_stock", "stock", "account", "purchase"],
    "data": [],
    "assets": {
        "web.assets_backend": ["tp_bugs_injectes/static/src/js/message_absent.js"],
    },
    "installable": True,
    "application": False,
}
