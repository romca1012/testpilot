"""Les bancs jouent en MODE STRICT : aucun LLM ne rattrape un test pendant la mesure (D25, audit du 2026-10-08).

Biais trouvé par l'audit : `banc_agents.executer_behave` et `banc_mesure.executer_cas` lançaient Behave sans `TP_MODE_STRICT`
ni `TESTPILOT_QUALIFICATION` ; la résolution adaptative (`_base_helpers._repli_adaptatif`, appel LLM) restait donc active et
pouvait faire passer un test cassé, ou un cas dont un bug injecté a renommé un champ. Les deux bancs mesuraient alors le repli,
pas le test. Ces tests capturent la connexion transmise au sous-processus, sans lancer Behave.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from testpilot.execution import behave_runner, executor
from testpilot.execution.behave_result import MODE_STRICT_ENV
from testpilot.verdict import status

RACINE = Path(__file__).resolve().parent.parent


def _charger(nom):
    spec = importlib.util.spec_from_file_location(f"{nom}_strict", RACINE / "scripts" / f"{nom}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"{nom}_strict"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def capture(monkeypatch):
    vues = []

    class FauxRunner:
        def __init__(self, connection=None, **_k):
            vues.append(dict(connection or {}))

        def cibler_artefacts(self, _d):
            pass

    class FauxExecutor:
        def __init__(self, runner, max_retries=0):
            self.max_retries = max_retries

        def execute(self, _module):
            return SimpleNamespace(real_run=None, error="", dry_run_passed=True, dry_run=None)

    verdict = SimpleNamespace(execution_status="success", functional_status="conforme", scenarios=[])
    monkeypatch.setattr(behave_runner, "BehaveRunner", FauxRunner)
    monkeypatch.setattr(executor, "Executor", FauxExecutor)
    monkeypatch.setattr(status, "derive_verdict", lambda *_a, **_k: verdict)
    monkeypatch.setattr(status, "statut_de_test", lambda *_a, **_k: "passed")
    return vues


def test_le_banc_d_agents_joue_chaque_test_en_mode_strict(capture, tmp_path):
    """Falsifiable : sans `TP_MODE_STRICT`, le sous-processus garde le repli LLM (`_base_helpers.py`, `_repli_adaptatif`)."""
    ba = _charger("banc_agents")

    ba.executer_behave(tmp_path, "m", {"WEB_URL": "http://127.0.0.1:1"}, 1, "web", None)

    assert capture[0][MODE_STRICT_ENV] == "1" and capture[0]["WEB_URL"] == "http://127.0.0.1:1"


def test_le_banc_odoo_joue_chaque_cas_en_mode_strict(capture, monkeypatch, tmp_path):
    bm = _charger("banc_mesure")
    monkeypatch.setattr(bm, "CAS_FIGES", tmp_path)
    (tmp_path / "c.feature").write_text("Feature: x", encoding="utf-8")
    (tmp_path / "c_steps.py").write_text("", encoding="utf-8")

    bm.executer_cas("c", {"ODOO_URL": "http://127.0.0.1:1"})

    assert capture[0][MODE_STRICT_ENV] == "1"


def test_le_nom_de_la_variable_lue_par_le_harnais_est_le_meme():
    """Le sous-processus lit `MODE_STRICT_ENV` de `_base_helpers` : les deux copies du nom doivent s'accorder."""
    sys.path.insert(0, str(RACINE / "behave_runtime" / "steps_library"))
    import _base_helpers

    assert _base_helpers.MODE_STRICT_ENV == MODE_STRICT_ENV
