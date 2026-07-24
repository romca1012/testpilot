"""L'annuaire du domaine appartient au PROJET — `0005` appliqué à ce qui lui avait échappé.

Avant : un fichier par **type de connecteur** (`data/domain/odoo.json`). Deux projets sur Odoo
mais deux **instances** différentes — le portail d'un client, puis celui d'un autre — partageaient
une seule cartographie. Les tests du second auraient été générés depuis les routes et les champs
du premier.

C'est le défaut exact que `0005` a corrigé pour le runtime (« l'interface promet du multi-projet,
chaque run tape la config globale »), resté en place pour la connaissance du domaine. Et c'est une
source d'erreurs techniques indiagnosticables : le test échoue sur un sélecteur qui existe… mais
dans une autre application.

Ce que ces tests figent :
- la cartographie est rangée sous l'id du projet ;
- le repli sur l'ancien fichier est STRICT — même instance, sinon rien ;
- l'exploration refuse de partir sans connexion, et refuse de se dédoubler ;
- une mesure VIDE n'est jamais écrite (un échec ne doit pas ressembler à un domaine connu).
"""

import json

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import app as app_mod
from testpilot.api.services import exploration_service
from testpilot.generation import domain_model
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import ProjectRepo


@pytest.fixture(autouse=True)
def domaine_isole(tmp_path, monkeypatch):
    """Chaque test a son répertoire `domain` : on n'écrit jamais dans le vrai dépôt."""
    d = tmp_path / "domain"
    d.mkdir()
    monkeypatch.setattr(domain_model, "DOMAIN_DIR", d)
    domain_model._charger.cache_clear()
    return d


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    exploration_service._JOBS.clear()
    return TestClient(app_mod.app)


def _ecrire(chemin, base_url, pages=("/a", "/b")):
    chemin.write_text(json.dumps({
        "base_url": base_url, "mesure_le": "2026-07-17", "connector_type": "odoo",
        "pages": {p: {"champs": []} for p in pages}, "transitions": {},
    }, ensure_ascii=False), encoding="utf-8")


# ── Le rangement ──────────────────────────────────────────────────────────────

def test_la_cartographie_est_rangee_sous_l_id_du_projet(domaine_isole):
    projet = {"id": 7, "connector_type": "odoo", "base_url": "http://a"}
    _ecrire(domain_model.chemin_du_modele(7), "http://a")

    modele = domain_model.charger_modele(projet)

    assert modele is not None
    assert len(modele["pages"]) == 2
    assert domain_model.chemin_du_modele(7).name == "projet-7.json"


def test_deux_projets_ne_PARTAGENT_PAS_leur_cartographie(domaine_isole):
    """⚠️ Le cœur du défaut. Le projet 2 ne doit RIEN voir de la mesure du projet 1."""
    _ecrire(domain_model.chemin_du_modele(1), "http://client-a", pages=("/x", "/y", "/z"))

    projet2 = {"id": 2, "connector_type": "odoo", "base_url": "http://client-b"}

    assert domain_model.charger_modele(projet2) is None, (
        "le projet 2 hérite de la cartographie du projet 1 — les tests seraient générés "
        "depuis les routes d'une autre application")


# ── Le repli sur l'ancien fichier ─────────────────────────────────────────────

def test_le_repli_legacy_marche_pour_la_MEME_instance(domaine_isole):
    """L'existant ne doit pas être perdu : `odoo.json` a mesuré le projet réel."""
    _ecrire(domain_model.chemin_legacy("odoo"), "http://localhost:10017")
    projet = {"id": 1, "connector_type": "odoo", "base_url": "http://localhost:10017"}

    assert domain_model.charger_modele(projet) is not None


def test_le_repli_legacy_est_REFUSE_pour_une_AUTRE_instance(domaine_isole):
    """Sans cette garde, le repli réintroduirait le bug qu'on corrige : mieux vaut aucun modèle
    qu'un modèle faux — un modèle absent rend le smoke-check muet, un modèle faux le rend MENTEUR."""
    _ecrire(domain_model.chemin_legacy("odoo"), "http://client-a")
    projet = {"id": 1, "connector_type": "odoo", "base_url": "http://client-b"}

    assert domain_model.charger_modele(projet) is None


def test_le_repli_tolere_un_slash_final_et_la_casse(domaine_isole):
    _ecrire(domain_model.chemin_legacy("odoo"), "http://Localhost:10017/")
    projet = {"id": 1, "connector_type": "odoo", "base_url": "http://localhost:10017"}

    assert domain_model.charger_modele(projet) is not None


def test_sans_projet_aucun_modele(domaine_isole):
    assert domain_model.charger_modele(None) is None


# ── L'API d'exploration ───────────────────────────────────────────────────────

def _projet(client, **kw):
    body = {"name": "Portail", "connector_type": "odoo", "base_url": "http://localhost:10017",
            "database": "db", "username": "u", "password": "p"}
    body.update(kw)
    return client.post("/api/projects", json=body).json()["id"]


def test_l_etat_dit_qu_aucune_exploration_n_a_eu_lieu(client):
    pid = _projet(client)

    r = client.get(f"/api/projects/{pid}/exploration")

    assert r.status_code == 200
    assert r.json()["explored"] is False
    assert r.json()["pages"] == 0


def test_explorer_SANS_connexion_est_refuse_AVANT_de_lancer_un_navigateur(client):
    """Le message dit quoi faire. Sans ce garde-fou, le crawl échouerait après plusieurs secondes
    sur une erreur réseau que personne ne sait interpréter."""
    pid = _projet(client, base_url="")

    r = client.post(f"/api/projects/{pid}/exploration")

    # ⚠️ 409 depuis le contrat d'erreur du 2026-07-24, et non plus 422. La MÊME situation métier
    # (« connexion du projet incomplète ») renvoyait 422 ici et 409 sur les trois autres portes :
    # un client aurait dû connaître la route pour savoir quoi tester. Une situation, un code, un
    # statut — c'est tout l'intérêt d'un catalogue unique.
    assert r.status_code == 409
    assert r.json()["code"] == "connexion_incomplete"
    # Depuis le 2026-07-24, la garde couvre les QUATRE éléments (adresse, base, utilisateur, mot
    # de passe) et non plus la seule URL : explorer avec une connexion partielle produisait un
    # annuaire mesuré sur l'instance par défaut de la machine — un modèle qui ne décrit PAS ce
    # projet, et que rien à l'écran ne distinguait d'une vraie mesure.
    assert "l'adresse de l'application" in r.json()["detail"]
    assert "incomplète" in r.json()["detail"]


def test_deux_explorations_simultanees_sont_refusees(client, monkeypatch):
    """Deux crawls écriraient le même fichier : le dernier gagnerait et la mesure rendue serait
    un mélange de deux passages."""
    monkeypatch.setattr(exploration_service, "run_exploration", lambda *a, **k: None)
    pid = _projet(client)
    client.post(f"/api/projects/{pid}/exploration")
    # Le job reste `running` (la tâche de fond est neutralisée).

    r = client.post(f"/api/projects/{pid}/exploration")

    assert r.status_code == 409


def test_projet_inconnu_404(client):
    assert client.post("/api/projects/999/exploration").status_code == 404
    assert client.get("/api/projects/999/exploration").status_code == 404


# ── La tâche de fond ──────────────────────────────────────────────────────────

def test_une_mesure_VIDE_n_est_jamais_ecrite(domaine_isole, monkeypatch):
    """⚠️ Zéro page n'est pas une cartographie. L'écrire ferait passer un échec de connexion pour
    un domaine « connu mais vide », et la génération croirait n'avoir rien à explorer."""
    monkeypatch.setattr(exploration_service, "_crawl",
                        lambda connexion, max_pages: {"pages": {}, "transitions": {},
                                                      "onglets_internes": {}})
    exploration_service._JOBS["J"] = {"status": "running", "project_id": 3, "error": "", "resume": ""}

    exploration_service.run_exploration("J", project_id=3, connexion={"base_url": "http://a"})

    assert exploration_service._JOBS["J"]["status"] == "failed"
    assert not domain_model.chemin_du_modele(3).exists()


def test_une_mesure_reussie_est_datee_et_tracee(domaine_isole, monkeypatch):
    """La cartographie est une PHOTO : sans date ni méthode, elle est inexploitable."""
    monkeypatch.setattr(exploration_service, "_crawl", lambda connexion, max_pages: {
        "pages": {"/my": {"champs": [{"name": "x"}]}}, "transitions": {"/my": ["/other"]},
        "onglets_internes": {}})
    exploration_service._JOBS["J"] = {"status": "running", "project_id": 4, "error": "", "resume": ""}

    exploration_service.run_exploration(
        "J", project_id=4,
        connexion={"base_url": "http://a", "connector_type": "odoo", "nom": "Portail"})

    ecrit = json.loads(domain_model.chemin_du_modele(4).read_text(encoding="utf-8"))
    assert ecrit["mesure_le"], "une photo sans date est inexploitable"
    assert "aucun LLM" in ecrit["methode"], "la provenance doit être lisible dans le fichier"
    assert ecrit["project_id"] == 4
    assert ecrit["base_url"] == "http://a"
    assert exploration_service._JOBS["J"]["status"] == "done"


def test_un_plantage_du_crawl_ne_laisse_pas_le_job_en_cours(domaine_isole, monkeypatch):
    def boum(connexion, max_pages):
        raise RuntimeError("navigateur mort")
    monkeypatch.setattr(exploration_service, "_crawl", boum)
    exploration_service._JOBS["J"] = {"status": "running", "project_id": 5, "error": "", "resume": ""}

    exploration_service.run_exploration("J", project_id=5, connexion={"base_url": "http://a"})

    assert exploration_service._JOBS["J"]["status"] == "failed"
    assert "navigateur mort" in exploration_service._JOBS["J"]["error"]
