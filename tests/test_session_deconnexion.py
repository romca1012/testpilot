"""Déconnexion adaptée (2026-09-25) : une session se ferme après INACTIVITÉ et ne dépasse jamais une durée MAXIMALE.

Avant : un jeton valait 30 jours fixes, sans inactivité ni renouvellement — un poste rouvert des semaines plus tard s'ouvrait
directement, sans mot de passe. Ces tests fixent les deux bornes et, surtout, qu'elles MORDENT (falsifiabilité).
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import access
from testpilot.api import app as app_mod


@pytest.fixture(autouse=True)
def _cle_isolee(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "s.db")


def _horloge(monkeypatch, valeur):
    monkeypatch.setattr(time, "time", lambda: valeur[0])


def test_une_session_inactive_se_ferme_meme_avant_la_duree_maximale(monkeypatch):
    """LA GARDE : le délai d'inactivité dépassé ferme la session alors que la durée maximale n'est pas atteinte."""
    t = [1_000_000.0]
    _horloge(monkeypatch, t)
    jeton = access.creer_jeton(1, "Awa")
    assert access.lire_jeton(jeton) is not None

    t[0] += config.SESSION_IDLE_MINUTES * 60 + 1

    assert access.lire_jeton(jeton) is None, "l'inactivité doit fermer la session"
    assert t[0] < 1_000_000.0 + config.SESSION_MAX_HOURS * 3600, "précondition : la borne absolue n'est pas atteinte"


def test_l_activite_repousse_l_inactivite_sans_jamais_depasser_la_borne_absolue(monkeypatch):
    t = [1_000_000.0]
    _horloge(monkeypatch, t)
    jeton = access.creer_jeton(1, "Awa")
    debut = t[0]

    # Une requête toutes les 60 minutes (< délai d'inactivité) garde la session vivante...
    for _ in range(11):
        t[0] += 60 * 60
        jeton = access.renouveler_jeton(jeton)
        assert jeton is not None and access.lire_jeton(jeton) is not None

    # ... jusqu'à la durée maximale absolue : au-delà, plus aucun renouvellement, activité ou non.
    t[0] = debut + config.SESSION_MAX_HOURS * 3600 + 1
    assert access.lire_jeton(jeton) is None
    assert access.renouveler_jeton(jeton) is None, "on ne renouvelle jamais une session expirée"


def test_falsifiable_le_renouvellement_ne_repousse_pas_la_borne_absolue(monkeypatch):
    """Sans la borne absolue, une session renouvelée chaque heure vivrait éternellement (l'ancien défaut, en pire)."""
    t = [1_000_000.0]
    _horloge(monkeypatch, t)
    jeton = access.creer_jeton(1, "Awa")
    absolue_initiale = access._decoder_jeton(jeton)["absolue"]

    t[0] += 3600
    renouvele = access.renouveler_jeton(jeton)

    assert access._decoder_jeton(renouvele)["absolue"] == absolue_initiale


def test_l_echeance_d_inactivite_ne_depasse_jamais_la_borne_absolue(monkeypatch):
    """Près de la fin de la durée maximale, le délai d'inactivité est rogné à la borne."""
    t = [1_000_000.0]
    _horloge(monkeypatch, t)
    jeton = access.creer_jeton(1, "Awa")
    absolue = access._decoder_jeton(jeton)["absolue"]

    t[0] = absolue - 60
    renouvele = access.renouveler_jeton(jeton)
    t[0] = absolue + 1

    assert access.lire_jeton(renouvele) is None


def test_un_ancien_jeton_a_30_jours_n_est_plus_accepte():
    """Les sessions d'avant le changement (ancien format à UNE échéance) sont fermées : c'est voulu."""
    ancien_charge = f"{int(time.time()) + 30 * 86400}.1.1.Awa"
    ancien = f"{ancien_charge}.{access._signer(ancien_charge)}"

    assert access.lire_jeton(ancien) is None


def test_un_jeton_falsifie_est_refuse():
    jeton = access.creer_jeton(1, "Awa")
    absolue, inactivite, reste = jeton.split(".", 2)
    falsifie = f"{int(absolue) + 10 * 86400}.{inactivite}.{reste}"

    assert access.lire_jeton(falsifie) is None


# ── Bout en bout : le cookie est renouvelé, et une session inactive répond 401 ────────────────────────────────


def _client_connecte():
    client = TestClient(app_mod.app)
    from testpilot.store.db import get_initialized_db
    from testpilot.store.repositories import UserRepo

    conn = get_initialized_db()
    UserRepo(conn).create(username="awa", password_hash=access.hacher_mot_de_passe("MotDePasse-Solide-1"),
                          role="admin")
    conn.close()
    reponse = client.post("/api/auth/login", json={"username": "awa", "password": "MotDePasse-Solide-1"})
    assert reponse.status_code == 200 and reponse.json()["authenticated"] is True
    return client


@pytest.mark.sans_bouchon_auth
def test_le_cookie_de_session_est_renouvele_a_chaque_requete_authentifiee():
    client = _client_connecte()

    reponse = client.get("/api/projects")

    assert reponse.status_code == 200
    assert "set-cookie" in reponse.headers, "une requête authentifiée renouvelle le cookie (session glissante)"
    assert f"Max-Age={config.SESSION_IDLE_MINUTES * 60}" in reponse.headers["set-cookie"]


@pytest.mark.sans_bouchon_auth
def test_falsifiable_une_session_inactive_repond_401_alors_qu_elle_est_valide_juste_avant(monkeypatch):
    client = _client_connecte()
    assert client.get("/api/projects").status_code == 200

    reel = time.time()
    monkeypatch.setattr(time, "time", lambda: reel + config.SESSION_IDLE_MINUTES * 60 + 5)

    assert client.get("/api/projects").status_code == 401, "après le délai d'inactivité, plus de session"
    assert client.get("/api/auth/session").json()["authenticated"] is False
