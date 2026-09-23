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


def test_before_all_expose_web_url_pour_le_connecteur_generique(monkeypatch):
    """⚠️ Bug SauceDemo (2026-09-13) : `WEB_URL`/`WEB_USER`/`WEB_PASSWORD` sont posées par
    `BehaveRunner._subprocess_env` (via `runtime_env.project_env`) depuis toujours, mais
    `environment.py` ne les lisait jamais — aucun step `generic/` n'avait de quoi naviguer vers
    l'application. `context.web_url` (le pendant générique de `context.odoo_url`) doit être
    rempli depuis ces variables d'environnement."""
    monkeypatch.setenv("WEB_URL", "https://www.saucedemo.com")
    monkeypatch.setenv("WEB_USER", "standard_user")
    monkeypatch.setenv("WEB_PASSWORD", "secret_sauce")
    mod = _load_environment()

    class _Ctx:
        pass

    ctx = _Ctx()
    mod.before_all(ctx)

    assert ctx.web_url == "https://www.saucedemo.com"
    assert ctx.web_user == "standard_user"
    assert ctx.web_password == "secret_sauce"


def test_before_all_web_url_vide_par_defaut_zero_regression(monkeypatch):
    """GARDE NÉGATIVE : un run Odoo (ou hors API, qui ne pose jamais ces variables) ne doit
    subir aucune régression — `context.web_url` existe mais reste vide, jamais `None` ni absent
    (le step générique qui le lit teste sa valeur, pas sa présence)."""
    monkeypatch.delenv("WEB_URL", raising=False)
    monkeypatch.delenv("WEB_USER", raising=False)
    monkeypatch.delenv("WEB_PASSWORD", raising=False)
    mod = _load_environment()

    class _Ctx:
        pass

    ctx = _Ctx()
    mod.before_all(ctx)

    assert ctx.web_url == ""
    assert ctx.web_user == ""
    assert ctx.web_password == ""


def test_before_all_expose_le_jeton_de_tentative(monkeypatch):
    """Lot 4 du plan de fiabilisation (2026-09-23) : le step partagé « … rendue unique pour
    cette tentative » lit `context.tentative_token`, posé ici depuis la variable d'environnement
    que `BehaveRunner._subprocess_env` désigne à CHAQUE appel de `dry_run`/`real_run`."""
    monkeypatch.setenv("TESTPILOT_ATTEMPT_TOKEN", "188-a1b2c3")
    mod = _load_environment()

    class _Ctx:
        pass

    ctx = _Ctx()
    mod.before_all(ctx)

    assert ctx.tentative_token == "188-a1b2c3"


def test_le_jeton_de_tentative_a_une_valeur_par_defaut_hors_run_pilote(monkeypatch):
    """GARDE NÉGATIVE : un appel direct du step (CLI, tests) sans `BehaveRunner` ne doit jamais
    lever — `context.tentative_token` doit toujours exister, jamais vide ni absent."""
    monkeypatch.delenv("TESTPILOT_ATTEMPT_TOKEN", raising=False)
    mod = _load_environment()

    class _Ctx:
        pass

    ctx = _Ctx()
    mod.before_all(ctx)

    assert ctx.tentative_token == "tentative-locale"


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


# ── Steps d'action enregistrés sous « Soit » ET « Quand » (bug SauceDemo, 2026-09-14) ─────────
# ⚠️ Le prompt système dit lui-même à l'IA que `Et` HÉRITE du type du step précédent — rien
# n'empêche « Soit j'accède à la page d'accueil … / Et je renseigne le champ … » (chaîne au type
# Given) d'être aussi légitime que « Quand je renseigne … / Et … » (chaîne au type When). Avant
# ce correctif, les steps d'action de `generic/_generic_steps.py` n'étaient enregistrés qu'en
# `@when` : la première forme échouait en step UNDEFINED — un `dry_run_stalled` sans rapport avec
# la vraie cause (mesuré en conditions réelles : 9 cas sur 15 contre SauceDemo).

_FEATURE_CHAINE_DEPUIS_SOIT = """# language: fr
Fonctionnalité: Connexion chaînée depuis un Given (bug SauceDemo)
  Scénario: la chaîne Soit puis Et doit résoudre les steps génériques
    Soit j'accède à la page d'accueil de l'application
    Et je renseigne le champ "user-name" avec la valeur "standard_user"
    Et je renseigne le champ "password" avec la valeur "secret_sauce"
    Et je clique sur le bouton "Login"
"""


def test_les_steps_generiques_resolvent_aussi_chaines_depuis_un_given(tmp_path):
    """⚠️ Reproduit EXACTEMENT le bug SauceDemo : avant le correctif, ce dry-run rapportait
    3 steps `undefined` (renseigner deux champs + cliquer), tous chaînés depuis un `Soit`."""
    generated = tmp_path / "generated"
    generated.mkdir()
    (generated / "chaine_given.feature").write_text(_FEATURE_CHAINE_DEPUIS_SOIT, encoding="utf-8")
    (generated / "chaine_given_steps.py").write_text("", encoding="utf-8")

    runner = BehaveRunner(
        runtime_dir=config.BEHAVE_RUNTIME_DIR,
        generated_dir=generated,
        steps_library_dir=config.STEPS_LIBRARY_DIR,
        connector_type="web",
    )
    result = runner.dry_run("chaine_given")

    assert not result.undefined_steps, f"steps non résolus : {result.undefined_steps}"
    assert not result.ambiguous_steps, f"steps ambigus : {result.ambiguous_steps}"
    assert result.success, f"dry-run échoué (rc={result.returncode})\n{result.raw_stderr}"
