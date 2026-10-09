"""Lot VH-04, étape 6 (audit V6, point 4) — « vérifié côté serveur » se mérite par les constats, jamais d'office.

Un constat consigné APRÈS une lecture RPC réussie du même step porte la source `rpc` (signal de l'instrumentation de
`execute_kw`, jamais déclaré par le test) ; un scénario n'est `serveur_verifie` que si un constat sous un `Alors` a lu le
serveur (oracle ou RPC). Le cas n'est `backend_verified` que si TOUS ses scénarios le sont — Odoo compris.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from testpilot.execution.behave_result import BehaveResult, BehaveScenario, rattacher_constats
from testpilot.verdict import status as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "behave_runtime" / "steps_library"))
import _base_helpers as H  # noqa: E402


@pytest.fixture
def sidecar(tmp_path, monkeypatch):
    chemin = tmp_path / "constats.jsonl"
    monkeypatch.setenv(H.CONSTATS_FILE_ENV, str(chemin))
    H.definir_etat_constat(scenario="s", step_type="then")
    H.debut_de_step()
    yield lambda: [json.loads(l) for l in chemin.read_text(encoding="utf-8").splitlines()] if chemin.exists() else []
    H.debut_de_step()


def test_un_constat_apres_une_lecture_rpc_du_step_porte_la_source_rpc(sidecar):
    H.noter_lecture_rpc()
    H.constater(True, "lu")

    assert sidecar()[0]["source"] == "rpc"


def test_falsifiable_un_constat_d_ecran_ne_porte_aucune_source(sidecar):
    H.constater(True, "écran")

    assert sidecar()[0]["source"] == ""


def test_la_lecture_d_un_step_precedent_ne_compte_pas(sidecar):
    H.noter_lecture_rpc()
    H.debut_de_step()   # nouveau step : le `Quand` qui a lu par RPC ne prête rien à l'`Alors`
    H.constater(True, "écran")

    assert sidecar()[0]["source"] == ""


def test_l_oracle_reste_prioritaire(sidecar):
    H.noter_lecture_rpc()
    with H._source_du_constat("oracle"):
        H.constater(True, "oracle")

    assert sidecar()[0]["source"] == "oracle"


def test_de_bout_en_bout_le_cas_odoo_n_est_backend_verified_que_par_ses_constats():
    resultat = BehaveResult(success=True, returncode=0,
                            scenarios=[BehaveScenario("ecran", "passed"), BehaveScenario("rpc", "passed")])
    rattacher_constats(resultat, [
        {"scenario": "ecran", "step_type": "then", "ok": True, "source": ""},
        {"scenario": "rpc", "step_type": "then", "ok": True, "source": "rpc"},
    ])
    verdicts = [st.scenario_verdict(s, []) for s in resultat.scenarios]

    assert [v.serveur_verifie for v in verdicts] == [False, True]
    assert st.aggregate(verdicts, connector_type="odoo").ground_truth == st.GROUND_TRUTH_UI_ONLY
    assert st.aggregate(verdicts[1:], connector_type="odoo").ground_truth == st.GROUND_TRUTH_BACKEND_VERIFIED


def test_le_harnais_marque_une_lecture_rpc_reussie_jamais_une_ecriture():
    """Le branchement : l'instrumentation de `execute_kw` (seul point de passage du RPC) pose le signal sur une LECTURE."""
    from types import SimpleNamespace

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from behave_runtime import environment

    appels = []
    context = SimpleNamespace(odoo=SimpleNamespace(execute_kw=lambda m, meth, a=None, k=None: appels.append(meth) or [1]),
                              _touched_models={"res.partner": 0})
    environment._instrumenter_creations_rpc(context)

    H.debut_de_step()
    context.odoo.execute_kw("res.partner", "write", [[1], {"name": "x"}])
    assert H._LECTURE_RPC_DU_STEP["vue"] is False
    context.odoo.execute_kw("res.partner", "search_count", [[]])
    assert H._LECTURE_RPC_DU_STEP["vue"] is True
    H.debut_de_step()
