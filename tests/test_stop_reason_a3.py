"""Étape A3 du §2bis — un tour LLM TRONQUÉ ou DÉCLINÉ n'est pas un succès.

⚠️ Le défaut fermé : l'adaptateur écrasait tout stop_reason non-outil en « end_turn ». Un
`max_tokens` (Gherkin coupé au milieu) passait donc pour une fin de tour normale → la génération
pouvait rendre un `.feature` incomplet, qui échouait plus loin avec une cause mal diagnostiquée.
On surface désormais le stop_reason BRUT et on interrompt proprement, avec une raison nommée.
"""

from __future__ import annotations

from testpilot.generation import react_loop
from testpilot.generation.state import AgentState
from testpilot.llm.adapter import LLMResponse


class _FakeLLM:
    def __init__(self, resp):
        self._resp = resp

    def call_with_tools(self, **_):
        return self._resp, None


def _run(resp):
    state = AgentState(module_name="m", messages=[])
    return react_loop.run_loop(
        llm=_FakeLLM(resp), system_prompt="sys", state=state, ctx=None,
        dry_runner=None, cost_tracker=None, max_iterations=3, stall_limit=2)


def test_un_tour_tronque_max_tokens_interrompt_sans_faux_succes():
    state = _run(LLMResponse(stop_reason="end_turn", raw_stop_reason="max_tokens",
                             text_blocks=["Scénario coupé au milie"]))
    assert state.stopped_reason == "max_tokens_truncated"
    assert not state.dry_run_passed          # donc success sera False en aval (agent.py)
    assert state.messages == [], "un tour tronqué n'est PAS ajouté à l'historique"


def test_un_tour_decline_refusal_interrompt():
    state = _run(LLMResponse(stop_reason="end_turn", raw_stop_reason="refusal"))
    assert state.stopped_reason == "refusal"
    assert not state.dry_run_passed


def test_un_tour_normal_end_turn_n_est_PAS_intercepte():
    """Garde négative : le durcissement ne doit pas se déclencher sur un tour légitime
    (raw_stop_reason vide ou « end_turn »)."""
    state = _run(LLMResponse(stop_reason="end_turn", raw_stop_reason="end_turn",
                             text_blocks=["fini"]))
    assert state.stopped_reason not in ("max_tokens_truncated", "refusal")
