"""Porteur, 2026-10-23 — l'onglet « Cas de test » filtre les cas qui ont un test technique, ou les seuls cas manuels.

Filtré par le SERVEUR (comme la recherche et le statut) : appliqué à la seule page chargée, il dirait « aucun cas manuel »
alors qu'il y en a plus loin. Même définition que la colonne `automatise` : la version courante porte un Gherkin non vide.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import app as app_mod
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, ModuleRepo, ProjectRepo, VersionRepo


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "db.sqlite")
    conn = get_initialized_db(config.DB_PATH)
    yield conn
    conn.close()


def _projet(conn):
    pid = ProjectRepo(conn).create(name="Filtre", connector_type="web", base_url="http://app")
    mid = ModuleRepo(conn).create(project_id=pid, name="M")
    auto = CaseRepo(conn).create(title="Automatisé", module_id=mid, feature_slug="auto")
    vid = VersionRepo(conn).create(test_case_id=auto, spec_content="", spec_hash="",
                                   feature_content="Fonctionnalité: x\n", steps_content="")
    CaseRepo(conn).set_current_version(auto, vid)
    vide = CaseRepo(conn).create(title="Version sans test", module_id=mid, feature_slug="vide")
    v2 = VersionRepo(conn).create(test_case_id=vide, spec_content="", spec_hash="", feature_content="  ", steps_content="")
    CaseRepo(conn).set_current_version(vide, v2)
    manuel = CaseRepo(conn).create(title="Manuel", module_id=mid, feature_slug="manuel")
    return pid, auto, vide, manuel


def _ids(pid, **params):
    reponse = TestClient(app_mod.app).get("/api/cases", params={"project_id": pid, **params})
    assert reponse.status_code == 200, reponse.text
    return sorted(c["id"] for c in reponse.json()["items"]), reponse.json()["total"]


def test_falsifiable_avec_test_technique_ou_manuels(base):
    pid, auto, vide, manuel = _projet(base)
    assert _ids(pid, automatise="true") == ([auto], 1)
    assert _ids(pid, automatise="false") == (sorted([vide, manuel]), 2), "une version sans Gherkin reste un cas manuel"
    assert _ids(pid) == (sorted([auto, vide, manuel]), 3), "sans filtre : tous"
