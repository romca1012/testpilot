"""Lot VH-03 (V3) — une réparation corrige OÙ le test lit l'application, jamais CE QU'IL VÉRIFIE (audit du 2026-10-08).

Avant : le gel du `.feature` n'existait que dans le prompt de réparation ; l'agent pouvait réécrire un `Alors`, une valeur
attendue ou une table d'Exemples, et le test « réparé » passait. Ici : refus MÉCANIQUE à l'écriture pendant une réparation,
et une correction automatique qui touche une vérification n'est plus approuvée d'office.
"""

from __future__ import annotations

import pytest

from testpilot.generation import gel_verifications as gel
from testpilot.generation.tools import ToolContext
from testpilot.generation.tools import write as w

FEATURE = """# language: fr
Fonctionnalité: Panier
  Scénario: Total TTC
    Soit j'ouvre la page "/produits"
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

STEPS = """from behave import then
from _base_helpers import constater

def _lire_total(page):
    return page.locator('#total').inner_text(timeout=5000)

@then('le total vaut "{montant}"')
def step_total(context, montant):
    constater(_lire_total(context.page) == montant, 'total')
"""


# ── .feature ──────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("avant, apres, attendu", [
    ('Alors la page affiche le texte "129,51"', 'Alors la page affiche le texte "130,81"', "vérifications"),
    ('    Et la page affiche le texte "TVA 19,76"\n', "", "vérifications"),
    ("      | 2 | 99,80 |", "      | 2 | 100,00 |", "Exemples"),
    ("Scénario: Total TTC", "Scénario: Total", "disparu"),
])
def test_falsifiable_toucher_a_une_verification_du_feature_est_detecte(avant, apres, attendu):
    ecarts = gel.feature_modifiee(FEATURE, FEATURE.replace(avant, apres))

    assert any(attendu in e for e in ecarts), ecarts


def test_reparer_la_navigation_ou_une_action_reste_permis():
    repare = FEATURE.replace('Soit j\'ouvre la page "/produits"', 'Soit j\'ouvre la page "/produits?page=1"').replace(
        'Quand je clique sur le bouton "Ajouter"', 'Quand je clique sur le bouton "Ajouter au panier"')

    assert gel.feature_modifiee(FEATURE, repare) == []


def test_ajouter_un_scenario_reste_permis():
    assert gel.feature_modifiee(FEATURE, FEATURE + "\n  Scénario: Nouveau\n    Alors la page affiche le texte \"x\"\n") == []


# ── _steps.py ─────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("avant, apres", [
    ("constater(_lire_total(context.page) == montant, 'total')", "constater(True, 'total')"),
    ("constater(_lire_total(context.page) == montant, 'total')", "constater(_lire_total(context.page) != '', 'total')"),
    ("return page.locator('#total').inner_text(timeout=5000)", "return montant_attendu"),  # helper appelé par un @then
    ("@then('le total vaut \"{montant}\"')", "@then('le total vaut environ \"{montant}\"')"),
])
def test_falsifiable_toucher_a_une_fonction_qui_verifie_est_detecte(avant, apres):
    assert gel.steps_modifies(STEPS, STEPS.replace(avant, apres))


def test_reparer_un_selecteur_ou_un_delai_reste_permis():
    repare = STEPS.replace("page.locator('#total')", "page.locator('[data-test=total]')").replace(
        "timeout=5000", "timeout=15000")

    assert gel.steps_modifies(STEPS, repare) == []


def test_supprimer_une_fonction_qui_verifie_est_detecte():
    assert any("disparu" in e for e in gel.steps_modifies(STEPS, STEPS.split("@then")[0]))


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


def test_en_reparation_corriger_un_selecteur_est_ecrit(tmp_path):
    sortie = w.write_steps_file(_ctx_reparation(tmp_path), STEPS.replace("'#total'", "'[data-test=total]'"))

    assert sortie.ok, sortie.observation


def test_hors_reparation_aucun_gel(tmp_path):
    ctx = ToolContext(module_name="m", generated_dir=tmp_path)

    assert w.write_feature_file(ctx, FEATURE.replace("129,51", "130,81")).ok


def test_l_agent_de_reparation_arme_le_gel_avec_la_version_de_reference(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from testpilot.generation import repair_agent

    monkeypatch.setattr(repair_agent.config, "GENERATED_DIR", tmp_path)
    (tmp_path / "m.feature").write_text(FEATURE, encoding="utf-8")
    vus = {}
    monkeypatch.setattr(repair_agent, "run_loop", lambda **k: vus.setdefault("ctx", k["ctx"]))

    repair_agent.propose_fix(module_name="m", scenarios=[], failures=[], steps_content=STEPS, llm=SimpleNamespace())

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
