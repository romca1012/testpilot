"""Lot VH-06 — deux gardes d'écriture désignées par la campagne base-5 (2026-10-10).

1. `client_creation_valide` (base-4 essai 2, base-5 essai 1) : le Gherkin portait la séquence d'échappement d'un caractère au lieu
   du caractère — texte introuvable à l'écran, `non_conforme` sur l'application saine (faux rouge).
2. `commande_persistance_serveur` (base-5, 3 essais sur 3) : l'oracle interrogé à la main — un faux rouge et deux erreurs du test.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from testpilot.generation import litteraux_observes as lo
from testpilot.generation.tools import ToolContext
from testpilot.generation.tools import write as w

RACINE = Path(__file__).resolve().parent.parent
BARRE = chr(92)  # écrite ainsi pour rester littérale : dans une chaîne Python, la séquence serait décodée en caractère

_FEATURE = """# language: fr
Fonctionnalité: Clients

  Scénario: Création
    Soit j'ouvre la page "/clients"
    Alors la page affiche "{texte}"
"""

_STEPS = """from behave import then
from _base_helpers import constater


@then('la commande est enregistrée')
def verifier(context):
{corps}
"""


def _ctx(tmp_path):
    ctx = ToolContext("demo", tmp_path)
    lo.brancher_controles(ctx, "web", None, RACINE / "behave_runtime")
    return ctx


def test_un_gherkin_qui_porte_la_sequence_au_lieu_du_caractere_est_refuse(tmp_path):
    sortie = w.write_feature_file(ToolContext("demo", tmp_path),
                                  _FEATURE.format(texte=f"{BARRE}u00ab{BARRE}u00a0Dupont SARL{BARRE}u00a0{BARRE}u00bb"))

    assert not sortie.ok and "ECHAPPEMENT_LITTERAL" in sortie.observation
    assert f"{BARRE}u00ab" in sortie.observation, "le refus cite la séquence fautive"
    assert not (tmp_path / "demo.feature").exists(), "rien n'est écrit sur un refus"


def test_falsifiable_le_caractere_lui_meme_et_une_barre_sans_code_passent(tmp_path):
    assert w.write_feature_file(ToolContext("demo", tmp_path), _FEATURE.format(texte="«\u00a0Dupont SARL\u00a0»")).ok
    assert w.write_feature_file(ToolContext("demo", tmp_path), _FEATURE.format(texte=f"C:{BARRE}utilisateurs")).ok


@pytest.mark.parametrize("corps", [
    "    reponse = context.oracle.executer('etat')\n    constater(reponse['numero'] == context.page.title(), 'numéro')",
    "    constater(context.oracle('etat')['numero'] == context.page.title(), 'numéro')",
    "    oracle = getattr(context, 'oracle')\n    constater(oracle.executer('etat') == context.page.title(), 'numéro')",
    "    constater(not context.oracle_erreur and context.page.title() == 'A', 'oracle')",
])
def test_l_oracle_interroge_a_la_main_est_refuse(tmp_path, corps):
    sortie = w.write_steps_file(_ctx(tmp_path), _STEPS.format(corps=corps))

    assert not sortie.ok and "LITTERAL_NON_OBSERVE" in sortie.observation
    assert "context.oracle" in sortie.observation and "de l'oracle" in sortie.observation, "le refus nomme les steps à utiliser"


def test_falsifiable_un_step_qui_ne_touche_pas_a_l_oracle_passe(tmp_path):
    sortie = w.write_steps_file(_ctx(tmp_path), _STEPS.format(corps="    constater(context.page.title() == 'A', 'titre')"))

    assert sortie.ok, sortie.observation


@pytest.mark.parametrize("code", [
    "from behave import then\nfrom _base_helpers import constater\n\n\n@then('x')\ndef v(context):\n    ctx = context\n"
    "    constater(ctx.oracle.executer('etat') == context.page.title(), 'n')\n",
    "from behave import then\nfrom _base_helpers import constater\n\n\ndef _aide(c):\n    return c.oracle.executer('etat')\n\n\n"
    "@then('x')\ndef v(context):\n    constater(_aide(context) == context.page.title(), 'n')\n",
    "from behave import then\nfrom _base_helpers import constater\n\nlire = lambda c: c.oracle\n\n\n"
    "@then('x')\ndef v(context):\n    constater(lire(context) == context.page.title(), 'n')\n",
    "from behave import then\nfrom _base_helpers import constater, _executer_oracle\n\n\n"
    "@then('x')\ndef v(context):\n    constater(_executer_oracle(context, 'etat') == context.page.title(), 'n')\n",
])
def test_falsifiable_les_contournements_de_la_garde_d_oracle_sont_refuses(tmp_path, code):
    """Relecture, reproduit : un alias de `context`, une fonction d'aide, une lambda, un import privé passaient."""
    sortie = w.write_steps_file(_ctx(tmp_path), code)

    assert not sortie.ok and ("context.oracle" in sortie.observation or "nom privé" in sortie.observation), sortie.observation


def test_une_variable_locale_nommee_oracle_n_est_pas_visee(tmp_path):
    sortie = w.write_steps_file(_ctx(tmp_path), _STEPS.format(
        corps="    oracle = context.page.title()\n    constater(oracle == 'A', 'titre')"))

    assert sortie.ok, sortie.observation


@pytest.mark.parametrize("ligne", [
    f'    # le texte source portait {BARRE}u00ab',
    f'    Alors la page affiche un texte de la forme "FAC-{BARRE}u00e9[0-9]{{4}}"',
])
def test_la_garde_d_echappement_ne_vise_ni_un_commentaire_ni_un_motif(tmp_path, ligne):
    """Relecture : faux refus sur un commentaire Gherkin et sur le motif d'une expression régulière, où la séquence est valide."""
    sortie = w.write_feature_file(ToolContext("demo", tmp_path), _FEATURE.format(texte="Bonjour") + ligne + "\n")

    assert "ECHAPPEMENT_LITTERAL" not in sortie.observation, sortie.observation


# ── `{relevé:nom}` : bien écrit, et relevé avant d'être cité ──────────────────────────────────────────────

_AVEC_RELEVE = """# language: fr
Fonctionnalité: Dossiers

  Scénario: Le dossier créé apparaît dans la liste
    Soit j'ouvre la page "/confirmation"
{avant}
    Quand je clique sur le bouton "Mes dossiers"
    Alors la page affiche le texte "{jeton}"
"""
_RELEVE = '    Quand je relève la valeur affichée pour "Numéro" comme "numero"'


@pytest.mark.parametrize("avant, jeton", [
    (_RELEVE, "{releve:numero}"), (_RELEVE, "{Relevé:numero}"), (_RELEVE, "{relevé : numero}"),   # mal écrit
    (_RELEVE, "{relevé:num}"),                                                                     # autre nom
    ('    Quand je clique sur le bouton "Suite"', "{relevé:numero}"),                              # jamais relevé
])
def test_falsifiable_un_releve_mal_ecrit_ou_jamais_fait_est_refuse_a_l_ecriture(tmp_path, avant, jeton):
    """Relecture, reproduit : `{releve:numero}` restait tel quel — « la page n'affiche pas "{releve:numero}" » sortait `conforme`."""
    sortie = w.write_feature_file(ToolContext("demo", tmp_path), _AVEC_RELEVE.format(avant=avant, jeton=jeton))

    assert not sortie.ok and "RELEVE_INVALIDE" in sortie.observation
    assert not (tmp_path / "demo.feature").exists()


def test_un_releve_bien_ecrit_et_fait_avant_passe_et_ne_vaut_pas_pour_le_scenario_suivant(tmp_path):
    bon = _AVEC_RELEVE.format(avant=_RELEVE, jeton="{relevé:numero}")
    assert w.write_feature_file(ToolContext("demo", tmp_path), bon).ok

    suivant = bon + """
  Scénario: Un autre
    Soit j'ouvre la page "/liste"
    Alors la page affiche le texte "{relevé:numero}"
"""
    sortie = w.write_feature_file(ToolContext("demo", tmp_path), suivant)
    assert not sortie.ok and "RELEVE_INVALIDE" in sortie.observation and "ligne 12" in sortie.observation


def test_falsifiable_un_step_genere_ne_pose_pas_lui_meme_un_releve(tmp_path):
    """Relecture : `context.releves = {"total": "999,99 €"}` dans un `@given` était accepté — le relecteur voyait
    `{relevé:total}` sans voir d'où venait la valeur."""
    code = ("from behave import given\n\n\n@given('un total connu')\ndef poser(context):\n"
            "    context._tp_releves = {'total': ('999,99 €', 0)}\n")

    sortie = w.write_steps_file(_ctx(tmp_path), code)

    assert not sortie.ok and "MECANISME_RESERVE" in sortie.observation
