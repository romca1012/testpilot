# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request

from ..models.bugs import CODES, bug_actif


class TpBugs(http.Controller):
    @http.route("/tp_bugs/actifs", type="json", auth="user")
    def actifs(self):
        """Les défauts actifs — lus par `static/src/js/message_absent.js` (défaut côté interface)."""
        return [code for code in CODES if bug_actif(request.env, code)]
