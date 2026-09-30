"""`OdooConnector.inspect_odoo_view` contre une VRAIE instance Odoo (lot 09, C9).

Complète `test_odoo_view.py` (analyse pure, fixtures figées) : ici, le VRAI round-trip RPC
(`get_views`) sur une vue réelle — même motif que `test_navigation_menu_banc.py` (marqueur
`banc`, ignoré si le banc ne répond pas, lancé séparément par `banc.yml`).
"""

from __future__ import annotations

import os
import urllib.request

import pytest

pytestmark = pytest.mark.banc

BANC = os.environ.get("BANC_URL", "http://127.0.0.1:18069")


def _banc_repond() -> bool:
    try:
        urllib.request.urlopen(BANC + "/web/login", timeout=5)
        return True
    except Exception:
        if os.environ.get("BANC_REQUIS") == "1":
            pytest.fail(f"BANC_REQUIS=1 mais le banc ne répond pas sur {BANC}")
        return False


@pytest.fixture
def connecteur():
    if not _banc_repond():
        pytest.skip(f"le banc ne répond pas sur {BANC} (scripts/banc_init.sh)")
    from testpilot.connectors.odoo import OdooConnector

    conn = OdooConnector(BANC, "banc", "admin", "admin")
    conn.connect()
    yield conn
    conn.disconnect()


def test_inspect_odoo_view_lit_les_boutons_la_barre_d_etat_et_les_requis_de_sale_order(connecteur):
    resultat = connecteur.inspect_odoo_view("sale.order", "form")

    assert resultat["erreur"] == ""
    assert resultat["boutons"], "un vrai formulaire de workflow a des boutons"
    assert resultat["barre_etat"]["champ"] == "state"
    assert "partner_id" in resultat["champs_requis"]


def test_falsifiable_les_boutons_de_workflow_portent_une_visibilite_conditionnelle_pas_un_bool(connecteur):
    """Preuve du correctif trouvé en construisant ce lot : sur un vrai formulaire, la plupart des
    boutons ont un `invisible` CONDITIONNEL (domaine Odoo), pas un simple `true`/`false`. Si ce
    test échoue en rendant tout booléen, c'est que la régression mesurée le 2026-09-30 est
    revenue."""
    resultat = connecteur.inspect_odoo_view("sale.order", "form")

    conditionnels = [b for b in resultat["boutons"] if isinstance(b["invisible"], list)]
    assert conditionnels, "aucun bouton conditionnel trouvé — la distinction a-t-elle régressé ?"


def test_inspect_odoo_view_recense_les_sous_champs_de_la_ligne_de_commande(connecteur):
    resultat = connecteur.inspect_odoo_view("sale.order", "form")

    order_line = next(c for c in resultat["champs_x2many"] if c["name"] == "order_line")
    assert order_line["relation"] == "sale.order.line"
    assert "product_id" in order_line["sous_champs"]


def test_inspect_odoo_view_met_en_cache_le_second_appel(connecteur):
    premier = connecteur.inspect_odoo_view("sale.order", "form")
    second = connecteur.inspect_odoo_view("sale.order", "form")
    assert premier is second


def test_inspect_odoo_view_gere_un_modele_sans_vue_form_reelle(connecteur):
    """Best-effort : un modèle technique sans vue `form` dédiée ne doit jamais lever, seulement
    remonter une erreur lisible."""
    resultat = connecteur.inspect_odoo_view("ir.model.fields", "form")
    assert isinstance(resultat, dict)
    assert "boutons" in resultat
