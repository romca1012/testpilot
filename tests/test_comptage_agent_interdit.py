"""§F9 (2026-09-23) — un step généré ne recompte JAMAIS lui-même les enregistrements.

Défaut mesuré en campagne réelle (cas 95 régénéré, projet Sapian portail, 23/09/2026) : l'agent a
écrit ses propres steps de comptage (`search_count([])` avant/après) au lieu des steps du
catalogue protégés par le lot 01 (`id > max_id`). Un comptage global recalculé dans le code
GÉNÉRÉ réintroduit le faux PASSED de F1 là où aucun test du dépôt ne le voit.

`write_steps_file` refuse (régime bloquant, comme le transport interdit) ; détection par AST.
"""
from pathlib import Path

import pytest

from testpilot.generation.tools import ToolContext
from testpilot.generation.tools import write as write_tools


def _ecrire(tmp_path, code):
    ctx = ToolContext(module_name="m", generated_dir=tmp_path, connector=None)
    return write_tools.write_steps_file(ctx, code)


_ENTETE = "from behave import when, then\n"


@pytest.mark.parametrize("corps", [
    # forme 1 : search_count
    "    context.n = context.odoo.env['helpdesk.ticket'].search_count([])\n",
    # forme 2 : len(search(...)) direct
    "    context.n = len(context.odoo.env['helpdesk.ticket'].search([]))\n",
    # forme 3 : len(read(...)) direct
    "    context.n = len(context.odoo.env['helpdesk.ticket'].read([1], ['name']))\n",
    # forme 4 : len() d'une variable issue d'un search
    "    ids = context.odoo.env['helpdesk.ticket'].search([])\n    context.n = len(ids)\n",
    # forme 5 : alias local du modèle (la forme la plus probable pour un LLM)
    "    M = context.odoo.env['helpdesk.ticket']\n    context.n = M.search_count([])\n",
    "    M = context.odoo.env['helpdesk.ticket']\n    context.n = len(M.search([]))\n",
])
def test_GARDE_les_formes_de_recomptage_sont_refusees(tmp_path, corps):
    code = _ENTETE + "@then('je compte')\ndef s(context):\n" + corps
    resultat = _ecrire(tmp_path, code)

    assert resultat.ok is False
    assert "COMPTAGE_INTERDIT" in resultat.observation
    assert "est enregistré pour comparaison" in resultat.observation
    assert not (tmp_path / "m_steps.py").exists(), "rien ne doit être écrit sur le disque"


def test_un_fichier_qui_ne_compte_pas_est_accepte(tmp_path):
    code = _ENTETE + (
        "@then('le ticket existe')\n"
        "def s(context):\n"
        "    rows = context.odoo.env['helpdesk.ticket'].read([context.last_record_ids[0]], ['name'])\n"
        "    assert rows[0]['name']\n")

    assert _ecrire(tmp_path, code).ok is True


def test_un_len_sans_rapport_avec_le_rpc_est_accepte(tmp_path):
    """Pas de faux positif : `len()` d'une liste locale ou d'un texte n'est pas un comptage."""
    code = _ENTETE + (
        "@then('le titre est court')\n"
        "def s(context):\n"
        "    titre = context.page.inner_text('h1')\n"
        "    assert len(titre) < 80\n"
        "    assert len([1, 2, 3]) == 3\n")

    assert _ecrire(tmp_path, code).ok is True


def test_une_mention_en_commentaire_ou_chaine_ne_declenche_pas(tmp_path):
    code = _ENTETE + (
        "@then('ok')\n"
        "def s(context):\n"
        "    # ne pas appeler context.odoo.env[m].search_count([]) ici\n"
        "    message = \"search_count([]) est interdit\"\n"
        "    assert message\n")

    assert _ecrire(tmp_path, code).ok is True


def test_le_message_de_refus_ne_recommande_plus_search_count():
    source = Path("src/testpilot/generation/tools/write.py").read_text(encoding="utf-8")
    bloc = source.split("TRANSPORT_INTERDIT")[1].split("COMPTAGE_INTERDIT")[0]

    assert "search_count" not in bloc, "le message de refus ne doit pas encourager le motif refusé"


def test_le_prompt_ne_recommande_plus_search_count_comme_exemple():
    prompt = Path("src/testpilot/generation/prompts/system_prompt.md").read_text(encoding="utf-8")

    assert 'env["model"].search_count([])' not in prompt


def test_limites_documentees_les_contournements_indirects_ne_sont_pas_vus(tmp_path):
    """Verrouille la LIMITE par un test plutôt qu'une doc que personne ne lit : si ce test échoue,
    le garde a gagné une capacité — mettre à jour la docstring de `_forbidden_recount`."""
    code = _ENTETE + (
        "@then('je compte')\n"
        "def s(context):\n"
        "    context.n = sum(1 for _ in context.odoo.env['helpdesk.ticket'].search([]))\n")

    assert _ecrire(tmp_path, code).ok is True
