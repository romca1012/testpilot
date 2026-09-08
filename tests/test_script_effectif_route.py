"""Script effectif consultable — service + endpoint (Phase 2, audit DA 2026-08-13).

Deux niveaux, comme `tests/test_edition_script.py` :
1. Le service (`script_service.resoudre_script_effectif`), pur, contre une base + une
   bibliothèque de steps de test sur disque.
2. La route `GET /api/cases/{case_id}/versions/{version_id}/script-effectif`.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import access
from testpilot.api import app as app_mod
from testpilot.api.services import script_service
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, ProjectRepo, UserRepo, VersionRepo

_STEP_GENERIC = (
    "from behave import when\n\n"
    '@when(\'je renseigne le champ "{field}" avec la valeur "{value}"\')\n'
    "def step_fill(context, field, value):\n"
    '    """Remplit un champ du formulaire."""\n'
    "    pass\n"
)


@pytest.fixture
def conn(tmp_path, monkeypatch):
    from testpilot import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "STEPS_LIBRARY_DIR", tmp_path / "steps_lib")
    generic = tmp_path / "steps_lib" / "generic"
    generic.mkdir(parents=True)
    (generic / "_generic_steps.py").write_text(_STEP_GENERIC, encoding="utf-8")
    c = get_initialized_db(tmp_path / "script.db")
    yield c
    c.close()


def _cas_avec_version(conn, *, feature_content: str = "", steps_content: str = "") -> tuple[int, int]:
    cid = CaseRepo(conn).create(title="Cas", feature_slug="cas-a")
    vid = VersionRepo(conn).create(
        test_case_id=cid, spec_content="s", spec_hash="h",
        feature_content=feature_content, steps_content=steps_content,
        title="Cas", preconditions="", test_steps="[]", expected_result="ok")
    CaseRepo(conn).set_current_version(cid, vid)
    return cid, vid


# ── 1. Le service ─────────────────────────────────────────────────────────────

def test_feature_vide_replie_sur_steps_content_tel_quel(conn):
    cid, vid = _cas_avec_version(conn, feature_content="", steps_content="# rien encore")
    resultat = script_service.resoudre_script_effectif(conn, case_id=cid, version_id=vid)
    assert resultat["steps_effectif"] == "# rien encore"
    assert resultat["shared_steps"] == []


def test_resout_le_code_des_steps_partages_references(conn):
    feature = (
        "# language: fr\nFonctionnalité: X\n  Scénario: Y\n"
        '    Quand je renseigne le champ "name" avec la valeur "TEST"\n'
    )
    cid, vid = _cas_avec_version(conn, feature_content=feature, steps_content="# propre au cas")
    resultat = script_service.resoudre_script_effectif(conn, case_id=cid, version_id=vid)

    assert "# propre au cas" in resultat["steps_effectif"]
    assert "def step_fill(context, field, value):" in resultat["steps_effectif"]
    assert len(resultat["shared_steps"]) == 1
    assert resultat["shared_steps"][0]["label"] == 'je renseigne le champ "{field}" avec la valeur "{value}"'
    assert resultat["shared_steps"][0]["code"]


def test_steps_content_vide_mais_steps_partages_trouves_rend_un_effectif_non_vide(conn):
    """Le cas d'usage central : un cas dont le fichier propre est quasi vide affiche quand même
    un script effectif complet, parce que la bibliothèque partagée derrière est résolue."""
    feature = (
        "# language: fr\nFonctionnalité: X\n  Scénario: Y\n"
        '    Quand je renseigne le champ "name" avec la valeur "TEST"\n'
    )
    cid, vid = _cas_avec_version(conn, feature_content=feature, steps_content="")
    resultat = script_service.resoudre_script_effectif(conn, case_id=cid, version_id=vid)
    assert resultat["steps_content"] == ""
    assert resultat["steps_effectif"].strip() != ""
    assert "def step_fill" in resultat["steps_effectif"]


def test_aucun_step_du_feature_ne_matche_le_catalogue_rend_effectif_egal_au_propre(conn):
    feature = "# language: fr\nFonctionnalité: X\n  Scénario: Y\n    Quand rien de connu ne se passe\n"
    cid, vid = _cas_avec_version(conn, feature_content=feature, steps_content="# propre")
    resultat = script_service.resoudre_script_effectif(conn, case_id=cid, version_id=vid)
    assert resultat["shared_steps"] == []
    assert resultat["steps_effectif"] == "# propre"


# ── 2. La route ───────────────────────────────────────────────────────────────

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "script_api.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "STEPS_LIBRARY_DIR", tmp_path / "steps_lib")
    (tmp_path / "steps_lib" / "generic").mkdir(parents=True)
    (tmp_path / "steps_lib" / "generic" / "_generic_steps.py").write_text(
        _STEP_GENERIC, encoding="utf-8")
    return TestClient(app_mod.app)


def _compte_et_connexion(client, username: str = "Awa", role: str = access.ROLE_DEV):
    conn = get_initialized_db(config.DB_PATH)
    try:
        UserRepo(conn).create(username=username, password_hash=access.hacher_mot_de_passe("mdp"),
                              role=role)
    finally:
        conn.close()
    r = client.post("/api/auth/login", json={"username": username, "password": "mdp"})
    assert r.status_code == 200, r.text


def _projet_module_cas(client, nom_projet: str = "Recette") -> tuple[int, int]:
    conn = get_initialized_db(config.DB_PATH)
    try:
        pid = ProjectRepo(conn).create(name=nom_projet, base_url="http://x", database="db",
                                       username="qa", password="p")
    finally:
        conn.close()
    mid = client.post(f"/api/projects/{pid}/modules", json={"name": "M"}).json()["id"]
    cid = client.post(f"/api/modules/{mid}/cases/manual", json={
        "title": "Cas", "test_steps": ["a"], "expected_result": "ok"}).json()["id"]
    return pid, cid


def test_endpoint_renvoie_le_script_effectif(client):
    _compte_et_connexion(client)
    _, cid = _projet_module_cas(client)
    conn = get_initialized_db(config.DB_PATH)
    try:
        feature = (
            "# language: fr\nFonctionnalité: X\n  Scénario: Y\n"
            '    Quand je renseigne le champ "name" avec la valeur "TEST"\n'
        )
        vid = VersionRepo(conn).create(
            test_case_id=cid, spec_content="s", spec_hash="h",
            feature_content=feature, steps_content="# propre",
            title="Cas", preconditions="", test_steps="[]", expected_result="ok")
        CaseRepo(conn).set_current_version(cid, vid)
    finally:
        conn.close()

    r = client.get(f"/api/cases/{cid}/versions/{vid}/script-effectif")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["feature_content"] == feature
    assert "def step_fill" in body["steps_effectif"]
    assert len(body["shared_steps"]) == 1


def test_endpoint_cas_introuvable_404(client):
    _compte_et_connexion(client)
    r = client.get("/api/cases/999999/versions/1/script-effectif")
    assert r.status_code == 404


def test_endpoint_version_dun_autre_cas_404(client):
    _compte_et_connexion(client)
    _, cid1 = _projet_module_cas(client, "Recette 1")
    _, cid2 = _projet_module_cas(client, "Recette 2")
    conn = get_initialized_db(config.DB_PATH)
    try:
        vid_cas2 = CaseRepo(conn).get(cid2)["current_version_id"]
    finally:
        conn.close()

    r = client.get(f"/api/cases/{cid1}/versions/{vid_cas2}/script-effectif")
    assert r.status_code == 404
