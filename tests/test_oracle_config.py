"""Lot 07e (C5, D7) — la configuration PURE de l'oracle backend HTTP d'un projet.

`connectors/oracle_config.py` ne fait que valider la FORME (JSON illisible, champs requis absents,
nom de requête dupliqué) — jamais l'exactitude auprès d'un serveur réel (ça, c'est
`OracleHttp.verifier_joignable`, testé à part).
"""

from __future__ import annotations

import json

import pytest

from testpilot.connectors import oracle_config as oracle


def test_type_aucun_ne_produit_aucune_erreur():
    assert oracle.erreurs("", "", "", "[]") == []


def test_type_inconnu_est_signale():
    assert oracle.erreurs("sql_invente", "", "", "[]") == [
        "type d'oracle « sql_invente » inconnu (attendu : aucun, http)"]


def test_http_sans_adresse_est_refuse():
    assert oracle.erreurs("http", "", "", "[]") == ["l'adresse de l'oracle est requise"]


@pytest.mark.parametrize("auth", [
    {"type": "bearer", "token": "abc"},
    {"type": "basic", "username": "u", "password": "p"},
    {"type": "en-tete", "name": "X-Api-Key", "value": "abc"},
    {"type": "aucune"},
])
def test_authentifications_valides_ne_produisent_aucune_erreur(auth):
    assert oracle.erreurs("http", "https://api.exemple", json.dumps(auth), "[]") == []


@pytest.mark.parametrize("auth", [
    {"type": "bearer"},
    {"type": "basic", "username": "u"},
    {"type": "en-tete", "name": "X-Api-Key"},
    {"type": "sso_devine"},
    "pas un objet",
])
def test_falsifiable_authentifications_incompletes_ou_inconnues_sont_refusees(auth):
    assert oracle.erreurs("http", "https://api.exemple", json.dumps(auth), "[]") != []


def test_falsifiable_authentification_illisible_est_refusee():
    assert oracle.erreurs("http", "https://api.exemple", "pas du json", "[]") != []


def test_requetes_valides_ne_produisent_aucune_erreur():
    requetes = json.dumps([
        {"name": "tickets_ouverts", "method": "GET", "path": "/tickets?status=open"},
        {"name": "creer_ticket", "method": "POST", "path": "/tickets", "params": {"a": 1}},
    ])
    assert oracle.erreurs("http", "https://api.exemple", "", requetes) == []


@pytest.mark.parametrize("requetes", [
    "pas du json",
    json.dumps({"pas": "une liste"}),
    json.dumps(["pas un objet"]),
    json.dumps([{"name": "", "method": "GET", "path": "/x"}]),
    json.dumps([{"name": "x", "method": "PATCH", "path": "/x"}]),
    json.dumps([{"name": "x", "method": "GET", "path": ""}]),
    json.dumps([{"name": "x", "method": "GET", "path": "/a"}, {"name": "x", "method": "GET", "path": "/b"}]),
])
def test_falsifiable_requetes_mal_formees_sont_refusees(requetes):
    assert oracle.erreurs("http", "https://api.exemple", "", requetes) != []


def test_noms_declares_rend_uniquement_les_noms():
    requetes = json.dumps([
        {"name": "tickets_ouverts", "method": "GET", "path": "/tickets", "params": {"secret": "x"}},
        {"name": "clients", "method": "GET", "path": "/clients"},
    ])
    noms = oracle.noms_declares(requetes)
    assert noms == ["tickets_ouverts", "clients"]
    # Rien d'autre que le nom ne doit fuiter (D8, précision 2 — même garantie côté oracle).
    assert "secret" not in json.dumps(noms) and "/tickets" not in json.dumps(noms)


@pytest.mark.parametrize("brut", ["", "pas du json", "{}", "null"])
def test_noms_declares_est_tolerant_a_une_valeur_illisible(brut):
    assert oracle.noms_declares(brut) == []
