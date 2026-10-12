"""Une exécution AUTOMATIQUE ne contient que les cas dotés d'un test technique (2026-10-12).

⚠️ **Le défaut que ce fichier empêche.** Un cas saisi à la main ou importé d'un cahier Excel n'a rien que la machine puisse
jouer. Il figurait quand même dans les exécutions automatiques (« tous les cas », ou coché dans une sélection) : il y restait
« Untested » pour toujours, gonflait le total et faussait le pourcentage de la campagne — une recette automatique terminée à
100 % de ce qu'elle pouvait jouer s'affichait à 10 %.

La règle : le critère est la PRÉSENCE d'un test technique sur la version courante (la mention « Test automatisé : Oui » de la
fiche), jamais l'origine du cas. Un cas manuel que l'on fait automatiser entre dans les exécutions automatiques ; une exécution
MANUELLE garde tous les cas ; l'historique des campagnes déjà jouées n'est pas réécrit.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from outils_cas import doter_d_un_test_technique

from testpilot import config
from testpilot.api import app as app_mod
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, ExecutionRepo, ResultRepo, RunRepo, ScheduledRunRepo


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "campagne-auto.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return TestClient(app_mod.app)


def _projet(client) -> tuple[int, int, int, int]:
    """Un projet, un cas AVEC test technique, un cas saisi à la main (sans). Rend (projet, module, avec, sans)."""
    pid = client.post("/api/projects", json={"name": "Recette", "base_url": "http://x", "database": "db",
                                             "username": "qa", "password": "p"}).json()["id"]
    mid = client.post(f"/api/projects/{pid}/modules", json={"name": "Clients"}).json()["id"]
    avec = client.post(f"/api/modules/{mid}/cases/manual", json={
        "title": "Création d'un client", "test_steps": ["a"], "expected_result": "r"}).json()["id"]
    doter_d_un_test_technique(avec)
    sans = client.post(f"/api/modules/{mid}/cases/manual", json={
        "title": "Contrôle visuel du bulletin", "test_steps": ["a"], "expected_result": "r"}).json()["id"]
    return pid, mid, avec, sans


def _cas_du_run(client, run_id: int) -> list[int]:
    return [c["id"] for c in client.get(f"/api/runs/{run_id}").json()["cases"]]


# ── « Tous les cas » ───────────────────────────────────────────────────────────────────────────────────────────────────

def test_falsifiable_tous_les_cas_en_automatique_ne_retient_que_les_cas_avec_test_technique(client):
    pid, _, avec, sans = _projet(client)

    run = client.post(f"/api/projects/{pid}/runs", json={"name": "Auto", "selection_mode": "all"}).json()

    assert run["mode"] == "automatique"
    assert run["case_count"] == 1, "le cas sans test technique ne doit pas gonfler le total"
    assert _cas_du_run(client, run["id"]) == [avec]
    assert sans not in _cas_du_run(client, run["id"])


def test_tous_les_cas_en_manuel_garde_tous_les_cas(client):
    """Une personne peut jouer à la main n'importe quel cas : la règle ne vaut que pour la machine."""
    pid, _, avec, sans = _projet(client)

    run = client.post(f"/api/projects/{pid}/runs", json={
        "name": "Manuel", "selection_mode": "all", "mode": "manuelle"}).json()

    assert run["case_count"] == 2
    assert _cas_du_run(client, run["id"]) == sorted([avec, sans])


def test_un_cas_manuel_que_l_on_automatise_rejoint_l_execution_automatique(client):
    """Le critère est le test technique, pas l'origine : dès qu'un cas saisi à la main en reçoit un, la sélection vivante
    le prend."""
    pid, _, avec, sans = _projet(client)
    run_id = client.post(f"/api/projects/{pid}/runs", json={"name": "Auto", "selection_mode": "all"}).json()["id"]
    assert _cas_du_run(client, run_id) == [avec]

    doter_d_un_test_technique(sans)

    assert _cas_du_run(client, run_id) == sorted([avec, sans])


def test_l_API_dit_quels_cas_ont_un_test_technique(client):
    """L'écran s'appuie sur ce champ pour ne proposer que les cas jouables : il doit refléter la base, pas l'origine."""
    pid, _, avec, sans = _projet(client)

    cas = {c["id"]: c for c in client.get("/api/cases", params={"project_id": pid}).json()["items"]}

    assert cas[avec]["automatise"] is True
    assert cas[sans]["automatise"] is False


# ── Sélection figée ────────────────────────────────────────────────────────────────────────────────────────────────────

def test_falsifiable_une_selection_automatique_refuse_un_cas_sans_test_technique_en_le_nommant(client):
    pid, _, avec, sans = _projet(client)

    r = client.post(f"/api/projects/{pid}/runs", json={
        "name": "Auto", "selection_mode": "frozen", "case_ids": [avec, sans]})

    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "Contrôle visuel du bulletin" in detail and f"C{sans}" in detail, "le cas refusé doit être nommé"
    assert "Création d'un client" not in detail, "le cas jouable ne doit pas être accusé"
    assert "manuelle" in detail, "le message doit dire quoi faire"
    assert client.get(f"/api/projects/{pid}/runs").json() == [], "rien n'est créé sur un refus"


def test_la_meme_selection_est_acceptee_en_manuel(client):
    pid, _, avec, sans = _projet(client)

    r = client.post(f"/api/projects/{pid}/runs", json={
        "name": "Manuel", "selection_mode": "frozen", "case_ids": [avec, sans], "mode": "manuelle"})

    assert r.status_code == 201
    assert r.json()["case_count"] == 2


# ── Lancement ──────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_falsifiable_lancer_une_execution_automatique_sans_aucun_cas_jouable_est_refuse(client):
    """Un projet fait de cas saisis à la main : l'exécution automatique est vide. La lancer la terminerait sans avoir rien
    joué — refusé, avec un message qui dit quoi faire."""
    pid = client.post("/api/projects", json={"name": "Import", "base_url": "http://x", "database": "db",
                                             "username": "qa", "password": "p"}).json()["id"]
    mid = client.post(f"/api/projects/{pid}/modules", json={"name": "M"}).json()["id"]
    client.post(f"/api/modules/{mid}/cases/manual", json={"title": "A", "test_steps": ["a"], "expected_result": "r"})
    run_id = client.post(f"/api/projects/{pid}/runs", json={"name": "Auto", "selection_mode": "all"}).json()["id"]

    r = client.post(f"/api/runs/{run_id}/launch")

    assert r.status_code == 422
    assert r.json()["code"] == "campagne_vide"
    assert "test technique" in r.json()["detail"] and "manuelle" in r.json()["detail"]


# ── L'historique n'est pas réécrit ─────────────────────────────────────────────────────────────────────────────────────

def test_falsifiable_un_cas_deja_juge_dans_une_campagne_y_reste_visible(client):
    """Campagne antérieure à la règle : un cas sans test technique y a déjà un résultat. Le faire disparaître réécrirait
    ce que la campagne a réellement produit."""
    pid, _, avec, sans = _projet(client)
    conn = get_initialized_db(config.DB_PATH)
    try:
        repo = RunRepo(conn)
        run_id = repo.create(project_id=pid, name="Ancienne", selection_mode="frozen", case_ids=[avec, sans])
        assert repo.case_ids(run_id) == [avec], "sans résultat, le cas sans test technique n'en fait pas partie"

        # La campagne l'a pourtant joué à l'époque : une exécution rattachée à ce run, inscrite au registre.
        version = CaseRepo(conn).get(sans)["current_version_id"]
        execution = ExecutionRepo(conn).create(test_case_id=sans, version_id=version)
        conn.execute("UPDATE execution SET run_id=? WHERE id=?", (run_id, execution))
        conn.commit()
        assert ResultRepo(conn).enregistrer_execution(execution, created_by="Awa") is not None

        assert repo.case_ids(run_id) == sorted([avec, sans])
    finally:
        conn.close()


# ── Planification ──────────────────────────────────────────────────────────────────────────────────────────────────────

def test_falsifiable_une_planification_ne_retient_que_les_cas_avec_test_technique(client):
    pid, _, avec, sans = _projet(client)
    conn = get_initialized_db(config.DB_PATH)
    try:
        repo = ScheduledRunRepo(conn)
        tous = repo.create(project_id=pid, name="Chaque nuit", selection_mode="all", frequency="daily", hour=2, minute=0,
                           weekday=None, case_ids=[], created_by="Awa")
        fige = repo.create(project_id=pid, name="Figée", selection_mode="frozen", frequency="daily", hour=3, minute=0,
                           weekday=None, case_ids=[avec, sans], created_by="Awa")

        assert repo.case_ids(tous) == [avec]
        assert repo.case_ids(fige) == [avec]
    finally:
        conn.close()
