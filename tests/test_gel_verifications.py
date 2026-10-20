"""Lot VH-03 (V3) — une réparation ne touche JAMAIS à ce qu'un test vérifie (audit et revue du 2026-10-08).

Avant : le gel du `.feature` n'existait que dans le prompt de réparation ; l'agent pouvait réécrire un `Alors`, une valeur
attendue ou une table d'Exemples, et le test « réparé » passait. Ici : refus MÉCANIQUE à l'écriture pendant une réparation, y
compris par les contournements relevés en revue (sélecteur vidé de sa valeur, nouvelle vérification qui l'emporte, constante ou
helper réaffecté, valeur écrite par un `Quand` puis relue). Une correction automatique qui touche une vérification reste
approuvée selon la décision du 2026-09-16 (question D30 ouverte), mais le dit en tête du résumé de sa version.
"""

from __future__ import annotations

import pytest

from testpilot.generation import gel_verifications as gel
from testpilot.generation.tools import ToolContext
from testpilot.generation.tools import write as w

FEATURE = """# language: fr
Fonctionnalité: Panier
  Contexte:
    Soit j'ouvre la page "/produits"
    Alors la page affiche le texte "Produits"

  Scénario: Total TTC
    Quand je clique sur le bouton "Ajouter"
    Alors la page affiche le texte "129,51"
    Et la page affiche le texte "TVA 19,76"

  Plan du scénario: Quantités
    Quand je renseigne le champ "quantite" avec la valeur "<q>"
    Alors la page affiche le texte "<total>"
    Exemples:
      | q | total |
      | 2 | 99,80 |
"""

STEPS = """from behave import given, when, then
from _base_helpers import constater

ATTENDU_MIN = 1

def _lire_total(page):
    return page.locator('#total').inner_text(timeout=5000)

@when('je relève les options')
def step_impl(context):
    context.options = context.page.locator('#options').all_inner_texts()

@when('je clique sur Valider')
def step_impl(context):
    context.page.locator('#valider').click(timeout=5000)

@then('le total vaut "{montant}"')
def step_impl(context, montant):
    constater(_lire_total(context.page) == montant, 'total')

@then('il y a des options')
def step_impl(context):
    constater(len(context.options) >= ATTENDU_MIN, 'options')
"""


# ── .feature ──────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("avant, apres, attendu", [
    ('Alors la page affiche le texte "129,51"', 'Alors la page affiche le texte "130,81"', "vérifications"),
    ('    Et la page affiche le texte "TVA 19,76"\n', "", "vérifications"),
    ("      | 2 | 99,80 |", "      | 2 | 100,00 |", "Exemples"),
    ("Scénario: Total TTC", "Scénario: Total", "disparu"),
    ('    Alors la page affiche le texte "Produits"\n', "", "Contexte"),
])
def test_falsifiable_toucher_a_une_verification_du_feature_est_detecte(avant, apres, attendu):
    ecarts = gel.feature_modifiee(FEATURE, FEATURE.replace(avant, apres))

    assert any(attendu in e for e in ecarts), ecarts


def test_reparer_une_action_du_feature_reste_permis():
    repare = FEATURE.replace('Quand je clique sur le bouton "Ajouter"', 'Quand je clique sur le bouton "Ajouter au panier"')

    assert gel.feature_modifiee(FEATURE, repare) == []


def test_ajouter_un_scenario_reste_permis():
    assert gel.feature_modifiee(FEATURE, FEATURE + "\n  Scénario: Nouveau\n    Alors la page affiche le texte \"x\"\n") == []


# ── _steps.py : contournements relevés en revue ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("avant, apres", [
    # la vérification elle-même
    ("constater(_lire_total(context.page) == montant, 'total')", "constater(True, 'total')"),
    # même un sélecteur ou un délai d'une vérification : il change ce qu'elle prouve
    ("page.locator('#total')", "page.locator('body')"),
    ("inner_text(timeout=5000)", "inner_text(timeout=60000)"),
    # helper, constante de module lue par une vérification
    ("return page.locator('#total').inner_text(timeout=5000)", "return '129,51'"),
    ("ATTENDU_MIN = 1", "ATTENDU_MIN = 0"),
    # valeur écrite par un Quand puis relue par un Alors
    ("context.options = context.page.locator('#options').all_inner_texts()", "context.options = ['x']"),
    # libellé de la vérification
    ("@then('le total vaut \"{montant}\"')", "@then('le total vaut environ \"{montant}\"')"),
])
def test_falsifiable_toucher_a_ce_qui_verifie_est_detecte(avant, apres):
    assert STEPS.count(avant) == 1, avant
    assert gel.steps_modifies(STEPS, STEPS.replace(avant, apres))


def test_falsifiable_une_nouvelle_verification_qui_l_emporterait_est_detectee():
    """Revue : dans Behave, une nouvelle définition placée AVANT l'ancienne gagne — sans `AmbiguousStep`."""
    ajout = STEPS.replace("@then('le total vaut", "@then('le total vaut \"42\"')\ndef step_impl(context):\n"
                          "    constater(True, 'x')\n\n@then('le total vaut", 1)

    assert any("nouvelle vérification" in e for e in gel.steps_modifies(STEPS, ajout))


def test_falsifiable_un_helper_reaffecte_au_niveau_module_est_detecte():
    assert gel.steps_modifies(STEPS, STEPS + "\n_lire_total = lambda page: '129,51'\n")


def test_falsifiable_un_step_decore_par_step_est_gele():
    code = "from behave import step\n@step('le total est bon')\ndef s(context):\n    constater(context.page.title() == 'A', 't')\n"

    assert gel.steps_modifies(code, code.replace("== 'A'", "!= ''"))


def test_reparer_un_step_d_action_reste_permis():
    """Ce que la réparation est là pour faire : corriger l'action d'un `Quand`."""
    repare = STEPS.replace("context.page.locator('#valider').click(timeout=5000)",
                           "context.page.get_by_role('button', name='Valider').click(timeout=15000)")

    assert gel.steps_modifies(STEPS, repare) == []


# ── Branché dans les outils d'écriture (réparation) ───────────────────────────────────────────────────────


def _ctx_reparation(tmp_path):
    return ToolContext(module_name="m", generated_dir=tmp_path, gel_feature=FEATURE, gel_steps=STEPS)


def test_falsifiable_en_reparation_reecrire_un_alors_est_refuse_a_l_ecriture(tmp_path):
    sortie = w.write_feature_file(_ctx_reparation(tmp_path), FEATURE.replace("129,51", "130,81"))

    assert not sortie.ok and "VERIFICATION_GELEE" in sortie.observation


def test_falsifiable_en_reparation_affaiblir_un_constat_est_refuse_a_l_ecriture(tmp_path):
    sortie = w.write_steps_file(_ctx_reparation(tmp_path), STEPS.replace(
        "_lire_total(context.page) == montant", "_lire_total(context.page) != ''"))

    assert not sortie.ok and "VERIFICATION_GELEE" in sortie.observation


def test_en_reparation_corriger_une_action_est_ecrit(tmp_path):
    sortie = w.write_steps_file(_ctx_reparation(tmp_path), STEPS.replace("'#valider'", "'[data-test=valider]'"))

    assert sortie.ok, sortie.observation


def test_hors_reparation_aucun_gel(tmp_path):
    ctx = ToolContext(module_name="m", generated_dir=tmp_path)

    assert w.write_feature_file(ctx, FEATURE.replace("129,51", "130,81")).ok


def test_l_agent_de_reparation_arme_le_gel_avec_la_version_de_reference(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from testpilot.generation import repair_agent

    vus = {}
    monkeypatch.setattr(repair_agent, "run_loop", lambda **k: vus.setdefault("ctx", k["ctx"]))

    repair_agent.propose_fix(module_name="m", scenarios=[], failures=[], steps_content=STEPS, feature_content=FEATURE,
                             llm=SimpleNamespace())

    assert vus["ctx"].gel_feature == FEATURE and vus["ctx"].gel_steps == STEPS


# ── Correction automatique : ce qu'elle change dans la preuve est écrit, visible à la relecture ──────────────


def test_une_correction_qui_touche_une_verification_le_dit_dans_l_historique(tmp_path, monkeypatch):
    from testpilot import config
    from testpilot.api.services import generation_service
    from testpilot.generation import correction_agent
    from testpilot.store.db import get_initialized_db
    from testpilot.store.repositories import CaseRepo, VersionRepo, ensure_default_module

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    conn = get_initialized_db(tmp_path / "a.db")
    tautologie = "from behave import then\n\n\n@then('truc')\ndef s(context):\n    assert True\n"
    mid = ensure_default_module(conn, "m")
    cid = CaseRepo(conn).create(title="C", module_id=mid, feature_slug="c")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="h", feature_content="# f",
                                   steps_content=tautologie)
    CaseRepo(conn).set_current_version(cid, vid)
    corrige = "from behave import then\n\n\n@then('truc')\ndef s(context):\n    assert context.page.title() == 'A'\n"
    monkeypatch.setattr(correction_agent, "propose_correction", lambda **kw: correction_agent.CorrectionProposal(
        changed=True, feature_content=kw["feature_content"], steps_content=corrige, summary="ok", cost_usd=0.0,
        stopped_reason="done"))

    generation_service._finaliser_version_generee(conn, cid, vid, module_name="c", dry_runner=object())

    courante = VersionRepo(conn).get(CaseRepo(conn).get(cid)["current_version_id"])
    assert courante["change_summary"].startswith("[VÉRIFICATIONS MODIFIÉES")
    conn.close()


def test_falsifiable_le_tableau_d_un_alors_est_gele():
    """Étape 3 (revue de l'étape 2, remarque 1) : seul le libellé de l'« Alors » était comparé."""
    from testpilot.generation import gel_verifications as gel

    avant = ("# language: fr\nFonctionnalité: F\n  Scénario: S\n    Alors le panier affiche :\n"
             "      | total  |\n      | 129,51 |\n")
    assert gel.feature_modifiee(avant, avant) == []
    assert gel.feature_modifiee(avant, avant.replace("129,51", "107,93")), "la valeur attendue du tableau a changé"
    texte = avant.replace("      | total  |\n      | 129,51 |\n", '      """\n      Total 129,51\n      """\n')
    assert gel.feature_modifiee(texte, texte.replace("129,51", "107,93")), "le texte joint aussi"
