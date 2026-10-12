"""D33 (validée par le porteur le 2026-10-10, prolonge D25) — une campagne se joue SANS repli par le modèle de langage par défaut.

Avant : seule la campagne « stricte » (D5) coupait la résolution adaptative, et elle coupait AUSSI le second essai et la
réparation ; décochée par défaut, une campagne ordinaire laissait l'IA « retrouver » un élément renommé et rendre un vert à
confirmer. Désormais une option dédiée, `sans_repli`, cochée par défaut (campagnes existantes comprises, migration 60), coupe le
SEUL repli adaptatif : second essai et réparation restent actifs.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from outils_cas import creer_cas_avec_test_technique
from testpilot import config
from testpilot.api import app as app_mod
from testpilot.api.services import campaign_service, run_service
from testpilot.execution.behave_result import MODE_STRICT_ENV, SANS_REPLI_ENV
from testpilot.store.db import _migrate_60_sans_repli_adaptatif, get_initialized_db
from testpilot.store.repositories import ModuleRepo, ProjectRepo, RunRepo, VersionRepo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "behave_runtime" / "steps_library"))
import _base_helpers as H  # noqa: E402


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "d33.db")
    c = get_initialized_db(tmp_path / "d33.db")
    yield c
    c.close()


def _projet_et_cas(conn):
    pid = ProjectRepo(conn).create(name="P")
    cid = creer_cas_avec_test_technique(conn, title="C", module_id=ModuleRepo(conn).create(project_id=pid, name="M"), feature_slug="c")
    VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="", feature_content="# f", steps_content="# s")
    return pid, cid


# ── Migration 60 ──────────────────────────────────────────────────────────────────────────────────────────


def test_une_base_neuve_coche_l_option_par_defaut(conn):
    pid, cid = _projet_et_cas(conn)

    assert RunRepo(conn).get(RunRepo(conn).create(project_id=pid, name="R", case_ids=[cid]))["sans_repli"] == 1
    assert RunRepo(conn).get(RunRepo(conn).create(project_id=pid, name="R2", case_ids=[cid], sans_repli=False))[
        "sans_repli"] == 0


def test_falsifiable_reprise_d_une_base_pre_60(tmp_path):
    """Avant migration la colonne n'existe pas ; après, les campagnes EXISTANTES sont cochées (D25) et le CHECK mord."""
    base = sqlite3.connect(str(tmp_path / "vieille.db"))
    base.row_factory = sqlite3.Row  # comme les connexions du produit (`_column_names` lit par nom)
    base.execute("CREATE TABLE test_run (id INTEGER PRIMARY KEY, name TEXT NOT NULL, strict INTEGER NOT NULL DEFAULT 0)")
    base.execute("INSERT INTO test_run (id, name) VALUES (1, 'ancienne')")
    base.commit()

    _migrate_60_sans_repli_adaptatif(base)
    _migrate_60_sans_repli_adaptatif(base)  # idempotente

    assert base.execute("SELECT sans_repli FROM test_run WHERE id=1").fetchone()[0] == 1
    with pytest.raises(sqlite3.IntegrityError):
        base.execute("INSERT INTO test_run (name, sans_repli) VALUES ('x', 2)")
    base.close()


# ── API et lancement ──────────────────────────────────────────────────────────────────────────────────────


def test_l_api_coche_l_option_par_defaut_et_respecte_un_refus_explicite(conn):
    pid, cid = _projet_et_cas(conn)
    client = TestClient(app_mod.app)

    defaut = client.post(f"/api/projects/{pid}/runs", json={"name": "A", "selection_mode": "frozen", "case_ids": [cid]})
    avec_repli = client.post(f"/api/projects/{pid}/runs", json={"name": "B", "selection_mode": "frozen", "case_ids": [cid],
                                                                 "sans_repli": False})

    assert defaut.json()["sans_repli"] is True and avec_repli.json()["sans_repli"] is False


def test_le_lancement_transmet_l_option_a_chaque_cas(conn, monkeypatch):
    pid, cid = _projet_et_cas(conn)
    monkeypatch.setattr("testpilot.connectors.runtime_env.verifier_connexion", lambda projet: None)
    sans = RunRepo(conn).create(project_id=pid, name="S", case_ids=[cid])
    avec = RunRepo(conn).create(project_id=pid, name="A", case_ids=[cid], sans_repli=False)
    assert campaign_service.start_campaign(conn, sans)["sans_repli"] is True
    assert campaign_service.start_campaign(conn, avec)["sans_repli"] is False

    vus = []
    monkeypatch.setattr(run_service, "trigger_run", lambda conn_, c, **k: (1, "slug", c, 1))
    monkeypatch.setattr(run_service, "run_execution", lambda *a, **k: vus.append(k))
    campaign_service.run_campaign(1, [cid])
    campaign_service.run_campaign(1, [cid], sans_repli=False)

    assert vus[0].get("sans_repli") is True and "sans_repli" not in vus[1]


def test_falsifiable_l_execution_coupe_le_seul_repli_sans_couper_retry_ni_reparation(monkeypatch):
    """`run_execution(sans_repli=True)` pose la variable sur le runner (donc pour les tentatives de réparation aussi), et PAS le
    mode strict : le second essai et la réparation restent permis."""
    vus = {}

    class _Runner:
        def __init__(self, **_kw):
            self.connection = {}

    monkeypatch.setattr(run_service, "BehaveRunner", _Runner)
    for nom in ("resolve_connection", "resolve_project_id", "resolve_connector_type", "resolve_profil_instance"):
        monkeypatch.setattr(run_service, nom, lambda *a, **k: None)
    monkeypatch.setattr(run_service, "_assurer_script_sur_disque", lambda *a, **k: None)
    monkeypatch.setattr(run_service, "get_initialized_db", lambda *a, **k: SimpleNamespace(close=lambda: None))

    def _executer(conn, eid, cid, module, runner, **options):
        vus["connexion"], vus["options"] = dict(runner.connection), options
        return SimpleNamespace()

    monkeypatch.setattr(run_service, "_execute_and_persist", _executer)
    monkeypatch.setattr(run_service, "_maybe_repair", lambda *a, **k: vus.setdefault("reparation", True))

    run_service.run_execution(1, "m", 1, 1, sans_repli=True)

    assert vus["connexion"].get(SANS_REPLI_ENV) == "1"
    assert MODE_STRICT_ENV not in vus["connexion"] and "strict" not in vus["options"]
    assert vus.get("reparation") is True, "la réparation reste permise"


# ── Le sous-processus : le repli adaptatif est coupé ──────────────────────────────────────────────────────


def test_falsifiable_le_repli_adaptatif_ne_tourne_pas_sous_l_option(monkeypatch):
    appels = []
    monkeypatch.setattr(H, "_adaptive_resolution",
                        SimpleNamespace(resoudre_champ_adaptatif=lambda *a, **k: appels.append(a) or None))
    monkeypatch.delenv("TESTPILOT_QUALIFICATION", raising=False)
    monkeypatch.delenv(MODE_STRICT_ENV, raising=False)
    page = SimpleNamespace()

    monkeypatch.setenv(SANS_REPLI_ENV, "1")
    assert H._repli_adaptatif(page, "sujet", "je renseigne le sujet") is None
    assert appels == []

    monkeypatch.delenv(SANS_REPLI_ENV)
    H._repli_adaptatif(page, "sujet", "je renseigne le sujet")
    assert len(appels) == 1, "sans l'option, le repli est tenté (comportement d'avant)"


def test_les_noms_de_la_variable_sont_d_accord():
    assert H.SANS_REPLI_ENV == SANS_REPLI_ENV
