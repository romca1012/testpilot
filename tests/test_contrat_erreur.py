"""Le CONTRAT D'ERREUR de l'API — RFC 9457 (lot B, 2026-07-24).

**Le défaut corrigé.** L'API répondait `{"detail": "La connexion du projet « X » est incomplète…"}`.
Un client qui veut *réagir* — proposer d'ouvrir l'écran des projets, réessayer, ignorer — n'avait
qu'une **phrase française** à interpréter. Corriger une faute de frappe dans un message cassait
ce client, en silence.

Le comble : les codes **existaient déjà** dans les services (`no_connection`, `duplicate`…) ; les
routes les jetaient pour ne garder que le texte.

Ce que ces tests figent :
  • toute erreur rend la MÊME forme, quelle que soit la route ;
  • `code` est stable et fait partie du contrat ; `detail` reste libre d'évoluer ;
  • une situation métier = un code = un statut, partout ;
  • un code inventé est refusé à la construction — sinon il finirait en production.
"""

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import app as app_mod
from testpilot.api.erreurs import CATALOGUE, ErreurMetier, depuis_service


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return TestClient(app_mod.app)


def _projet(client, **champs) -> int:
    corps = {"name": "Recette", "base_url": "http://x:8069", "database": "db",
             "username": "qa", "password": "p"}
    corps.update(champs)
    return client.post("/api/projects", json=corps).json()["id"]


# ── La forme ─────────────────────────────────────────────────────────────────

def test_une_erreur_metier_rend_la_forme_RFC_9457(client):
    pid = _projet(client, name="Sans mot de passe", password="")
    mid = client.post(f"/api/projects/{pid}/modules", json={"name": "M"}).json()["id"]

    r = client.post(f"/api/modules/{mid}/cases", json={"spec_content": "Une spec"})

    assert r.status_code == 409
    assert r.headers["content-type"].startswith("application/problem+json")
    corps = r.json()
    assert corps["code"] == "connexion_incomplete"          # ← l'API STABLE
    assert corps["type"].endswith("/connexion_incomplete")
    assert corps["title"] == "La connexion du projet est incomplète"
    assert corps["status"] == 409
    assert corps["instance"] == f"/api/modules/{mid}/cases"
    assert "le mot de passe" in corps["detail"]             # ← la phrase pour l'humain


def test_le_client_n_a_JAMAIS_besoin_de_lire_le_francais(client):
    """La garantie qui justifie le lot : décider sur `code`, jamais sur `detail`.

    ⚠️ `detail` doit rester libre d'évoluer — corriger une tournure ne doit casser personne.
    C'est précisément ce qu'un client qui teste la phrase empêche.
    """
    pid = _projet(client)
    client.post(f"/api/projects/{pid}/modules", json={"name": "Doublon"})
    r = client.post(f"/api/projects/{pid}/modules", json={"name": "Doublon"})

    assert r.json()["code"] == "nom_deja_pris"
    assert r.status_code == 409


def test_les_erreurs_NON_converties_rendent_la_meme_forme(client):
    """Une `HTTPException` restée telle quelle ne doit pas produire un second format : un client
    n'a jamais à gérer deux formes d'erreur selon la route qu'il appelle."""
    r = client.get("/api/cases/999999")

    assert r.status_code == 404
    corps = r.json()
    assert corps["code"] == "introuvable"
    assert set(corps) == {"type", "title", "status", "detail", "instance", "code"}


def test_UNE_situation_metier_UN_code_partout(client):
    """La même cause devait déjà rendre le même code, quelle que soit la porte d'entrée.

    ⚠️ Avant ce lot, la connexion incomplète rendait **422 sur l'exploration** et **409 sur les
    trois autres portes** : un client devait connaître la route pour savoir quoi tester.
    """
    pid = _projet(client, name="Incomplet", password="")
    mid = client.post(f"/api/projects/{pid}/modules", json={"name": "M"}).json()["id"]
    # ⚠️ Un cas dans la campagne : sans lui, le lancement répond « campagne vide » — le diagnostic
    # le plus précis quand les deux sont vrais (ordre voulu, lot 1). Le test doit isoler la cause
    # qu'il prétend vérifier, sinon il vérifie autre chose.
    client.post(f"/api/modules/{mid}/cases/manual",
                json={"title": "Un cas", "test_steps": ["a"], "expected_result": "ok"})
    rid = client.post(f"/api/projects/{pid}/runs",
                      json={"name": "C", "selection_mode": "all"}).json()["id"]

    portes = [
        client.post(f"/api/projects/{pid}/exploration"),
        client.post(f"/api/modules/{mid}/cases", json={"spec_content": "Une spec"}),
        client.post(f"/api/runs/{rid}/launch"),
    ]
    for r in portes:
        assert r.json()["code"] == "connexion_incomplete", r.json()
        assert r.status_code == 409


# ── Le catalogue ─────────────────────────────────────────────────────────────

def test_un_code_INVENTE_est_refuse_a_la_construction():
    """Brutal, et délibérément : un code absent du catalogue passerait sinon en production, et un
    client bâtirait sa logique sur une valeur que personne ne s'est engagé à maintenir."""
    with pytest.raises(ValueError, match="code d'erreur inconnu"):
        ErreurMetier("je_nexiste_pas", "peu importe")


def test_les_codes_des_services_sont_TOUS_traduits():
    """Les services portent leurs propres codes (hérités). Un code non traduit tomberait
    silencieusement sur `non_gere` — une erreur juste, mais muette pour le client."""
    codes_services = [
        "not_found", "duplicate", "no_connection", "no_version", "needs_review",
        "invalid_spec", "invalid_metier", "invalid_state", "empty", "already_running", "archived",
    ]
    for code in codes_services:
        traduit = depuis_service(code, "détail")
        assert traduit.code != "non_gere", f"{code} n'est pas traduit"
        assert traduit.code in CATALOGUE


def test_chaque_code_du_catalogue_porte_un_statut_et_un_titre():
    for code, (statut, titre) in CATALOGUE.items():
        assert 400 <= statut < 600, code
        assert titre and titre[0].isupper(), code
