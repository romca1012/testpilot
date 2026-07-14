"""§5 asymétrique — origine du défaut et régime de confirmation humaine.

« test à réparer » et « indéterminé » exigent une confirmation humaine ; « vrai bug »
se remonte directement (faux positif acceptable, faux négatif inacceptable).
"""

from testpilot.execution.behave_result import BehaveFailure
from testpilot.verdict import defect_origin as do
from testpilot.verdict import defect_taxonomy as dt


def test_business_assertion_is_direct_bug_no_confirmation():
    origin = do.classify_defect_origin(dt.ASSERTION_MISMATCH)
    assert origin == do.VRAI_BUG
    assert do.confirmation_for(origin) == do.NOT_REQUIRED


def test_technical_cause_needs_human_confirmation():
    for cause in (dt.WRONG_NAVIGATION, dt.WRONG_FIELD_NAME, dt.MISSING_ROLE,
                  dt.MISSING_SERVER_CONTEXT):
        origin = do.classify_defect_origin(cause)
        assert origin == do.TEST_A_REPARER
        assert do.confirmation_for(origin) == do.PENDING_HUMAN


def test_unknown_defaults_to_confirmation():
    origin = do.classify_defect_origin(dt.UNKNOWN)
    assert origin == do.INDETERMINE
    assert do.confirmation_for(origin) == do.PENDING_HUMAN


def test_diagnose_timeout_run_is_test_to_repair_pending():
    failures = [BehaveFailure("s", "je clique", "ui_timeout", "TimeoutError: locator")]
    verdict = do.diagnose(failures)
    assert verdict.defect_origin == do.TEST_A_REPARER
    assert verdict.requires_human_confirmation is True


def test_diagnose_assertion_run_is_direct_bug():
    failures = [BehaveFailure("s", "le total", "assertion", "AssertionError: attendu 0")]
    verdict = do.diagnose(failures)
    assert verdict.defect_origin == do.VRAI_BUG
    assert verdict.requires_human_confirmation is False


def test_diagnose_no_failures_returns_none():
    assert do.diagnose([]) is None
