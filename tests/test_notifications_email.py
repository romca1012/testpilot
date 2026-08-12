"""Notifications par email (migration 33, 2026-08-12) — prévenir l'auteur d'une campagne ou d'une
automatisation quand elle se termine, priorité 1 des trois écarts TestRail identifiés avec le
porteur (réglages manquants).

Deux invariants vérifiés ici :
- **Un réglage `secret` (`smtp_password`) n'est JAMAIS rendu en clair** — ni par l'API, ni par
  erreur en base (chiffré au repos, même mécanisme que le mot de passe de connexion d'un projet).
- **Best-effort absolu** : un envoi qui échoue (SMTP indisponible, config incomplète) ne lève
  jamais — c'est ce qui garantit qu'une campagne se clôt normalement même si la notification rate.
"""

from __future__ import annotations

import smtplib

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import access
from testpilot.api.app import app
from testpilot.api.deps import get_conn
from testpilot.api.services import notification_service
from testpilot.store.db import _migrate_33_email_utilisateur, get_initialized_db
from testpilot.store.repositories import SettingRepo, UserRepo


def _compte(conn, username: str, password: str, role: str, email: str = "") -> int:
    return UserRepo(conn).create(username=username,
                                 password_hash=access.hacher_mot_de_passe(password), role=role,
                                 email=email)


def _connecte(client, username: str, password: str):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text


@pytest.fixture
def conn(tmp_path, monkeypatch):
    # Même piège que `test_reglages_instance.py` : le middleware d'auth ouvre sa propre connexion
    # via `config.DB_PATH`, hors du système de dépendances FastAPI.
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "notif.db")
    c = get_initialized_db(tmp_path / "notif.db")
    yield c
    c.close()


@pytest.fixture
def client(conn):
    app.dependency_overrides[get_conn] = lambda: conn
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ── Migration 33 ────────────────────────────────────────────────────────────

def test_le_schema_neuf_porte_l_email(conn):
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(user)")}
    assert "email" in cols


def test_migration_33_est_idempotente(tmp_path):
    import sqlite3
    raw = sqlite3.connect(str(tmp_path / "x.db"))
    raw.row_factory = sqlite3.Row
    raw.execute("CREATE TABLE user (id INTEGER PRIMARY KEY)")
    _migrate_33_email_utilisateur(raw)
    _migrate_33_email_utilisateur(raw)  # rejoué
    cols = [r["name"] for r in raw.execute("PRAGMA table_info(user)")]
    assert cols.count("email") == 1, "email ajouté une seule fois"
    raw.close()


# ── UserRepo : l'email d'un compte ───────────────────────────────────────────

def test_create_et_set_email(conn):
    uid = UserRepo(conn).create(username="awa", password_hash="x", role="testeur",
                                email="awa@exemple.fr")
    assert UserRepo(conn).get(uid)["email"] == "awa@exemple.fr"

    UserRepo(conn).set_email(uid, "nouvelle@exemple.fr")
    assert UserRepo(conn).get(uid)["email"] == "nouvelle@exemple.fr"


def test_email_vide_par_defaut(conn):
    uid = UserRepo(conn).create(username="sans-email", password_hash="x", role="testeur")
    assert UserRepo(conn).get(uid)["email"] == ""


# ── SettingRepo : le mécanisme `secret` ──────────────────────────────────────

def test_smtp_password_est_chiffre_en_base(conn):
    """⚠️ Le cœur du chantier : la base ne doit JAMAIS porter le mot de passe SMTP en clair."""
    SettingRepo(conn).ecrire("smtp_password", "un-secret-tres-sensible", par="admin")

    ligne = conn.execute("SELECT value FROM app_setting WHERE key='smtp_password'").fetchone()
    assert "un-secret-tres-sensible" not in ligne["value"]
    assert ligne["value"].startswith("enc:v1:")


def test_smtp_password_resoudre_dechiffre_pour_un_usage_serveur(conn):
    """`resoudre()`/`valeur()` restent la vraie valeur — usage INTERNE (ouvrir la connexion)."""
    SettingRepo(conn).ecrire("smtp_password", "un-secret", par="admin")
    assert SettingRepo(conn).valeur("smtp_password") == "un-secret"


def test_tous_ne_rend_jamais_le_secret_en_clair(conn):
    """La vue API (`tous()`) — jamais le mot de passe réel, un masque fixe seulement."""
    SettingRepo(conn).ecrire("smtp_password", "un-secret", par="admin")
    reglages = {r["key"]: r for r in SettingRepo(conn).tous()}
    assert reglages["smtp_password"]["value"] == SettingRepo.MASQUE_SECRET
    assert reglages["smtp_password"]["secret"] is True
    assert "un-secret" not in str(reglages)


def test_tous_secret_non_pose_est_vide_pas_masque(conn):
    """Un secret jamais réglé ne doit pas laisser croire qu'il l'est."""
    reglages = {r["key"]: r for r in SettingRepo(conn).tous()}
    assert reglages["smtp_password"]["value"] == ""


def test_ecrire_le_masque_est_un_no_op(conn):
    """⚠️ Filet de sécurité : si jamais le masque affiché revenait tel quel (bug d'écran), il ne
    doit PAS écraser le vrai secret par le texte littéral « •••••••• »."""
    SettingRepo(conn).ecrire("smtp_password", "vrai-mot-de-passe", par="admin")
    SettingRepo(conn).ecrire("smtp_password", SettingRepo.MASQUE_SECRET, par="admin")
    assert SettingRepo(conn).valeur("smtp_password") == "vrai-mot-de-passe"


def test_reglage_non_secret_reste_en_clair(conn):
    """Non-régression : le mécanisme `secret` ne touche PAS les réglages non secrets."""
    SettingRepo(conn).ecrire("smtp_host", "smtp.exemple.fr", par="admin")
    ligne = conn.execute("SELECT value FROM app_setting WHERE key='smtp_host'").fetchone()
    assert ligne["value"] == "smtp.exemple.fr"


# ── API : réservé à l'Admin ───────────────────────────────────────────────────

@pytest.mark.parametrize("cle", ["smtp_host", "notifications_enabled", "smtp_password"])
def test_reglages_smtp_reserves_a_l_admin(conn, client, cle):
    _compte(conn, "Awa", "mdp12345", access.ROLE_TESTEUR)
    _connecte(client, "Awa", "mdp12345")
    r = client.patch(f"/api/settings/{cle}", json={"value": "x"})
    assert r.status_code == 403


def test_reglages_smtp_un_admin_peut(conn, client):
    _compte(conn, "Root", "mdp12345", access.ROLE_ADMIN)
    _connecte(client, "Root", "mdp12345")
    r = client.patch("/api/settings/smtp_host", json={"value": "smtp.exemple.fr"})
    assert r.status_code == 200
    assert r.json()["value"] == "smtp.exemple.fr"


def test_api_expose_le_champ_secret(client):
    lignes = {r["key"]: r for r in client.get("/api/settings").json()}
    assert lignes["smtp_password"]["secret"] is True
    assert lignes["smtp_host"]["secret"] is False


# ── notification_service.envoyer() — smtplib monkeypatché, jamais de vrai réseau ────

class _FauxSMTP:
    """Espionne les appels sans jamais ouvrir de vraie connexion."""
    instances: list["_FauxSMTP"] = []

    def __init__(self, host, port, timeout=10):
        self.host, self.port = host, port
        self.starttls_appele = False
        self.login_appele = None
        self.message_envoye = None
        _FauxSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self):
        self.starttls_appele = True

    def login(self, username, password):
        self.login_appele = (username, password)

    def send_message(self, message):
        self.message_envoye = message


@pytest.fixture(autouse=True)
def _reset_faux_smtp():
    _FauxSMTP.instances = []
    yield


def test_envoyer_ouvre_bien_la_connexion_et_envoie(conn, monkeypatch):
    monkeypatch.setattr(smtplib, "SMTP", _FauxSMTP)
    SettingRepo(conn).ecrire("notifications_enabled", "1", par="admin")
    SettingRepo(conn).ecrire("smtp_host", "smtp.exemple.fr", par="admin")
    SettingRepo(conn).ecrire("smtp_from", "testpilot@exemple.fr", par="admin")
    SettingRepo(conn).ecrire("smtp_username", "svc", par="admin")
    SettingRepo(conn).ecrire("smtp_password", "secret", par="admin")

    succes, erreur = notification_service.envoyer(
        conn, destinataire="dest@exemple.fr", sujet="Sujet", corps="Corps")

    assert succes is True
    assert erreur == ""
    assert len(_FauxSMTP.instances) == 1
    appel = _FauxSMTP.instances[0]
    assert appel.host == "smtp.exemple.fr"
    assert appel.starttls_appele is True   # smtp_use_tls par défaut = "1"
    assert appel.login_appele == ("svc", "secret")
    assert appel.message_envoye["To"] == "dest@exemple.fr"


def test_envoyer_jamais_d_exception_meme_si_smtp_plante(conn, monkeypatch):
    def _explose(*a, **k):
        raise OSError("connexion refusée")
    monkeypatch.setattr(smtplib, "SMTP", _explose)
    SettingRepo(conn).ecrire("notifications_enabled", "1", par="admin")
    SettingRepo(conn).ecrire("smtp_host", "smtp.exemple.fr", par="admin")
    SettingRepo(conn).ecrire("smtp_from", "testpilot@exemple.fr", par="admin")

    succes, erreur = notification_service.envoyer(
        conn, destinataire="dest@exemple.fr", sujet="Sujet", corps="Corps")

    assert succes is False
    assert "connexion refusée" in erreur


def test_envoyer_desactive_par_defaut_ne_tente_rien(conn, monkeypatch):
    """Non-régression : `notifications_enabled` vaut vide par défaut — aucune tentative SMTP."""
    appels = []
    monkeypatch.setattr(smtplib, "SMTP", lambda *a, **k: appels.append(1))
    SettingRepo(conn).ecrire("smtp_host", "smtp.exemple.fr", par="admin")
    SettingRepo(conn).ecrire("smtp_from", "testpilot@exemple.fr", par="admin")

    succes, erreur = notification_service.envoyer(
        conn, destinataire="dest@exemple.fr", sujet="Sujet", corps="Corps")

    assert succes is False
    assert appels == []


# ── notification_service.notifier() — résolution par username ───────────────

def test_notifier_no_op_si_le_compte_n_a_pas_d_email(conn, monkeypatch):
    appels = []
    monkeypatch.setattr(notification_service, "envoyer", lambda *a, **k: appels.append(k))
    _compte(conn, "sans-email", "mdp12345", access.ROLE_TESTEUR)

    notification_service.notifier(conn, triggered_by="sans-email", sujet="S", corps="C")

    assert appels == []


def test_notifier_no_op_si_le_compte_est_inconnu(conn, monkeypatch):
    appels = []
    monkeypatch.setattr(notification_service, "envoyer", lambda *a, **k: appels.append(k))

    notification_service.notifier(conn, triggered_by="fantome", sujet="S", corps="C")

    assert appels == []


def test_notifier_envoie_au_bon_destinataire(conn, monkeypatch):
    appels = []
    monkeypatch.setattr(notification_service, "envoyer", lambda *a, **k: appels.append(k) or (True, ""))
    _compte(conn, "awa", "mdp12345", access.ROLE_TESTEUR, email="awa@exemple.fr")

    notification_service.notifier(conn, triggered_by="awa", sujet="Sujet", corps="Corps")

    assert len(appels) == 1
    assert appels[0]["destinataire"] == "awa@exemple.fr"
    assert appels[0]["sujet"] == "Sujet"


# ── Route de test SMTP ────────────────────────────────────────────────────────

def test_route_test_smtp_reservee_a_l_admin(conn, client):
    _compte(conn, "Awa", "mdp12345", access.ROLE_TESTEUR)
    _connecte(client, "Awa", "mdp12345")
    r = client.post("/api/settings/smtp/test", json={"destinataire": "x@exemple.fr"})
    assert r.status_code == 403


def test_route_test_smtp_fonctionne_meme_desactivee(conn, client, monkeypatch):
    """Un Admin qui règle sa config doit pouvoir la tester SANS l'activer d'abord."""
    monkeypatch.setattr(smtplib, "SMTP", _FauxSMTP)
    _compte(conn, "Root", "mdp12345", access.ROLE_ADMIN)
    _connecte(client, "Root", "mdp12345")
    client.patch("/api/settings/smtp_host", json={"value": "smtp.exemple.fr"})
    client.patch("/api/settings/smtp_from", json={"value": "testpilot@exemple.fr"})
    # notifications_enabled reste "0"/vide — c'est justement ce que ce test vérifie.

    r = client.post("/api/settings/smtp/test", json={"destinataire": "x@exemple.fr"})

    assert r.status_code == 200
    assert r.json()["succes"] is True
    assert len(_FauxSMTP.instances) == 1


def test_route_test_smtp_config_incomplete(conn, client):
    _compte(conn, "Root", "mdp12345", access.ROLE_ADMIN)
    _connecte(client, "Root", "mdp12345")

    r = client.post("/api/settings/smtp/test", json={"destinataire": "x@exemple.fr"})

    assert r.status_code == 200
    assert r.json()["succes"] is False
    assert r.json()["erreur"]
