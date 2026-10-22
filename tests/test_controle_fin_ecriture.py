"""Étape 2 du plan unique (A61, A63 — porteur, 2026-10-20) : le contrôle de fin d'écriture.

Quand le test passe la vérification à blanc, ses points de vigilance — le MÊME calcul que sur la version enregistrée — sont
renvoyés à l'IA, qui les corrige avant de rendre la main (deux fois au plus). Si elle garde son test, il est livré BLOQUÉ, et
aucune correction d'après-coup ne repasse sur ces points. Interrupteur éteint par défaut (change ce que l'API reçoit) :
éteint, la boucle est exactement celle d'avant.
"""

from __future__ import annotations

import json

import pytest

from testpilot import config
from testpilot.analysis.plan import ScenarioIntent, TestPlan
from testpilot.api.services import generation_service as service
from testpilot.generation import interrupteurs
from testpilot.generation.agent import GenerationAgent
from testpilot.guardrails.cost_tracker import CostTracker
from testpilot.llm.adapter import LLMResponse, ToolUseBlock
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, ReviewRepo, VersionRepo
from testpilot.verdict.review_gate import evaluate_gate

# Le point choisi n'est PAS refusé à l'écriture (une vérification vide l'est déjà) : un champ saisi sans avoir été vu.
SAISIE = ('# language: fr\nFonctionnalité: Démo\n  Scénario: ok\n'
          '    Quand je renseigne le champ "age" avec la valeur "17"\n')
SANS_SAISIE = "# language: fr\nFonctionnalité: Démo\n  Scénario: ok\n    Quand je fais l'action\n"
STEPS = ('from behave import when\n\n\n@when(\'je renseigne le champ "{champ}" avec la valeur "{valeur}"\')\n'
         'def step_saisie(context, champ, valeur):\n    context.saisi = valeur\n\n\n'
         '@when("je fais l\'action")\ndef step_action(context):\n    context.fait = True\n')
MARQUE = "[contrôle de fin d'écriture]"
# Le champ « age » n'a été ni vu à l'écran ni relevé par un outil : deux points, tous deux corrigeables en écriture.
AVIS = ["champ_inconnu", "champ_ui_non_verifie"]


class _IA:
    def __init__(self, script):
        self.script, self.recus = list(script), []

    def call_with_tools(self, *, system_prompt, messages, tools, cost_tracker=None, **_):
        self.recus.append(json.dumps(messages[-1], ensure_ascii=False, default=str))
        return self.script[min(len(self.recus) - 1, len(self.script) - 1)], None


class _DR:
    success, undefined_steps, ambiguous_steps = True, [], []


class _DryRunner:
    def dry_run(self, module_name):
        return _DR()


def _ecrit(feature):
    return LLMResponse(stop_reason="tool_use", tool_calls=[
        ToolUseBlock(id="f", name="write_feature_file", input={"content": feature}),
        ToolUseBlock(id="s", name="write_steps_file", input={"content": STEPS})])


FIN = LLMResponse(stop_reason="end_turn", text_blocks=["fini"])


def _plan():
    return TestPlan(module_name="demo", models=[], scenarios=[ScenarioIntent(name="ok", type="nominal", action="a",
                                                                               persona="u")],
                    personas=["u"], portal_routes=[], risks=[], raw_spec="spec")


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "GENERATED_DIR", tmp_path / "gen")
    monkeypatch.setattr(config, "STEPS_LIBRARY_DIR", tmp_path / "steps_lib")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "controle.db")
    (tmp_path / "steps_lib").mkdir()
    c = get_initialized_db()
    yield c
    c.close()


def _generer(conn, script, *, allume=True, monkeypatch):
    monkeypatch.setenv(interrupteurs.ENV_CONTROLE_FIN_ECRITURE, "1" if allume else "")
    ia = _IA(script)
    agent = GenerationAgent(llm=ia, dry_runner=_DryRunner(), cost_tracker=CostTracker(limit_usd=2.0),
                            case_repo=CaseRepo(conn), version_repo=VersionRepo(conn), max_iterations=8, stall_limit=3)
    return agent.generate(_plan(), title="Démo", author="qa"), ia


def test_eteint_la_boucle_est_celle_d_avant(conn, monkeypatch):
    resultat, ia = _generer(conn, [_ecrit(SAISIE), FIN], allume=False, monkeypatch=monkeypatch)
    assert resultat.success and resultat.feature_content == SAISIE
    assert len(ia.recus) == 1, "clos dès la vérification à blanc"
    assert "controle_fin_ecriture" not in resultat.generation_provenance


def test_falsifiable_l_ia_recoit_les_points_et_les_corrige_avant_de_rendre_la_main(conn, monkeypatch):
    resultat, ia = _generer(conn, [_ecrit(SAISIE), _ecrit(SANS_SAISIE), FIN], monkeypatch=monkeypatch)
    assert MARQUE in ia.recus[1] and "champ_ui_non_verifie" in ia.recus[1]
    assert resultat.success and resultat.feature_content == SANS_SAISIE
    controle = resultat.generation_provenance["controle_fin_ecriture"]
    assert controle == {"tours": 1, "avis_envoyes": AVIS, "avis_restants": []}
    service._finaliser_version_generee(conn, resultat.case_id, resultat.version_id)
    assert evaluate_gate(ReviewRepo(conn), resultat.version_id).allowed, "propre : prête à lancer"


def test_falsifiable_si_l_ia_garde_son_test_la_reparation_est_tentee_puis_le_test_n_est_pas_livre(conn, monkeypatch):
    """Porteur, 2026-10-22 (remplace « livré bloqué sans correction de plus ») : même un point déjà vu à l'écriture passe
    par la réparation bornée ; sans réparation sûre, le test n'est pas livré — jamais un cas bloqué."""
    from testpilot.generation import correction_agent

    resultat, _ = _generer(conn, [_ecrit(SAISIE), FIN], monkeypatch=monkeypatch)
    assert resultat.success and resultat.feature_content == SAISIE
    assert resultat.generation_provenance["controle_fin_ecriture"]["avis_restants"] == AVIS
    appels = []

    def rien(**kw):
        appels.append(kw)
        return correction_agent.CorrectionProposal(changed=False, stopped_reason="incomplete")
    monkeypatch.setattr("testpilot.generation.correction_agent.propose_correction", rien)
    service._finaliser_version_generee(conn, resultat.case_id, resultat.version_id, module_name="demo",
                                       dry_runner=_DryRunner())
    assert len(appels) == service.REPARATIONS_MAX
    assert not evaluate_gate(ReviewRepo(conn), resultat.version_id).allowed, "le test fautif n'est jamais approuvé"
    courante = VersionRepo(conn).get(CaseRepo(conn).get(resultat.case_id)["current_version_id"])
    assert courante["feature_content"] == "" and courante["change_summary"].startswith(service.TEST_NON_LIVRE)


def test_le_nombre_de_tours_est_borne(conn, monkeypatch):
    resultat, ia = _generer(conn, [_ecrit(SAISIE)], monkeypatch=monkeypatch)
    assert resultat.success and resultat.generation_provenance["controle_fin_ecriture"]["tours"] == 2
    assert sum(MARQUE in m for m in ia.recus) == 2


def test_falsifiable_meme_calcul_pendant_l_ecriture_et_sur_la_version_enregistree(conn, monkeypatch):
    resultat, _ = _generer(conn, [_ecrit(SAISIE), FIN], monkeypatch=monkeypatch)
    cas = CaseRepo(conn).get(resultat.case_id)
    sur_la_version = {w["kind"] for w in service.lint_warnings_for_version(
        conn, cas, VersionRepo(conn).list_for_case(resultat.case_id), resultat.version_id)}
    assert sur_la_version == set(AVIS)
    assert set(resultat.generation_provenance["controle_fin_ecriture"]["avis_restants"]) == sur_la_version


# ── Revue de l'étape 2 (B1) : pendant le contrôle, ce que le test VÉRIFIE est gelé ─────────────────────────────────────

AVEC_ALORS = SAISIE + '    Alors le message "Vous devez avoir 18 ans" est affiché\n'
AFFAIBLI = SAISIE + "    Alors une erreur est affichée\n"
STEPS_ALORS = STEPS.replace("from behave import when", "from behave import then, when\nfrom _base_helpers import constater") + (
    "\n\n@then('le message \"{texte}\" est affiché')\ndef step_message(context, texte):\n"
    "    constater(texte in context.page.content(), 'message')\n")
STEPS_AFFAIBLI = STEPS.replace("from behave import when", "from behave import then, when\nfrom _base_helpers import constater") + (
    "\n\n@then('une erreur est affichée')\ndef step_erreur(context):\n"
    "    constater(context.page.title() != '', 'erreur')\n")


def _ecrit_avec(feature, steps):
    return LLMResponse(stop_reason="tool_use", tool_calls=[
        ToolUseBlock(id="f", name="write_feature_file", input={"content": feature}),
        ToolUseBlock(id="s", name="write_steps_file", input={"content": steps})])


def test_falsifiable_l_ia_ne_peut_pas_faire_taire_un_point_en_affaiblissant_l_alors(conn, monkeypatch):
    """Revue B1 : un message exact remplacé par « une erreur est affichée » passerait au vert sur une application qui
    affiche une AUTRE erreur. Pendant le contrôle, la réécriture est refusée ; le test d'origine est livré bloqué."""
    resultat, ia = _generer(conn, [_ecrit_avec(AVEC_ALORS, STEPS_ALORS), _ecrit_avec(AFFAIBLI, STEPS_AFFAIBLI), FIN],
                            monkeypatch=monkeypatch)
    assert "VERIFICATION_GELEE" in ia.recus[2], "la réécriture qui touche l'« Alors » est refusée"
    assert resultat.success and resultat.feature_content == AVEC_ALORS
    service._finaliser_version_generee(conn, resultat.case_id, resultat.version_id)
    assert not evaluate_gate(ReviewRepo(conn), resultat.version_id).allowed


def test_un_point_a_juger_par_une_personne_n_est_pas_renvoye_a_l_ia(conn, monkeypatch):
    """Revue C4 : « même résultat pour toutes les lignes » peut être légitime ; l'IA ne doit pas être poussée à le changer."""
    from testpilot.generation import agent as agent_mod
    from testpilot.generation.variables_de_test import ALORS_IDENTIQUE

    monkeypatch.setattr("testpilot.generation.avis_du_test.avis_du_test",
                        lambda **kw: [{"kind": ALORS_IDENTIQUE, "step": "", "line": 0, "message": "m"}])
    resultat, ia = _generer(conn, [_ecrit(SAISIE), FIN], monkeypatch=monkeypatch)
    assert not any(MARQUE in m for m in ia.recus) and agent_mod is not None
    assert resultat.generation_provenance["controle_fin_ecriture"]["tours"] == 0
