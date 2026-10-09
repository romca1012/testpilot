"""Lot VH-03 (V5) — un échec sous un « Alors », ou une vérification en échec n'importe où dans le run, n'ouvre jamais la
réparation automatique (audit du 2026-10-08).

Avant : la cause DOMINANTE du run décidait. Un vrai bug « élément absent » sous un `Alors` (message de succès disparu) était
classé `wrong_field_name` → `test_a_reparer`, et la réparation — qui peut changer un sélecteur — pouvait le faire passer en
désignant un autre élément. Et une assertion en échec noyée parmi deux délais dépassés laissait la réparation s'ouvrir.
"""

from __future__ import annotations

from testpilot.execution.behave_result import BehaveFailure
from testpilot.guardrails import repair_circuit as rc


def _echec(step_type: str, raw: str, scenario: str = "S") -> BehaveFailure:
    return BehaveFailure(scenario_name=scenario, step_text="x", failure_type="error", traceback_summary="", raw=raw,
                         step_type=step_type)


_DELAI = "playwright._impl._errors.TimeoutError: Locator.wait_for: Timeout 8000ms exceeded."
_ASSERTION = "ASSERT FAILED: Total attendu 129,51, obtenu 130,81"


def _etat():
    return rc.CircuitState(max_iterations=3, stall_limit=3)


def test_falsifiable_un_element_absent_sous_un_alors_demande_une_decision_humaine():
    decision = rc.evaluate(_etat(), [_echec("then", _DELAI)])

    assert decision.should_continue is False and decision.outcome == rc.NEEDS_CONFIRMATION


def test_un_element_absent_sous_un_quand_reste_reparable():
    """Sens inverse : un sélecteur faux dans une ACTION reste le cas normal de la réparation."""
    decision = rc.evaluate(_etat(), [_echec("when", _DELAI)])

    assert decision.should_continue is True and decision.outcome == rc.CONTINUE


def test_falsifiable_une_assertion_en_echec_arrete_meme_si_la_cause_dominante_est_technique():
    echecs = [_echec("when", _DELAI, "A"), _echec("when", _DELAI, "B"), _echec("then", _ASSERTION, "C")]

    decision = rc.evaluate(_etat(), echecs)

    assert decision.should_continue is False and decision.outcome == rc.REAL_BUG
