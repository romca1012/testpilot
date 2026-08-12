"""Routes profondes — l'accès par projet doit gouverner TOUTE l'API (2026-08-11).

Le chantier de la migration 31 (2026-08-10) n'avait gardé que les routes portant `project_id`
DIRECTEMENT dans leur chemin — assumé, écrit dans le code. Ce fichier fige la fermeture de ce
trou : un compte à qui l'accès à un projet est retiré (`no_access`) ou dégradé (rôle forcé) ne
doit RIEN pouvoir faire via un identifiant profond déjà connu (cas, module, section, exécution,
campagne, résultat, pièce jointe, job de génération, corbeille) — même contrat que le reste :
**404 (jamais 403) si `no_access`, 403 si écriture et rôle effectif sous Testeur.**

Un seul échantillon PAR résolveur (pas API × résolveur × rôle en entier — le contrat lui-même est
déjà figé pour `project_id` direct dans `test_acces_par_projet.py` ; ici on vérifie que CHAQUE
nouveau résolveur remonte au bon projet, pas que le contrat générique marche encore).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import access
from testpilot.api import app as app_mod
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import (
    CaseGroupRepo,
    CaseRepo,
    ExecutionRepo,
    GenerationJobRepo,
    ModuleRepo,
    ProjectAccessRepo,
    ProjectRepo,
    ResultRepo,
    RunRepo,
    UserRepo,
    VersionRepo,
)
from testpilot.verdict.status import MODE_MANUELLE, STATUT_PASSED

_PROJET = {"base_url": "http://x", "database": "db", "username": "qa", "password": "p"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "a.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return TestClient(app_mod.app)


def _compte(username: str, role: str) -> int:
    conn = get_initialized_db(config.DB_PATH)
    try:
        return UserRepo(conn).create(username=username,
                                     password_hash=access.hacher_mot_de_passe("mdp"), role=role)
    finally:
        conn.close()


def _connecte(client, username: str):
    r = client.post("/api/auth/login", json={"username": username, "password": "mdp"})
    assert r.status_code == 200, r.text


def _cacher_projet(project_id: int, user_id: int) -> None:
    conn = get_initialized_db(config.DB_PATH)
    try:
        ProjectAccessRepo(conn).set_override(project_id, user_id, access.ACCES_PROJET_REFUSE)
    finally:
        conn.close()


def _forcer_lecture_seule(project_id: int, user_id: int) -> None:
    conn = get_initialized_db(config.DB_PATH)
    try:
        ProjectAccessRepo(conn).set_override(project_id, user_id, access.ROLE_LECTURE_SEULE)
    finally:
        conn.close()


class _Arbre:
    """Un projet → module → section → cas → version → exécution → campagne (manuelle) → résultat
    → pièce jointe → job de génération, construits UNE fois, réutilisés par chaque test — la même
    hiérarchie que celle que chaque résolveur doit remonter jusqu'au projet."""
    def __init__(self, conn):
        self.project_id = ProjectRepo(conn).create(name="Recette", **_PROJET)
        self.module_id = ModuleRepo(conn).create(project_id=self.project_id, name="M")
        self.group_id = CaseGroupRepo(conn).create(module_id=self.module_id, title="Section")
        self.case_id = CaseRepo(conn).create(title="Cas", module_id=self.module_id,
                                             group_id=self.group_id)
        self.version_id = VersionRepo(conn).create(
            test_case_id=self.case_id, spec_content="", spec_hash="h",
            feature_content="Feature: x", steps_content="")
        self.execution_id = ExecutionRepo(conn).create(
            test_case_id=self.case_id, version_id=self.version_id)
        self.run_id = RunRepo(conn).create(
            project_id=self.project_id, name="Campagne", selection_mode="frozen",
            mode=MODE_MANUELLE, case_ids=[self.case_id])
        self.result_id = ResultRepo(conn).saisir(
            run_id=self.run_id, case_id=self.case_id, statut=STATUT_PASSED)
        self.attachment_id = ResultRepo(conn).ajouter_piece_jointe(
            self.result_id, filename="capture.png", stored_name="x.png", dossier=".")
        self.job_id = "job-1"
        GenerationJobRepo(conn).creer(self.job_id, module_id=self.module_id)


@pytest.fixture
def arbre(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "a.db")
    conn = get_initialized_db(tmp_path / "a.db")
    try:
        yield _Arbre(conn)
    finally:
        conn.close()


# ── 1. Résolveurs — chacun remonte au bon projet (unitaire, sans HTTP) ────────────────────────

def test_project_id_depuis_case(arbre):
    conn = get_initialized_db(config.DB_PATH)
    try:
        assert access.project_id_depuis_case(conn, arbre.case_id) == arbre.project_id
    finally:
        conn.close()


def test_project_id_depuis_module(arbre):
    conn = get_initialized_db(config.DB_PATH)
    try:
        assert access.project_id_depuis_module(conn, arbre.module_id) == arbre.project_id
    finally:
        conn.close()


def test_project_id_depuis_group(arbre):
    conn = get_initialized_db(config.DB_PATH)
    try:
        assert access.project_id_depuis_group(conn, arbre.group_id) == arbre.project_id
    finally:
        conn.close()


def test_project_id_depuis_execution(arbre):
    conn = get_initialized_db(config.DB_PATH)
    try:
        assert access.project_id_depuis_execution(conn, arbre.execution_id) == arbre.project_id
    finally:
        conn.close()


def test_project_id_depuis_run(arbre):
    conn = get_initialized_db(config.DB_PATH)
    try:
        assert access.project_id_depuis_run(conn, arbre.run_id) == arbre.project_id
    finally:
        conn.close()


def test_project_id_depuis_result(arbre):
    conn = get_initialized_db(config.DB_PATH)
    try:
        assert access.project_id_depuis_result(conn, arbre.result_id) == arbre.project_id
    finally:
        conn.close()


def test_project_id_depuis_attachment(arbre):
    conn = get_initialized_db(config.DB_PATH)
    try:
        assert access.project_id_depuis_attachment(conn, arbre.attachment_id) == arbre.project_id
    finally:
        conn.close()


def test_project_id_depuis_job(arbre):
    conn = get_initialized_db(config.DB_PATH)
    try:
        assert access.project_id_depuis_job(conn, arbre.job_id) == arbre.project_id
    finally:
        conn.close()


def test_un_id_inconnu_rend_None_jamais_une_exception(arbre):
    conn = get_initialized_db(config.DB_PATH)
    try:
        assert access.project_id_depuis_case(conn, 999999) is None
        assert access.project_id_depuis_execution(conn, 999999) is None
        assert access.project_id_depuis_job(conn, "job-inconnu") is None
    finally:
        conn.close()


# ── 2. Chaque route profonde — 404 sur no_access, jamais 403 ──────────────────────────────────
# Un échantillon représentatif (pas les ~45 routes) : un GET et une ÉCRITURE par résolveur.

def _prepare(client, arbre) -> int:
    """Root Admin, Awa Testeur — puis cache le projet à Awa. Rend l'id d'Awa."""
    _compte("Root", access.ROLE_ADMIN)
    uid = _compte("Awa", access.ROLE_TESTEUR)
    _cacher_projet(arbre.project_id, uid)
    _connecte(client, "Awa")
    return uid


def test_cas_no_access_404_get_et_ecriture(client, arbre):
    _prepare(client, arbre)
    assert client.get(f"/api/cases/{arbre.case_id}").status_code == 404
    r = client.patch(f"/api/cases/{arbre.case_id}", json={"priority": "high"})
    assert r.status_code == 404  # jamais 403 : no_access prime toujours


def test_module_no_access_404(client, arbre):
    _prepare(client, arbre)
    assert client.get(f"/api/modules/{arbre.module_id}").status_code == 404
    r = client.patch(f"/api/modules/{arbre.module_id}", json={"name": "Autre"})
    assert r.status_code == 404


def test_group_no_access_404(client, arbre):
    _prepare(client, arbre)
    assert client.get(f"/api/groups/{arbre.group_id}").status_code == 404


def test_execution_no_access_404(client, arbre):
    _prepare(client, arbre)
    assert client.get(f"/api/executions/{arbre.execution_id}").status_code == 404
    assert client.get(f"/api/executions/{arbre.execution_id}/artifacts").status_code == 404


def test_run_no_access_404(client, arbre):
    _prepare(client, arbre)
    assert client.get(f"/api/runs/{arbre.run_id}").status_code == 404
    r = client.post(f"/api/runs/{arbre.run_id}/archive", json={"archived": True})
    assert r.status_code == 404


def test_result_et_attachment_no_access_404(client, arbre):
    _prepare(client, arbre)
    assert client.get(
        f"/api/results/{arbre.result_id}/attachments/{arbre.attachment_id}").status_code == 404


def test_job_no_access_404(client, arbre):
    _prepare(client, arbre)
    assert client.get(f"/api/modules/jobs/{arbre.job_id}").status_code == 404


# ── 3. Rôle forcé sous Testeur — 403 en écriture, lecture toujours permise ─────────────────────

def test_role_force_lecture_seule_bloque_l_ecriture_pas_la_lecture(client, arbre):
    _compte("Root", access.ROLE_ADMIN)
    uid = _compte("Awa", access.ROLE_TESTEUR)
    _forcer_lecture_seule(arbre.project_id, uid)
    _connecte(client, "Awa")

    assert client.get(f"/api/cases/{arbre.case_id}").status_code == 200
    r = client.patch(f"/api/cases/{arbre.case_id}", json={"priority": "high"})
    assert r.status_code == 403


# ── 4. Accès suffisant — 200 partout ───────────────────────────────────────────────────────────

def test_acces_suffisant_laisse_tout_passer(client, arbre):
    _compte("Root", access.ROLE_ADMIN)
    _compte("Awa", access.ROLE_TESTEUR)
    _connecte(client, "Awa")

    assert client.get(f"/api/cases/{arbre.case_id}").status_code == 200
    assert client.get(f"/api/modules/{arbre.module_id}").status_code == 200
    assert client.get(f"/api/groups/{arbre.group_id}").status_code == 200
    assert client.get(f"/api/executions/{arbre.execution_id}").status_code == 200
    assert client.get(f"/api/runs/{arbre.run_id}").status_code == 200
    assert client.get(f"/api/modules/jobs/{arbre.job_id}").status_code == 200


# ── 5. Corbeille — le trou le plus grave, testé sur `cas` ET `projet` ──────────────────────────

def test_corbeille_purger_un_cas_no_access_rend_404(client, arbre):
    conn = get_initialized_db(config.DB_PATH)
    try:
        CaseRepo(conn).delete(arbre.case_id, par="root")
    finally:
        conn.close()
    _prepare(client, arbre)
    r = client.delete(f"/api/corbeille/cas/{arbre.case_id}")
    assert r.status_code == 404


def test_corbeille_restaurer_un_cas_deja_a_la_corbeille_marche_AVEC_acces(client, arbre):
    """Le piège trouvé en planifiant : un résolveur bâti sur `CaseRepo.get()` (qui filtre les
    lignes VIVANTES) renverrait ici « introuvable » pour l'élément même que cette route traite."""
    conn = get_initialized_db(config.DB_PATH)
    try:
        CaseRepo(conn).delete(arbre.case_id, par="root")
    finally:
        conn.close()
    _compte("Root", access.ROLE_ADMIN)
    _compte("Awa", access.ROLE_TESTEUR)
    _connecte(client, "Awa")
    r = client.post(f"/api/corbeille/cas/{arbre.case_id}/restaurer")
    assert r.status_code == 204


def test_corbeille_purger_un_PROJET_no_access_rend_404(client, arbre):
    """Le geste le plus destructeur de toute l'API — irréversible — ne filtrait sur RIEN avant
    ce chantier : un compte pouvait détruire un projet entier sans le moindre accès dessus."""
    conn = get_initialized_db(config.DB_PATH)
    try:
        ProjectRepo(conn).delete(arbre.project_id, par="root")
    finally:
        conn.close()
    _prepare(client, arbre)
    r = client.delete(f"/api/corbeille/projet/{arbre.project_id}")
    assert r.status_code == 404


def test_corbeille_type_element_inconnu_reste_422_pas_404(client, arbre):
    """Un `type_element` invalide est une erreur de REQUÊTE, pas d'accès — ne doit pas se
    transformer en 404 « ressource introuvable » qui masquerait le vrai problème."""
    _compte("Root", access.ROLE_ADMIN)
    _connecte(client, "Root")
    r = client.post(f"/api/corbeille/inconnu/{arbre.case_id}/restaurer")
    assert r.status_code == 422


# ── 6. Lot (corps de requête) — filtrage silencieux, jamais un 403 sur tout le lot ─────────────

def test_lot_priorite_ignore_silencieusement_un_cas_devenu_no_access(client, arbre):
    conn = get_initialized_db(config.DB_PATH)
    try:
        autre_module = ModuleRepo(conn).create(project_id=arbre.project_id, name="M2")
        autre_cas = CaseRepo(conn).create(title="Autre cas", module_id=autre_module)
    finally:
        conn.close()

    uid = _prepare(client, arbre)  # Awa : projet caché
    r = client.patch("/api/cases/lot", json={"case_ids": [arbre.case_id, autre_cas],
                                             "priority": "high"})
    assert r.status_code == 200
    body = r.json()
    assert body["traites"] == 0
    assert body["ignores"] == 2


def test_lot_priorite_traite_ce_qui_reste_accessible(client, arbre):
    conn = get_initialized_db(config.DB_PATH)
    try:
        autre_projet = ProjectRepo(conn).create(name="Autre", **_PROJET)
        autre_module = ModuleRepo(conn).create(project_id=autre_projet, name="M")
        autre_cas = CaseRepo(conn).create(title="Cas isolé", module_id=autre_module)
    finally:
        conn.close()

    _compte("Root", access.ROLE_ADMIN)
    uid = _compte("Awa", access.ROLE_TESTEUR)
    _cacher_projet(autre_projet, uid)  # Awa perd SEULEMENT le second projet
    _connecte(client, "Awa")

    r = client.patch("/api/cases/lot",
                     json={"case_ids": [arbre.case_id, autre_cas], "priority": "high"})
    assert r.status_code == 200
    body = r.json()
    assert body["traites"] == 1
    assert body["ignores"] == 1


# ── 7. Liste des exécutions — filtrée, jamais de fuite inter-projets ──────────────────────────

def test_liste_executions_cache_celles_du_projet_no_access(client, arbre):
    _prepare(client, arbre)
    ids = {e["id"] for e in client.get("/api/executions").json()}
    assert arbre.execution_id not in ids


def test_quality_summary_avec_project_id_no_access_rend_404(client, arbre):
    _prepare(client, arbre)
    r = client.get(f"/api/executions/quality/summary?project_id={arbre.project_id}")
    assert r.status_code == 404
