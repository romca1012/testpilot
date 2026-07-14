"""Tests du pilier execution — sans sous-processus behave réel (validé à l'e2e).

Verrouillent : le parsing de la sortie JSON Behave (statuts, undefined, failure_type),
le détecteur Smart-Run (runnable/stale/absent + spec changée), et l'orchestration de
l'exécuteur (dry bloquant, run réel, retry sur timeout UI).
"""

import json

from testpilot.execution.behave_result import (
    BehaveFailure,
    BehaveResult,
    BehaveScenario,
    parse_behave_json,
)
from testpilot.execution.detector import ABSENT, RUNNABLE, STALE, module_state
from testpilot.execution.executor import Executor


def _behave_json(scenarios):
    return json.dumps([{"keyword": "Feature", "name": "F", "elements": scenarios}])


def _scenario(name, steps, status=None):
    sc = {"type": "scenario", "keyword": "Scenario", "name": name, "steps": steps}
    if status:
        sc["status"] = status
    return sc


def _step(keyword, name, status, error=""):
    res = {"status": status, "duration": 0.1}
    if error:
        res["error_message"] = error
    return {"keyword": keyword, "name": name, "result": res}


# ── Parser ────────────────────────────────────────────────────────────────────
def test_parse_counts_and_scenarios():
    out = _behave_json([
        _scenario("[Nominal] ok", [_step("Quand ", "je fais", "passed")], status="passed"),
        _scenario("[Erreur] ko", [_step("Alors ", "ça échoue", "failed",
                                        "AssertionError: attendu 1")], status="failed"),
    ])
    r = parse_behave_json(out, returncode=1, dry_run=False)
    assert r.passed == 1 and r.failed == 1
    assert len(r.scenarios) == 2
    assert r.failures[0].failure_type == "assertion"
    assert r.scenarios[1].status == "failed"


def test_parse_dry_run_undefined():
    out = _behave_json([_scenario("[Nominal]", [_step("Quand ", "je clique", "undefined")])])
    r = parse_behave_json(out, returncode=1, dry_run=True)
    assert r.undefined_steps == ["Quand je clique"]
    assert r.has_undefined is True


def test_parse_timeout_classified():
    out = _behave_json([_scenario("s", [_step("Quand ", "je vais", "failed",
                                              "TimeoutError: locator not found")])])
    r = parse_behave_json(out, returncode=1, dry_run=False)
    assert r.failures[0].failure_type == "ui_timeout"


def test_parse_empty_json_is_minimal():
    r = parse_behave_json("", returncode=0, dry_run=True)
    assert r.success is True and r.scenarios == []


# ── Détecteur (runner simulé) ────────────────────────────────────────────────
class FakeRunner:
    def __init__(self, dry=None, real=None):
        self._dry = dry
        self._real = real
        self.dry_calls = 0
        self.real_calls = 0

    def dry_run(self, module_name):
        self.dry_calls += 1
        return self._dry

    def real_run(self, module_name):
        self.real_calls += 1
        return self._real.pop(0) if isinstance(self._real, list) else self._real


def _ok_dry():
    return BehaveResult(success=True, returncode=0, dry_run=True,
                        scenarios=[BehaveScenario("s", "passed")])


def test_detector_absent_when_no_feature(tmp_path):
    st = module_state(FakeRunner(), "nope", generated_dir=tmp_path)
    assert st.state == ABSENT


def test_detector_runnable(tmp_path):
    (tmp_path / "m.feature").write_text("# language: fr", encoding="utf-8")
    st = module_state(FakeRunner(dry=_ok_dry()), "m", generated_dir=tmp_path)
    assert st.state == RUNNABLE and st.runnable is True


def test_detector_stale_on_undefined(tmp_path):
    (tmp_path / "m.feature").write_text("x", encoding="utf-8")
    dry = BehaveResult(success=False, returncode=1, dry_run=True, undefined_steps=["Quand X"])
    st = module_state(FakeRunner(dry=dry), "m", generated_dir=tmp_path)
    assert st.state == STALE and st.undefined_steps == ["Quand X"]


def test_detector_stale_on_spec_change(tmp_path):
    from testpilot.analysis.spec_analyzer import spec_hash
    (tmp_path / "m.feature").write_text("x", encoding="utf-8")
    st = module_state(FakeRunner(dry=_ok_dry()), "m", generated_dir=tmp_path,
                      spec_content="nouvelle spec", prev_spec_hash=spec_hash("ancienne spec"))
    assert st.state == STALE and st.spec_changed is True


# ── Exécuteur (runner simulé) ────────────────────────────────────────────────
def test_executor_blocks_on_failed_dry_run():
    dry = BehaveResult(success=False, returncode=1, dry_run=True, undefined_steps=["Quand X"])
    outcome = Executor(FakeRunner(dry=dry)).execute("m")
    assert outcome.dry_run_passed is False and outcome.real_run is None
    assert "non définis" in outcome.error


def test_executor_runs_real_after_green_dry():
    real = BehaveResult(success=True, returncode=0, passed=3)
    outcome = Executor(FakeRunner(dry=_ok_dry(), real=real)).execute("m")
    assert outcome.dry_run_passed is True
    assert outcome.real_run.passed == 3 and outcome.retried is False


def test_executor_retries_once_on_ui_timeout():
    fail = BehaveResult(success=False, returncode=1,
                        failures=[BehaveFailure("s", "je vais", "ui_timeout", "TimeoutError")])
    ok = BehaveResult(success=True, returncode=0, passed=1)
    runner = FakeRunner(dry=_ok_dry(), real=[fail, ok])
    outcome = Executor(runner, max_retries=1).execute("m")
    assert outcome.retried is True
    assert outcome.real_run.success is True and runner.real_calls == 2
