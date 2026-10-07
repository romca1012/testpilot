"""Règles par connecteur (lot Q3, D20) : éteintes par défaut, génériques, et reliées à des éléments qui existent."""

from __future__ import annotations

import re

import pytest

from testpilot import config
from testpilot.connectors.generic_web import GenericWebConnector
from testpilot.generation import interrupteurs, prompt, regles_connecteur
from testpilot.generation.tools import TOOLS_DEFINITIONS

ENV = interrupteurs.ENV_REGLES_CONNECTEUR
_MOTS_DE_CLIENT = ("sapian", "saucedemo", "odoo", "yros", "boutique", "panier", "clavier")


@pytest.fixture
def web():
    return GenericWebConnector("http://127.0.0.1:1")


def test_eteint_par_defaut_rien_ne_change(monkeypatch, web):
    monkeypatch.delenv(ENV, raising=False)

    assert web.rules() == ""
    assert prompt._section_comptes(None) == ""
    assert prompt._section_comptes([]) == ""


def test_allume_le_connecteur_web_annonce_le_compte_principal(monkeypatch, web):
    monkeypatch.setenv(ENV, "1")

    regles = web.rules()

    assert 'je me connecte en tant que "principal"' in regles
    assert "JAMAIS d'identifiant" in regles


def test_allume_la_section_comptes_existe_des_le_compte_principal(monkeypatch):
    """Falsifiable : avant, un projet à un seul compte n'envoyait RIEN — l'agent a inventé un mot de passe (2026-10-07)."""
    monkeypatch.setenv(ENV, "1")

    section = prompt._section_comptes(None)

    assert "« principal »" in section and "JAMAIS d'identifiant ni de mot de passe" in section


def test_allume_les_comptes_secondaires_restent_listes(monkeypatch):
    monkeypatch.setenv(ENV, "1")

    section = prompt._section_comptes([{"label": "gestionnaire", "business_role": "valide"}])

    assert "« gestionnaire » — rôle : valide" in section and "« principal »" in section


def test_les_regles_sont_generiques_aucun_nom_de_client():
    texte = (regles_connecteur.REGLE_COMPTE_PRINCIPAL + regles_connecteur.REGLES_WEB).lower()

    for mot in _MOTS_DE_CLIENT:
        assert mot not in texte, mot


def test_chaque_outil_ou_step_cite_existe():
    """Une règle qui renvoie à un outil ou à un step inexistant fait chercher l'agent dans le vide."""
    noms_outils = {d["name"] for d in TOOLS_DEFINITIONS}
    cites = set(re.findall(r"`(inspect_[a-z_]+)`", regles_connecteur.REGLES_WEB))
    assert cites and cites <= noms_outils, cites - noms_outils

    sources = config.BEHAVE_RUNTIME_DIR / "steps_library"
    for connecteur in ("web/_web_steps.py", "odoo/_odoo_steps.py"):
        source = (sources / connecteur).read_text(encoding="utf-8")
        assert "@when('je me connecte en tant que \"{libelle}\"')" in source


def test_le_prompt_complet_ne_change_pas_eteint_et_change_allume(monkeypatch):
    monkeypatch.delenv(ENV, raising=False)
    eteint = prompt._section_comptes(None) + GenericWebConnector("http://127.0.0.1:1").rules()
    monkeypatch.setenv(ENV, "1")
    allume = prompt._section_comptes(None) + GenericWebConnector("http://127.0.0.1:1").rules()

    assert eteint == "" and allume != ""
