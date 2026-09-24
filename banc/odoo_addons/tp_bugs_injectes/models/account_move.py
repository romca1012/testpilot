# -*- coding: utf-8 -*-
from odoo import models

from .bugs import bug_actif


class AccountMove(models.Model):
    _inherit = "account.move"

    # ── facture_non_postee : la validation ne passe pas en `posted`, sans erreur ────────────────
    def action_post(self):
        if bug_actif(self.env, "facture_non_postee"):
            return True
        return super().action_post()
