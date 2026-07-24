"""Lot 2 du chemin de déploiement (2026-07-24) : **sortir de la machine du développeur**.

Cible arrêtée par le porteur : un **serveur interne**, **plusieurs testeurs**. Deux conséquences
que ces tests figent :

1. **Le secret de connexion ne dort plus en clair.** Un `SELECT * FROM project` rendait les
   identifiants de l'application testée — et la base part dans les sauvegardes.
2. **L'instance n'est plus grande ouverte.** Sans verrou, quiconque atteint le port pilote des
   tests contre l'application cible et lit les rapports.

⚠️ Ce qui est testé ici est un **verrou d'instance**, pas un système de comptes (hors V1, §8) : un
mot de passe partagé et un nom déclaré. Les tests le disent, pour qu'on ne prenne jamais ce nom
pour une identité vérifiée.
"""

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import access
from testpilot.api import app as app_mod
from testpilot.store import secrets as secrets_mod
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import ProjectRepo


@pytest.fixture
def cle(tmp_path, monkeypatch):
    """Une clé de chiffrement propre à chaque test, hors du dépôt."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "SECRET_KEY", "")
    return tmp_path


@pytest.fixture
def conn(tmp_path, cle):
    c = get_initialized_db(tmp_path / "sec.db")
    yield c
    c.close()


# ── 1. Le secret au repos ─────────────────────────────────────────────────────

def test_le_mot_de_passe_n_est_PAS_lisible_dans_la_base(conn):
    """Le test qui compte : ouvrir la base et ne PAS y trouver le mot de passe."""
    pid = ProjectRepo(conn).create(name="Recette", base_url="http://x", database="db",
                                   username="qa", password="s3cr3t")

    brut = conn.execute("SELECT password FROM project WHERE id=?", (pid,)).fetchone()["password"]
    assert "s3cr3t" not in brut
    assert brut.startswith("enc:v1:")  # format reconnaissable : ni clair, ni base64 ambigu

    # …et l'outil, lui, sait toujours s'en servir.
    assert ProjectRepo(conn).get(pid)["password"] == "s3cr3t"


def test_l_edition_du_mot_de_passe_chiffre_aussi(conn):
    pid = ProjectRepo(conn).create(name="Recette", password="ancien")
    ProjectRepo(conn).update_connection(pid, password="nouveau")

    brut = conn.execute("SELECT password FROM project WHERE id=?", (pid,)).fetchone()["password"]
    assert "nouveau" not in brut
    assert ProjectRepo(conn).get(pid)["password"] == "nouveau"


def test_toutes_les_lectures_dechiffrent_pas_seulement_get(conn):
    """`list_all`, `first`, `find_by_name` servent le runtime autant que `get` : si l'une d'elles
    rendait le jeton chiffré, la connexion échouerait sur un « mot de passe invalide » dont la
    vraie cause serait invisible."""
    ProjectRepo(conn).create(name="Recette", password="s3cr3t")
    assert ProjectRepo(conn).list_all()[0]["password"] == "s3cr3t"
    assert ProjectRepo(conn).first()["password"] == "s3cr3t"
    assert ProjectRepo(conn).find_by_name("Recette")["password"] == "s3cr3t"


def test_une_valeur_vide_reste_vide(conn):
    """L'absence de secret n'est pas un secret : la chiffrer produirait un jeton, donc un projet
    qui aurait l'air d'avoir un mot de passe — et la garde de connexion ne le refuserait plus."""
    pid = ProjectRepo(conn).create(name="Sans mot de passe", password="")
    assert conn.execute("SELECT password FROM project WHERE id=?",
                        (pid,)).fetchone()["password"] == ""
    assert ProjectRepo(conn).get(pid)["password"] == ""


def test_la_migration_reprend_les_secrets_deja_stockes_en_clair(tmp_path, monkeypatch):
    """Une base d'avant le 2026-07-24 porte des mots de passe en clair : la migration 21 les reprend."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "SECRET_KEY", "")
    chemin = tmp_path / "ancienne.db"

    conn = get_initialized_db(chemin)
    conn.execute("INSERT INTO project (name, description, connector_type, base_url, database,"
                 " username, password, created_at) VALUES"
                 " ('Vieux','','odoo','http://x','db','qa','EN_CLAIR',datetime('now'))")
    conn.execute("PRAGMA user_version = 20")  # état d'avant la migration
    conn.commit()
    conn.close()

    conn = get_initialized_db(chemin)
    try:
        brut = conn.execute("SELECT password FROM project").fetchone()["password"]
        assert "EN_CLAIR" not in brut
        assert ProjectRepo(conn).get(1)["password"] == "EN_CLAIR"  # toujours utilisable
    finally:
        conn.close()


def test_la_migration_est_rejouable_sans_double_chiffrement(conn):
    """Rejouer ne doit pas chiffrer un jeton déjà chiffré — le mot de passe deviendrait illisible."""
    from testpilot.store.db import _migrate_21_chiffrer_secrets

    pid = ProjectRepo(conn).create(name="Recette", password="s3cr3t")
    _migrate_21_chiffrer_secrets(conn)
    _migrate_21_chiffrer_secrets(conn)
    assert ProjectRepo(conn).get(pid)["password"] == "s3cr3t"


def test_une_cle_perdue_ne_fait_PAS_passer_le_jeton_pour_un_mot_de_passe(conn, monkeypatch):
    """⚠️ Le piège à éviter : rendre le texte chiffré « au cas où ».

    L'outil tenterait de se connecter avec `enc:v1:…`, l'application répondrait « identifiants
    invalides », et personne ne saurait que la vraie cause est une clé changée. On rend une
    chaîne vide : la garde de connexion dira « mot de passe manquant », ce qui envoie corriger
    au bon endroit.
    """
    pid = ProjectRepo(conn).create(name="Recette", password="s3cr3t")
    monkeypatch.setattr(config, "SECRET_KEY",
                        secrets_mod._fernet().generate_key().decode())  # autre clé

    rendu = ProjectRepo(conn).get(pid)["password"]
    assert rendu == ""
    assert "enc:v1:" not in rendu


def test_la_cle_par_variable_d_environnement_prime_sur_le_fichier(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    cle = secrets_mod._fernet().generate_key().decode()
    monkeypatch.setattr(config, "SECRET_KEY", cle)

    jeton = secrets_mod.chiffrer("s3cr3t")
    assert secrets_mod.dechiffrer(jeton) == "s3cr3t"
    # Aucune clé n'a été écrite sur le disque : c'est tout l'intérêt de la variable d'environnement.
    assert not (tmp_path / ".secret_key").exists()


# ── 2. Le verrou d'instance ───────────────────────────────────────────────────

@pytest.fixture
def client_verrouille(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "ACCESS_PASSWORD", "entrez-moi")
    return TestClient(app_mod.app)


@pytest.fixture
def client_ouvert(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "ACCESS_PASSWORD", "")
    return TestClient(app_mod.app)


def test_sans_session_l_api_repond_401(client_verrouille):
    assert client_verrouille.get("/api/projects").status_code == 401


def test_le_mauvais_mot_de_passe_est_refuse(client_verrouille):
    r = client_verrouille.post("/api/auth/login", json={"password": "au hasard", "name": "Awa"})
    assert r.status_code == 401
    assert r.json()["authenticated"] is False
    assert client_verrouille.get("/api/projects").status_code == 401


def test_le_bon_mot_de_passe_ouvre_l_acces(client_verrouille):
    r = client_verrouille.post("/api/auth/login",
                               json={"password": "entrez-moi", "name": "Awa"})
    assert r.status_code == 200 and r.json()["authenticated"] is True
    assert client_verrouille.get("/api/projects").status_code == 200


def test_sans_verrou_configure_rien_n_est_bloque(client_ouvert):
    """Le mode poste isolé, celui d'avant : aucun formulaire, aucune gêne."""
    assert client_ouvert.get("/api/projects").status_code == 200
    session = client_ouvert.get("/api/auth/session").json()
    assert session["lock_enabled"] is False
    assert session["authenticated"] is True


def test_l_ecran_de_connexion_reste_atteignable(client_verrouille):
    """Verrouiller la route de connexion elle-même rendrait l'instance inutilisable."""
    assert client_verrouille.get("/api/health").status_code == 200
    assert client_verrouille.get("/api/auth/session").status_code == 200


def test_l_etat_du_verrou_est_VERIFIABLE_sans_entrer(client_verrouille):
    """⚠️ Trouvé en démarrant vraiment le serveur, pas par les tests.

    La procédure de déploiement demandait de vérifier une **ligne de journal** — qui n'apparaît
    jamais sous la commande `uvicorn` recommandée (uvicorn ne configure pas les journaux de
    l'application). L'exploitant croyait donc vérifier que son instance est verrouillée, et ne
    vérifiait rien. L'état est désormais exposé là où un `curl` le voit, sans session.

    ⚠️ Les deux cas sont testés SÉPARÉMENT : demander les deux clients dans un même test ferait
    appliquer la configuration de la seconde fixture aux deux — le test passerait ou échouerait
    pour une raison qui n'a rien à voir avec ce qu'il prétend vérifier.
    """
    assert client_verrouille.get("/api/health").json()["access_lock"] is True


def test_sans_verrou_la_sante_le_dit_aussi(client_ouvert):
    assert client_ouvert.get("/api/health").json()["access_lock"] is False


def test_un_jeton_falsifie_ne_passe_pas(client_verrouille):
    client_verrouille.cookies.set(access.COOKIE, "99999999999.Intrus.signaturebidon")
    assert client_verrouille.get("/api/projects").status_code == 401


def test_changer_le_mot_de_passe_invalide_les_sessions(client_verrouille, monkeypatch):
    """Le seul geste dont dispose l'équipe quand quelqu'un part : il doit mordre tout de suite."""
    client_verrouille.post("/api/auth/login", json={"password": "entrez-moi", "name": "Awa"})
    assert client_verrouille.get("/api/projects").status_code == 200

    monkeypatch.setattr(config, "ACCESS_PASSWORD", "un-autre-secret")
    assert client_verrouille.get("/api/projects").status_code == 401


def test_un_jeton_expire_est_refuse(monkeypatch):
    monkeypatch.setattr(config, "ACCESS_PASSWORD", "entrez-moi")
    monkeypatch.setattr(config, "SESSION_DAYS", 0)
    jeton = access.creer_jeton("Awa")
    import time as _t
    _t.sleep(0.01)
    assert access.lire_jeton(jeton) is None


# ── 3. Qui a fait quoi ────────────────────────────────────────────────────────

def test_le_nom_de_session_signe_les_cas_crees(client_verrouille):
    """Sans comptes, c'est ce qui répond à « qui a créé ce cas ? » sur un serveur partagé."""
    client_verrouille.post("/api/auth/login", json={"password": "entrez-moi", "name": "Awa"})
    pid = client_verrouille.post("/api/projects", json={
        "name": "Recette", "base_url": "http://x", "database": "db",
        "username": "qa", "password": "p"}).json()["id"]
    mid = client_verrouille.post(f"/api/projects/{pid}/modules", json={"name": "M"}).json()["id"]

    client_verrouille.post(f"/api/modules/{mid}/cases/manual", json={
        "title": "Cas signé", "test_steps": ["a"], "expected_result": "ok"})

    conn = get_initialized_db(config.DB_PATH)
    try:
        auteur = conn.execute("SELECT author FROM test_case WHERE title='Cas signé'").fetchone()
    finally:
        conn.close()
    assert auteur["author"] == "Awa"


def test_sans_nom_l_auteur_reste_ANONYME_et_n_est_pas_invente(client_ouvert):
    """⚠️ Vide se lit « on ne sait pas ». Écrire « admin » ferait signer un cas par quelqu'un qui
    n'existe pas — « affiché ≠ réel » appliqué à l'auteur d'un test."""
    from starlette.requests import Request

    requete = Request({"type": "http", "headers": [], "path": "/api/x", "method": "GET"})
    assert access.utilisateur_de(requete) == ""
