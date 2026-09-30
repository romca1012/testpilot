"""Tool `inspect_odoo_view` (lot 09, C9) — perception, jamais l'analyse elle-même (déjà couverte
par `test_odoo_view.py`/`test_odoo_view_banc.py`). Connecteur factice par duck-typing
(`SimpleNamespace`), même motif que `test_generation_verified_fields.py`.
"""

from __future__ import annotations

from types import SimpleNamespace

from testpilot.generation.tools import ToolContext, dispatch
from testpilot.generation.tools.inspect import inspect_odoo_view

_VUE_COMPLETE = {
    "boutons": [
        {"name": "action_confirm", "libelle": "Confirmer", "type": "object",
         "invisible": [["state", "not in", ["draft"]]]},
        {"name": "action_preview", "libelle": "Aperçu", "type": "object", "invisible": False},
    ],
    "barre_etat": {"champ": "state", "valeurs_visibles": ["draft", "sale"],
                   "valeurs_toutes": ["draft", "sale", "cancel"]},
    "champs_x2many": [{"name": "order_line", "relation": "sale.order.line",
                       "sous_champs": ["product_id", "product_uom_qty"]}],
    "champs_requis": ["partner_id"],
    "erreur": "",
}


def test_inspect_odoo_view_decrit_boutons_barre_etat_et_x2many_dans_l_observation():
    ctx = ToolContext("m", None, connector=SimpleNamespace(
        inspect_odoo_view=lambda model, view_type="form": _VUE_COMPLETE))

    outcome = inspect_odoo_view(ctx, "sale.order", "form")

    assert outcome.ok is True
    assert "action_confirm" in outcome.observation
    assert "Confirmer" in outcome.observation
    assert "state" in outcome.observation
    assert "order_line" in outcome.observation
    assert "product_id" in outcome.observation


def test_inspect_odoo_view_traduit_la_visibilite_conditionnelle_en_francais_lisible():
    """Falsifiable : ce test échoue si le domaine conditionnel est réduit à « caché »/« visible »
    au lieu d'exposer la condition elle-même (voir `_rendre_invisible`)."""
    ctx = ToolContext("m", None, connector=SimpleNamespace(
        inspect_odoo_view=lambda model, view_type="form": _VUE_COMPLETE))

    outcome = inspect_odoo_view(ctx, "sale.order", "form")

    assert "not in" in outcome.observation  # le domaine brut, pas une traduction opaque
    assert "toujours visible" in outcome.observation  # action_preview


def test_inspect_odoo_view_verified_fields_exclut_les_noms_de_bouton():
    """Un nom de bouton (`action_confirm`) n'est PAS un nom de champ — le smoke-check
    (`check_champs_existants`) ne doit jamais le considérer comme un champ Odoo réel."""
    ctx = ToolContext("m", None, connector=SimpleNamespace(
        inspect_odoo_view=lambda model, view_type="form": _VUE_COMPLETE))

    outcome = inspect_odoo_view(ctx, "sale.order", "form")

    noms = outcome.verified_fields["inspect_odoo_view:sale.order:form"]
    assert "action_confirm" not in noms
    assert "partner_id" in noms
    assert "order_line" in noms
    assert "product_id" in noms


def test_inspect_odoo_view_sans_connecteur():
    ctx = ToolContext("m", None, connector=None)
    outcome = inspect_odoo_view(ctx, "sale.order", "form")
    assert outcome.ok is False


def test_inspect_odoo_view_sans_modele():
    ctx = ToolContext("m", None, connector=SimpleNamespace(inspect_odoo_view=lambda *a, **k: {}))
    outcome = inspect_odoo_view(ctx, "", "form")
    assert outcome.ok is False


def test_inspect_odoo_view_connecteur_sans_support_odoo():
    def _leve(*_a, **_k):
        raise NotImplementedError("pas de vues Odoo")
    ctx = ToolContext("m", None, connector=SimpleNamespace(inspect_odoo_view=_leve))

    outcome = inspect_odoo_view(ctx, "sale.order", "form")

    assert outcome.ok is False
    assert "non-Odoo" in outcome.observation


def test_inspect_odoo_view_relaie_l_erreur_de_perception():
    ctx = ToolContext("m", None, connector=SimpleNamespace(
        inspect_odoo_view=lambda model, view_type="form": {
            "boutons": [], "barre_etat": None, "champs_x2many": [], "champs_requis": [],
            "erreur": "arch illisible : ParseError"}))

    outcome = inspect_odoo_view(ctx, "sale.order", "form")

    assert outcome.ok is False
    assert "arch illisible" in outcome.observation


def test_inspect_odoo_view_est_route_par_dispatch():
    ctx = ToolContext("m", None, connector=SimpleNamespace(
        inspect_odoo_view=lambda model, view_type="form": _VUE_COMPLETE))

    outcome = dispatch("inspect_odoo_view", {"model": "sale.order", "view_type": "form"}, ctx)

    assert outcome.ok is True
    assert "action_confirm" in outcome.observation
