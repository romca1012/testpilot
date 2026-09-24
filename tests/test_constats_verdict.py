"""Lot 03 (D3) — pas de `conforme` sans un constat EXÉCUTÉ.

Un scénario vert devenait `conforme` même si aucune assertion ne s'était exécutée (assertion dans une
branche non prise, `Alors` qui ne fait qu'attendre). Chaque `constater*` consigne maintenant une ligne
dans un sidecar ; le verdict la lit : vert + 0 constat réussi sous un `Alors` → `indetermine`.

Chaque test prouve les DEUX sens (falsifiabilité) : ≥ 1 constat → `conforme`, 0 → `indetermine`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from testpilot.execution import behave_result
from testpilot.execution.behave_result import (
    BehaveResult,
    BehaveScenario,
    rattacher_constats,
    read_constats,
)
from testpilot.execution.behave_runner import BehaveRunner
from testpilot.execution.executor import ExecutionOutcome
from testpilot.guardrails import repair_circuit  # noqa: F401  (import: le module existe)
from testpilot.verdict import defect_origin as origin
from testpilot.verdict import defect_taxonomy as dt
from testpilot.verdict import status as st

_STEPS_LIB = Path(__file__).resolve().parent.parent / "behave_runtime" / "steps_library"
sys.path.insert(0, str(_STEPS_LIB))


def _outcome(scenarios, dry_ok=True):
    reel = BehaveResult(success=True, returncode=0, scenarios=scenarios)
    return ExecutionOutcome(module_name="m", dry_run_passed=dry_ok, real_run=reel)


def _scenario(nom="[Nominal]", constats=None):
    return BehaveScenario(nom, "passed", constats_reussis=constats)


# ── La règle D3 ─────────────────────────────────────────────────────────────────────────────

def test_vert_sans_aucun_constat_est_indetermine_jamais_conforme():
    v = st.derive_verdict(_outcome([_scenario(constats=0)]))

    assert (v.execution_status, v.functional_status) == (st.EXEC_SUCCESS, st.FUNC_INDETERMINE)
    assert v.scenarios[0].cause_category == dt.AUCUN_CONSTAT
    assert st.statut_de_test(v.execution_status, v.functional_status) == st.STATUT_RETEST
    assert dt.LABELS[dt.AUCUN_CONSTAT] == "Aucune vérification exécutée"


def test_vert_avec_au_moins_un_constat_reussi_est_conforme():
    v = st.derive_verdict(_outcome([_scenario(constats=1)]))

    assert (v.execution_status, v.functional_status) == (st.EXEC_SUCCESS, st.FUNC_CONFORME)
    assert v.scenarios[0].cause_category == ""


def test_sans_mecanisme_de_constat_le_comportement_historique_est_inchange():
    """`None` = dry-run, résultat construit à la main, exécution antérieure au lot : D3 ne s'applique
    pas (sinon toute l'historique et tous les tests du dépôt basculeraient)."""
    v = st.derive_verdict(_outcome([_scenario(constats=None)]))

    assert v.functional_status == st.FUNC_CONFORME


def test_un_scenario_sans_constat_empeche_le_conforme_du_cas_meme_si_un_autre_constate():
    v = st.derive_verdict(_outcome([_scenario("[Nominal]", 2), _scenario("[Erreur]", 0)]))

    assert (v.execution_status, v.functional_status) == (st.EXEC_SUCCESS, st.FUNC_INDETERMINE)
    assert v.scenarios_passed == 1


def test_un_constat_ne_masque_jamais_un_echec_et_un_echec_reste_un_echec():
    echoue = BehaveScenario("[Erreur]", "failed", error="ASSERT FAILED", constats_reussis=0)
    from testpilot.execution.behave_result import BehaveFailure

    v = st.derive_verdict(ExecutionOutcome(
        module_name="m", dry_run_passed=True,
        real_run=BehaveResult(success=False, returncode=1, scenarios=[echoue, _scenario(constats=0)],
                              failures=[BehaveFailure("[Erreur]", "", "assertion", "",
                                                      raw="ASSERT FAILED: x", step_type="then")])))

    assert v.functional_status == st.FUNC_NON_CONFORME, "un vrai constat d'échec surface toujours"


def test_la_cause_aucun_constat_n_est_jamais_reparee_automatiquement():
    assert origin._ORIGIN_BY_CAUSE[dt.AUCUN_CONSTAT] == origin.INDETERMINE
    assert dt.AUCUN_CONSTAT in dt.CATEGORIES


# ── Le sidecar, lu par le runner ────────────────────────────────────────────────────────────

def _ligne(scenario, step_type, ok):
    return json.dumps({"scenario": scenario, "step_type": step_type, "ok": ok})


def test_read_constats_saute_une_ligne_illisible_et_rend_vide_sans_fichier(tmp_path):
    fichier = tmp_path / "c.jsonl"
    fichier.write_text(_ligne("s", "then", True) + "\nn'importe quoi\n" + _ligne("s", "then", False) + "\n",
                       encoding="utf-8")

    assert [c["ok"] for c in read_constats(fichier)] == [True, False]
    assert read_constats(tmp_path / "absent.jsonl") == []


def test_seuls_les_constats_reussis_sous_un_alors_comptent_par_scenario():
    resultat = BehaveResult(success=True, returncode=0, scenarios=[
        BehaveScenario("A", "passed"), BehaveScenario("B", "passed"), BehaveScenario("C", "passed")])
    constats = [
        {"scenario": "A", "step_type": "then", "ok": True},
        {"scenario": "A", "step_type": "then", "ok": True},
        {"scenario": "A", "step_type": "then", "ok": False},   # un échec ne compte pas
        {"scenario": "B", "step_type": "given", "ok": True},   # hors Alors : ne compte pas
        {"scenario": "B", "step_type": "when", "ok": True},
        {"scenario": "C", "step_type": "", "ok": True},        # type inconnu : côté prudent
    ]

    rattacher_constats(resultat, constats)

    assert [s.constats_reussis for s in resultat.scenarios] == [2, 0, 0]
    assert resultat.constats == constats


def test_run_reel_sans_aucune_ligne_donne_zero_et_non_none():
    resultat = BehaveResult(success=True, returncode=0, scenarios=[BehaveScenario("A", "passed")])

    rattacher_constats(resultat, [])

    assert resultat.scenarios[0].constats_reussis == 0
    assert st.derive_verdict(_outcome(resultat.scenarios)).functional_status == st.FUNC_INDETERMINE


def test_le_runner_designe_le_sidecar_et_les_deux_noms_concordent(tmp_path):
    import _base_helpers as helpers

    env = BehaveRunner()._subprocess_env(tmp_path)

    assert behave_result.CONSTATS_FILE_ENV == helpers.CONSTATS_FILE_ENV
    assert env[behave_result.CONSTATS_FILE_ENV] == str(tmp_path / behave_result.CONSTATS_FILENAME)


# ── La note déterministe (jamais confiée au LLM) ────────────────────────────────────────────

def test_l_explication_dit_qu_aucune_verification_ne_s_est_executee():
    from testpilot.verdict import explication

    assert "aucune vérification" in explication._NOTE_AUCUN_CONSTAT.lower()
    assert "pas une preuve" in explication._NOTE_AUCUN_CONSTAT


@pytest.mark.parametrize("valeur", ["indetermine"])
def test_l_axe_fonctionnel_reste_dans_ses_valeurs_connues(valeur):
    """Aucune nouvelle valeur d'enum : `aucun_constat` est une CAUSE, pas un statut (pas de migration)."""
    assert st.FUNC_INDETERMINE == valeur


def test_un_scenario_aucun_constat_n_ouvre_aucune_boucle_de_reparation_payante():
    """Un vert sans constat ne produit AUCUN échec Behave : le circuit de réparation n'a rien à réparer
    (`evaluate` ne poursuit jamais sans échec). Le coût des « Retest » transitoires (D3) ne se double donc
    pas d'une réparation automatique."""
    from testpilot.guardrails.repair_circuit import CircuitState, evaluate

    v = st.derive_verdict(_outcome([_scenario(constats=0)]))
    assert v.scenarios[0].cause_category == dt.AUCUN_CONSTAT
    assert _outcome([_scenario(constats=0)]).real_run.failures == []

    decision = evaluate(CircuitState(max_iterations=5, stall_limit=3), [])

    assert decision.should_continue is False
