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

⚠️ Les tests « bout en bout » ci-dessous lancent un VRAI sous-processus Behave (comme
`test_artefacts_execution.py::test_la_trace_SURVIT_a_un_vrai_run_behave`) — c'est le seul moyen
de prouver que le correctif est branché, pas seulement que sa logique est correcte isolément.
Le scénario ne touche ni réseau ni page : `connector_type="web"` évite toute session Odoo, et
le step ne fait rien — un navigateur headless réel se lance quand même (coût minime, aucune
dépendance externe).
"""

from __future__ import annotations

from testpilot import config
from testpilot.api.services import run_service
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


# ── 2. Bout en bout : le vrai bug, reproduit puis corrigé ──────────────────────

def test_re_execution_reussit_meme_si_generated_dir_a_ete_vide_par_un_redeploiement(
        tmp_path, monkeypatch):
    """LE test qui compte : simule exactement ce qui s'est produit sur /dev — un cas déjà
    généré, dont le `.feature`/`_steps.py` ont disparu du disque (redéploiement), qu'on
    RE-exécute (pas qu'on régénère). Doit réussir : la base reste la source de vérité."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "GENERATED_DIR", tmp_path / "generated")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "d.db")  # `run_execution` rouvre via ce chemin
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
    assert execution["scenarios_total"] == 1
    assert execution["scenarios_passed"] == 1


def test_sans_le_correctif_le_meme_run_echoue_fichier_introuvable(tmp_path, monkeypatch):
    """Contre-épreuve : en désactivant SEULEMENT la réécriture (le correctif), le run reproduit
    exactement le symptôme observé sur /dev — technique, indéterminé, zéro scénario joué."""
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
