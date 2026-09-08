"""Le dry-run valide le correctif AVANT le run réel — la promesse de `repair_agent`, enfin tenue.

`repair_agent` promet dans sa docstring de module :

    « l'agent réécrit, le **dry-run valide le correctif** (il parse encore ?), et seulement
      ensuite l'orchestrateur le rejoue pour de vrai. Un correctif qui ne parse même pas est
      ainsi rattrapé sans coûter une exécution réelle. »

`propose_fix` accepte bien un `dry_runner`… que **personne ne lui passait**. `repair_service`
l'appelait sans, donc `None`, donc `react_loop._maybe_dry_run` rendait `skip` à tous les tours :
**aucun correctif n'était validé par quoi que ce soit** avant un run réel de ~300 s. La docstring
décrivait un garde-fou qui n'existait sur aucun chemin d'exécution.

Le prix mesuré, rejeu du 2026-07-17 (v12) : l'agent a supprimé son step d'authentification sans
mettre à jour le `.feature`, qui le réclamait encore → `undefined` → dry-run de l'`Executor` en
échec → `RUN_FAILED` → aucune adoption, disque rembobiné. Le dry-run de la SESSION aurait rendu
la liste des steps undefined à l'agent, qui corrigeait dans le même appel.

C'est le **principe 6** : toute promesse doit avoir sa vérification. Ces tests lient la phrase de
la docstring au câblage réel — ils échouent tous sur le code d'avant le correctif.
"""

from dataclasses import dataclass, field

import pytest

from testpilot import config
from testpilot.api.services import repair_service, run_service
from testpilot.generation import repair_agent
from testpilot.llm.adapter import LLMResponse, ToolUseBlock
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, ExecutionRepo, ReviewRepo, VersionRepo

_STEPS = "from behave import when\n\n\n@when(\"je fais l'action\")\ndef step_impl(context):\n    pass\n"
_STEPS_V2 = _STEPS.replace("pass", "context.ok = True")


# ── Doublures ─────────────────────────────────────────────────────────────────

class FakeLLM:
    """Rejoue un script de LLMResponse. Ne coûte rien, ne parle à personne."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def call_with_tools(self, *, system_prompt, messages, tools, cost_tracker=None, **_):
        self.calls += 1
        if cost_tracker is not None:
            cost_tracker.track_call(model=config.MODEL_REPAIR, input_tokens=10,
                                    output_tokens=10, label="repair")
        return self.script[min(self.calls - 1, len(self.script) - 1)], None


class DR:
    def __init__(self, success, undefined=None):
        self.success = success
        self.undefined_steps = undefined or []
        self.ambiguous_steps = []


class FakeDryRunner:
    """Compte ses appels : c'est LUI la mesure — un dry-runner jamais appelé est le bug."""

    def __init__(self, results):
        self.results = list(results)
        self.calls = 0

    def dry_run(self, module_name):
        self.calls += 1
        return self.results[min(self.calls - 1, len(self.results) - 1)]


def _ecrit_steps(content=_STEPS):
    return LLMResponse(stop_reason="tool_use", tool_calls=[
        ToolUseBlock(id="s", name="write_steps_file", input={"content": content}),
    ])


@dataclass
class _Failure:
    scenario_name: str = "[Nominal]"
    step_text: str = "Quand je fais l'action"
    failure_type: str = "unknown"
    traceback_summary: str = ""
    raw: str = "TypeError: 'int' object is not subscriptable"


@dataclass
class _Scenario:
    name: str = "[Nominal]"
    status: str = "failed"
    error: str = ""


@dataclass
class _RealRun:
    failures: list = field(default_factory=lambda: [_Failure()])
    scenarios: list = field(default_factory=lambda: [_Scenario()])
    returncode: int = 1


@dataclass
class _Outcome:
    real_run: _RealRun | None
    execution_id: int | None = None
    dry_run_passed: bool = True
    module_name: str = "cas"


@pytest.fixture(autouse=True)
def _isolate_paths(tmp_path, monkeypatch):
    """Ni bibliothèque de steps réelle, ni répertoire généré réel : le test reste déterministe."""
    monkeypatch.setattr(config, "GENERATED_DIR", tmp_path / "gen")
    monkeypatch.setattr(config, "STEPS_LIBRARY_DIR", tmp_path / "steps_lib")
    (tmp_path / "gen").mkdir()
    (tmp_path / "steps_lib").mkdir()


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    c = get_initialized_db(tmp_path / "r.db")
    yield c
    c.close()


def _cas(conn, *, budget=2):
    cid = CaseRepo(conn).create(title="Cas", feature_slug="cas")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="spec", spec_hash="h",
                                   feature_content="# feature v1", steps_content=_STEPS)
    CaseRepo(conn).set_current_version(cid, vid)
    ReviewRepo(conn).create(test_case_id=cid, version_id=vid, decision="approved",
                            reviewer="qa", repair_budget=budget)
    eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid)
    return cid, vid, eid


# ── La promesse de la docstring, vérifiée ─────────────────────────────────────

def test_le_dry_run_valide_le_correctif_comme_la_docstring_le_promet():
    """« le dry-run valide le correctif » — donc il est APPELÉ. Il ne l'était jamais."""
    dry = FakeDryRunner([DR(success=True)])

    proposal = repair_agent.propose_fix(
        module_name="cas", scenarios=[_Scenario()], failures=[_Failure()],
        steps_content=_STEPS, llm=FakeLLM([_ecrit_steps()]), dry_runner=dry)

    assert dry.calls == 1, "le correctif n'a été validé par RIEN avant le run réel"
    assert proposal.changed
    assert proposal.stopped_reason == "done"


def test_un_correctif_qui_ne_parse_plus_est_rattrape_dans_la_session():
    """Le cas v12 : un step disparaît, le `.feature` le réclame encore → `undefined`.

    Sans dry-run dans la session, ça coûtait un run réel (~300 s) pour finir en `RUN_FAILED`.
    Avec, l'agent reçoit la liste des steps undefined et corrige au tour suivant — la boucle
    rend un correctif VALIDE, sans qu'aucun run réel n'ait été gaspillé.
    """
    dry = FakeDryRunner([DR(success=False, undefined=["Soit le demandeur est authentifié"]),
                         DR(success=True)])

    proposal = repair_agent.propose_fix(
        module_name="cas", scenarios=[_Scenario()], failures=[_Failure()],
        steps_content=_STEPS,
        llm=FakeLLM([_ecrit_steps(), _ecrit_steps(_STEPS_V2)]), dry_runner=dry)

    assert dry.calls == 2, "l'agent n'a pas été re-sollicité après un dry-run en échec"
    assert proposal.stopped_reason == "done"
    assert proposal.steps_content == _STEPS_V2


def test_sans_dry_runner_rien_ne_valide_le_correctif():
    """Le comportement d'AVANT, verrouillé comme repoussoir : `None` ⇒ aucune validation.

    On ne teste pas un défaut qu'on garderait : on montre que le défaut à `None` (nécessaire aux
    tests qui injectent l'agent) ne valide rien — c'est pourquoi la production doit passer le
    vrai runner, ce que garde le test suivant.
    """
    proposal = repair_agent.propose_fix(
        module_name="cas", scenarios=[_Scenario()], failures=[_Failure()],
        steps_content=_STEPS, llm=FakeLLM([_ecrit_steps(), LLMResponse(
            stop_reason="end_turn", text_blocks=["corrigé"])]), dry_runner=None)

    assert proposal.changed
    # Aveu du code d'avant : l'agent a réécrit, et la boucle clôt sur « incomplete » — elle
    # n'a jamais pu dire si le correctif parse.
    assert proposal.stopped_reason == "incomplete"


# ── Le câblage, de bout en bout ───────────────────────────────────────────────

def test_la_boucle_transmet_le_dry_runner_a_l_agent(conn, monkeypatch):
    """`run_repair_loop` ne doit pas avaler le runner qu'on lui confie."""
    cid, vid, eid = _cas(conn)
    recu = {}

    def faux_propose(**kwargs):
        recu.update(kwargs)
        return repair_agent.RepairProposal(changed=False)

    monkeypatch.setattr(repair_service.repair_agent, "propose_fix", faux_propose)
    dry = FakeDryRunner([DR(success=True)])
    depart = _Outcome(real_run=_RealRun(), execution_id=eid)

    repair_service.run_repair_loop(
        conn, case_id=cid, version_id=vid, module_name="cas", outcome=depart,
        run_once=lambda v: depart, dry_runner=dry)

    assert recu.get("dry_runner") is dry


def test_le_service_de_run_branche_le_vrai_runner(conn, monkeypatch):
    """LE test du P0 : sur le chemin de production, l'agent reçoit un dry-runner NON nul.

    C'est celui qui échoue sur le code d'avant — `run_service` avait le runner sous la main
    (il venait de s'en servir pour le run réel) et ne le passait pas.
    """
    cid, vid, eid = _cas(conn)
    recu = {}

    def faux_propose(**kwargs):
        recu.update(kwargs)
        return repair_agent.RepairProposal(changed=False)

    monkeypatch.setattr(repair_service.repair_agent, "propose_fix", faux_propose)
    runner = FakeDryRunner([DR(success=True)])
    depart = _Outcome(real_run=_RealRun(), execution_id=eid)

    run_service._maybe_repair(conn, case_id=cid, version_id=vid, module_name="cas",
                              outcome=depart, runner=runner)

    assert recu.get("dry_runner") is runner, (
        "le dry-runner n'arrive pas jusqu'à l'agent : la docstring de repair_agent ment"
    )
