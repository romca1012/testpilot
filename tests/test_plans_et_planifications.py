"""Plans de test + planifications récurrentes (migration 43).

Couvre : `PlanRepo`/`ScheduledRunRepo` (store), les routes (permissions Dev+ pour une
planification, Testeur+ pour un plan — un Plan n'exécute rien, une planification si), et
`scheduler_service.tick()` (le cœur du réacteur : une planification due se déclenche, jamais en
mode manuel, jamais deux fois le même jour).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import access
from testpilot.api import app as app_mod
from testpilot.api.services import scheduler_service
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import (
    CaseRepo,
    ModuleRepo,
    PlanRepo,
    ProjectRepo,
    RunRepo,
    ScheduledRunRepo,
    UserRepo,
)
from testpilot.verdict.status import MODE_AUTOMATIQUE, MODE_MANUELLE


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    c = get_initialized_db(tmp_path / "p.db")
    yield c
    c.close()


@pytest.fixture(autouse=True)
def _pas_de_vrai_thread_de_fond(monkeypatch):
    """`durable_jobs.submit_immediat` lance un VRAI thread (aucun `BackgroundTasks` hors requête
    — voir sa docstring) : le laisser courir en profiterait pour ouvrir un vrai navigateur contre
    `http://x` en course avec le nettoyage de `monkeypatch` en fin de test, exactement la classe
    de bug que le garde-fou anti-pollution de `conftest.py` a déjà attrapée une fois ici. Ces
    tests vérifient la logique de DÉCLENCHEMENT (`scheduler_service`), pas l'exécution réelle
    d'une campagne — déjà couverte par les tests de `campaign_service`/`run_service`."""
    from testpilot.guardrails import durable_jobs
    monkeypatch.setattr(durable_jobs, "submit_immediat",
                        lambda conn, **kwargs: "job-factice")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return TestClient(app_mod.app)


def _projet_avec_cas(conn_ou_client) -> tuple[int, int]:
    """Un projet + un cas, directement en base — plus rapide que de passer par l'API pour les
    tests qui ne vérifient pas cette API elle-même."""
    c = get_initialized_db(config.DB_PATH)
    pid = ProjectRepo(c).create(name="Portail")
    mid = ModuleRepo(c).create(project_id=pid, name="Module")
    cid = CaseRepo(c).create(title="Cas", module_id=mid, feature_slug="cas")
    c.close()
    return pid, cid


def _compte_et_connexion(client, username: str, role: str) -> None:
    c = get_initialized_db(config.DB_PATH)
    UserRepo(c).create(username=username, password_hash=access.hacher_mot_de_passe("mdp12345"),
                       role=role)
    c.close()
    r = client.post("/api/auth/login", json={"username": username, "password": "mdp12345"})
    assert r.status_code == 200, r.text


# ── PlanRepo / ScheduledRunRepo (store) ───────────────────────────────────────

def test_plan_regroupe_plusieurs_runs_chacun_avec_son_propre_mode(conn):
    pid = ProjectRepo(conn).create(name="Portail")
    mid = ModuleRepo(conn).create(project_id=pid, name="Module")
    cid = CaseRepo(conn).create(title="Cas", module_id=mid, feature_slug="cas")
    plan_id = PlanRepo(conn).create(project_id=pid, name="Régression 2.4")
    r_auto = RunRepo(conn).create(project_id=pid, name="Auto", mode=MODE_AUTOMATIQUE,
                                  selection_mode="frozen", case_ids=[cid])
    r_manuel = RunRepo(conn).create(project_id=pid, name="Manuel", mode=MODE_MANUELLE,
                                    selection_mode="frozen", case_ids=[cid])
    PlanRepo(conn).assign_run(plan_id, r_auto)
    PlanRepo(conn).assign_run(plan_id, r_manuel)

    runs = PlanRepo(conn).runs_of_plan(plan_id)
    modes = {r["id"]: r["mode"] for r in runs}
    assert modes == {r_auto: MODE_AUTOMATIQUE, r_manuel: MODE_MANUELLE}  # jamais fusionnés


def test_editer_un_plan_ne_touche_que_les_champs_fournis(conn):
    pid = ProjectRepo(conn).create(name="Portail")
    plan_id = PlanRepo(conn).create(project_id=pid, name="Brouillon", description="", refs="")

    PlanRepo(conn).update(plan_id, name="Régression 2.4")  # description/refs non fournis

    plan = PlanRepo(conn).get(plan_id)
    assert plan["name"] == "Régression 2.4"
    assert plan["description"] == ""  # inchangé, pas écrasé par une chaîne vide


def test_supprimer_un_plan_libere_ses_runs_sans_les_toucher(conn):
    pid = ProjectRepo(conn).create(name="Portail")
    plan_id = PlanRepo(conn).create(project_id=pid, name="Plan")
    run_id = RunRepo(conn).create(project_id=pid, name="R", selection_mode="all")
    PlanRepo(conn).assign_run(plan_id, run_id)

    PlanRepo(conn).delete(plan_id)

    assert PlanRepo(conn).get(plan_id) is None
    run = RunRepo(conn).get(run_id)
    assert run is not None  # la campagne survit
    assert run["plan_id"] is None  # simplement rendue hors de tout plan


def test_retirer_un_run_du_plan_le_laisse_intact_ailleurs(conn):
    pid = ProjectRepo(conn).create(name="Portail")
    plan_id = PlanRepo(conn).create(project_id=pid, name="Plan")
    run_id = RunRepo(conn).create(project_id=pid, name="R", selection_mode="all")
    PlanRepo(conn).assign_run(plan_id, run_id)
    PlanRepo(conn).unassign_run(run_id)

    assert PlanRepo(conn).runs_of_plan(plan_id) == []
    assert RunRepo(conn).get(run_id) is not None  # le run lui-même survit, jamais supprimé


def test_scheduled_run_case_ids_figee_vs_vivante(conn):
    pid = ProjectRepo(conn).create(name="Portail")
    mid = ModuleRepo(conn).create(project_id=pid, name="Module")
    cid = CaseRepo(conn).create(title="Cas", module_id=mid, feature_slug="cas")
    figee = ScheduledRunRepo(conn).create(
        project_id=pid, name="Nocturne", selection_mode="frozen",
        frequency="daily", hour=2, minute=0, case_ids=[cid])
    vivante = ScheduledRunRepo(conn).create(
        project_id=pid, name="Tout", selection_mode="all", frequency="daily", hour=2, minute=0)

    assert ScheduledRunRepo(conn).case_ids(figee) == [cid]
    assert ScheduledRunRepo(conn).case_ids(vivante) == [cid]  # vivante = tous les cas du projet


def test_planification_hebdomadaire_sans_jour_est_refusee(conn):
    pid = ProjectRepo(conn).create(name="Portail")
    with pytest.raises(ValueError):
        ScheduledRunRepo(conn).create(project_id=pid, name="X", frequency="weekly",
                                      hour=2, minute=0)  # weekday manquant


# ── scheduler_service.tick() ───────────────────────────────────────────────────

def test_une_planification_due_se_declenche_et_produit_un_run_automatique(conn):
    pid = ProjectRepo(conn).create(
        name="Portail", base_url="http://x", database="db", username="u", password="p")
    mid = ModuleRepo(conn).create(project_id=pid, name="Module")
    cid = CaseRepo(conn).create(title="Cas", module_id=mid, feature_slug="cas")
    ScheduledRunRepo(conn).create(
        project_id=pid, name="Nocturne", selection_mode="frozen",
        frequency="daily", hour=2, minute=0, case_ids=[cid])
    maintenant = datetime(2026, 9, 10, 2, 5, tzinfo=timezone.utc)  # 5 min après l'heure due

    declenches = scheduler_service.tick(conn, now=maintenant)

    assert len(declenches) == 1
    run = RunRepo(conn).get(declenches[0])
    assert run["mode"] == MODE_AUTOMATIQUE  # ⚠️ jamais autre chose, quelle que soit l'entrée
    assert run["status"] == "running"


def test_ne_se_declenche_pas_avant_l_heure(conn):
    pid = ProjectRepo(conn).create(name="Portail")
    ScheduledRunRepo(conn).create(project_id=pid, name="Nocturne", selection_mode="all",
                                  frequency="daily", hour=2, minute=0)
    trop_tot = datetime(2026, 9, 10, 1, 59, tzinfo=timezone.utc)

    assert scheduler_service.tick(conn, now=trop_tot) == []


def test_ne_se_declenche_pas_deux_fois_le_meme_jour(conn):
    pid = ProjectRepo(conn).create(
        name="Portail", base_url="http://x", database="db", username="u", password="p")
    mid = ModuleRepo(conn).create(project_id=pid, name="Module")
    CaseRepo(conn).create(title="Cas", module_id=mid, feature_slug="cas")
    ScheduledRunRepo(conn).create(project_id=pid, name="Nocturne", selection_mode="all",
                                  frequency="daily", hour=2, minute=0)
    premier_passage = datetime(2026, 9, 10, 2, 5, tzinfo=timezone.utc)
    second_passage = datetime(2026, 9, 10, 2, 10, tzinfo=timezone.utc)  # même jour, plus tard

    assert len(scheduler_service.tick(conn, now=premier_passage)) == 1
    assert scheduler_service.tick(conn, now=second_passage) == []  # pas une seconde fois


def test_une_planification_desactivee_ne_se_declenche_jamais(conn):
    pid = ProjectRepo(conn).create(name="Portail")
    sid = ScheduledRunRepo(conn).create(project_id=pid, name="Nocturne", selection_mode="all",
                                        frequency="daily", hour=2, minute=0)
    ScheduledRunRepo(conn).set_active(sid, False)
    maintenant = datetime(2026, 9, 10, 2, 5, tzinfo=timezone.utc)

    assert scheduler_service.tick(conn, now=maintenant) == []


def test_planification_hebdomadaire_ne_se_declenche_que_le_bon_jour(conn):
    pid = ProjectRepo(conn).create(
        name="Portail", base_url="http://x", database="db", username="u", password="p")
    mid = ModuleRepo(conn).create(project_id=pid, name="Module")
    CaseRepo(conn).create(title="Cas", module_id=mid, feature_slug="cas")
    ScheduledRunRepo(conn).create(project_id=pid, name="Hebdo", selection_mode="all",
                                  frequency="weekly", weekday=0, hour=2, minute=0)  # lundi
    mardi = datetime(2026, 9, 8, 2, 5, tzinfo=timezone.utc)   # mardi
    lundi = datetime(2026, 9, 7, 2, 5, tzinfo=timezone.utc)   # lundi

    assert scheduler_service.tick(conn, now=mardi) == []
    assert len(scheduler_service.tick(conn, now=lundi)) == 1


def test_une_planification_en_echec_n_empeche_pas_les_autres(conn):
    """Best-effort PAR planification — une campagne vide (aucun cas) ne doit jamais bloquer une
    autre planification due au même moment."""
    pid = ProjectRepo(conn).create(
        name="Portail", base_url="http://x", database="db", username="u", password="p")
    mid = ModuleRepo(conn).create(project_id=pid, name="Module")
    cid = CaseRepo(conn).create(title="Cas", module_id=mid, feature_slug="cas")
    ScheduledRunRepo(conn).create(project_id=pid, name="Vide", selection_mode="frozen",
                                  frequency="daily", hour=2, minute=0, case_ids=[])  # échouera
    ScheduledRunRepo(conn).create(
        project_id=pid, name="OK", selection_mode="frozen", frequency="daily",
        hour=2, minute=0, case_ids=[cid])
    maintenant = datetime(2026, 9, 10, 2, 5, tzinfo=timezone.utc)

    declenches = scheduler_service.tick(conn, now=maintenant)
    assert len(declenches) == 1  # seule "OK" a produit un run


# ── Routes : permissions ──────────────────────────────────────────────────────

def test_un_testeur_ne_peut_pas_creer_de_planification(client):
    pid, cid = _projet_avec_cas(client)
    _compte_et_connexion(client, "Awa", access.ROLE_TESTEUR)

    r = client.post(f"/api/projects/{pid}/schedules", json={
        "name": "Nocturne", "selection_mode": "frozen", "case_ids": [cid],
        "frequency": "daily", "hour": 2, "minute": 0})
    assert r.status_code == 403


def test_un_dev_peut_creer_une_planification(client):
    pid, cid = _projet_avec_cas(client)
    _compte_et_connexion(client, "Bob", access.ROLE_DEV)

    r = client.post(f"/api/projects/{pid}/schedules", json={
        "name": "Nocturne", "selection_mode": "frozen", "case_ids": [cid],
        "frequency": "daily", "hour": 2, "minute": 0})
    assert r.status_code == 201
    assert "mode" not in r.json()  # ⚠️ jamais exposé : ça n'existe pas pour une planification


def test_un_testeur_peut_creer_un_plan(client):
    pid, _cid = _projet_avec_cas(client)
    _compte_et_connexion(client, "Awa", access.ROLE_TESTEUR)

    r = client.post(f"/api/projects/{pid}/plans", json={"name": "Régression 2.4"})
    assert r.status_code == 201  # Testeur+ suffit : un plan n'exécute rien


def test_get_plan_regroupe_les_runs_avec_leur_mode(client):
    pid, cid = _projet_avec_cas(client)
    r = client.post(f"/api/projects/{pid}/plans", json={"name": "Plan"})
    plan_id = r.json()["id"]
    run = client.post(f"/api/projects/{pid}/runs", json={
        "name": "R1", "selection_mode": "frozen", "case_ids": [cid], "mode": "automatique"})
    run_id = run.json()["id"]

    client.post(f"/api/plans/{plan_id}/runs/{run_id}")
    detail = client.get(f"/api/plans/{plan_id}").json()

    assert detail["plan"]["id"] == plan_id
    assert len(detail["runs"]) == 1
    assert detail["runs"][0]["mode"] == "automatique"


def test_editer_un_plan_via_l_api(client):
    pid, _cid = _projet_avec_cas(client)
    plan_id = client.post(f"/api/projects/{pid}/plans", json={"name": "Brouillon"}).json()["id"]

    r = client.patch(f"/api/plans/{plan_id}", json={"name": "Régression 2.4", "refs": "JIRA-1"})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Régression 2.4"
    assert r.json()["refs"] == "JIRA-1"


def test_supprimer_un_plan_via_l_api_ne_supprime_pas_ses_runs(client):
    pid, cid = _projet_avec_cas(client)
    plan_id = client.post(f"/api/projects/{pid}/plans", json={"name": "Plan"}).json()["id"]
    run_id = client.post(f"/api/projects/{pid}/runs", json={
        "name": "R1", "selection_mode": "frozen", "case_ids": [cid], "mode": "automatique"}).json()["id"]
    client.post(f"/api/plans/{plan_id}/runs/{run_id}")

    r = client.delete(f"/api/plans/{plan_id}")
    assert r.status_code == 204
    assert client.get(f"/api/plans/{plan_id}").status_code == 404
    assert client.get(f"/api/runs/{run_id}").status_code == 200  # la campagne existe toujours


def test_desactiver_une_planification_ne_la_supprime_pas(client):
    pid, cid = _projet_avec_cas(client)
    r = client.post(f"/api/projects/{pid}/schedules", json={
        "name": "Nocturne", "selection_mode": "frozen", "case_ids": [cid],
        "frequency": "daily", "hour": 2, "minute": 0})
    sid = r.json()["id"]

    r2 = client.patch(f"/api/schedules/{sid}", json={"is_active": False})
    assert r2.status_code == 200
    assert r2.json()["is_active"] is False
    assert client.get(f"/api/projects/{pid}/schedules").json()[0]["id"] == sid  # toujours listée
