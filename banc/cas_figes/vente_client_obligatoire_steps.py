"""Cas FIGÉ du banc de mesure (lot 04) — vente_client_obligatoire. Écrit à la main, sans LLM : il tient lieu de version de
cas déjà approuvée (mode `figé` de `scripts/banc_mesure.py`, coût nul). Les vérifications passent par
`constater(...)` / les steps de la bibliothèque, comme tout cas produit après le lot 03."""
from behave import given, then, when
from _base_helpers import PreconditionNonRemplieError, constater  # noqa: F401


def _E(context):
    return context.odoo.env


def _client(context):
    E = _E(context)
    nom = "Client banc " + context.tentative_token
    ids = E["res.partner"].search([("name", "=", nom)])
    return ids[0] if ids else E["res.partner"].create({"name": nom})


def _produit(context):
    E = _E(context)
    ids = E["product.product"].search([("default_code", "=", "BANC-P1")])
    if ids:
        return ids[0]
    return E["product.product"].create({
        "name": "Produit banc", "default_code": "BANC-P1", "type": "consu", "list_price": 100.0,
        "standard_price": 60.0, "taxes_id": [(5, 0, 0)], "supplier_taxes_id": [(5, 0, 0)]})


def _commande_vente(context, env=None):
    E = env or _E(context)
    return E["sale.order"].create({
        "partner_id": _client(context),
        "order_line": [(0, 0, {"product_id": _produit(context), "product_uom_qty": 2})]})


def _session(context, login, mot_de_passe):
    """Une session RPC SÉPARÉE (autre compte de test que celui du projet)."""
    import odoorpc
    from urllib.parse import urlparse
    url = urlparse(context.odoo_url)
    connexion = odoorpc.ODOO(url.hostname, protocol="jsonrpc", port=url.port or 8069)
    connexion.login(context.odoo_db, login, mot_de_passe)
    return connexion

@when('je tente de créer une commande de vente sans client')
def step_sans_client(context):
    context.refus = None
    try:
        _E(context)["sale.order"].create({"order_line": [
            (0, 0, {"product_id": _produit(context), "product_uom_qty": 1})]})
    except Exception as exc:  # RPCError côté serveur : c'est le refus attendu
        context.refus = str(exc)


@then('la création de la commande est refusée')
def step_refusee(context):
    constater(context.refus is not None, "Une commande sans client a été acceptée par le serveur.")
