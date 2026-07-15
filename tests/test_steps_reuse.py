"""§6 / décision 0003 — l'agent doit RÉUTILISER la bibliothèque, pas la réinventer.

Deux volets :
- A : on lui MONTRE le catalogue (il ne pouvait pas réutiliser ce qu'il ne voyait pas) ;
- B : on lui REFUSE de réinventer le transport HTTP (le geste qui a tué le premier e2e :
      un helper `requests` vers /web/dataset/call_kw → 404 avant toute vérification).
"""

import ast

import pytest

from testpilot.generation import steps_library
from testpilot.generation.prompt import build_system_prompt
from testpilot.generation.tools import ToolContext
from testpilot.generation.tools.write import _forbidden_transport, write_steps_file

_LIB = '''
from behave import given, when, then

@given('le nombre d\\'enregistrements dans le modèle "{model}" est enregistré pour comparaison')
def s1(context, model):
    pass

@when('je clique sur le bouton "{label}"')
def s2(context, label):
    pass

@then('aucun enregistrement en double avec le champ "{field}" égal à "{value}" '
      'n\\'existe dans le modèle "{model}"')
def s3(context, field, value, model):
    pass
'''


# ── Extraction du catalogue ──────────────────────────────────────────────────
def test_libelle_multiligne_est_extrait_entier():
    """Le libellé écrit en concaténation implicite doit être restitué ENTIER.

    Une regex ne capture que le premier fragment : on montrerait à l'agent un step qui
    n'existe pas, et la détection de collision porterait sur un texte tronqué.
    """
    steps = steps_library.extract_steps(_LIB, source="_generic_steps.py")
    labels = {s.label for s in steps}
    assert ('aucun enregistrement en double avec le champ "{field}" égal à "{value}" '
            'n\'existe dans le modèle "{model}"') in labels


def test_extraction_capture_le_mot_cle_et_la_source():
    steps = steps_library.extract_steps(_LIB, source="_generic_steps.py")
    by_label = {s.label: s for s in steps}
    assert by_label['je clique sur le bouton "{label}"'].keyword == "when"
    assert by_label['je clique sur le bouton "{label}"'].source == "_generic_steps.py"


def test_extraction_tolere_un_code_invalide():
    assert steps_library.extract_steps("def broken(:\n") == []


def test_catalogue_reel_non_vide_et_reserved_coherent():
    """Le catalogue réel et les libellés réservés viennent de la MÊME source."""
    catalogue = steps_library.catalogue()
    assert len(catalogue) > 10, "la bibliothèque partagée doit être détectée"
    assert steps_library.reserved_labels() == frozenset(s.label for s in catalogue)


# ── A : le catalogue est montré à l'agent ────────────────────────────────────
def test_prompt_expose_tous_les_steps_partages():
    catalogue = steps_library.catalogue()
    prompt = build_system_prompt(None, catalogue)
    assert "## Steps partagés disponibles" in prompt
    manquants = [s.label for s in catalogue if s.label not in prompt]
    assert not manquants, f"steps absents du prompt : {manquants[:3]}"


def test_prompt_groupe_par_mot_cle_gherkin():
    section = steps_library.as_prompt_section(steps_library.extract_steps(_LIB))
    assert "### Soit (`@given`)" in section
    assert "### Quand (`@when`)" in section
    assert "### Alors (`@then`)" in section


def test_prompt_sans_catalogue_reste_valide():
    # Bibliothèque absente → pas de section vide parasite.
    prompt = build_system_prompt(None, [])
    assert "## Steps partagés disponibles" not in prompt
    assert len(prompt) > 100


# ── B : le transport réinventé est refusé ────────────────────────────────────
def _check(code: str) -> str:
    return _forbidden_transport(ast.parse(code), code)


def test_import_requests_est_refuse():
    assert "requests" in _check("import requests\n")
    assert "requests" in _check("from requests import Session\n")


def test_urllib_et_httpx_sont_refuses():
    assert _check("import urllib.request\n")
    assert _check("import httpx\n")


def test_endpoint_interne_est_refuse():
    code = 'BASE = "http://x/web/dataset/call_kw"\n'
    assert "/web/dataset" in _check(code)


def test_step_conforme_est_accepte():
    code = (
        "from behave import when\n"
        "@when(u'je fais un truc')\n"
        "def s(context):\n"
        "    context.odoo.env['helpdesk.ticket'].search_count([])\n"
        "    context.page.click('button')\n"
    )
    assert _check(code) == ""


def test_mention_en_commentaire_nest_pas_un_faux_positif():
    """Détection par AST : une mention en commentaire/docstring n'est pas un import."""
    code = (
        "from behave import when\n"
        "# surtout pas de requests ici : on passe par context.odoo\n"
        "@when(u'x')\n"
        "def s(context):\n"
        "    '''httpx et urllib sont interdits'''\n"
        "    pass\n"
    )
    assert _check(code) == ""


def test_write_steps_file_refuse_le_transport_et_guide(tmp_path):
    ctx = ToolContext(module_name="m", generated_dir=tmp_path, reserved_steps=frozenset())
    code = (
        "import requests\n"
        "from behave import given\n"
        "@given(u'le compteur de tickets est enregistre comme baseline')\n"
        "def s(context):\n"
        "    requests.post('http://x/web/dataset/call_kw')\n"
    )
    outcome = write_steps_file(ctx, code)

    assert outcome.ok is False
    assert "TRANSPORT_INTERDIT" in outcome.observation
    assert "context.odoo" in outcome.observation      # le message doit indiquer l'alternative
    assert not (tmp_path / "m_steps.py").exists()      # rien n'est écrit


def test_write_steps_file_detecte_la_collision_sur_libelle_entier(tmp_path):
    """Avec l'extraction AST, un libellé multi-ligne est enfin comparable (la regex le
    tronquait → la collision passait inaperçue)."""
    label = ('aucun enregistrement en double avec le champ "{field}" égal à "{value}" '
             'n\'existe dans le modèle "{model}"')
    ctx = ToolContext(module_name="m", generated_dir=tmp_path, reserved_steps=frozenset({label}))
    code = (
        "from behave import then\n"
        "@then('aucun enregistrement en double avec le champ \"{field}\" égal à \"{value}\" '\n"
        "      'n\\'existe dans le modèle \"{model}\"')\n"
        "def s(context, field, value, model):\n"
        "    pass\n"
    )
    outcome = write_steps_file(ctx, code)
    assert outcome.ok is False
    assert "AmbiguousStep" in outcome.observation


def test_write_steps_file_accepte_un_fichier_valide(tmp_path):
    ctx = ToolContext(module_name="m", generated_dir=tmp_path, reserved_steps=frozenset())
    code = (
        "from behave import when\n"
        "@when(u'je fais une action specifique au module')\n"
        "def s(context):\n"
        "    context.page.click('button')\n"
    )
    outcome = write_steps_file(ctx, code)
    assert outcome.ok is True
    assert (tmp_path / "m_steps.py").exists()
