"""Lot PT-02b — créer une exécution avec un ou plusieurs jeux de données (décision A28, puis A52 le 2026-10-16).

Décision A52 (porteur, 2026-10-16, changement DÉLIBÉRÉ des attendus) : plusieurs jeux ne donnent plus une exécution par jeu
regroupées dans un plan, mais UNE exécution qui les joue en itérations (`tests/test_iterations.py`) ; un test sans variable
n'y est joué qu'une fois par construction. Les tests du tri A35 (exécutions « suivantes ») portent désormais sur les
exécutions créées AVANT A52, encore en base.

Ce que ces tests gardent :
1. sans jeu demandé, la création est celle d'avant (une exécution, aucun jeu posé) ;
2. un jeu : une exécution qui le porte ; plusieurs : une exécution PAR jeu, nommées d'après lui, regroupées dans un plan ;
   un test qui n'écrit aucune variable n'est joué qu'UNE fois, dans la première (« Par défaut » en tête) — décision A35 ;
3. 50 jeux au plus, des jeux du projet et vivants seulement, et seulement pour une campagne automatique ;
4. les valeurs ne sont figées qu'au LANCEMENT (A29) : l'exécution créée ne porte encore aucune valeur.
"""

import json

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import app as app_mod
from testpilot.api.routes import runs as routes_runs
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, ExecutionRepo, ModuleRepo, RunRepo, VersionRepo


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return TestClient(app_mod.app)


SANS_VARIABLE = "Fonctionnalité: X\n  Scénario: Y\n    Alors ok\n"
AVEC_VARIABLE = "Fonctionnalité: X\n  Scénario: Y\n    Alors le client {{client}} est servi\n"


def _cas(pid: int, titre: str, feature: str) -> int:
    """Un cas automatisé du projet, dont la version courante a ce texte."""
    conn = get_initialized_db(config.DB_PATH)
    try:
        module = conn.execute("SELECT id FROM module WHERE project_id=? ORDER BY id", (pid,)).fetchone()
        module_id = module["id"] if module else ModuleRepo(conn).create(project_id=pid, name="Ventes")
        cid = CaseRepo(conn).create(title=titre, module_id=module_id, feature_slug=titre.lower().replace(" ", "_"))
        vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="", feature_content=feature,
                                       steps_content="")
        conn.execute("UPDATE test_case SET current_version_id=? WHERE id=?", (vid, cid))
        conn.commit()
        return cid
    finally:
        conn.close()


def _projet_avec_jeux(client, *noms: str, feature: str = AVEC_VARIABLE) -> tuple[int, int, dict[str, int]]:
    pid = client.post("/api/projects", json={"name": "Boutique", "connector_type": "web", "base_url": "https://app.exemple.test",
                                              "username": "u", "password": "p"}).json()["id"]
    cid = _cas(pid, "Commande", feature)   # un cas automatisé, pour une sélection figée valable
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


def test_falsifiable_plusieurs_jeux_une_seule_execution_qui_les_porte(client):
    """A52 : une exécution, une itération par jeu — plus d'exécution par jeu ni de plan."""
    pid, cid, jeux = _projet_avec_jeux(client, "Client particulier", "Grosse commande")
    demandes = [jeux["Grosse commande"], jeux["Par défaut"], jeux["Grosse commande"]]   # un doublon : un seul compte

    r = _creer(client, pid, cid, dataset_ids=demandes)

    assert r.status_code == 201 and r.json()["plan_id"] is None and r.json()["name"] == "Recette"
    assert client.get(f"/api/projects/{pid}/plans").json() == []
    conn = get_initialized_db(config.DB_PATH)
    try:
        ligne = RunRepo(conn).get(r.json()["id"])
    finally:
        conn.close()
    assert json.loads(ligne["dataset_ids"]) == [jeux["Par défaut"], jeux["Grosse commande"]], "« Par défaut » en tête"
    assert ligne["parametres_figes"] == "", "rien n'est figé avant le lancement (A29)"
    assert ligne["status"] == "draft", "créer ne lance rien"


def _executions_du_plan(client, plan_id: int) -> dict[str, list[int]]:
    """{nom de l'exécution: ses cas}."""
    runs = client.get(f"/api/plans/{plan_id}").json()["runs"]
    conn = get_initialized_db(config.DB_PATH)
    try:
        return {x["name"]: RunRepo(conn).case_ids(x["id"]) for x in runs}
    finally:
        conn.close()


@pytest.mark.parametrize("selection", ["frozen", "all"])
def test_falsifiable_tous_les_tests_sont_dans_l_unique_execution(client, selection):
    """A52 : les tests avec et sans variable sont dans la même exécution ; celui sans variable n'a qu'une itération."""
    pid, avec, jeux = _projet_avec_jeux(client, "Grosse commande", "Export")
    sans = _cas(pid, "Accueil", SANS_VARIABLE)
    plus = {"dataset_ids": [jeux["Grosse commande"], jeux["Export"], jeux["Par défaut"]], "selection_mode": selection,
            "case_ids": [] if selection == "all" else [avec, sans]}

    r = _creer(client, pid, avec, **plus)

    assert r.status_code == 201, r.text
    conn = get_initialized_db(config.DB_PATH)
    try:
        assert RunRepo(conn).case_ids(r.json()["id"]) == sorted([avec, sans])
    finally:
        conn.close()


def _nouvelle_version(cid: int, feature: str) -> None:
    """Le test est régénéré : sa version courante a désormais ce texte."""
    conn = get_initialized_db(config.DB_PATH)
    try:
        vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="", feature_content=feature,
                                       steps_content="")
        conn.execute("UPDATE test_case SET current_version_id=? WHERE id=?", (vid, cid))
        conn.commit()
    finally:
        conn.close()


def _execution_suivante_d_avant_a52(pid: int, cid: int, dataset_id: int) -> int:
    """Une exécution « suivante » créée AVANT A52 (encore en base) : elle ne joue que les tests qui écrivent des variables."""
    conn = get_initialized_db(config.DB_PATH)
    try:
        return RunRepo(conn).create(project_id=pid, name="Recette — Grosse commande", case_ids=[cid],
                                    dataset_id=dataset_id, seulement_variables=True)
    finally:
        conn.close()


def test_falsifiable_aucun_test_avec_variable_l_execution_du_jeu_refuse_de_se_lancer_en_le_disant(client):
    from testpilot.api.services import campaign_service

    pid, cid, jeux = _projet_avec_jeux(client, "Grosse commande", feature=SANS_VARIABLE)
    second = _execution_suivante_d_avant_a52(pid, cid, jeux["Grosse commande"])
    conn = get_initialized_db(config.DB_PATH)
    try:
        with pytest.raises(campaign_service.CampaignError) as refus:
            campaign_service.start_campaign(conn, second)
    finally:
        conn.close()
    assert refus.value.code == "empty" and "n'utilise de donnée de test" in str(refus.value)


def test_une_execution_de_jeu_vide_pour_une_autre_raison_garde_le_message_d_origine(client):
    """Tous ses tests à la corbeille : dire « aucun test n'utilise de donnée de test » serait faux."""
    from testpilot.api.services import campaign_service

    pid, cid, jeux = _projet_avec_jeux(client, "Grosse commande")
    second = _execution_suivante_d_avant_a52(pid, cid, jeux["Grosse commande"])
    conn = get_initialized_db(config.DB_PATH)
    try:
        conn.execute("UPDATE test_case SET deleted_at='2026-10-14' WHERE id=?", (cid,))
        conn.commit()
        with pytest.raises(campaign_service.CampaignError) as refus:
            campaign_service.start_campaign(conn, second)
    finally:
        conn.close()
    assert refus.value.code == "empty" and "n'utilise de donnée de test" not in str(refus.value)


def test_la_liste_des_tests_avec_variables_pour_l_ecran(client):
    pid, avec, _ = _projet_avec_jeux(client)
    _cas(pid, "Accueil", SANS_VARIABLE)

    assert client.get(f"/api/projects/{pid}/donnees-de-test/cas-avec-variables").json() == [avec]


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


def test_l_apercu_par_jeu_de_la_fiche_d_un_test(client):
    """Lot PT-02c : la fiche d'un test montre ce test avec les valeurs d'un jeu ; un jeu inconnu : 404."""
    pid, cid, jeux = _projet_avec_jeux(client, "Grosse commande")
    base = f"/api/projects/{pid}/donnees-de-test"
    variable = client.get(base).json()["variables"][0]["id"]
    client.put(f"{base}/jeux/{jeux['Grosse commande']}/valeurs", json={"valeurs": {str(variable): "Durand"}})
    vid = client.get(f"/api/cases/{cid}").json()["current_version_id"]

    vu = client.get(f"/api/cases/{cid}/versions/{vid}/apercu-donnees", params={"dataset_id": jeux["Grosse commande"]})
    inconnu = client.get(f"/api/cases/{cid}/versions/{vid}/apercu-donnees", params={"dataset_id": 999999})

    assert vu.status_code == 200, vu.text
    assert "Alors le client Durand est servi" in vu.json()["texte"] and vu.json()["jeu"] == "Grosse commande"
    assert inconnu.status_code == 404
