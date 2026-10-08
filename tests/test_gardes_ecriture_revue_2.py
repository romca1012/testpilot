"""Lot VH-02 / VH-05 — cas relevés par la 2e revue `verdict-reviewer` (2026-10-08), chacun prouvé de bout en bout par
`write_steps_file` avec les attributs réels du harnais.

Bloquants : `constater(condition=True)` passait ; une valeur du Gherkin rangée par le test dans `context.valeur` comptait comme
une lecture de l'application. À corriger : refus à tort (helper qui reçoit `context`, `getattr(context, …)`, drapeau rempli dans
une boucle, liste remplie par `.append`, dictionnaire rempli par indice, fonction imbriquée), action RPC par alias ou par une
méthode hors liste, `getattr` vers un secret ou le harnais, `from __future__`, et contrôles absents en correction/réparation.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from testpilot import config
from testpilot.generation import litteraux_observes as lo
from testpilot.generation.tools import ToolContext
from testpilot.generation.tools import write as w

ENTETE = "from behave import given, when, then\nfrom _base_helpers import constater\n"
ATTRIBUTS = frozenset(lo.attributs_du_harnais(config.BEHAVE_RUNTIME_DIR))


def _ecrire(code, tmp_path):
    return w.write_steps_file(ToolContext(module_name="m", generated_dir=tmp_path, attributs_contexte=ATTRIBUTS),
                              ENTETE + code)


# ── Bloquants ─────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("corps", [
    "@then('ok')\ndef s(context):\n    constater(condition=True, message='ok')\n",
    "@then('ok')\ndef s(context):\n    args = (True, 'ok')\n    constater(*args)\n",
    "@then('ok')\ndef s(context):\n    constater(**{'condition': True})\n",
])
def test_falsifiable_une_condition_en_mot_cle_ou_deballee_est_jugee(corps, tmp_path):
    sortie = _ecrire(corps, tmp_path)

    assert not sortie.ok and "CONSTAT_SANS_LECTURE" in sortie.observation


def test_falsifiable_une_valeur_du_gherkin_rangee_dans_context_n_est_pas_une_lecture(tmp_path):
    corps = ("@when('je saisis \"{v}\"')\ndef w(context, v):\n    context.valeur = v\n"
             "@then('la valeur est \"{a}\"')\ndef t(context, a):\n    constater(context.valeur == a, 'valeur')\n")

    sortie = _ecrire(corps, tmp_path)

    assert not sortie.ok and "CONSTAT_SANS_LECTURE" in sortie.observation


def test_une_valeur_lue_a_l_ecran_et_rangee_dans_context_reste_une_lecture(tmp_path):
    corps = ("@when('je relève le numéro')\ndef w(context):\n    context.numero = context.page.inner_text('#n')\n"
             "@then('le numéro est \"{a}\"')\ndef t(context, a):\n    constater(context.numero == a, 'numéro')\n")

    assert _ecrire(corps, tmp_path).ok


# ── Refus à tort corrigés ─────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("corps", [
    # (A) helper de module qui lit avec `context`
    "def lire_statut(context):\n    return context.page.inner_text('#s')\n"
    "@then('le statut est \"{a}\"')\ndef t(context, a):\n    statut = lire_statut(context)\n    constater(statut == a, 's')\n",
    # (D) getattr sur un attribut posé par le harnais
    "@then('un enregistrement existe')\ndef t(context):\n    ids = getattr(context, 'last_record_ids', None)\n"
    "    constater(ids is not None, 'ids')\n",
    # (B) drapeau rempli dans une boucle qui lit la page
    "@then('la ligne \"{a}\" existe')\ndef t(context, a):\n    trouve = False\n"
    "    for l in context.page.locator('tr').all():\n        if a in l.inner_text():\n            trouve = True\n"
    "    constater(trouve, 'ligne')\n",
    # (C) liste remplie par .append
    "@then('il y a des lignes')\ndef t(context):\n    lignes = []\n"
    "    for l in context.page.locator('tr').all():\n        lignes.append(l.inner_text())\n"
    "    constater(len(lignes) > 0, 'lignes')\n",
    # (J) dictionnaire rempli par indice
    "@then('le statut est lu')\ndef t(context):\n    vals = {}\n    vals['s'] = context.page.inner_text('#s')\n"
    "    constater(vals['s'] != '', 's')\n",
    # (I) fonction imbriquée : jugée avec ses propres paramètres
    "@then('le statut est \"{a}\"')\ndef t(context, a):\n    def verif(v):\n        constater(v != '', 'non vide')\n"
    "    verif(context.page.inner_text('#s'))\n    constater(context.page.inner_text('#s') == a, 's')\n",
    # Odoo : création en Soit, relecture en Alors
    "@given('un client existe')\ndef g(context):\n    context.client_id = context.odoo.env['res.partner'].create({'name': 'x'})\n"
    "@then('le client existe')\ndef t(context):\n    env = context.odoo.env\n"
    "    constater(bool(env['res.partner'].browse(context.client_id).read(['name'])), 'client')\n",
])
def test_les_formes_legitimes_ne_sont_plus_refusees(corps, tmp_path):
    sortie = _ecrire(corps, tmp_path)

    assert sortie.ok, sortie.observation


# ── Action par RPC : alias et liste blanche de lectures ────────────────────────────────────────────────────


@pytest.mark.parametrize("corps", [
    "@when('je confirme')\ndef w(context):\n    env = context.odoo.env\n"
    "    env['sale.order'].browse(context.last_record_ids[0]).action_confirm()\n",
    "@when('je confirme l achat')\ndef w(context):\n    context.odoo.env['purchase.order'].browse(1).button_confirm()\n",
    "@then('l etat est fait')\ndef t(context):\n    m = context.odoo.env['sale.order']\n    m.browse(1).write({'state': 'done'})\n"
    "    constater(m.browse(1).read(['state'])[0]['state'] == 'done', 'etat')\n",
])
def test_falsifiable_une_action_par_rpc_meme_par_alias_est_refusee(corps, tmp_path):
    sortie = _ecrire(corps, tmp_path)

    assert not sortie.ok and "ACTION_PAR_RPC" in sortie.observation


# ── Python limité ─────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("code", [
    "def f(context):\n    getattr(context, '_runner').hooks.clear()\n",
    "def f(context):\n    p = getattr(context, 'web_password')\n",
])
def test_falsifiable_getattr_vers_le_harnais_ou_un_secret_est_refuse(code, tmp_path):
    assert not _ecrire(code, tmp_path).ok


def test_from_future_et_modules_de_dates_sont_permis(tmp_path):
    code = "from __future__ import annotations\nimport calendar\nimport copy\nfrom zoneinfo import ZoneInfo\n"

    assert w.write_steps_file(ToolContext(module_name="m", generated_dir=tmp_path), code).ok


# ── Correction et réparation armées comme la génération ───────────────────────────────────────────────────


@pytest.mark.parametrize("module, fonction, kwargs", [
    ("correction_agent", "propose_correction",
     {"lint_warnings": [], "feature_content": "", "steps_content": ""}),
    ("repair_agent", "propose_fix", {"scenarios": [], "failures": []}),
])
def test_correction_et_reparation_passent_par_les_memes_controles(module, fonction, kwargs, monkeypatch, tmp_path):
    import importlib

    agent = importlib.import_module(f"testpilot.generation.{module}")
    vus = {}
    monkeypatch.setattr(agent, "run_loop", lambda **k: vus.setdefault("ctx", k["ctx"]))
    modele = {"pages": {"/p": {"champs": [{"name": "nom"}], "actions": [], "liens": []}}}

    getattr(agent, fonction)(module_name="m", llm=SimpleNamespace(), connector_type="web", modele=modele, **kwargs)

    assert vus["ctx"].annuaire is not None and "page" in vus["ctx"].attributs_contexte
