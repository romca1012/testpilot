"""Migration 7 — suppression des colonnes MORTES `report_json_path` / `report_html_path`.

⚠️ Ce n'était PAS un bug (« écart 4 »), c'est un **diagnostic faux** corrigé après vérification —
le 3ᵉ de ce projet, après 0002 et 0007. La note affirmait :
  1. « `_persist` ne les écrit pas **alors que la CLI le fait** » → la CLI ne les persiste pas non
     plus (son `finalize()` ne les passe pas) ;
  2. « l'UI promet un rapport que le runtime ne fournit pas (§4.6) » → le rapport d'un run API
     répond bien : il est **reconstruit depuis la base**, sans fichier.

Le vrai défaut était l'inverse : jamais alimentées, jamais lues — un champ mort, comme le
`position` décoratif que §2.4 dénonce et la colonne `module` que 0004 a supprimée plutôt que
laissée inerte. Ces tests figent la suppression ET le fait que le rapport marche sans elles.
"""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import app as app_mod
from testpilot.api.services import run_service
from testpilot.execution.behave_result import BehaveResult, BehaveScenario
from testpilot.execution.executor import ExecutionOutcome
from testpilot.store.db import (
    _SCHEMA_VERSION,
    _column_names,
    _migrate_7_drop_report_paths,
    get_initialized_db,
)
from testpilot.store.repositories import CaseRepo, ReviewRepo, VersionRepo


class _FakeExecutor:
    def __init__(self, runner=None):
        pass

    def execute(self, module_name):
        real = BehaveResult(success=True, returncode=0, passed=1,
                            scenarios=[BehaveScenario("cas nominal", "passed")], failures=[])
        return ExecutionOutcome(module_name=module_name, dry_run_passed=True, real_run=real)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(run_service, "Executor", _FakeExecutor)
    run_service._RUNNING.clear()
    return TestClient(app_mod.app)


def test_colonnes_absentes_dune_base_neuve(tmp_path, monkeypatch):
    from testpilot import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    conn = get_initialized_db(tmp_path / "n.db")
    colonnes = _column_names(conn, "execution")
    assert "report_json_path" not in colonnes
    assert "report_html_path" not in colonnes
    conn.close()


def test_migration_7_supprime_les_colonnes_dune_base_existante(tmp_path):
    db = tmp_path / "old.db"
    conn = get_initialized_db(db)
    # Simule une base d'AVANT : on remet les colonnes mortes, version ramenée à 6.
    conn.execute("ALTER TABLE execution ADD COLUMN report_json_path TEXT NOT NULL DEFAULT ''")
    conn.execute("ALTER TABLE execution ADD COLUMN report_html_path TEXT NOT NULL DEFAULT ''")
    conn.execute("PRAGMA user_version = 6")
    conn.commit()
    assert "report_json_path" in _column_names(conn, "execution")
    conn.close()

    conn = get_initialized_db(db)   # réouverture → migration 7
    assert "report_json_path" not in _column_names(conn, "execution")
    assert "report_html_path" not in _column_names(conn, "execution")
    assert conn.execute("PRAGMA user_version").fetchone()[0] == _SCHEMA_VERSION
    conn.close()


def test_migration_7_idempotente(tmp_path, monkeypatch):
    from testpilot import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    conn = get_initialized_db(tmp_path / "i.db")
    _migrate_7_drop_report_paths(conn)   # rejouée sur une base déjà à la cible
    _migrate_7_drop_report_paths(conn)
    assert "report_json_path" not in _column_names(conn, "execution")
    conn.close()


def test_le_rapport_dun_run_API_marche_SANS_ces_colonnes(client):
    """Le point que le diagnostic avait manqué : le rapport n'a jamais eu besoin d'un fichier.

    Il est reconstruit à la demande depuis la base — c'est le seul mécanisme réel, et il tient
    sans les colonnes supprimées.
    """
    from testpilot.store.repositories import ModuleRepo, ProjectRepo

    conn = get_initialized_db(config.DB_PATH)
    # Un cas rattaché à un projet CONNECTÉ : depuis le 2026-07-24, un cas sans cible connue
    # n'est plus exécutable (on ne saurait pas contre quelle application le lancer).
    pid = ProjectRepo(conn).create(name="Recette", connector_type="odoo",
                                   base_url="http://recette:8069", database="db",
                                   username="qa", password="p")
    mid = ModuleRepo(conn).create(project_id=pid, name="M")
    cid = CaseRepo(conn).create(title="Cas", module_id=mid, feature_slug="cas", author="qa")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="s", spec_hash="h",
                                   feature_content="# language: fr\nFonctionnalité: X",
                                   steps_content="from behave import *")
    CaseRepo(conn).set_current_version(cid, vid)
    ReviewRepo(conn).create(test_case_id=cid, version_id=vid, decision="approved", reviewer="qa")
    conn.close()

    eid = client.post(f"/api/cases/{cid}/runs").json()["execution_id"]

    assert client.get(f"/api/executions/{eid}/report").status_code == 200
    html = client.get(f"/api/executions/{eid}/report.html")
    assert html.status_code == 200
    assert "Axe exécution" in html.text   # le rapport est bien rendu, pas une coquille


def test_finalize_ne_prend_plus_de_chemins(tmp_path):
    """Garde : réintroduire ces paramètres relancerait un champ mort (§2.4, 0004)."""
    import inspect

    from testpilot.store.repositories import ExecutionRepo
    params = inspect.signature(ExecutionRepo.finalize).parameters
    assert "report_json_path" not in params
    assert "report_html_path" not in params
