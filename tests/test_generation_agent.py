"""Tests du pilier generation — déterministes, sans réseau (LLM/DryRunner/Connector simulés).

Verrouillent : le chemin nominal (fichiers écrits + hand-off « en attente de relecture »),
et l'activation des trois garde-fous (coût par-run, itérations, stall dry-run), plus le
rejet d'une redéfinition de step partagé.
"""

import pytest

from testpilot import config
from testpilot.analysis.plan import ScenarioIntent, TestPlan
from testpilot.generation.agent import GenerationAgent
from testpilot.generation.tools import ToolContext, write as write_tools
from testpilot.guardrails.cost_tracker import CostTracker
from testpilot.llm.adapter import LLMResponse, ToolUseBlock
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, VersionRepo

_FEATURE = "# language: fr\nFonctionnalité: Démo\n  Scénario: [Nominal] ok\n    Quand je fais l'action\n"
_STEPS = "from behave import when\n\n\n@when(\"je fais l'action\")\ndef step_impl(context):\n    pass\n"


class FakeLLM:
    """Rejoue un script de LLMResponse ; simule le suivi de coût comme le vrai adaptateur."""

    def __init__(self, script, tokens=(10, 10)):
        self.script = list(script)
        self.tokens = tokens
        self.calls = 0

    def call_with_tools(self, *, system_prompt, messages, tools, cost_tracker=None, **_):
        self.calls += 1
        if cost_tracker is not None:
            cost_tracker.track_call(model="claude-sonnet-4-6", input_tokens=self.tokens[0],
                                    output_tokens=self.tokens[1], label="gen")
        resp = self.script[min(self.calls - 1, len(self.script) - 1)]
        return resp, None


class DR:
    def __init__(self, success, undefined=None, ambiguous=None):
        self.success = success
        self.undefined_steps = undefined or []
        self.ambiguous_steps = ambiguous or []


class FakeDryRunner:
    def __init__(self, results):
        self.results = list(results)
        self.calls = 0

    def dry_run(self, module_name):
        self.calls += 1
        return self.results[min(self.calls - 1, len(self.results) - 1)]


def _write_both():
    return LLMResponse(stop_reason="tool_use", tool_calls=[
        ToolUseBlock(id="f", name="write_feature_file", input={"content": _FEATURE}),
        ToolUseBlock(id="s", name="write_steps_file", input={"content": _STEPS}),
    ])


def _end_turn():
    return LLMResponse(stop_reason="end_turn", text_blocks=["fini"])


def _inspect():
    return LLMResponse(stop_reason="tool_use", tool_calls=[
        ToolUseBlock(id="i", name="inspect_schema", input={"model": "x"}),
    ])


def _plan():
    return TestPlan(
        module_name="demo", models=["helpdesk.ticket"],
        scenarios=[ScenarioIntent(name="ok", type="nominal", action="a", persona="u")],
        personas=["u"], portal_routes=[], risks=[], raw_spec="spec de démo",
    )


@pytest.fixture(autouse=True)
def _isolate_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "GENERATED_DIR", tmp_path / "gen")
    monkeypatch.setattr(config, "STEPS_LIBRARY_DIR", tmp_path / "steps_lib")
    (tmp_path / "steps_lib").mkdir()


def test_happy_path_writes_files_and_awaits_review(tmp_path):
    conn = get_initialized_db(tmp_path / "t.db")
    agent = GenerationAgent(
        llm=FakeLLM([_write_both(), _end_turn()]),
        dry_runner=FakeDryRunner([DR(True)]),
        cost_tracker=CostTracker(limit_usd=2.0),
        case_repo=CaseRepo(conn), version_repo=VersionRepo(conn),
        max_iterations=5, stall_limit=3,
    )
    result = agent.generate(_plan(), title="Demande de matériel", author="qa")

    assert result.success is True
    assert result.stopped_reason == "done"
    assert result.awaiting_review is True
    assert result.feature_path.exists() and result.steps_path.exists()

    # Hand-off vers verdict : version persistée, cas « jamais exécuté » (à relire).
    case = CaseRepo(conn).get(result.case_id)
    assert case["validation_status"] == "never_executed"
    assert case["current_version_id"] == result.version_id
    version = VersionRepo(conn).get(result.version_id)
    assert version["feature_content"] == _FEATURE
    conn.close()


def test_cost_guardrail_stops_generation():
    agent = GenerationAgent(
        llm=FakeLLM([_write_both()], tokens=(1_000_000, 1_000_000)),  # ~18$ dès le 1er appel
        dry_runner=FakeDryRunner([DR(True)]),
        cost_tracker=CostTracker(limit_usd=2.0),
        max_iterations=5, stall_limit=3,
    )
    result = agent.generate(_plan())
    assert result.success is False
    assert result.stopped_reason == "cost_exceeded"


def test_max_iterations_guardrail():
    agent = GenerationAgent(
        llm=FakeLLM([_inspect()]),           # n'écrit jamais les fichiers
        dry_runner=None,
        cost_tracker=CostTracker(limit_usd=100.0),
        max_iterations=3, stall_limit=3,
    )
    result = agent.generate(_plan())
    assert result.success is False
    assert result.stopped_reason == "max_iterations"
    assert result.iterations == 3


def test_dry_run_stall_guardrail():
    agent = GenerationAgent(
        llm=FakeLLM([_write_both(), _end_turn()]),
        dry_runner=FakeDryRunner([DR(False, undefined=["je fais l'action"])]),  # échoue toujours pareil
        cost_tracker=CostTracker(limit_usd=100.0),
        max_iterations=10, stall_limit=3,
    )
    result = agent.generate(_plan())
    assert result.success is False
    assert result.stopped_reason == "dry_run_stalled"


def test_write_steps_rejects_shared_step_redefinition(tmp_path):
    ctx = ToolContext(module_name="demo", generated_dir=tmp_path / "gen",
                      reserved_steps=frozenset({"je me connecte"}))
    content = "from behave import given\n\n\n@given('je me connecte')\ndef s(context):\n    pass\n"
    outcome = write_tools.write_steps_file(ctx, content)
    assert outcome.ok is False
    assert "AmbiguousStep" in outcome.observation
    assert not (tmp_path / "gen" / "demo_steps.py").exists()
