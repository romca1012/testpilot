"""`repair_agent._failure_report` (lot 09, C9) — ce qu'on transmet à l'agent de réparation.

Deux volets : les paliers de résolution (`field_fallbacks`) AJOUTÉS par ce lot — un fait RUNTIME,
jamais une conclusion ; et la confirmation que la CAUSE classifiée (`defect_taxonomy`) reste
délibérément ABSENTE — décision reconfirmée en écrivant ce lot (cas 6, voir la docstring du
module), pas silencieusement oubliée.
"""

from __future__ import annotations

from testpilot.execution.behave_result import BehaveFailure, BehaveScenario
from testpilot.generation.repair_agent import _failure_report


def test_les_paliers_de_resolution_apparaissent_dans_le_rapport():
    rapport = _failure_report(
        [BehaveScenario("s", "failed")],
        [BehaveFailure("s", "je clique", "ui_timeout", "TimeoutError")],
        field_fallbacks=['champ "email" résolu par repli placeholder (name introuvable)'])

    assert "Champs résolus par repli" in rapport
    assert 'champ "email" résolu par repli placeholder' in rapport


def test_sans_paliers_de_resolution_la_section_est_absente():
    rapport = _failure_report(
        [BehaveScenario("s", "failed")],
        [BehaveFailure("s", "je clique", "ui_timeout", "TimeoutError")],
        field_fallbacks=[])

    assert "Champs résolus par repli" not in rapport


def test_falsifiable_la_cause_classifiee_n_apparait_jamais_dans_le_rapport():
    """Garde de non-régression sur une décision explicitement reconfirmée en écrivant le lot 09 :
    le cas 6 (docstring du module) a montré qu'une conclusion soufflée à l'agent l'enferme sur une
    fausse piste. Si ce test échoue, quelqu'un a réintroduit la cause dans le prompt de
    réparation — à rediscuter, pas à corriger en silence."""
    rapport = _failure_report(
        [BehaveScenario("s", "failed")],
        [BehaveFailure("s", "je clique", "ui_timeout",
                       "PreconditionNonRemplieError: environnement absent", step_type="hook")])

    for mot_interdit in ("precondition_non_remplie", "cause :", "cause:", "diagnostic"):
        assert mot_interdit not in rapport.lower()
