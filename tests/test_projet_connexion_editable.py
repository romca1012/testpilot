"""Éditer la CONNEXION d'un projet — étape 1 du flux « projet → connecteur → exploration ».

Avant : `PATCH /api/projects/{id}` acceptait un corps portant les champs de connecteur et **les
jetait en silence**. Une faute de frappe dans l'URL obligeait à supprimer le projet — donc à
perdre ses modules, ses cas et tout son historique. C'est aussi le préalable à l'exploration :
on ne cartographie pas une application dont on ne peut pas corriger l'adresse.

L'invariant le plus important est ici celui du MOT DE PASSE : l'API ne le renvoie jamais
(write-only, décision `0005`), donc tout écran d'édition l'affiche vide. Si ce vide écrasait le
secret enregistré, ouvrir puis enregistrer un projet sans rien changer casserait toutes ses
exécutions.
"""

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import app as app_mod
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import ProjectRepo


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return TestClient(app_mod.app)


def _projet(client, **kw):
    body = {"name": "Portail Sapian", "connector_type": "odoo",
            "base_url": "http://localhost:10017", "database": "sapian",
            "username": "admin", "password": "secret-initial"}
    body.update(kw)
    return client.post("/api/projects", json=body).json()["id"]


def _mot_de_passe(pid: int) -> str:
    conn = get_initialized_db(config.DB_PATH)
    try:
        return ProjectRepo(conn).get(pid)["password"]
    finally:
        conn.close()


def test_la_connexion_est_editable(client):
    pid = _projet(client)

    r = client.patch(f"/api/projects/{pid}", json={
        "base_url": "http://localhost:9999", "database": "autre", "username": "qa"})

    assert r.status_code == 200
    assert r.json()["base_url"] == "http://localhost:9999"
    assert r.json()["database"] == "autre"
    assert r.json()["username"] == "qa"


def test_enregistrer_SANS_toucher_au_mot_de_passe_ne_l_efface_PAS(client):
    """⚠️ L'invariant vital. L'API ne renvoie jamais le secret, donc l'écran le raffiche vide.

    Si ce vide était pris pour « efface-le », ouvrir un projet et cliquer « Enregistrer » sans
    rien modifier détruirait la connexion — et toutes les exécutions du projet échoueraient, sans
    que personne comprenne pourquoi.
    """
    pid = _projet(client)

    client.patch(f"/api/projects/{pid}", json={"name": "Portail Sapian (recette)"})

    assert _mot_de_passe(pid) == "secret-initial"


def test_le_mot_de_passe_ne_change_QUE_s_il_est_fourni(client):
    pid = _projet(client)

    client.patch(f"/api/projects/{pid}", json={"password": "nouveau-secret"})

    assert _mot_de_passe(pid) == "nouveau-secret"


def test_vider_le_mot_de_passe_exige_une_chaine_vide_EXPLICITE(client):
    """`None` ne vide jamais ; `""` vide. Les deux gestes doivent rester distinguables."""
    pid = _projet(client)

    client.patch(f"/api/projects/{pid}", json={"password": ""})

    assert _mot_de_passe(pid) == ""


def test_le_mot_de_passe_n_est_JAMAIS_renvoye(client):
    """Décision `0005` : write-only. Le vérifier ici aussi, parce que cette route est le seul
    endroit où un secret transite dans les deux sens."""
    pid = _projet(client)

    r = client.patch(f"/api/projects/{pid}", json={"password": "nouveau-secret"})

    assert "password" not in r.json()
    assert "nouveau-secret" not in r.text


def test_renommer_ne_touche_pas_a_la_connexion(client):
    """La régression que ce chantier corrige, prise par l'autre bout : un PATCH de nom ne doit
    rien changer d'autre."""
    pid = _projet(client, connector_version="17")

    r = client.patch(f"/api/projects/{pid}", json={"name": "Nouveau nom"})

    assert r.json()["name"] == "Nouveau nom"
    assert r.json()["base_url"] == "http://localhost:10017"
    assert r.json()["database"] == "sapian"
    assert r.json()["username"] == "admin"
    # La VERSION (migration 38) suit la même règle que le reste de la connexion : absente du
    # corps du PATCH, elle ne bouge pas.
    assert r.json()["connector_version"] == "17"


# ── Calibration en écriture (migration 45, 2026-09-16) — éteinte par défaut, décidée par PATCH ──

def test_calibration_writes_enabled_est_eteinte_a_la_creation(client):
    pid = _projet(client)
    assert client.get("/api/projects").json()[0]["calibration_writes_enabled"] is False


def test_calibration_writes_enabled_est_activable_par_patch(client):
    pid = _projet(client)

    r = client.patch(f"/api/projects/{pid}", json={"calibration_writes_enabled": True})

    assert r.json()["calibration_writes_enabled"] is True


def test_calibration_writes_enabled_absent_du_corps_ne_change_rien(client):
    """Comme le mot de passe : absent du PATCH, `None` ne doit JAMAIS être pris pour « désactive-
    le » — sinon renommer un projet éteindrait silencieusement un réglage déjà activé."""
    pid = _projet(client)
    client.patch(f"/api/projects/{pid}", json={"calibration_writes_enabled": True})

    r = client.patch(f"/api/projects/{pid}", json={"name": "Renommé"})

    assert r.json()["calibration_writes_enabled"] is True


def test_un_nom_deja_pris_reste_un_409(client):
    _projet(client)
    pid2 = _projet(client, name="Autre projet")

    r = client.patch(f"/api/projects/{pid2}", json={"name": "portail sapian"})

    assert r.status_code == 409


def test_un_nom_vide_est_refuse(client):
    pid = _projet(client)

    assert client.patch(f"/api/projects/{pid}", json={"name": "   "}).status_code == 422


def test_projet_inconnu_404(client):
    assert client.patch("/api/projects/999", json={"name": "X"}).status_code == 404
