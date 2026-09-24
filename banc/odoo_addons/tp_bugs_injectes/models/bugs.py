# -*- coding: utf-8 -*-
"""Lecture des défauts actifs — un défaut = un `ir.config_parameter` `tp_bug.<code>` valant `1`."""

CODES = (
    "vente_sans_livraison",
    "total_faux",
    "client_non_requis",
    "etat_bloque",
    "facture_non_postee",
    "droit_trop_large",
    "message_absent",
)


def bug_actif(env, code):
    """Vrai si `tp_bug.<code>` vaut `1`. Toujours faux par défaut (aucun paramètre = aucun défaut)."""
    assert code in CODES, code
    return env["ir.config_parameter"].sudo().get_param("tp_bug." + code) == "1"
