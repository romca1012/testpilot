"""§6 — le harnais Behave (environment.py + steps_library) résout hors-ligne.

Deux niveaux, sans Odoo ni navigateur :
- unitaire : le shim d'alias ``features.*`` s'installe et ``register_created`` fonctionne ;
- intégration : un ``behave --dry-run`` réel sur le harnais assemblé résout la bibliothèque
  partagée ET les imports ``features.environment`` / ``features.steps._base_helpers`` d'un
  step « généré » (le dry-run parse et importe les steps sans exécuter les fixtures).
"""

import importlib.util
import sys

from testpilot import config
from testpilot.execution.behave_runner import BehaveRunner

_ENV_PATH = config.BEHAVE_RUNTIME_DIR / "environment.py"


def _load_environment():
    spec = importlib.util.spec_from_file_location("environment", _ENV_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["environment"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_shim_alias_installe_et_register_created():
    mod = _load_environment()
    # Le shim rend features.environment importable et y expose register_created.
    assert "features.environment" in sys.modules
    assert hasattr(sys.modules["features.environment"], "register_created")
    # features.steps existe comme package-espace de noms (pour _base_helpers).
    assert "features.steps" in sys.modules

    class _Ctx:
        created = {}

    ctx = _Ctx()
    mod.register_created(ctx, "helpdesk.ticket", 42)
    assert ctx.created == {"helpdesk.ticket": [42]}


def test_la_session_odoo_ne_s_ouvre_que_pour_le_connecteur_odoo():
    """Un projet `web` (générique, sans backend Odoo) ferait échouer TOUT scénario dès
    `before_scenario` si la session RPC s'ouvrait quand même — audit multi-connecteurs,
    2026-09-08 (voir `connectors/generic_web.py`)."""
    mod = _load_environment()
    assert mod._doit_ouvrir_session_odoo("odoo") is True
    assert mod._doit_ouvrir_session_odoo("ODOO") is True  # insensible à la casse
    assert mod._doit_ouvrir_session_odoo("web") is False
    assert mod._doit_ouvrir_session_odoo("") is True   # défaut historique : pas de régression
    assert mod._doit_ouvrir_session_odoo(None) is True  # idem, variable absente


_PROBE_FEATURE = """# language: fr
Fonctionnalité: Sonde du harnais Behave
  Scénario: la bibliothèque et le shim résolvent
    Soit l'instance Odoo accessible à l'URL définie dans "ODOO_URL"
    Quand je clique sur le bouton "Envoyer"
    Et je réalise une action de sonde du harnais
"""

# Un step « généré » qui suit la convention du prompt : imports qualifiés features.*
# (résolus uniquement grâce au shim de environment.py).
_PROBE_STEPS = """from behave import when
from features.environment import register_created
from features.steps._base_helpers import fill_field


@when('je réalise une action de sonde du harnais')
def step_probe(context):
    _ = (register_created, fill_field)  # prouve que les imports du shim ont résolu
"""


def test_dry_run_resout_bibliotheque_et_shim(tmp_path):
    generated = tmp_path / "generated"
    generated.mkdir()
    (generated / "probe_harness.feature").write_text(_PROBE_FEATURE, encoding="utf-8")
    (generated / "probe_harness_steps.py").write_text(_PROBE_STEPS, encoding="utf-8")

    runner = BehaveRunner(
        runtime_dir=config.BEHAVE_RUNTIME_DIR,
        generated_dir=generated,
        steps_library_dir=config.STEPS_LIBRARY_DIR,
    )
    result = runner.dry_run("probe_harness")

    # Aucun step indéfini / ambigu et parsing réussi = harnais + shim opérationnels.
    assert not result.undefined_steps, f"steps non résolus : {result.undefined_steps}"
    assert not result.ambiguous_steps, f"steps ambigus : {result.ambiguous_steps}"
    assert result.success, f"dry-run échoué (rc={result.returncode})\n{result.raw_stderr}"
