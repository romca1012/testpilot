"""Réglages d'instance — la valeur qui s'applique, et **d'où elle vient**.

⚠️ **Ce que ce fichier empêche.** Un réglage a trois sources possibles : la base (posée depuis
l'écran), la variable d'environnement du serveur, le défaut du code. La base l'emporte. Une
installation qui affiche la valeur sans dire d'où elle sort produit exactement une scène :
l'exploitant pose `TESTPILOT_SERVICE_ACCOUNT`, redémarre, voit autre chose, et cherche pendant
une heure une panne qui n'existe pas. La provenance est donc une donnée de l'API, testée ici.

Le second invariant est la **fermeture du vocabulaire** : une table clé/valeur qui accepte
n'importe quelle clé devient un dépotoir où plus personne ne sait ce qui est réellement lu. C'est
le défaut que `erreurs.CATALOGUE` évite déjà pour les codes d'erreur ; `CLES_CONNUES` le fait ici.
"""
import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api.app import app
from testpilot.api.deps import get_conn
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import SettingRepo, _DEFAUTS_USINE

CLE = "service_account_name"


@pytest.fixture
def conn(tmp_path):
    c = get_initialized_db(tmp_path / "reglages.db")
    yield c
    c.close()


@pytest.fixture
def client(conn):
    app.dependency_overrides[get_conn] = lambda: conn
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ── La résolution, et sa provenance ──────────────────────────────────────────

def test_sans_rien_de_pose_c_est_le_defaut_du_code(conn):
    valeur, source = SettingRepo(conn).resoudre(CLE)
    assert valeur == config.SERVICE_ACCOUNT_NAME
    assert source == "default"


def test_la_variable_d_environnement_est_annoncee_comme_telle(conn, monkeypatch):
    """L'exploitant qui a configuré son serveur doit VOIR que c'est sa valeur qui s'applique."""
    monkeypatch.setattr(config, "SERVICE_ACCOUNT_NAME", "Robot de la recette")
    assert SettingRepo(conn).resoudre(CLE) == ("Robot de la recette", "env")


def test_la_base_l_emporte_sur_l_environnement_et_le_dit(conn, monkeypatch):
    monkeypatch.setattr(config, "SERVICE_ACCOUNT_NAME", "Robot de la recette")
    SettingRepo(conn).ecrire(CLE, "Compte QA", par="chef")
    assert SettingRepo(conn).resoudre(CLE) == ("Compte QA", "db")


def test_effacer_rend_la_main_a_l_environnement(conn, monkeypatch):
    """⚠️ Une valeur vide SUPPRIME la ligne au lieu d'écrire une chaîne vide. « Pas de réglage »
    et « réglé à rien » ne sont pas le même fait — et sans cette distinction, un réglage posé par
    erreur serait définitif : plus aucun moyen de revenir à la configuration du serveur."""
    monkeypatch.setattr(config, "SERVICE_ACCOUNT_NAME", "Robot de la recette")
    reglages = SettingRepo(conn)
    reglages.ecrire(CLE, "Compte QA")
    reglages.ecrire(CLE, "   ")          # blancs seuls = vide
    assert reglages.resoudre(CLE) == ("Robot de la recette", "env")
    assert conn.execute("SELECT COUNT(*) AS n FROM app_setting").fetchone()["n"] == 0


def test_les_valeurs_d_usine_suivent_config(conn):
    """⚠️ La même valeur existe à DEUX endroits : le défaut de `config.py` et la table
    `_DEFAUTS_USINE`, qui sert à distinguer « l'exploitant a posé une variable » de « personne
    n'a rien réglé ». Si elles divergent, l'écran annoncera « variable d'environnement » à des
    installations qui n'en ont aucune — un mensonge discret et jamais détecté autrement.

    Même patron que la comparaison Python ↔ SQL du statut de lecture : deux formes d'une valeur,
    un test qui les confronte."""
    for attribut, usine in _DEFAUTS_USINE.items():
        assert usine == getattr(config, attribut), (
            f"{attribut} : le défaut de config.py a changé sans mettre à jour _DEFAUTS_USINE")


# ── Le vocabulaire est fermé ─────────────────────────────────────────────────

def test_une_cle_inconnue_est_refusee(conn):
    with pytest.raises(ValueError):
        SettingRepo(conn).ecrire("couleur_du_bandeau", "bleu")
    with pytest.raises(ValueError):
        SettingRepo(conn).resoudre("couleur_du_bandeau")


# ── L'API ────────────────────────────────────────────────────────────────────

def test_l_api_expose_la_valeur_ET_sa_provenance(client):
    lignes = client.get("/api/settings").json()
    assert [l["key"] for l in lignes] == [CLE]
    assert lignes[0]["source"] == "default"
    assert lignes[0]["description"], "un réglage sans explication est un réglage qu'on n'ose pas toucher"


def test_l_api_enregistre_puis_efface(client):
    maj = client.patch(f"/api/settings/{CLE}", json={"value": "Compte QA"}).json()
    assert (maj["value"], maj["source"]) == ("Compte QA", "db")

    efface = client.patch(f"/api/settings/{CLE}", json={"value": ""}).json()
    assert (efface["value"], efface["source"]) == (config.SERVICE_ACCOUNT_NAME, "default")


def test_l_api_refuse_une_cle_inconnue_avec_un_code_stable(client):
    r = client.patch("/api/settings/couleur_du_bandeau", json={"value": "bleu"})
    assert r.status_code == 422
    # Le code RFC 9457 est le contrat : c'est lui qu'un écran teste, jamais la phrase française.
    assert r.json()["code"] == "requete_invalide"
