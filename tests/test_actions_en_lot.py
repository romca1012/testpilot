"""Les ACTIONS EN LOT — le quotidien du QA (lot C, 2026-07-24).

**Le constat de l'audit.** Composer une campagne de 20 cas demandait 20 gestes ; changer leur
priorité, 20 de plus. C'est là que le testeur passe sa journée, et c'est là que l'outil était le
plus pauvre.

**Pourquoi un endpoint et non N appels depuis l'écran.** Vingt requêtes déplaceraient le problème
sans le résoudre : la moitié peut échouer et laisser le référentiel dans un état que personne n'a
voulu. Une action, une requête, **un compte rendu** — qui distingue ce qui a été traité de ce qui
a été ignoré.
"""

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import access, app as app_mod
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import UserRepo


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return TestClient(app_mod.app)


def _creer_compte(username: str, password: str) -> None:
    """Un compte réel — depuis le lot 2026-08-07, se connecter exige un compte qui existe
    vraiment, plus un simple nom déclaré au clavier."""
    conn = get_initialized_db(config.DB_PATH)
    try:
        UserRepo(conn).create(username=username, password_hash=access.hacher_mot_de_passe(password),
                              role=access.ROLE_TESTEUR)
    finally:
        conn.close()


def _projet(client, nb_cas: int = 3):
    pid = client.post("/api/projects", json={
        "name": "Recette", "base_url": "http://x", "database": "db",
        "username": "qa", "password": "p"}).json()["id"]
    mid = client.post(f"/api/projects/{pid}/modules", json={"name": "Demandes"}).json()["id"]
    ids = [client.post(f"/api/modules/{mid}/cases/manual", json={
        "title": f"Cas {i + 1}", "test_steps": ["a"], "expected_result": "ok"}).json()["id"]
        for i in range(nb_cas)]
    return pid, mid, ids


# ── Priorité en lot ──────────────────────────────────────────────────────────

def test_changer_la_priorite_de_N_cas_en_UNE_requete(client):
    pid, _, ids = _projet(client, 3)

    r = client.patch("/api/cases/lot", json={"case_ids": ids, "priority": "high"})

    assert r.status_code == 200
    assert r.json() == {"traites": 3, "ignores": 0}
    assert {c["priority"] for c in client.get(f"/api/cases?project_id={pid}").json()["items"]} == {"high"}


def test_un_cas_DISPARU_est_ignore_et_COMPTE_pas_fatal(client):
    """⚠️ Entre l'affichage de la liste et le clic, un cas a pu être supprimé par quelqu'un
    d'autre. Refuser toute l'action pour un élément disparu ferait perdre les autres — mais le
    taire ferait croire à un succès complet. On traite, et on dit combien on a ignoré."""
    pid, _, ids = _projet(client, 2)

    r = client.patch("/api/cases/lot", json={"case_ids": ids + [999999], "priority": "low"})

    assert r.json() == {"traites": 2, "ignores": 1}


def test_une_priorite_invalide_est_REFUSEE_avec_son_code(client):
    _, _, ids = _projet(client, 1)

    r = client.patch("/api/cases/lot", json={"case_ids": ids, "priority": "urgentissime"})

    assert r.status_code == 422
    assert r.json()["code"] == "requete_invalide"


def test_une_selection_VIDE_est_refusee(client):
    """Sans ce refus, l'action « réussirait » en ne faisant rien — un succès trompeur."""
    r = client.patch("/api/cases/lot", json={"case_ids": [], "priority": "high"})

    assert r.status_code == 422
    assert "aucun cas" in r.json()["detail"]


def test_une_selection_ENORME_est_bornee(client):
    """La borne n'est pas décorative : sans elle, une requête devient une transaction longue qui
    bloque la base pour tous les autres testeurs."""
    r = client.patch("/api/cases/lot",
                     json={"case_ids": list(range(1, 2000)), "priority": "high"})

    assert r.status_code == 422
    assert "maximum" in r.json()["detail"]


def test_les_doublons_ne_sont_comptes_qu_une_fois(client):
    """Une sélection peut contenir deux fois le même identifiant (clics répétés) : le compte
    rendu doit rester juste, sinon il annonce plus de travail qu'il n'en a fait."""
    _, _, ids = _projet(client, 1)

    r = client.patch("/api/cases/lot", json={"case_ids": ids * 3, "priority": "high"})

    assert r.json() == {"traites": 1, "ignores": 0}


# ── Suppression en lot ───────────────────────────────────────────────────────

def test_supprimer_N_cas_en_UNE_requete_SANS_rien_detruire(client):
    pid, _, ids = _projet(client, 3)

    r = client.post("/api/cases/lot/suppression", json={"case_ids": ids[:2]})

    assert r.json() == {"traites": 2, "ignores": 0}
    restants = [c["id"] for c in client.get(f"/api/cases?project_id={pid}").json()["items"]]
    assert restants == [ids[2]]
    # §7 : rien n'est détruit — les deux cas sont à la corbeille, donc restaurables.
    corbeille = client.get(f"/api/projects/{pid}/corbeille").json()
    assert {e["titre"] for e in corbeille if e["type"] == "cas"} == {"Cas 1", "Cas 2"}


def test_la_suppression_en_lot_trace_QUI(client):
    """Sur un serveur partagé, une suppression de masse sans auteur est ingérable."""
    _creer_compte("Awa", "secret")
    r = client.post("/api/auth/login", json={"username": "Awa", "password": "secret"})
    assert r.status_code == 200
    pid, _, ids = _projet(client, 2)

    client.post("/api/cases/lot/suppression", json={"case_ids": ids})

    corbeille = client.get(f"/api/projects/{pid}/corbeille").json()
    assert {e["deleted_by"] for e in corbeille if e["type"] == "cas"} == {"Awa"}


# ── Composer une campagne depuis une sélection ───────────────────────────────

def test_creer_une_campagne_DEPUIS_une_selection(client):
    """Le geste que le lot C vise : 20 cas cochés → une campagne, en une fois.

    L'API le permettait déjà (`selection_mode: frozen`) — c'est l'écran qui ne l'exposait pas.
    Ce test fige le contrat dont l'interface dépend.
    """
    pid, _, ids = _projet(client, 3)

    r = client.post(f"/api/projects/{pid}/runs", json={
        "name": "Campagne du jour", "selection_mode": "frozen", "case_ids": ids[:2]})

    assert r.status_code == 201
    assert r.json()["case_count"] == 2
    detail = client.get(f"/api/runs/{r.json()['id']}").json()
    assert [c["id"] for c in detail["cases"]] == ids[:2]
