"""Steps de Contexte (Background) spécifiques au connecteur Odoo — session RPC, garde-fous env.

Ces 4 steps sont les SEULS à avoir des décorateurs Behave dans ce fichier (le 5e du fichier
d'origine, la déclaration de teardown, ne dépend d'aucun connecteur — il vit maintenant dans
`../generic/_generic_steps.py`). Ils ne causent jamais d'AmbiguousStep car aucun agent ne les
régénère.
"""
from behave import given


@given('l\'instance Odoo accessible à l\'URL définie dans "ODOO_URL"')
def step_odoo_accessible(context):
    assert context.odoo is not None, "La session OdooRPC n'est pas initialisée."


@given('la variable d\'environnement "ODOO_ENV" n\'est pas définie à "prod"')
def step_env_not_prod(context):
    import os
    if os.environ.get("ODOO_ENV") == "prod":
        raise EnvironmentError(
            "SAFETY: Refus d'exécution contre une instance Odoo de production."
        )


@given('je suis authentifié en tant qu\'utilisateur défini dans "ODOO_USER" '
       'avec le mot de passe défini dans "ODOO_PASSWORD"')
def step_authenticated(context):
    """VÉRIFIE la session RPC (odoorpc) — ne connecte PAS le navigateur : pour ouvrir une page du portail, utilise « je me connecte avec mes identifiants utilisateur »."""
    assert context.odoo.env.uid, "L'utilisateur Odoo n'est pas authentifié."


@given('le module Odoo "{module_name}" est installé et actif sur la base '
       'définie dans "ODOO_DB"')
def step_module_installed(context, module_name):
    IrModule = context.odoo.env["ir.module.module"]
    ids = IrModule.search([("name", "=", module_name), ("state", "=", "installed")])
    assert ids, f"Le module Odoo '{module_name}' n'est pas installé."
