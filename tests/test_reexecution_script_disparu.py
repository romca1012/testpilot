"""Bug réel constaté sur /dev le 2026-09-14 : 15/15 cas SauceDemo revenus « difficulté
technique — le test n'a pas pu démarrer » (verdict `technical_error`/`indetermine`, AUCUN
scénario joué), sur DEUX exécutions distinctes, alors que le Gherkin/steps de chaque cas
restait intact en base.

Cause racine : `BehaveRunner` lit le script SUR DISQUE (`config.GENERATED_DIR`), jamais depuis
la base — un fait déjà connu et compensé ailleurs (`CaseRepo.copier`/`update_version`, voir
`repositories.py`). Mais `GENERATED_DIR` (`behave_runtime/generated/`) vit HORS du volume
persistant (`testpilot-data:/var/lib/testpilot`, `compose.production.yml`) : le `Dockerfile` le
recrée VIDE à chaque build, et `deploy-dev.yml` reconstruit l'image après CHAQUE CI verte sur
master. La RE-exécution d'un cas déjà généré (run normal, campagne, planification) n'avait,
elle, aucun filet — contrairement à la génération, à la copie et à l'édition manuelle, qui
réécrivent toutes le fichier au moment où elles touchent une version.

⚠️ **CI n'installe PAS de navigateur Playwright pour le job `pytest` — voir `ci.yml`** (`playwright
install` n'y figure nulle part ; c'est le job frontend/postgres qui n'en a pas besoin non plus).
Un premier jet de ces tests appelait `run_service.run_execution` de bout en bout, ce qui déclenche
un VRAI `real_run` (hooks Behave exécutés, donc lancement d'un navigateur) dès que le `.feature`
existe — et a fait échouer la CI (`OSError`/lancement Chromium impossible), pas parce que le
correctif était faux, mais parce que le test exigeait un navigateur absent de cet environnement.

Le bug lui-même (« `.feature introuvable` ») se manifeste dès le **dry-run**, qui n'exécute AUCUN
hook (`before_scenario` compris — voir `environment.py`, et la doc Behave : dry-run ne valide que
le parsing/l'appariement des steps) : `test_le_runner_dry_run_echoue_puis_reussit_apres_reecriture`
ci-dessous lance donc un VRAI sous-processus Behave (comme
`test_artefacts_execution.py::test_la_trace_SURVIT_a_un_vrai_run_behave`), sans navigateur,
directement sur `BehaveRunner.dry_run` — assez pour prouver le défaut ET le correctif. Le
branchement dans `run_execution` (l'appel a bien lieu AVANT que le runner ne soit utilisé) est,
lui, vérifié avec un runner factice — même patron que `test_reparation_isole_le_verdict.py`.
"""

from __future__ import annotations

from testpilot import config
from testpilot.api.services import run_service
from testpilot.execution.behave_runner import BehaveRunner
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import (
    CaseRepo,
    ExecutionRepo,
    ModuleRepo,
    ProjectRepo,
    VersionRepo,
)

FEATURE = (
    "# language: fr\n"
    "Fonctionnalité: Démo\n"
    "  Scénario: rien à vérifier\n"
    "    Soit je ne fais rien\n"
)
STEPS = (
    "from behave import given\n\n"
    "@given('je ne fais rien')\n"
    "def pas_grand_chose(context):\n"
    "    pass\n"
)


def _projet_web_avec_cas(conn):
    pid = ProjectRepo(conn).create(name="Démo web", connector_type="web",
                                   base_url="https://example.invalid",
                                   database="", username="", password="")
    mid = ModuleRepo(conn).create(project_id=pid, name="M")
    cid = CaseRepo(conn).create(title="Cas", module_id=mid, feature_slug="demo")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="",
                                   feature_content=FEATURE, steps_content=STEPS)
    CaseRepo(conn).set_current_version(cid, vid)
    eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid)
    return cid, vid, eid


# ── 1. Le cœur du correctif, isolé ─────────────────────────────────────────────

def test_assurer_script_sur_disque_reecrit_depuis_la_base(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "GENERATED_DIR", tmp_path / "generated")  # vide au départ
    conn = get_initialized_db(tmp_path / "d.db")
    try:
        _cid, vid, _eid = _projet_web_avec_cas(conn)

        assert not (config.GENERATED_DIR / "demo.feature").exists()

        run_service._assurer_script_sur_disque(conn, vid, "demo")

        assert (config.GENERATED_DIR / "demo.feature").read_text(encoding="utf-8") == FEATURE
        assert (config.GENERATED_DIR / "demo_steps.py").read_text(encoding="utf-8") == STEPS
    finally:
        conn.close()


def test_assurer_script_sur_disque_ne_fait_rien_pour_un_cas_sans_gherkin(tmp_path, monkeypatch):
    """Un cas encore en saisie manuelle (aucun script généré) : rien à réécrire, le runner le
    dira lui-même — on ne fabrique pas un `.feature` vide qui masquerait ce constat."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "GENERATED_DIR", tmp_path / "generated")
    conn = get_initialized_db(tmp_path / "d.db")
    try:
        cid = CaseRepo(conn).create(title="Cas manuel", feature_slug="")
        vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="",
                                       feature_content="", steps_content="")
        CaseRepo(conn).set_current_version(cid, vid)

        run_service._assurer_script_sur_disque(conn, vid, "cas-manuel")

        assert not config.GENERATED_DIR.exists()
    finally:
        conn.close()


# ── 2. Le vrai bug, reproduit puis corrigé — sur le VRAI `BehaveRunner`, sans navigateur ───

def test_le_runner_dry_run_echoue_puis_reussit_apres_reecriture(tmp_path):
    """LE test qui compte : un `.feature`/`_steps.py` absent du disque (redéploiement) fait
    échouer `dry_run` avec « introuvable » — EXACTEMENT le symptôme /dev (`dry_run_passed=False`
    → `technical_error`/`indetermine`, zéro scénario). Après réécriture depuis la base (ce que
    fait `_assurer_script_sur_disque`), le même runner réussit. Zéro navigateur : le dry-run
    n'exécute aucun hook (voir docstring du module)."""
    generated = tmp_path / "generated"
    generated.mkdir()
    runner = BehaveRunner(generated_dir=generated, steps_library_dir=tmp_path / "vide",
                          runtime_dir=tmp_path / "vide", dry_timeout=120)

    avant = runner.dry_run("demo")   # vrai `python -m behave --dry-run`

    assert avant.success is False
    assert "introuvable" in (avant.raw_stderr or "")

    (generated / "demo.feature").write_text(FEATURE, encoding="utf-8")
    (generated / "demo_steps.py").write_text(STEPS, encoding="utf-8")

    apres = runner.dry_run("demo")

    assert apres.success is True


class _RunnerFactice:
    """Vérifie que le fichier existe déjà AU MOMENT où le runner est utilisé — sans lancer Behave
    ni Playwright. Prouve l'ORDRE (`_assurer_script_sur_disque` avant `Executor.execute`), pas la
    mécanique réelle du runner (déjà prouvée ci-dessus)."""

    def __init__(self, generated_dir):
        self._feature = generated_dir / "demo.feature"

    def cibler_artefacts(self, _chemin):
        pass

    def cibler_execution(self, _execution_id):
        pass

    def dry_run(self, _module_name):
        from testpilot.execution.behave_result import BehaveResult
        assert self._feature.exists(), "le script doit déjà être sur disque avant le dry-run"
        return BehaveResult(success=True, returncode=0, dry_run=True)

    def real_run(self, _module_name):
        from testpilot.execution.behave_result import BehaveResult, BehaveScenario
        assert self._feature.exists(), "le script doit déjà être sur disque avant le run réel"
        return BehaveResult(success=True, returncode=0,
                            scenarios=[BehaveScenario(name="rien à vérifier", status="passed")])


def test_run_execution_reecrit_le_script_AVANT_d_utiliser_le_runner(tmp_path, monkeypatch):
    """LE branchement : `run_execution` doit appeler `_assurer_script_sur_disque` avant de
    construire/utiliser le `BehaveRunner` — sinon le correctif existe mais ne sert à rien."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "GENERATED_DIR", tmp_path / "generated")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "d.db")  # `run_execution` rouvre via ce chemin
    monkeypatch.setattr(run_service, "BehaveRunner",
                        lambda **_kw: _RunnerFactice(config.GENERATED_DIR))
    conn = get_initialized_db(config.DB_PATH)
    try:
        cid, vid, eid = _projet_web_avec_cas(conn)
        assert not (config.GENERATED_DIR / "demo.feature").exists()  # le redéploiement simulé

        run_service.run_execution(eid, "demo", cid, vid)

        execution = ExecutionRepo(conn).get(eid)
    finally:
        conn.close()

    assert execution["execution_status"] == "success", execution.get("error_message")
    assert execution["functional_status"] == "conforme"


def test_sans_le_correctif_le_meme_run_echoue_fichier_introuvable(tmp_path, monkeypatch):
    """Contre-épreuve : en désactivant SEULEMENT la réécriture (le correctif), le run reproduit
    exactement le symptôme observé sur /dev — technique, indéterminé, zéro scénario joué. Le VRAI
    `BehaveRunner` suffit ici : le run s'arrête au dry-run (fichier introuvable), avant tout hook,
    donc avant tout besoin de navigateur."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "GENERATED_DIR", tmp_path / "generated")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "d.db")  # `run_execution` rouvre via ce chemin
    monkeypatch.setattr(run_service, "_assurer_script_sur_disque", lambda *a, **k: None)
    conn = get_initialized_db(config.DB_PATH)
    try:
        cid, vid, eid = _projet_web_avec_cas(conn)

        run_service.run_execution(eid, "demo", cid, vid)

        execution = ExecutionRepo(conn).get(eid)
    finally:
        conn.close()

    assert execution["execution_status"] == "technical_error"
    assert execution["functional_status"] == "indetermine"
    assert execution["scenarios_total"] == 0
