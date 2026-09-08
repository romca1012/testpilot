"""Comptes utilisateurs + rôles (2026-08-07) — remplace le mot de passe unique partagé du lot 2.

Quatre invariants que ce fichier fige :

1. Un mot de passe est haché (jamais en clair, jamais deux fois le même hachage pour la même
   valeur — le sel protège ça), et un jeton de session est signé/vérifiable/expirable.
2. La connexion est désormais OBLIGATOIRE partout — plus de mode « poste isolé sans verrou ».
3. Le rôle `lecture_seule` ne peut RIEN écrire ; les autres rôles héritent des droits du
   précédent. Un changement de rôle ou une désactivation prend effet IMMÉDIATEMENT (pas
   seulement à la prochaine connexion) — vérifié en base à chaque requête, jamais depuis le
   jeton.
4. Seul un Admin gère les comptes (`/api/admin/users`) ; jamais de suppression définitive.
"""

from __future__ import annotations

import hashlib
import time

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import access
from testpilot.api import app as app_mod
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import ProjectRepo, UserRepo


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    c = get_initialized_db(tmp_path / "u.db")
    yield c
    c.close()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "u.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return TestClient(app_mod.app)


def _compte(client_ou_conn, username: str, password: str, role: str) -> int:
    """Crée un compte directement en base — plus rapide que de passer par l'API admin pour les
    tests qui ne vérifient pas cette API elle-même."""
    c = client_ou_conn if hasattr(client_ou_conn, "execute") else get_initialized_db(config.DB_PATH)
    return UserRepo(c).create(username=username,
                              password_hash=access.hacher_mot_de_passe(password), role=role)


def _connecte(client, username: str, password: str):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r


def test_cookie_de_session_est_secure_quand_le_profil_production_l_impose(
        client, monkeypatch):
    _compte(client, "secure-user", "mot-de-passe", access.ROLE_TESTEUR)
    monkeypatch.setattr(config, "COOKIE_SECURE", True)

    r = client.post("/api/auth/login", json={
        "username": "secure-user", "password": "mot-de-passe",
    })

    assert r.status_code == 200
    assert "Secure" in r.headers["set-cookie"]


def test_cookie_de_session_est_cantonne_au_sous_chemin_configure(client, monkeypatch):
    """Sans cette isolation (audit déploiement Scaleway, 2026-09-08), deux environnements
    TestPilot sur le MÊME domaine (ex. Traefik qui route /dev et /staging vers deux conteneurs)
    écraseraient silencieusement le cookie de session l'un de l'autre — `path=/` implicite le
    rend valide pour tout le domaine, identique par nom entre les deux environnements."""
    _compte(client, "chemin-user", "mot-de-passe", access.ROLE_TESTEUR)
    monkeypatch.setattr(config, "COOKIE_PATH", "/dev")

    r = client.post("/api/auth/login", json={
        "username": "chemin-user", "password": "mot-de-passe",
    })

    assert r.status_code == 200
    assert "Path=/dev" in r.headers["set-cookie"]


def test_la_deconnexion_efface_le_cookie_au_meme_sous_chemin(client, monkeypatch):
    """Un `path` différent entre la pose et l'effacement ferait échouer l'effacement : un
    navigateur n'efface un cookie que si (nom, path, domain) correspondent EXACTEMENT à
    l'original — la déconnexion semblerait fonctionner sans invalider le cookie d'origine."""
    _compte(client, "chemin-logout", "mot-de-passe", access.ROLE_TESTEUR)
    monkeypatch.setattr(config, "COOKIE_PATH", "/dev")
    client.post("/api/auth/login", json={"username": "chemin-logout", "password": "mot-de-passe"})

    r = client.post("/api/auth/logout")

    assert "Path=/dev" in r.headers["set-cookie"]


# ── 1. Mots de passe et jetons ────────────────────────────────────────────────

def test_un_mot_de_passe_hache_ne_se_relit_pas_en_clair():
    hache = access.hacher_mot_de_passe("s3cr3t")
    assert "s3cr3t" not in hache
    assert access.verifier_mot_de_passe("s3cr3t", hache) is True
    assert access.verifier_mot_de_passe("faux", hache) is False


def test_deux_comptes_au_meme_mot_de_passe_ont_des_hachages_DIFFERENTS():
    """Le sel est PAR mot de passe — sans lui, une égalité de hachage se lirait dans la base."""
    assert access.hacher_mot_de_passe("identique") != access.hacher_mot_de_passe("identique")


def test_un_hachage_historique_reste_valide_et_doit_etre_renforce():
    sel = bytes.fromhex("00" * 16)
    ancien = hashlib.pbkdf2_hmac("sha256", b"ancienmdp", sel, 200_000)
    hache = f"{sel.hex()}${ancien.hex()}"

    assert access.verifier_mot_de_passe("ancienmdp", hache) is True
    assert access.hachage_a_mettre_a_niveau(hache) is True
    assert access.hachage_a_mettre_a_niveau(access.hacher_mot_de_passe("nouveau")) is False


def test_un_jeton_se_relit_avec_le_bon_user_id_et_username(tmp_path, monkeypatch):
    # Sans clé de session en environnement, `creer_jeton` en CRÉE une sous `config.DATA_DIR` —
    # isolée ici, sinon elle atterrit dans le VRAI `data/` du poste (trouvé en CI, garde-fou
    # `conftest.py`).
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    jeton = access.creer_jeton(42, "Awa")
    assert access.lire_jeton(jeton) == (42, 1, "Awa")


def test_un_jeton_falsifie_est_refuse(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)  # même isolation que ci-dessus
    jeton = access.creer_jeton(1, "Awa")
    falsifie = jeton[:-4] + "0000"
    assert access.lire_jeton(falsifie) is None


def test_un_jeton_expire_est_refuse(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)  # même isolation que ci-dessus
    monkeypatch.setattr(config, "SESSION_DAYS", 0)
    jeton = access.creer_jeton(1, "Awa")
    time.sleep(0.01)
    assert access.lire_jeton(jeton) is None


def test_role_suffisant_respecte_la_hierarchie():
    assert access.role_suffisant(access.ROLE_ADMIN, access.ROLE_TESTEUR) is True
    assert access.role_suffisant(access.ROLE_LECTURE_SEULE, access.ROLE_TESTEUR) is False
    assert access.role_suffisant(access.ROLE_TESTEUR, access.ROLE_TESTEUR) is True


# ── 2. Le premier Admin, et la connexion obligatoire ──────────────────────────

def test_le_premier_admin_nait_des_variables_d_environnement(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "boot.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "ADMIN_USERNAME", "root")
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "changez-moi")

    app_mod._amorcer_premier_admin()

    conn = get_initialized_db(tmp_path / "boot.db")
    try:
        admin = UserRepo(conn).get_by_username("root")
        assert admin is not None
        assert admin["role"] == access.ROLE_ADMIN
        assert access.verifier_mot_de_passe("changez-moi", admin["password_hash"])
    finally:
        conn.close()


def test_l_amorce_NE_REJOUE_PAS_si_un_compte_existe_deja(tmp_path, monkeypatch):
    """Sinon un Admin qui change son propre mot de passe le verrait réécrasé au redémarrage."""
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "boot2.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "ADMIN_USERNAME", "root")
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "premier-mdp")
    app_mod._amorcer_premier_admin()

    monkeypatch.setattr(config, "ADMIN_PASSWORD", "second-mdp")
    app_mod._amorcer_premier_admin()

    conn = get_initialized_db(tmp_path / "boot2.db")
    try:
        admin = UserRepo(conn).get_by_username("root")
        assert access.verifier_mot_de_passe("premier-mdp", admin["password_hash"])
    finally:
        conn.close()


@pytest.mark.sans_bouchon_auth
def test_sans_session_l_api_repond_401(client):
    assert client.get("/api/projects").status_code == 401


def test_un_prevol_CORS_OPTIONS_n_est_jamais_bloque(client):
    """⚠️ Bug réel, trouvé en vérification live (2026-08-07) : un navigateur n'envoie pas le
    cookie de session sur le préflight CORS — bloqué en 401 sans les en-têtes CORS attendus, le
    navigateur le traduit en `net::ERR_FAILED`, invisible tant que `verrou_actif()` pouvait être
    faux. Révélé dès que la connexion est devenue obligatoire partout."""
    r = client.options("/api/projects", headers={
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "GET",
    })
    assert r.status_code != 401


@pytest.mark.sans_bouchon_auth
def test_un_401_cross_origine_porte_les_en_tetes_CORS(client):
    """⚠️ Bug réel, trouvé en vérification live (2026-08-07) — le même symptôme que le préflight
    OPTIONS, une couche plus profonde : `verrou_acces` court-circuite avec un 401/403 SANS
    appeler `call_next`. Tant que `CORSMiddleware` était ajouté AVANT lui (donc plus INTÉRIEUR,
    Starlette empile en LIFO), ce court-circuit ne traversait jamais `CORSMiddleware` — la
    réponse partait sans `Access-Control-Allow-Origin`, et le navigateur la remontait en
    `net::ERR_FAILED` plutôt qu'en 401 exploitable par le code JS. Un compte Lecture seule bloqué
    À RAISON affichait une erreur réseau opaque, jamais « droits insuffisants »."""
    r = client.get("/api/projects", headers={"Origin": "http://localhost:5173"})
    assert r.status_code == 401
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_un_403_cross_origine_porte_les_en_tetes_CORS(client):
    _compte(client, "Lea", "mdp", access.ROLE_LECTURE_SEULE)
    _connecte(client, "Lea", "mdp")
    r = client.post("/api/projects", headers={"Origin": "http://localhost:5173"},
                    json={"name": "R", "base_url": "http://x", "database": "db",
                          "username": "qa", "password": "p"})
    assert r.status_code == 403
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_identifiant_inconnu_est_refuse(client):
    r = client.post("/api/auth/login", json={"username": "personne", "password": "x"})
    assert r.status_code == 401
    assert r.json()["authenticated"] is False
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["x-request-id"]


def test_mauvais_mot_de_passe_est_refuse(client):
    _compte(client, "Awa", "bonmdp", access.ROLE_TESTEUR)
    r = client.post("/api/auth/login", json={"username": "Awa", "password": "mauvais"})
    assert r.status_code == 401


def test_cinq_echecs_bloquent_temporairement_la_connexion(client):
    _compte(client, "CibleLimitation", "bon-mot-de-passe", access.ROLE_TESTEUR)
    reponses = [client.post("/api/auth/login", json={
        "username": "CibleLimitation", "password": "mauvais",
    }) for _ in range(5)]
    assert [r.status_code for r in reponses[:4]] == [401, 401, 401, 401]
    assert reponses[4].status_code == 429
    assert reponses[4].headers["retry-after"] == "900"
    assert "15 minutes" in reponses[4].json()["detail"]


def test_un_succes_remet_le_compteur_d_echecs_a_zero(client):
    _compte(client, "CompteurReinitialise", "bon-mot-de-passe", access.ROLE_TESTEUR)
    for _ in range(4):
        assert client.post("/api/auth/login", json={
            "username": "CompteurReinitialise", "password": "mauvais",
        }).status_code == 401
    assert client.post("/api/auth/login", json={
        "username": "CompteurReinitialise", "password": "bon-mot-de-passe",
    }).status_code == 200
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={
        "username": "CompteurReinitialise", "password": "mauvais",
    }).status_code == 401


def test_bon_identifiant_ouvre_l_acces(client):
    _compte(client, "Awa", "bonmdp", access.ROLE_TESTEUR)
    _connecte(client, "Awa", "bonmdp")
    assert client.get("/api/projects").status_code == 200


def test_un_compte_desactive_ne_peut_pas_se_connecter(client):
    uid = _compte(client, "Awa", "bonmdp", access.ROLE_TESTEUR)
    conn = get_initialized_db(config.DB_PATH)
    try:
        UserRepo(conn).set_active(uid, False)
    finally:
        conn.close()
    r = client.post("/api/auth/login", json={"username": "Awa", "password": "bonmdp"})
    assert r.status_code == 401


def test_la_session_reflete_le_role_reel(client):
    _compte(client, "Awa", "bonmdp", access.ROLE_DEV)
    _connecte(client, "Awa", "bonmdp")
    session = client.get("/api/auth/session").json()
    assert session["authenticated"] is True
    assert session["name"] == "Awa"
    assert session["role"] == access.ROLE_DEV


# ── 3. Lecture seule ne peut RIEN écrire ──────────────────────────────────────

def test_lecture_seule_est_bloque_sur_une_ecriture(client):
    _compte(client, "Lea", "mdp", access.ROLE_LECTURE_SEULE)
    _connecte(client, "Lea", "mdp")
    r = client.post("/api/projects", json={
        "name": "Recette", "base_url": "http://x", "database": "db",
        "username": "qa", "password": "p"})
    assert r.status_code == 403


def test_lecture_seule_peut_toujours_SE_DECONNECTER(client):
    """⚠️ Bug réel, trouvé en vérification live (2026-08-07) : `/api/auth/logout` est un `POST`,
    donc une « écriture » aux yeux d'`ecriture_bloquee` — un compte Lecture seule ne pouvait
    simplement pas cliquer son propre bouton « Se déconnecter » (403). Se déconnecter n'est
    jamais un geste à restreindre par rôle."""
    _compte(client, "Lea", "mdp", access.ROLE_LECTURE_SEULE)
    _connecte(client, "Lea", "mdp")
    assert client.post("/api/auth/logout").status_code == 200


def test_lecture_seule_peut_toujours_LIRE(client):
    _compte(client, "Lea", "mdp", access.ROLE_LECTURE_SEULE)
    _connecte(client, "Lea", "mdp")
    assert client.get("/api/projects").status_code == 200


def test_testeur_peut_ecrire(client):
    _compte(client, "Awa", "mdp", access.ROLE_TESTEUR)
    _connecte(client, "Awa", "mdp")
    # Un Testeur écrit dans un projet autorisé, mais ne crée pas l'espace projet lui-même.
    conn = get_initialized_db(config.DB_PATH)
    try:
        pid = ProjectRepo(conn).create(name="Recette")
    finally:
        conn.close()
    r = client.post(f"/api/projects/{pid}/modules", json={"name": "Recette fonctionnelle"})
    assert r.status_code == 201


def test_une_desactivation_EN_COURS_DE_SESSION_coupe_l_acces_immediatement(client):
    """Le point qui compte : pas besoin d'attendre l'expiration du jeton (30 jours par défaut)."""
    uid = _compte(client, "Awa", "mdp", access.ROLE_TESTEUR)
    _connecte(client, "Awa", "mdp")
    assert client.get("/api/projects").status_code == 200

    conn = get_initialized_db(config.DB_PATH)
    try:
        UserRepo(conn).set_active(uid, False)
    finally:
        conn.close()

    assert client.get("/api/projects").status_code == 401


def test_une_retrogradation_EN_COURS_DE_SESSION_revoque_la_session_immediatement(client):
    uid = _compte(client, "Awa", "mdp", access.ROLE_TESTEUR)
    _connecte(client, "Awa", "mdp")
    conn = get_initialized_db(config.DB_PATH)
    try:
        pid = ProjectRepo(conn).create(name="R1")
    finally:
        conn.close()
    assert client.post(f"/api/projects/{pid}/modules", json={"name": "M1"}).status_code == 201

    conn = get_initialized_db(config.DB_PATH)
    try:
        UserRepo(conn).set_role(uid, access.ROLE_LECTURE_SEULE)
    finally:
        conn.close()

    r = client.post(f"/api/projects/{pid}/modules", json={"name": "M2"})
    assert r.status_code == 401


def test_logout_revoque_aussi_une_copie_du_cookie(client):
    _compte(client, "Awa", "motdepasse", access.ROLE_TESTEUR)
    _connecte(client, "Awa", "motdepasse")
    ancien_cookie = client.cookies.get(access.COOKIE)

    assert client.post("/api/auth/logout").status_code == 200
    # `delete` avant `set` : même précaution que `test_changer_son_mot_de_passe_revoque_le_cookie_precedent`
    # ci-dessus, pour ne jamais dépendre de la façon dont la bibliothèque HTTP du client de test
    # traite un `set` sur un nom de cookie déjà suivi dans le jar.
    client.cookies.delete(access.COOKIE)
    client.cookies.set(access.COOKIE, ancien_cookie)

    assert client.get("/api/projects").status_code == 401


# ── 4. Gestion des comptes — Admin seulement ──────────────────────────────────

def test_un_testeur_ne_peut_pas_gerer_les_comptes(client):
    _compte(client, "Awa", "mdp", access.ROLE_TESTEUR)
    _connecte(client, "Awa", "mdp")
    assert client.get("/api/admin/users").status_code == 403
    assert client.post("/api/admin/users",
                       json={"username": "x", "password": "y",
                             "role": access.ROLE_TESTEUR}).status_code == 403


def test_un_dev_ne_peut_pas_gerer_les_comptes(client):
    """Dev peut éditer un script, pas gérer qui a accès — deux crans distincts."""
    _compte(client, "Awa", "mdp", access.ROLE_DEV)
    _connecte(client, "Awa", "mdp")
    assert client.get("/api/admin/users").status_code == 403


def test_un_admin_cree_liste_et_modifie_un_compte(client):
    _compte(client, "Root", "adminmdp", access.ROLE_ADMIN)
    _connecte(client, "Root", "adminmdp")

    r = client.post("/api/admin/users",
                    json={"username": "Bob", "password": "bobmdp12",
                          "role": access.ROLE_TESTEUR})
    assert r.status_code == 200
    bob = r.json()
    assert bob["role"] == access.ROLE_TESTEUR
    assert bob["is_active"] is True
    assert "password" not in bob and "password_hash" not in bob

    usernames = {u["username"] for u in client.get("/api/admin/users").json()}
    assert {"Root", "Bob"} <= usernames

    r = client.patch(f"/api/admin/users/{bob['id']}", json={"role": access.ROLE_DEV})
    assert r.status_code == 200 and r.json()["role"] == access.ROLE_DEV

    r = client.patch(f"/api/admin/users/{bob['id']}", json={"is_active": False})
    assert r.status_code == 200 and r.json()["is_active"] is False


def test_un_nom_d_utilisateur_deja_pris_est_refuse(client):
    _compte(client, "Root", "adminmdp", access.ROLE_ADMIN)
    _connecte(client, "Root", "adminmdp")
    client.post("/api/admin/users",
               json={"username": "Bob", "password": "motdepasse1", "role": access.ROLE_TESTEUR})
    r = client.post("/api/admin/users",
                    json={"username": "Bob", "password": "motdepasse2", "role": access.ROLE_TESTEUR})
    assert r.status_code == 409


def test_desactiver_un_compte_NE_LE_SUPPRIME_PAS(client):
    """Jamais de suppression définitive — cohérent avec la suppression douce du reste de l'app."""
    _compte(client, "Root", "adminmdp", access.ROLE_ADMIN)
    _connecte(client, "Root", "adminmdp")
    bob = client.post("/api/admin/users",
                      json={"username": "Bob", "password": "motdepasse-de-bob",
                            "role": access.ROLE_TESTEUR}).json()

    client.patch(f"/api/admin/users/{bob['id']}", json={"is_active": False})

    usernames = {u["username"] for u in client.get("/api/admin/users").json()}
    assert "Bob" in usernames  # toujours listé, juste inactif


# ── 5. Peaufinage du 2026-08-11 — dernier Admin protégé, réinitialisation, longueur ───────────

def test_le_dernier_admin_actif_ne_peut_pas_etre_desactive(client):
    """Sinon plus personne ne pourrait plus gérer aucun compte ni aucun accès."""
    root_id = _compte(client, "Root", "adminmdp", access.ROLE_ADMIN)
    _connecte(client, "Root", "adminmdp")
    r = client.patch(f"/api/admin/users/{root_id}", json={"is_active": False})
    assert r.status_code == 409
    assert client.get("/api/admin/users").json()[0]["is_active"] is True


def test_le_dernier_admin_actif_ne_peut_pas_etre_retrograde(client):
    root_id = _compte(client, "Root", "adminmdp", access.ROLE_ADMIN)
    _connecte(client, "Root", "adminmdp")
    r = client.patch(f"/api/admin/users/{root_id}", json={"role": access.ROLE_DEV})
    assert r.status_code == 409
    assert client.get("/api/admin/users").json()[0]["role"] == access.ROLE_ADMIN


def test_un_SECOND_admin_actif_permet_de_desactiver_ou_retrograder_le_premier(client):
    """Le garde-fou vise le DERNIER Admin, pas « toucher à un Admin » en général."""
    root_id = _compte(client, "Root", "adminmdp", access.ROLE_ADMIN)
    _compte(client, "Second", "mdp12345", access.ROLE_ADMIN)
    _connecte(client, "Second", "mdp12345")

    r = client.patch(f"/api/admin/users/{root_id}", json={"is_active": False})
    assert r.status_code == 200 and r.json()["is_active"] is False


def test_desactiver_un_admin_DEJA_inactif_ne_declenche_pas_la_garde(client):
    """Un Admin déjà hors-jeu ne « perd » rien — la garde ne doit pas confondre intention et état."""
    root_id = _compte(client, "Root", "adminmdp", access.ROLE_ADMIN)
    second_id = _compte(client, "Second", "mdp12345", access.ROLE_ADMIN)
    _connecte(client, "Root", "adminmdp")
    assert client.patch(f"/api/admin/users/{second_id}",
                        json={"is_active": False}).status_code == 200
    # Second est maintenant inactif : le repatcher (même en Testeur) ne doit PAS être bloqué par
    # la garde du dernier Admin — il n'était déjà plus le dernier Admin ACTIF.
    r = client.patch(f"/api/admin/users/{second_id}", json={"role": access.ROLE_TESTEUR})
    assert r.status_code == 200


def test_un_admin_peut_toujours_se_reinitialiser_LUI_MEME_sans_perdre_son_statut(client):
    """Réinitialiser un mot de passe seul ne touche ni au rôle ni à `is_active` — la garde du
    dernier Admin ne doit jamais s'y appliquer."""
    root_id = _compte(client, "Root", "adminmdp", access.ROLE_ADMIN)
    _connecte(client, "Root", "adminmdp")
    r = client.patch(f"/api/admin/users/{root_id}", json={"new_password": "nouveaumdp"})
    assert r.status_code == 200


def test_reinitialiser_le_mot_de_passe_permet_de_se_reconnecter_avec_le_NOUVEAU(client):
    bob_id = _compte(client, "Bob", "ancienmdp", access.ROLE_TESTEUR)
    _compte(client, "Root", "adminmdp", access.ROLE_ADMIN)
    _connecte(client, "Root", "adminmdp")

    r = client.patch(f"/api/admin/users/{bob_id}", json={"new_password": "nouveaumdp"})
    assert r.status_code == 200

    client.post("/api/auth/logout")
    assert client.post("/api/auth/login",
                       json={"username": "Bob", "password": "ancienmdp"}).status_code == 401
    assert client.post("/api/auth/login",
                       json={"username": "Bob", "password": "nouveaumdp"}).status_code == 200


def test_un_mot_de_passe_trop_court_est_refuse_A_LA_CREATION(client):
    _compte(client, "Root", "adminmdp", access.ROLE_ADMIN)
    _connecte(client, "Root", "adminmdp")
    r = client.post("/api/admin/users",
                    json={"username": "Bob", "password": "court", "role": access.ROLE_TESTEUR})
    assert r.status_code == 422


def test_un_mot_de_passe_trop_court_est_refuse_A_LA_REINITIALISATION(client):
    bob_id = _compte(client, "Bob", "ancienmdp", access.ROLE_TESTEUR)
    _compte(client, "Root", "adminmdp", access.ROLE_ADMIN)
    _connecte(client, "Root", "adminmdp")
    r = client.patch(f"/api/admin/users/{bob_id}", json={"new_password": "court"})
    assert r.status_code == 422
    # Refusé => l'ANCIEN mot de passe doit toujours fonctionner.
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login",
                       json={"username": "Bob", "password": "ancienmdp"}).status_code == 200
# ── 6. Changer SON PROPRE mot de passe (2026-09-03) ───────────────────────────
# Jusqu'ici, seul un Admin pouvait réinitialiser le mot de passe D'UN AUTRE (section 4 ci-dessus,
# `new_password` — sans exiger l'ancien). `PATCH /api/auth/password` couvre le geste symétrique :
# un titulaire qui CONNAÎT encore son mot de passe change lui-même le sien.

def test_changer_son_mot_de_passe_reussit_et_permet_de_se_reconnecter_avec_le_NOUVEAU(client):
    _compte(client, "Awa", "ancienmdp", access.ROLE_TESTEUR)
    _connecte(client, "Awa", "ancienmdp")

    r = client.patch("/api/auth/password",
                     json={"old_password": "ancienmdp", "new_password": "nouveaumdp"})
    assert r.status_code == 200, r.text
    assert r.json()["authenticated"] is True
    assert r.json()["name"] == "Awa"

    client.post("/api/auth/logout")
    assert client.post("/api/auth/login",
                       json={"username": "Awa", "password": "ancienmdp"}).status_code == 401
    assert client.post("/api/auth/login",
                       json={"username": "Awa", "password": "nouveaumdp"}).status_code == 200


def test_changer_son_mot_de_passe_NE_DECONNECTE_PAS_la_session_en_cours(client):
    """Un changement réussi ne doit jamais forcer une reconnexion — la session qui vient de le
    prouver reste valide."""
    _compte(client, "Awa", "ancienmdp", access.ROLE_TESTEUR)
    _connecte(client, "Awa", "ancienmdp")

    client.patch("/api/auth/password",
                 json={"old_password": "ancienmdp", "new_password": "nouveaumdp"})

    # Toujours connecté, SANS repasser par /api/auth/login : le cookie de session posé au login
    # doit encore ouvrir l'accès.
    assert client.get("/api/auth/session").json()["authenticated"] is True
    assert client.get("/api/projects").status_code == 200


def test_changer_son_mot_de_passe_revoque_le_cookie_precedent(client):
    _compte(client, "Awa", "ancienmdp", access.ROLE_TESTEUR)
    _connecte(client, "Awa", "ancienmdp")
    ancien_cookie = client.cookies.get(access.COOKIE)

    r = client.patch("/api/auth/password",
                     json={"old_password": "ancienmdp", "new_password": "nouveaumdp"})
    assert r.status_code == 200
    nouveau_cookie = client.cookies.get(access.COOKIE)
    assert nouveau_cookie != ancien_cookie

    # ⚠️ `delete` AVANT `set` : le client garde déjà une entrée pour ce cookie (posée par la
    # réponse du changement de mot de passe ci-dessus) — `set` seul en ajoute une seconde au lieu
    # de la remplacer, et lequel des deux part réellement dans la requête suivante dépend alors
    # de la bibliothèque HTTP installée (constaté : 200 au lieu de 401 avec httpx2, reproduit
    # sous Linux). Un problème du CLIENT de test, pas de l'application — voir `access.py::utilisateur_actuel`,
    # inchangé, qui rejette bien une version de session périmée dès qu'un seul cookie est envoyé.
    client.cookies.delete(access.COOKIE)
    client.cookies.set(access.COOKIE, ancien_cookie)
    assert client.get("/api/projects").status_code == 401


def test_un_mauvais_ancien_mot_de_passe_est_refuse(client):
    _compte(client, "Awa", "ancienmdp", access.ROLE_TESTEUR)
    _connecte(client, "Awa", "ancienmdp")

    r = client.patch("/api/auth/password",
                     json={"old_password": "faux", "new_password": "nouveaumdp"})
    assert r.status_code == 401
    assert r.json()["code"] == "mot_de_passe_incorrect"

    # Refusé => l'ANCIEN mot de passe doit toujours fonctionner.
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login",
                       json={"username": "Awa", "password": "ancienmdp"}).status_code == 200


def test_un_nouveau_mot_de_passe_trop_court_est_refuse(client):
    _compte(client, "Awa", "ancienmdp", access.ROLE_TESTEUR)
    _connecte(client, "Awa", "ancienmdp")

    r = client.patch("/api/auth/password",
                     json={"old_password": "ancienmdp", "new_password": "court"})
    assert r.status_code == 422

    client.post("/api/auth/logout")
    assert client.post("/api/auth/login",
                       json={"username": "Awa", "password": "ancienmdp"}).status_code == 200


@pytest.mark.sans_bouchon_auth
def test_sans_session_le_changement_est_refuse(client):
    """Sans le bouchon `_connecte_par_defaut` (`conftest.py`) — sinon un compte Admin de
    complaisance masquerait ici le VRAI comportement (aucune session ⇒ le middleware `verrou_acces`
    répond 401 avant même d'atteindre la route)."""
    r = client.patch("/api/auth/password",
                     json={"old_password": "x", "new_password": "nouveaumdp"})
    assert r.status_code == 401


def test_un_utilisateur_ne_peut_pas_changer_le_mot_de_passe_dun_AUTRE(client):
    """Aucun `user_id` n'est accepté dans le corps de la requête : l'identité vient UNIQUEMENT de
    la session. Une tentative de falsification (`user_id` pointant vers un autre compte) est
    silencieusement ignorée par le schéma — c'est TOUJOURS le compte de la session qui change."""
    bob_id = _compte(client, "Bob", "mdpbob123", access.ROLE_TESTEUR)
    _compte(client, "Awa", "mdpawa123", access.ROLE_TESTEUR)
    _connecte(client, "Awa", "mdpawa123")

    r = client.patch("/api/auth/password", json={
        "old_password": "mdpawa123", "new_password": "nouveauawa",
        "user_id": bob_id,  # champ inconnu du schéma — doit être sans effet
    })
    assert r.status_code == 200

    # Le mot de passe de BOB n'a pas bougé.
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login",
                       json={"username": "Bob", "password": "mdpbob123"}).status_code == 200
    client.post("/api/auth/logout")
    # Celui d'AWA, si.
    assert client.post("/api/auth/login",
                       json={"username": "Awa", "password": "nouveauawa"}).status_code == 200


def test_lecture_seule_peut_changer_SON_PROPRE_mot_de_passe(client):
    """Exception étroite et délibérée à « Lecture seule ne doit RIEN écrire » (section 3) — même
    raisonnement que `/api/auth/logout` : sécuriser son propre compte n'est jamais un geste à
    restreindre par rôle."""
    _compte(client, "Lea", "ancienmdp", access.ROLE_LECTURE_SEULE)
    _connecte(client, "Lea", "ancienmdp")

    r = client.patch("/api/auth/password",
                     json={"old_password": "ancienmdp", "new_password": "nouveaumdp"})
    assert r.status_code == 200

    client.post("/api/auth/logout")
    assert client.post("/api/auth/login",
                       json={"username": "Lea", "password": "nouveaumdp"}).status_code == 200


def test_un_compte_desactive_entre_temps_ne_peut_pas_changer_son_mot_de_passe(client):
    """Le middleware relit `is_active` EN BASE à chaque requête (voir `access.utilisateur_actuel`)
    — une désactivation par un Admin doit couper l'accès tout de suite, y compris à cette route."""
    uid = _compte(client, "Awa", "ancienmdp", access.ROLE_TESTEUR)
    _connecte(client, "Awa", "ancienmdp")

    conn = get_initialized_db(config.DB_PATH)
    try:
        UserRepo(conn).set_active(uid, False)
    finally:
        conn.close()

    r = client.patch("/api/auth/password",
                     json={"old_password": "ancienmdp", "new_password": "nouveaumdp"})
    assert r.status_code == 401
