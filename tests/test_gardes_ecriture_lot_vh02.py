"""Lot VH-02 (V1, V9) — gardes BLOQUANTES de `write_steps_file` : un constat lit l'application, une action ne se fait pas par
RPC, le Python d'un fichier de steps est limité (audit du 2026-10-08).

Chaque refus correspond à un faux `conforme` possible relevé par l'audit ; chaque acceptation, à une forme RÉELLE des tests
générés de la campagne `base-3` (aucun des 29 fichiers générés n'est refusé par ces gardes — calibrage du 2026-10-08).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from testpilot.generation.tools import ToolContext
from testpilot.generation.tools import write as w

ENTETE = "from behave import given, when, then\nfrom _base_helpers import constater\n"


def _ecrire(code: str, tmp_path: Path):
    ctx = ToolContext(module_name="m", generated_dir=tmp_path)
    return w.write_steps_file(ctx, ENTETE + code)


# ── Un constat doit lire l'application ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("corps", [
    "@then('le statut est \"{statut}\"')\ndef s(context, statut):\n    attendu = 'Validé'\n    constater(statut == attendu, 'x')\n",
    "@then('ok')\ndef s(context):\n    constater(True, 'toujours vrai')\n",
    "@then('ok')\ndef s(context):\n    v = 3\n    constater(v == v, 'tautologie')\n",
    "@then('la ligne \"{a}\" a \"{b}\"')\ndef s(context, a, b):\n    constater(context.table is None or a in b, 'données du test')\n",
])
def test_falsifiable_un_constat_qui_ne_lit_rien_de_l_application_est_refuse(corps, tmp_path):
    sortie = _ecrire(corps, tmp_path)

    assert not sortie.ok and "CONSTAT_SANS_LECTURE" in sortie.observation


@pytest.mark.parametrize("corps", [
    # formes RÉELLES de base-3 (lecture à l'écran puis comparaison à une valeur du Gherkin)
    "@then('le total vaut \"{montant}\"')\ndef s(context, montant):\n"
    "    texte = context.page.locator('#total').inner_text()\n    constater(montant in texte, 'total')\n",
    "@then('le panier est vide')\ndef s(context):\n    lignes = [l for l in context.page.locator('tr').all()]\n"
    "    constater(len(lignes) == 0, 'vide')\n",
    "@then('le numéro est affiché')\ndef s(context):\n    import re\n    match = re.search(r'CMD-\\\\d+', context.page.content())\n"
    "    constater(match is not None, 'numéro')\n",
    # helper non décoré : ses paramètres viennent d'un step
    "def _verifier(page, attendu):\n    constater(page.locator('#s').inner_text() == attendu, 's')\n"
    "@then('le statut est \"{s}\"')\ndef s(context, s):\n    _verifier(context.page, s)\n    constater(context.page.url.endswith('/ok'), 'url')\n",
])
def test_un_constat_qui_lit_l_application_est_accepte(corps, tmp_path):
    sortie = _ecrire(corps, tmp_path)

    assert sortie.ok, sortie.observation


@pytest.mark.parametrize("code, attendu", [
    ("from _base_helpers import constater as verifier\n", "autre nom"),
    ("def constater(c, m=''):\n    pass\n", "redéfinition"),
    ("constater = print\n", "réaffectation"),
])
def test_falsifiable_constater_ne_se_redefinit_ni_ne_se_renomme(code, attendu, tmp_path):
    sortie = _ecrire(code, tmp_path)

    assert not sortie.ok and attendu in sortie.observation


# ── Une action ne se fait pas par RPC ─────────────────────────────────────────────────────────────────────


def test_falsifiable_une_action_par_rpc_dans_un_quand_est_refusee(tmp_path):
    corps = ("@when('je valide la commande')\ndef s(context):\n"
             "    context.odoo.env['sale.order'].browse(context.last_record_ids[0]).write({'state': 'done'})\n")

    sortie = _ecrire(corps, tmp_path)

    assert not sortie.ok and "ACTION_PAR_RPC" in sortie.observation


def test_une_preparation_par_rpc_dans_un_soit_reste_permise(tmp_path):
    corps = ("@given('un client « {nom} » existe')\ndef s(context, nom):\n"
             "    context.client_id = context.odoo.env['res.partner'].create({'name': nom})\n")

    assert _ecrire(corps, tmp_path).ok


# ── Python limité ─────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("code", [
    "import odoorpc\n",
    "import socket\n",
    "import subprocess\n",
    "from pathlib import Path\n",
    "x = __import__('os')\n",
    "def f(context):\n    open('C:/sidecar.jsonl', 'w')\n",
    "def f(context):\n    exec('x=1')\n",
    "def f(context):\n    context._runner.hooks.clear()\n",
    "def f(context):\n    getattr(context, 'web_' + 'password')\n",
])
def test_falsifiable_le_python_hors_cadre_est_refuse(code, tmp_path):
    sortie = _ecrire(code, tmp_path)

    assert not sortie.ok and "PYTHON_INTERDIT" in sortie.observation


def test_les_imports_reels_des_tests_generes_restent_permis(tmp_path):
    code = ("from features.environment import register_created\nimport re\nimport json\n"
            "from playwright.sync_api import expect\n"
            "def f(context):\n    return getattr(context, 'numero', None)\n")

    assert _ecrire(code, tmp_path).ok


def test_aucun_test_genere_de_base_3_n_est_refuse_par_ces_gardes():
    """Calibrage : les 28 fichiers générés de `base-3` (s'ils sont présents localement) passent les trois gardes."""
    fichiers = list(Path(".local-preview/qualification").glob("banc-agents-*-t*/pilote-*/generated/*_steps.py"))
    if not fichiers:
        pytest.skip("artefacts de la campagne base-3 absents de ce poste")
    for f in fichiers:
        arbre = ast.parse(f.read_text(encoding="utf-8"))
        assert not (w._forbidden_python(arbre) or w._forbidden_ecriture_rpc(arbre) or w._constat_sans_lecture(arbre)), f
