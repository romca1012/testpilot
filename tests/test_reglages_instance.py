"""Réglages d'instance — la valeur qui s'applique, et **d'où elle vient**.

⚠️ **Ce que ce fichier empêche.** Un réglage a trois sources possibles : la base (posée depuis
l'écran), la variable d'environnement du serveur, le défaut du code. La base l'emporte. Une
installation qui affiche la valeur sans dire d'où elle sort produit exactement une scène :
l'exploitant pose une variable d'environnement, redémarre, voit autre chose, et cherche pendant
une heure une panne qui n'existe pas. La provenance est donc une donnée de l'API, testée ici.

Le second invariant est la **fermeture du vocabulaire** : une table clé/valeur qui accepte
n'importe quelle clé devient un dépotoir où plus personne ne sait ce qui est réellement lu. C'est
le défaut que `erreurs.CATALOGUE` évite déjà pour les codes d'erreur ; `CLES_CONNUES` le fait ici.

⚠️ **`service_account_name` a été RETIRÉ du vocabulaire le 2026-08-12**, sur demande explicite du
porteur (« ça ne devrait pas être un paramètre modifiable » depuis l'écran Réglages). Les tests
de résolution générique (base → env → défaut) qui l'utilisaient comme exemple sont retargetés sur
`smtp_port` (`SettingRepo`, réglages SMTP du 2026-08-12) — même forme (un défaut non vide), pour
ne pas perdre la couverture du mécanisme lui-même.
"""
import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import access
from testpilot.api.app import app
from testpilot.api.deps import get_conn
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import SettingRepo, UserRepo, _DEFAUTS_USINE


def _compte(conn, username: str, password: str, role: str) -> int:
    return UserRepo(conn).create(username=username,
                                 password_hash=access.hacher_mot_de_passe(password), role=role)


def _connecte(client, username: str, password: str):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text


@pytest.fixture
def conn(tmp_path, monkeypatch):
    # ⚠️ `config.DB_PATH` DOIT être isolé, pas seulement la dépendance `get_conn` (2026-08-11) :
    # le middleware d'auth (`verrou_acces`) ouvre SA PROPRE connexion via `config.DB_PATH`
    # directement, hors du système de dépendances FastAPI — `dependency_overrides` ne le couvre
    # pas. Sans ce monkeypatch, un test qui se connecte VRAIMENT (`_connecte`) obtient un jeton
    # valide pour CETTE base (ex. user_id=1 = « Awa »), mais le middleware le résout ensuite
    # contre la VRAIE base du poste — où l'id 1 est souvent le VRAI compte Admin. Trouvé en
    # écrivant un test de permission qui recevait 200 au lieu de 403, sans aucune autre explication.
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "reglages.db")
    c = get_initialized_db(tmp_path / "reglages.db")
    yield c
    c.close()


@pytest.fixture
def client(conn):
    app.dependency_overrides[get_conn] = lambda: conn
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ── La résolution, et sa provenance (mécanisme générique, illustré par smtp_port) ─────

_CLE_RESOLUTION = "smtp_port"


def test_sans_rien_de_pose_c_est_le_defaut_du_code(conn):
    valeur, source = SettingRepo(conn).resoudre(_CLE_RESOLUTION)
    assert valeur == config.SMTP_PORT
    assert source == "default"


def test_la_variable_d_environnement_est_annoncee_comme_telle(conn, monkeypatch):
    """L'exploitant qui a configuré son serveur doit VOIR que c'est sa valeur qui s'applique."""
    monkeypatch.setattr(config, "SMTP_PORT", "2525")
    assert SettingRepo(conn).resoudre(_CLE_RESOLUTION) == ("2525", "env")


def test_la_base_l_emporte_sur_l_environnement_et_le_dit(conn, monkeypatch):
    monkeypatch.setattr(config, "SMTP_PORT", "2525")
    SettingRepo(conn).ecrire(_CLE_RESOLUTION, "465", par="chef")
    assert SettingRepo(conn).resoudre(_CLE_RESOLUTION) == ("465", "db")


def test_effacer_rend_la_main_a_l_environnement(conn, monkeypatch):
    """⚠️ Une valeur vide SUPPRIME la ligne au lieu d'écrire une chaîne vide. « Pas de réglage »
    et « réglé à rien » ne sont pas le même fait — et sans cette distinction, un réglage posé par
    erreur serait définitif : plus aucun moyen de revenir à la configuration du serveur."""
    monkeypatch.setattr(config, "SMTP_PORT", "2525")
    reglages = SettingRepo(conn)
    reglages.ecrire(_CLE_RESOLUTION, "465")
    reglages.ecrire(_CLE_RESOLUTION, "   ")          # blancs seuls = vide
    assert reglages.resoudre(_CLE_RESOLUTION) == ("2525", "env")
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


# ── Le compte de service n'est plus un réglage (2026-08-12) ──────────────────

def test_le_compte_de_service_n_est_plus_un_reglage_modifiable(conn, client):
    """⚠️ Verrouille la demande du porteur : `service_account_name` a existé comme réglage
    d'écran (2026-08-04 → 2026-08-11), retiré ensuite — ne doit plus jamais réapparaître dans le
    vocabulaire connu ni dans la liste exposée par l'API."""
    assert "service_account_name" not in SettingRepo.CLES_CONNUES
    with pytest.raises(ValueError):
        SettingRepo(conn).resoudre("service_account_name")

    cles = {r["key"] for r in client.get("/api/settings").json()}
    assert "service_account_name" not in cles


def test_le_nom_du_compte_de_service_reste_reglable_par_variable_d_environnement(monkeypatch):
    """Reste un réglage d'EXPLOITANT (au déploiement), plus un réglage produit (à l'écran) — les
    deux ne sont pas la même chose. Vérifié directement sur `config`, plus via `SettingRepo`."""
    monkeypatch.setattr(config, "SERVICE_ACCOUNT_NAME", "Robot de la recette")
    assert config.SERVICE_ACCOUNT_NAME == "Robot de la recette"


# ── Références cliquables (2026-08-11) — le gabarit d'URL, même patron ────────

_CLE_REFS = "reference_url_template"


def test_gabarit_de_reference_vide_par_defaut(conn):
    assert SettingRepo(conn).resoudre(_CLE_REFS) == ("", "default")


def test_regler_le_gabarit_puis_l_effacer(client):
    r = client.patch(f"/api/settings/{_CLE_REFS}",
                     json={"value": "https://exemple.atlassian.net/browse/{ref}"})
    assert r.status_code == 200
    assert r.json()["value"] == "https://exemple.atlassian.net/browse/{ref}"
    assert r.json()["source"] == "db"

    r = client.patch(f"/api/settings/{_CLE_REFS}", json={"value": ""})
    assert r.status_code == 200
    assert r.json() == {"key": _CLE_REFS, "value": "", "source": "default",
                        "description": SettingRepo.CLES_CONNUES[_CLE_REFS][1],
                        "admin_only": True, "secret": False}


def test_le_gabarit_est_reserve_a_l_admin_un_testeur_est_refuse(conn, client):
    """Un gabarit mal réglé change ce que voit TOUTE l'équipe, sur tous les projets — pas un
    geste à laisser à n'importe quel rôle qui sait écrire."""
    _compte(conn, "Awa", "mdp12345", access.ROLE_TESTEUR)
    _connecte(client, "Awa", "mdp12345")
    r = client.patch(f"/api/settings/{_CLE_REFS}", json={"value": "https://x/{ref}"})
    assert r.status_code == 403


def test_le_gabarit_reserve_a_l_admin_un_admin_peut(conn, client):
    _compte(conn, "Root", "mdp12345", access.ROLE_ADMIN)
    _connecte(client, "Root", "mdp12345")
    r = client.patch(f"/api/settings/{_CLE_REFS}", json={"value": "https://x/{ref}"})
    assert r.status_code == 200


# ── Le vocabulaire est fermé ─────────────────────────────────────────────────

def test_une_cle_inconnue_est_refusee(conn):
    with pytest.raises(ValueError):
        SettingRepo(conn).ecrire("couleur_du_bandeau", "bleu")
    with pytest.raises(ValueError):
        SettingRepo(conn).resoudre("couleur_du_bandeau")


# ── L'API ────────────────────────────────────────────────────────────────────

def test_l_api_expose_la_valeur_ET_sa_provenance(client):
    lignes = client.get("/api/settings").json()
    ligne = next(l for l in lignes if l["key"] == _CLE_REFS)
    assert ligne["source"] == "default"
    assert ligne["description"], "un réglage sans explication est un réglage qu'on n'ose pas toucher"


def test_l_api_enregistre_puis_efface(client):
    maj = client.patch(f"/api/settings/{_CLE_REFS}", json={"value": "https://x/{ref}"}).json()
    assert (maj["value"], maj["source"]) == ("https://x/{ref}", "db")

    efface = client.patch(f"/api/settings/{_CLE_REFS}", json={"value": ""}).json()
    assert (efface["value"], efface["source"]) == ("", "default")


def test_l_api_refuse_une_cle_inconnue_avec_un_code_stable(client):
    r = client.patch("/api/settings/couleur_du_bandeau", json={"value": "bleu"})
    assert r.status_code == 422
    # Le code RFC 9457 est le contrat : c'est lui qu'un écran teste, jamais la phrase française.
    assert r.json()["code"] == "requete_invalide"


# ── Paramètres généraux de l'instance ────────────────────────────────────────

def test_les_parametres_generaux_ont_des_defauts_explicites(conn):
    reglages = SettingRepo(conn)
    assert reglages.valeur("instance_name") == "TestPilot"
    assert reglages.valeur("instance_timezone") == "Europe/Paris"
    assert reglages.valeur("date_format") == "DD/MM/YYYY"


def test_un_admin_enregistre_les_parametres_generaux(conn, client):
    _compte(conn, "RootGeneral", "mdp12345", access.ROLE_ADMIN)
    _connecte(client, "RootGeneral", "mdp12345")
    valeurs = {
        "instance_name": "Recette AXENEO",
        "instance_timezone": "Africa/Dakar",
        "date_format": "YYYY-MM-DD",
    }
    for cle, valeur in valeurs.items():
        r = client.patch(f"/api/settings/{cle}", json={"value": valeur})
        assert r.status_code == 200, r.text
        assert r.json()["value"] == valeur
        assert r.json()["source"] == "db"


@pytest.mark.parametrize(("cle", "valeur"), [
    ("instance_name", "X"),
    ("instance_timezone", "Paris"),
    ("date_format", "libre"),
])
def test_les_parametres_generaux_invalides_sont_refuses(conn, client, cle, valeur):
    _compte(conn, f"Admin-{cle}", "mdp12345", access.ROLE_ADMIN)
    _connecte(client, f"Admin-{cle}", "mdp12345")
    r = client.patch(f"/api/settings/{cle}", json={"value": valeur})
    assert r.status_code == 422
    assert r.json()["code"] == "requete_invalide"


def test_un_testeur_ne_modifie_pas_les_parametres_generaux(conn, client):
    _compte(conn, "AwaGeneral", "mdp12345", access.ROLE_TESTEUR)
    _connecte(client, "AwaGeneral", "mdp12345")
    r = client.patch("/api/settings/instance_name", json={"value": "Autre instance"})
    assert r.status_code == 403


def test_le_catalogue_des_fuseaux_est_reel_et_limite_a_paris_et_senegal(client):
    r = client.get("/api/settings/options/timezones")
    assert r.status_code == 200
    assert r.json() == [
        {"value": "Europe/Paris", "label": "Paris"},
        {"value": "Africa/Dakar", "label": "Sénégal"},
    ]


def test_l_etat_de_securite_est_reserve_a_l_admin_et_ne_revele_aucun_secret(conn, client):
    _compte(conn, "LecteurSecurite", "mdp12345", access.ROLE_TESTEUR)
    _connecte(client, "LecteurSecurite", "mdp12345")
    assert client.get("/api/settings/security-status").status_code == 403

    client.post("/api/auth/logout")
    _compte(conn, "AdminSecurite", "mdp12345", access.ROLE_ADMIN)
    _connecte(client, "AdminSecurite", "mdp12345")
    r = client.get("/api/settings/security-status")
    assert r.status_code == 200
    corps = r.json()
    assert corps["password_min_length"] == access.MOT_DE_PASSE_LONGUEUR_MIN
    assert corps["login_max_failures"] == 5
    assert corps["login_window_minutes"] == 15
    assert "secret" not in str(corps).lower() or all(
        isinstance(corps[k], bool) for k in ("session_secret_external", "data_secret_external"))
