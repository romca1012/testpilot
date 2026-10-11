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

    assert not sortie.ok and any(refus in sortie.observation for refus in ("context.oracle", "nom privé", "_executer_oracle")), \
        sortie.observation


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


def test_falsifiable_l_alias_du_module_ne_donne_pas_acces_a_l_oracle(tmp_path):
    """Contre-relecture : `import _base_helpers as H` puis `H._executer_oracle(...)` passait la garde des imports privés."""
    code = ("import _base_helpers as H\nfrom behave import then\n\n\n@then('x')\ndef v(context):\n"
            "    H.constater(H._executer_oracle(context, 'etat') == context.page.title(), 'n')\n")

    sortie = w.write_steps_file(_ctx(tmp_path), code)

    assert not sortie.ok and "MECANISME_RESERVE" in sortie.observation, sortie.observation


@pytest.mark.parametrize("jeton", ["{relevé:numero}", "{releve:numero}", "{Relevé : numero}", "{ RELEVE:n }"])
def test_falsifiable_le_gabarit_de_releve_retire_est_refuse_a_l_ecriture(tmp_path, jeton):
    """Le gabarit `{relevé:nom}` a été retiré après deux relectures. Écrit quand même, il ne serait plus qu'un texte : « la page
    n'affiche pas "{relevé:numero}" » serait toujours vraie (troisième relecture)."""
    assert not hasattr(w, "_releves_fautifs")
    sortie = w.write_feature_file(ToolContext("demo", tmp_path), _FEATURE.format(texte=jeton))

    assert not sortie.ok and "RELEVE_INCONNU" in sortie.observation and "est la valeur affichée pour" in sortie.observation
    assert not (tmp_path / "demo.feature").exists()


def test_des_accolades_ordinaires_ne_sont_pas_visees(tmp_path):
    assert w.write_feature_file(ToolContext("demo", tmp_path), _FEATURE.format(texte="Bonjour {prenom}, relevé du mois")).ok
