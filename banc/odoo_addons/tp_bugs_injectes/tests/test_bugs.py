# -*- coding: utf-8 -*-
"""Chaque défaut ACTIVÉ produit l'effet décrit ; DÉSACTIVÉ, il ne change rien (comportement d'Odoo d'origine).

Lancer : odoo -d <base> -i tp_bugs_injectes --test-tags /tp_bugs_injectes --stop-after-init
"""
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from ..models.bugs import CODES


@tagged("post_install", "-at_install", "tp_bugs_injectes")
class TestBugsInjectes(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create({"name": "Client banc"})
        cls.produit = cls.env["product.product"].create({
            "name": "Produit banc", "type": "consu",
            "list_price": 100.0, "taxes_id": [(5, 0, 0)],
        })

    def _activer(self, code, valeur="1"):
        self.env["ir.config_parameter"].sudo().set_param("tp_bug." + code, valeur)

    def _commande(self, partner=True):
        vals = {"order_line": [(0, 0, {"product_id": self.produit.id, "product_uom_qty": 2})]}
        if partner:
            vals["partner_id"] = self.partner.id
        return self.env["sale.order"].create(vals)

    # ── Tous les défauts sont inactifs par défaut ──────────────────────────────────────────────
    def test_aucun_defaut_actif_par_defaut(self):
        for code in CODES:
            self.assertFalse(self.env["ir.config_parameter"].sudo().get_param("tp_bug." + code), code)

    # ── vente_sans_livraison ────────────────────────────────────────────────────────────────────
    def test_vente_sans_livraison(self):
        normal = self._commande()
        normal.action_confirm()
        self.assertTrue(normal.picking_ids, "sain : la confirmation crée un bon de livraison")

        self._activer("vente_sans_livraison")
        casse = self._commande()
        casse.action_confirm()
        self.assertEqual(casse.state, "sale")
        self.assertFalse(casse.picking_ids, "défaut : aucun bon de livraison")

    # ── total_faux ──────────────────────────────────────────────────────────────────────────────
    def test_total_faux(self):
        normal = self._commande()
        self.assertAlmostEqual(normal.amount_total, 200.0, places=2)

        self._activer("total_faux")
        casse = self._commande()
        self.assertAlmostEqual(casse.amount_total, 202.0, places=2, msg="défaut : +1 %")

    # ── client_non_requis ───────────────────────────────────────────────────────────────────────
    def test_client_non_requis(self):
        with self.assertRaises(ValidationError):
            self._commande(partner=False)
        self.assertTrue(self.env["sale.order"].fields_get(["partner_id"])["partner_id"]["required"])

        self._activer("client_non_requis")
        commande = self._commande(partner=False)
        self.assertFalse(commande.partner_id, "défaut : une commande sans client est acceptée")
        self.assertFalse(self.env["sale.order"].fields_get(["partner_id"])["partner_id"]["required"])

    # ── etat_bloque ─────────────────────────────────────────────────────────────────────────────
    def test_etat_bloque(self):
        normal = self._commande()
        normal.action_confirm()
        self.assertEqual(normal.state, "sale")

        self._activer("etat_bloque")
        casse = self._commande()
        casse.action_confirm()
        self.assertEqual(casse.state, "draft", "défaut : l'état reste `draft`, sans erreur")

    # ── facture_non_postee ──────────────────────────────────────────────────────────────────────
    def _facture(self):
        return self.env["account.move"].create({
            "move_type": "out_invoice", "partner_id": self.partner.id,
            "invoice_line_ids": [(0, 0, {"name": "Ligne banc", "quantity": 1, "price_unit": 50.0})],
        })

    def test_facture_non_postee(self):
        normale = self._facture()
        normale.action_post()
        self.assertEqual(normale.state, "posted")

        self._activer("facture_non_postee")
        casse = self._facture()
        casse.action_post()
        self.assertEqual(casse.state, "draft", "défaut : la facture reste brouillon")

    # ── droit_trop_large ────────────────────────────────────────────────────────────────────────
    def test_droit_trop_large(self):
        utilisateur = self.env["res.users"].create({
            "name": "Commercial test", "login": "commercial_test_tp",
            "groups_id": [(6, 0, [self.env.ref("sales_team.group_sale_salesman").id,
                                  self.env.ref("base.group_user").id])],
        })
        normal = self._commande()
        normal.action_confirm()
        with self.assertRaises(UserError):
            normal.with_user(utilisateur).unlink()
        self.assertTrue(normal.exists(), "sain : une commande confirmée ne se supprime pas")

        self._activer("droit_trop_large")
        casse = self._commande()
        casse.action_confirm()
        casse.with_user(utilisateur).unlink()
        self.assertFalse(casse.exists(), "défaut : la commande confirmée est supprimée")

    # ── message_absent (interface) ──────────────────────────────────────────────────────────────
    def test_message_absent_est_expose_a_l_interface(self):
        from ..controllers.main import TpBugs  # noqa: F401  (le contrôleur existe)
        from ..models.bugs import bug_actif

        self.assertFalse(bug_actif(self.env, "message_absent"))
        self._activer("message_absent")
        self.assertTrue(bug_actif(self.env, "message_absent"))
        self._activer("message_absent", "0")
        self.assertFalse(bug_actif(self.env, "message_absent"))
