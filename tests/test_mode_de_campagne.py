"""Le MODE D'EXÉCUTION d'une campagne commande les GESTES qu'elle accepte (2026-08-04).

⚠️ **Le défaut que ce fichier empêche.** Avant, le mode se posait résultat par résultat : chaque
ligne d'une campagne portait à la fois « Lancer » (en haut) et « + Résultat » (à droite). Deux
gestes proposés en permanence, aucun qui s'impose — donc un historique où le manuel et
l'automatique se mélangent sans que personne l'ait voulu, et un pourcentage de complétion dont
plus personne ne peut dire ce qu'il mesure.

Le mode remonte donc à la CAMPAGNE, choisi à sa création. Ce fichier vérifie que ce choix
**engage l'API**, et pas seulement l'écran :

- une campagne **automatique** se LANCE, et refuse la saisie d'un résultat à la main ;
- une campagne **manuelle** se SAISIT, et refuse d'être lancée ;
- un mode inconnu est refusé à la création (une campagne sans mode valable ne saurait rien faire).

⚠️ **Les refus portent des CODES d'erreur**, pas seulement des phrases : c'est le code que
l'écran teste pour proposer la bonne réparation. Brancher sur le français casserait à la première
reformulation, sans que personne le voie venir (contrat RFC 9457).

La concordance en BASE — un résultat ne peut pas être d'un autre mode que sa campagne, même écrit
par un script qui ne passe pas par l'API — est testée dans `test_migration_27.py` : c'est un
trigger, pas une règle de route.
"""
import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import app as app_mod


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "modes.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return TestClient(app_mod.app)


def _campagne(client, mode: str):
    """Un projet, un cas, une campagne du mode demandé — le décor minimal des deux gestes."""
    pid = client.post("/api/projects", json={"name": "P"}).json()["id"]
    mid = client.post(f"/api/projects/{pid}/modules", json={"name": "M"}).json()["id"]
    cid = client.post(f"/api/modules/{mid}/cases/manual", json={
        "title": "Nominal", "test_steps": ["a"], "expected_result": "r"}).json()["id"]
    run = client.post(f"/api/projects/{pid}/runs", json={
        "name": f"Recette {mode}", "selection_mode": "frozen", "case_ids": [cid], "mode": mode})
    assert run.status_code == 201, run.text
    return run.json()["id"], cid


# ── Le mode se choisit à la création, et se relit ────────────────────────────

def test_le_mode_choisi_a_la_creation_est_celui_que_l_API_rend(client):
    """Sans cette relecture, l'écran ne saurait pas quel geste proposer — et retomberait sur les
    deux, c'est-à-dire sur l'écran d'avant."""
    rid, _ = _campagne(client, "manuelle")
    assert client.get(f"/api/runs/{rid}").json()["run"]["mode"] == "manuelle"


def test_le_mode_par_defaut_est_AUTOMATIQUE(client):
    """C'est ce que TestPilot sait faire de plus, et ce qui distingue le produit. Le manuel est un
    choix délibéré, jamais une valeur dans laquelle on tombe faute d'avoir répondu."""
    pid = client.post("/api/projects", json={"name": "P"}).json()["id"]
    r = client.post(f"/api/projects/{pid}/runs", json={"name": "R", "selection_mode": "all"})
    assert r.json()["mode"] == "automatique"


def test_un_mode_inconnu_est_refuse_a_la_creation(client):
    """Une campagne dont le mode ne veut rien dire ne saurait ni se lancer ni se saisir : elle
    naîtrait inutilisable, et le refus n'arriverait qu'au premier geste."""
    pid = client.post("/api/projects", json={"name": "P"}).json()["id"]
    r = client.post(f"/api/projects/{pid}/runs", json={
        "name": "R", "selection_mode": "all", "mode": "semi-automatique"})
    assert r.status_code == 422
    assert "automatique" in r.json()["detail"] and "manuelle" in r.json()["detail"]


# ── Une campagne MANUELLE ne se lance pas ────────────────────────────────────

def test_lancer_une_campagne_MANUELLE_est_refuse(client):
    """🔴 Sans cette garde, le lancement produirait des exécutions machine dans une campagne dont
    tout l'historique doit être humain — et le trigger de la base les refuserait une par une, sans
    que personne ne comprenne pourquoi la campagne reste vide."""
    rid, _ = _campagne(client, "manuelle")

    r = client.post(f"/api/runs/{rid}/launch")

    assert r.status_code == 409
    assert r.json()["code"] == "campagne_manuelle"
    # Le message doit dire QUOI FAIRE, pas seulement « non » : sinon l'utilisateur conclut à une
    # panne de l'outil plutôt qu'à un mode mal choisi.
    assert "à la main" in r.json()["detail"]


# ── Une campagne AUTOMATIQUE ne se saisit pas ────────────────────────────────

def test_saisir_un_resultat_dans_une_campagne_AUTOMATIQUE_est_refuse(client):
    """L'autre moitié de la règle. Une saisie humaine glissée dans une campagne automatique rendrait
    son « 100 % vert » impossible à interpréter : on ne saurait plus ce qui a réellement tourné."""
    rid, cid = _campagne(client, "automatique")

    r = client.post(f"/api/runs/{rid}/cases/{cid}/results", json={"statut": "passed"})

    assert r.status_code == 409
    assert r.json()["code"] == "campagne_automatique"
    assert "manuelle" in r.json()["detail"]


def test_saisir_un_resultat_dans_une_campagne_MANUELLE_passe(client):
    """Le pendant positif : sans lui, les deux tests ci-dessus seraient satisfaits par une API qui
    refuse tout le monde."""
    rid, cid = _campagne(client, "manuelle")

    r = client.post(f"/api/runs/{rid}/cases/{cid}/results", json={"statut": "passed"})

    assert r.status_code == 201
    assert r.json()["mode"] == "manuelle"
