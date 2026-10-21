"""Étape 4 du plan unique (A71, A75) : la remise à zéro de l'Odoo du banc, contre la VRAIE instance (marqueur `banc`, ignoré si
le banc ne répond pas, lancé séparément — `scripts/banc_init.*` puis `pytest -m banc`).

Ce qu'elle doit prouver :
1. ce qu'un test a créé disparaît (la base revient à la base modèle) ;
2. un défaut ACTIVÉ pour une mesure reste actif — sinon le test suivant sortirait vert sur une application devenue saine ;
3. Odoo répond normalement juste après, et l'adresse est acceptée par TestPilot (même origine, réponse explicite).
"""

from __future__ import annotations

import os
import urllib.request
import xmlrpc.client

import pytest

from testpilot.guardrails import bac_a_sable

pytestmark = pytest.mark.banc

BANC = os.environ.get("BANC_URL", "http://127.0.0.1:18069")
BASE, ADMIN = "banc", ("admin", "admin")


def _banc_repond() -> bool:
    try:
        urllib.request.urlopen(BANC + "/web/login", timeout=5)
        return True
    except Exception:
        if os.environ.get("BANC_REQUIS") == "1":
            pytest.fail(f"BANC_REQUIS=1 mais le banc ne répond pas sur {BANC}")
        return False


@pytest.fixture
def odoo():
    if not _banc_repond():
        pytest.skip(f"le banc ne répond pas sur {BANC} (scripts/banc_init.*)")

    def appeler(modele, methode, *args, **kw):
        uid = xmlrpc.client.ServerProxy(f"{BANC}/xmlrpc/2/common").authenticate(BASE, *ADMIN, {})
        return xmlrpc.client.ServerProxy(f"{BANC}/xmlrpc/2/object").execute_kw(BASE, uid, ADMIN[1], modele, methode,
                                                                               list(args), kw)
    yield appeler
    appeler("ir.config_parameter", "set_param", "tp_bug.total_faux", "0")   # le banc repart sain


def test_falsifiable_ce_qu_un_test_a_cree_disparait(odoo):
    pid = odoo("res.partner", "create", {"name": "Martin SARL (remise à zéro)"})
    assert odoo("res.partner", "search_count", [("id", "=", pid)]) == 1
    bac_a_sable.remettre_a_zero(f"{BANC}/__reset", delai_s=120)
    assert odoo("res.partner", "search_count", [("name", "=", "Martin SARL (remise à zéro)")]) == 0


def test_falsifiable_un_defaut_active_reste_actif_apres_la_remise_a_zero(odoo):
    odoo("ir.config_parameter", "set_param", "tp_bug.total_faux", "1")
    bac_a_sable.remettre_a_zero(f"{BANC}/__reset", delai_s=120)
    assert odoo("ir.config_parameter", "get_param", "tp_bug.total_faux") == "1", \
        "un défaut perdu à la remise à zéro fausserait la mesure (vert sur une application devenue saine)"


def test_l_adresse_est_acceptee_par_testpilot_et_odoo_repond_juste_apres(odoo):
    from testpilot.generation.tools.essai import adresse_de_remise_a_zero

    assert adresse_de_remise_a_zero(BANC, "/__reset") == f"{BANC}/__reset", "même origine que l'application"
    bac_a_sable.remettre_a_zero(f"{BANC}/__reset", delai_s=120)
    assert urllib.request.urlopen(BANC + "/web/login", timeout=30).status == 200
    assert odoo("res.users", "search_count", [("login", "=", "admin")]) == 1
