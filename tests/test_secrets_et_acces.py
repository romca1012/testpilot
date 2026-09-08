"""Lot 2 du chemin de déploiement (2026-07-24) : **le secret de connexion ne dort plus en clair**.

Un `SELECT * FROM project` rendait les identifiants de l'application testée — et la base part
dans les sauvegardes. Ces tests figent le chiffrement au repos (`store/secrets.py`).

⚠️ Le verrou d'instance qui vivait aussi dans ce fichier a été remplacé par de vrais comptes
utilisateurs (2026-08-07) — voir `test_comptes_utilisateurs.py`, qui reprend cet invariant.
"""

import pytest

from testpilot import config
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
def conn(tmp_path, cle, monkeypatch):
    from testpilot import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
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
