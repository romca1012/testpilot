"""Lot 03 (D4, validée le 2026-09-24) — `write_steps_file` REFUSE les assertions mal placées.

Régime BLOQUANT (dérogation au régime détectif de 0008, cohérente avec F9/lot 11) : l'agent reçoit un
refus déterministe qui dit quoi faire, ce qui coûte moins qu'un run réel raté. Trois refus attendus,
un fichier correct accepté. Le runtime (D3) attrape ce que ce filet statique ne voit pas.
"""

from __future__ import annotations

import pytest

from testpilot.generation.tools import ToolContext
from testpilot.generation.tools import write as write_tools

_ENTETE = "from behave import given, when, then\nfrom _base_helpers import constater, constater_visible\n\n"


def _ecrire(tmp_path, code):
    ctx = ToolContext(module_name="m", generated_dir=tmp_path, connector=None)
    return write_tools.write_steps_file(ctx, code)


def _refuse(tmp_path, code, *, contient):
    resultat = _ecrire(tmp_path, code)

    assert resultat.ok is False
    assert "ASSERTION_MAL_PLACEE" in resultat.observation
    assert contient in resultat.observation
    assert "constater" in resultat.observation, "le refus dit quoi faire"
    assert not (tmp_path / "m_steps.py").exists(), "rien ne doit être écrit sur le disque"


# ── Refus 1 : assertion dans un @given / @when ──────────────────────────────────────────────

@pytest.mark.parametrize("decorateur", ["given", "when", "step"])
@pytest.mark.parametrize("assertion, nom", [
    ("    assert context.x, 'vide'\n", "assert"),
    ("    raise AssertionError('x')\n", "raise AssertionError"),
    ("    expect(context.page.locator('a')).to_be_visible()\n", "expect"),
    ("    constater(context.x, 'vide')\n", "constater"),
])
def test_refus_d_une_assertion_dans_un_given_ou_un_when(tmp_path, decorateur, assertion, nom):
    code = _ENTETE + f"@{decorateur}('je prépare')\ndef s(context):\n{assertion}"

    _refuse(tmp_path, code, contient=nom)


# ── Refus 2 : @then sans constater* ni helper de la bibliothèque ────────────────────────────

def test_refus_d_un_then_sans_aucun_constat(tmp_path):
    code = _ENTETE + "@then('c est bon')\ndef s(context):\n    x = context.page.url\n"

    _refuse(tmp_path, code, contient="n'appelle ni `constater(...)`")


def test_refus_d_un_then_qui_n_a_qu_un_assert_nu(tmp_path):
    """Un `assert` nu ne consignerait aucune ligne : D3 ne le verrait jamais."""
    code = _ENTETE + "@then('c est bon')\ndef s(context):\n    assert 'x' in context.page.url\n"

    _refuse(tmp_path, code, contient="n'appelle ni `constater(...)`")


# ── Refus 3 : except qui avale l'échec ──────────────────────────────────────────────────────

@pytest.mark.parametrize("handler", [
    "    except Exception:\n        pass\n",
    "    except:\n        return\n",
    "    except Exception as exc:\n        print(exc)\n",
    "    except AssertionError:\n        pass\n",
])
def test_refus_d_un_except_large_qui_avale_l_echec_dans_un_then(tmp_path, handler):
    code = _ENTETE + ("@then('c est bon')\ndef s(context):\n    try:\n"
                      "        constater('x' in context.page.url, 'url')\n" + handler)

    _refuse(tmp_path, code, contient="except")


# ── Acceptés : pas de faux positif ──────────────────────────────────────────────────────────

def test_un_fichier_correct_est_accepte(tmp_path):
    code = _ENTETE + (
        "@given('je prépare')\ndef a(context):\n    context.page.goto('/x')\n\n"
        "@when('j agis')\ndef b(context):\n    context.page.click('a')\n\n"
        "@then('la page de succès est affichée')\ndef c(context):\n"
        "    constater('/succes' in context.page.url, 'issue inattendue')\n"
        "    constater_visible(context.page.locator('.ok'), 'pas de message')\n")

    assert _ecrire(tmp_path, code).ok is True


def test_un_then_qui_appelle_un_helper_de_la_bibliotheque_qui_constate_est_accepte(tmp_path):
    code = ("from behave import then\nfrom _base_helpers import validation_error_inline\n\n"
            "@then('une erreur est affichée')\ndef s(context):\n    validation_error_inline(context.page)\n")

    assert _ecrire(tmp_path, code).ok is True


def test_un_helper_de_la_bibliotheque_qui_ne_constate_pas_ne_suffit_pas(tmp_path):
    """`fill_field` agit, il ne constate rien : un `@then` qui n'appelle que lui ne prouve rien."""
    code = ("from behave import then\nfrom _base_helpers import fill_field\n\n"
            "@then('ok')\ndef s(context):\n    fill_field(context.page, 'a', 'b')\n")

    _refuse(tmp_path, code, contient="n'appelle ni `constater(...)`")


def test_un_except_large_qui_releve_est_accepte(tmp_path):
    code = _ENTETE + ("@then('c est bon')\ndef s(context):\n    try:\n"
                      "        constater('x' in context.page.url, 'url')\n"
                      "    except Exception:\n        raise\n")

    assert _ecrire(tmp_path, code).ok is True


def test_un_except_etroit_dans_un_then_est_accepte(tmp_path):
    code = _ENTETE + ("@then('c est bon')\ndef s(context):\n    try:\n        n = int(context.x)\n"
                      "    except ValueError:\n        n = 0\n    constater(n > 0, 'nul')\n")

    assert _ecrire(tmp_path, code).ok is True


def test_le_refus_ne_masque_pas_les_autres_gardes_qui_passent_avant(tmp_path):
    """Le transport interdit reste refusé en premier (ordre inchangé des gardes existantes)."""
    code = "import requests\n" + _ENTETE + "@then('x')\ndef s(context):\n    pass\n"

    resultat = _ecrire(tmp_path, code)

    assert "TRANSPORT_INTERDIT" in resultat.observation


def test_la_liste_des_helpers_qui_constatent_est_lue_dans_la_bibliotheque():
    noms = write_tools._helpers_qui_constatent()

    assert {"constater", "constater_visible", "constater_texte", "validation_error_inline",
            "check_count_increased_by_one", "no_duplicate"} <= noms
    assert "fill_field" not in noms and "wait_form_submission" not in noms
