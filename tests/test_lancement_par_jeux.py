"""Lot PT-02b — créer une exécution avec un ou plusieurs jeux de données (décision A28).

Ce que ces tests gardent :
1. sans jeu demandé, la création est celle d'avant (une exécution, aucun jeu posé) ;
2. un jeu : une exécution qui le porte ; plusieurs : une exécution PAR jeu, nommées d'après lui, regroupées dans un plan ;
3. 50 jeux au plus, des jeux du projet et vivants seulement, et seulement pour une campagne automatique ;
4. les valeurs ne sont figées qu'au LANCEMENT (A29) : l'exécution créée ne porte encore aucune valeur.
"""

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import app as app_mod
from testpilot.api.routes import runs as routes_runs
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, ModuleRepo, RunRepo, VersionRepo


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return TestClient(app_mod.app)


def _projet_avec_jeux(client, *noms: str) -> tuple[int, int, dict[str, int]]:
    pid = client.post("/api/projects", json={"name": "Boutique", "connector_type": "web", "base_url": "https://app.exemple.test",
                                              "username": "u", "password": "p"}).json()["id"]
    conn = get_initialized_db(config.DB_PATH)
    try:   # un cas automatisé, pour une sélection figée valable
        cid = CaseRepo(conn).create(title="Commande", module_id=ModuleRepo(conn).create(project_id=pid, name="Ventes"),
                                    feature_slug="commande")
        vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="",
                                       feature_content="Fonctionnalité: X\n  Scénario: Y\n    Alors ok\n", steps_content="")
        conn.execute("UPDATE test_case SET current_version_id=? WHERE id=?", (vid, cid))
        conn.commit()
    finally:
        conn.close()
    base = f"/api/projects/{pid}/donnees-de-test"
    client.post(f"{base}/variables", json={"nom": "client"})
    for nom in noms:
        client.post(f"{base}/jeux", json={"nom": nom})
    jeux = {j["nom"]: j["id"] for j in client.get(base).json()["jeux"]}
    return pid, cid, jeux


def _creer(client, pid, cid, **plus):
    return client.post(f"/api/projects/{pid}/runs", json={"name": "Recette", "selection_mode": "frozen", "case_ids": [cid], **plus})


def test_sans_jeu_demande_la_creation_est_celle_d_avant(client):
    pid, cid, _ = _projet_avec_jeux(client)

    r = _creer(client, pid, cid)

    assert r.status_code == 201 and r.json()["dataset_id"] is None and r.json()["plan_id"] is None
    assert [x["name"] for x in client.get(f"/api/projects/{pid}/runs").json()] == ["Recette"]


def test_un_jeu_une_execution_qui_le_porte(client):
    pid, cid, jeux = _projet_avec_jeux(client, "Grosse commande")

    r = _creer(client, pid, cid, dataset_ids=[jeux["Grosse commande"]])

    assert r.status_code == 201
    assert (r.json()["name"], r.json()["dataset_id"], r.json()["plan_id"]) == ("Recette", jeux["Grosse commande"], None)


def test_falsifiable_plusieurs_jeux_une_execution_par_jeu_regroupees_dans_un_plan(client):
    pid, cid, jeux = _projet_avec_jeux(client, "Client particulier", "Grosse commande")
    demandes = [jeux["Par défaut"], jeux["Grosse commande"], jeux["Grosse commande"]]   # un doublon : un seul compte

    r = _creer(client, pid, cid, dataset_ids=demandes)

    assert r.status_code == 201 and r.json()["plan_id"] is not None
    plan = client.get(f"/api/plans/{r.json()['plan_id']}").json()
    assert plan["plan"]["name"] == "Recette"
    assert sorted(x["name"] for x in plan["runs"]) == ["Recette — Grosse commande", "Recette — Par défaut"]
    conn = get_initialized_db(config.DB_PATH)
    try:
        lignes = [RunRepo(conn).get(x["id"]) for x in plan["runs"]]
    finally:
        conn.close()
    assert sorted(l["dataset_id"] for l in lignes) == sorted([jeux["Par défaut"], jeux["Grosse commande"]])
    assert {l["parametres_figes"] for l in lignes} == {""}, "rien n'est figé avant le lancement (A29)"
    assert all(l["status"] == "draft" for l in lignes), "créer ne lance rien"


@pytest.mark.parametrize("cas", ["autre_projet", "corbeille", "manuelle", "trop"])
def test_falsifiable_une_demande_invalide_ne_cree_rien(client, monkeypatch, cas):
    pid, cid, jeux = _projet_avec_jeux(client, "Export")
    plus = {"dataset_ids": [jeux["Export"]]}
    if cas == "autre_projet":
        autre = client.post("/api/projects", json={"name": "Autre", "connector_type": "web", "base_url": "https://b.test",
                                                   "username": "u", "password": "p"}).json()["id"]
        client.post(f"/api/projects/{autre}/donnees-de-test/variables", json={"nom": "x"})
        plus = {"dataset_ids": [client.get(f"/api/projects/{autre}/donnees-de-test").json()["jeux"][0]["id"]]}
    elif cas == "corbeille":
        client.delete(f"/api/projects/{pid}/donnees-de-test/jeux/{jeux['Export']}")
    elif cas == "manuelle":
        plus["mode"] = "manuelle"
    else:
        monkeypatch.setattr(routes_runs, "JEUX_PAR_LANCEMENT_MAX", 1)
        plus = {"dataset_ids": [jeux["Par défaut"], jeux["Export"]]}

    r = _creer(client, pid, cid, **plus)

    assert r.status_code == 422, r.text
    assert client.get(f"/api/projects/{pid}/runs").json() == [], "aucune exécution créée"
    assert client.get(f"/api/projects/{pid}/plans").json() == [], "aucun plan créé"
