# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .bugs import bug_actif


class SaleOrder(models.Model):
    _inherit = "sale.order"

    # ── total_faux : `amount_total` décalé de 1 % ─────────────────────────────────────────────
    @api.depends("order_line.price_subtotal", "order_line.price_tax", "order_line.price_total")
    def _compute_amounts(self):
        super()._compute_amounts()
        if bug_actif(self.env, "total_faux"):
            for order in self:
                order.amount_total = order.amount_total * 1.01

    # ── etat_bloque : `action_confirm` laisse l'état `draft` sans erreur ────────────────────────
    def action_confirm(self):
        if bug_actif(self.env, "etat_bloque"):
            return True
        return super().action_confirm()

    # ── client_non_requis : `partner_id` optionnel ─────────────────────────────────────────────
    # La colonne est NULLABLE dans tous les cas (`required=False` au niveau du champ : Odoo remet sinon
    # `NOT NULL` à chaque mise à jour). Le comportement d'ORIGINE — un client obligatoire — est rendu en Python
    # (contrainte ci-dessous) ET côté interface (`fields_get`), tant que le défaut n'est pas actif.
    partner_id = fields.Many2one(required=False)
    # Les adresses de facturation/livraison, calculées depuis le client, sont NOT NULL elles aussi.
    partner_invoice_id = fields.Many2one(required=False)
    partner_shipping_id = fields.Many2one(required=False)

    # Sans le défaut actif, l'obligation d'origine est rendue en Python.
    @api.constrains("partner_id")
    def _tp_client_obligatoire(self):
        if bug_actif(self.env, "client_non_requis"):
            return
        for order in self:
            if not order.partner_id:
                raise ValidationError(_("Le client est obligatoire sur une commande."))

    @api.model_create_multi
    def create(self, vals_list):
        # `@api.constrains` ne se déclenche que pour les champs ÉCRITS : une création sans `partner_id` passerait.
        if not bug_actif(self.env, "client_non_requis"):
            for vals in vals_list:
                if not vals.get("partner_id"):
                    raise ValidationError(_("Le client est obligatoire sur une commande."))
        return super().create(vals_list)

    @api.model
    def fields_get(self, allfields=None, attributes=None):
        res = super().fields_get(allfields=allfields, attributes=attributes)
        if "partner_id" in res and (not attributes or "required" in attributes):
            res["partner_id"]["required"] = not bug_actif(self.env, "client_non_requis")
        return res

    # ── droit_trop_large : un utilisateur Ventes supprime une commande confirmée ────────────────
    def unlink(self):
        if bug_actif(self.env, "droit_trop_large"):
            confirmees = self.filtered(lambda o: o.state not in ("draft", "cancel"))
            if confirmees:
                confirmees.sudo().write({"state": "cancel"})
                return super(SaleOrder, self.sudo()).unlink()
        return super().unlink()


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    # ── vente_sans_livraison : confirmer un devis ne crée pas de bon de livraison ───────────────
    def _action_launch_stock_rule(self, previous_product_uom_qty=False):
        if bug_actif(self.env, "vente_sans_livraison"):
            return True
        return super()._action_launch_stock_rule(previous_product_uom_qty=previous_product_uom_qty)
