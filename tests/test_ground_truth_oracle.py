"""Lot 07e (C5, D7) — `ground_truth` passe à `backend_verified` sur le connecteur `web` SEULEMENT
si un constat d'oracle a tourné (réussi OU échoué) sous un `Alors` — jamais par défaut, jamais
parce que l'agent le prétend (le signal vient du sidecar des constats, lot 03, pas du texte).
"""

from __future__ import annotations

from testpilot.execution.behave_result import BehaveResult, BehaveScenario, rattacher_constats
from testpilot.verdict.status import (
    GROUND_TRUTH_BACKEND_VERIFIED,
    GROUND_TRUTH_UI_ONLY,
    aggregate,
    scenario_verdict,
)


def _scenario(nom: str, *, oracle_verifie: bool = False) -> BehaveScenario:
    s = BehaveScenario(nom, "passed", constats_reussis=1)
    s.oracle_verifie = oracle_verifie
    return s


def test_falsifiable_sans_constat_d_oracle_le_web_reste_ui_only():
    verdicts = [scenario_verdict(_scenario("cas nominal"), [])]
    case = aggregate(verdicts, connector_type="web")
    assert case.ground_truth == GROUND_TRUTH_UI_ONLY


def test_un_constat_d_oracle_fait_passer_le_web_en_backend_verified():
    verdicts = [scenario_verdict(_scenario("cas nominal", oracle_verifie=True), [])]
    case = aggregate(verdicts, connector_type="web")
    assert case.ground_truth == GROUND_TRUTH_BACKEND_VERIFIED


def test_falsifiable_un_seul_scenario_sur_plusieurs_ne_suffit_pas():
    """Unanimité, pas majorité (revue du 2026-09-28) : un SEUL scénario recoupé par l'oracle ne peut
    pas prêter `backend_verified` aux AUTRES scénarios du cas, qui ne prouvent que l'UI — même
    convention que `functional_status = conforme`, qui exige TOUS les scénarios conformes."""
    verdicts = [scenario_verdict(_scenario("un"), []),
                scenario_verdict(_scenario("deux", oracle_verifie=True), [])]
    case = aggregate(verdicts, connector_type="web")
    assert case.ground_truth == GROUND_TRUTH_UI_ONLY


def test_tous_les_scenarios_verifies_par_l_oracle_donnent_backend_verified():
    verdicts = [scenario_verdict(_scenario("un", oracle_verifie=True), []),
                scenario_verdict(_scenario("deux", oracle_verifie=True), [])]
    case = aggregate(verdicts, connector_type="web")
    assert case.ground_truth == GROUND_TRUTH_BACKEND_VERIFIED


def test_odoo_reste_backend_verified_avec_ou_sans_oracle():
    """Le RPC d'Odoo donne déjà `backend_verified` — l'oracle n'AJOUTE rien pour ce connecteur."""
    sans_oracle = aggregate([scenario_verdict(_scenario("cas"), [])], connector_type="odoo")
    avec_oracle = aggregate([scenario_verdict(_scenario("cas", oracle_verifie=True), [])], connector_type="odoo")
    assert sans_oracle.ground_truth == avec_oracle.ground_truth == GROUND_TRUTH_BACKEND_VERIFIED


def test_falsifiable_un_constat_d_oracle_echoue_compte_aussi():
    """Un ÉCART trouvé par l'oracle est aussi une preuve qu'il a tourné (« a tourné », pas « a
    réussi ») : le sidecar consigne `ok: False`, mais `rattacher_constats` marque quand même le
    scénario comme vérifié par l'oracle."""
    result = BehaveResult(success=True, returncode=0, scenarios=[BehaveScenario("cas", "failed")])
    constats = [{"scenario": "cas", "step_type": "then", "ok": False, "source": "oracle"}]

    rattacher_constats(result, constats)
    verdict = scenario_verdict(result.scenarios[0], [])
    case = aggregate([verdict], connector_type="web")

    assert result.scenarios[0].oracle_verifie is True
    assert case.ground_truth == GROUND_TRUTH_BACKEND_VERIFIED


def test_rattacher_constats_detecte_un_constat_d_oracle_sous_un_alors():
    """Bout en bout depuis le sidecar RÉEL (lot 03) : `source: "oracle"` sous `then` marque le scénario."""
    result = BehaveResult(success=True, returncode=0, scenarios=[BehaveScenario("cas", "passed")])
    constats = [{"scenario": "cas", "step_type": "then", "ok": True, "source": "oracle"}]

    rattacher_constats(result, constats)

    assert result.scenarios[0].oracle_verifie is True


def test_rattacher_constats_ignore_un_constat_d_oracle_hors_alors():
    """Un constat d'oracle sous un `Quand`/`Soit` (mal placé, ou un futur usage) ne prouve rien
    sur le RÉSULTAT du scénario — même règle que `constats_reussis` (lot 03)."""
    result = BehaveResult(success=True, returncode=0, scenarios=[BehaveScenario("cas", "passed")])
    constats = [{"scenario": "cas", "step_type": "given", "ok": True, "source": "oracle"}]

    rattacher_constats(result, constats)

    assert result.scenarios[0].oracle_verifie is False


def test_rattacher_constats_ignore_un_constat_ordinaire():
    result = BehaveResult(success=True, returncode=0, scenarios=[BehaveScenario("cas", "passed")])
    constats = [{"scenario": "cas", "step_type": "then", "ok": True, "source": ""}]

    rattacher_constats(result, constats)

    assert result.scenarios[0].oracle_verifie is False
