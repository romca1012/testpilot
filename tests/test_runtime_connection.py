"""§8/décision 0005 — le runtime tape la connexion DU PROJET, pas la config globale.

L'interface promet un multi-projet : un run déclenché depuis un projet doit atteindre
l'application de CE projet. Sans ça, l'outil afficherait un projet et en testerait un autre —
exactement le décalage « affiché ≠ réel » qu'il est censé supprimer.
"""

import pytest

from testpilot import config
from testpilot.api.services import run_service
from testpilot.connectors.odoo import OdooConnector
from testpilot.connectors.runtime_env import project_env
from testpilot.execution.behave_result import (
    FIELD_FALLBACK_FILE_ENV,
    FIELD_FALLBACK_FILENAME,
)
from testpilot.execution.behave_runner import BehaveRunner
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, ModuleRepo, ProjectRepo


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    c = get_initialized_db(tmp_path / "rt.db")
    yield c
    c.close()


# ── Mapping projet → variables d'environnement ────────────────────────────────
def test_project_env_mappe_la_connexion_odoo():
    env = project_env({
        "connector_type": "odoo", "base_url": "http://autre:8069",
        "database": "db_client", "username": "u", "password": "p",
    })
    assert env == {"ODOO_URL": "http://autre:8069", "ODOO_DB": "db_client",
                   "ODOO_USER": "u", "ODOO_PASSWORD": "p"}


def test_project_env_ignore_les_valeurs_vides_pour_repli_config():
    # Connexion partielle → seules les valeurs saisies sont propagées ; le reste retombe
    # sur la config globale du harnais.
    env = project_env({"connector_type": "odoo", "base_url": "http://x", "database": "",
                       "username": "", "password": ""})
    assert env == {"ODOO_URL": "http://x"}


def test_project_env_connecteur_inconnu_ou_absent():
    assert project_env(None) == {}
    assert project_env({"connector_type": "sap", "base_url": "http://x"}) == {}


# ── Connecteur web générique (2026-09-08, multi-connecteurs) ──────────────────
# Seule différence structurelle avec Odoo : identifiant/mot de passe sont FACULTATIFS (voir
# `connectors/generic_web.py` — l'application ciblée peut n'exiger aucune connexion).
def test_project_env_mappe_la_connexion_web_generique():
    env = project_env({"connector_type": "web", "base_url": "http://intranet:8080",
                       "username": "bob", "password": "pwd"})
    assert env == {"WEB_URL": "http://intranet:8080", "WEB_USER": "bob", "WEB_PASSWORD": "pwd"}


def test_project_env_web_generique_sans_identifiant_ni_mot_de_passe():
    """Rien à écarter : une application accessible sans connexion reste testable telle quelle."""
    env = project_env({"connector_type": "web", "base_url": "http://intranet:8080"})
    assert env == {"WEB_URL": "http://intranet:8080"}


def test_verifier_connexion_web_generique_exige_seulement_l_url():
    """⚠️ Contrairement à Odoo : identifiant/mot de passe manquants ne doivent JAMAIS refuser
    le lancement d'un projet `web` — ce serait bloquer une application qui n'exige aucune
    connexion, la situation même que ce connecteur existe pour couvrir."""
    from testpilot.connectors.runtime_env import verifier_connexion

    env = verifier_connexion({"connector_type": "web", "base_url": "http://intranet:8080"})
    assert env == {"WEB_URL": "http://intranet:8080"}


def test_verifier_connexion_web_generique_refuse_sans_url():
    from testpilot.connectors.runtime_env import ConnexionIncomplete, verifier_connexion

    with pytest.raises(ConnexionIncomplete):
        verifier_connexion({"connector_type": "web", "base_url": ""})


def test_project_env_ne_produit_jamais_odoo_env():
    # Le garde-fou anti-production ne doit jamais être piloté par un projet.
    env = project_env({"connector_type": "odoo", "base_url": "http://x", "database": "d",
                       "username": "u", "password": "p"})
    assert "ODOO_ENV" not in env


# ── Injection dans le sous-processus behave ───────────────────────────────────
def test_runner_injecte_la_connexion_du_projet(monkeypatch, tmp_path):
    monkeypatch.setenv("ODOO_DB", "globale")
    runner = BehaveRunner(connection={"ODOO_DB": "db_du_projet"})
    env = runner._subprocess_env(tmp_path)
    assert env["ODOO_DB"] == "db_du_projet"       # le projet prime sur l'env globale
    assert "PATH" in env                           # l'environnement parent est conservé


def test_runner_sans_connexion_herite_de_l_environnement(monkeypatch, tmp_path):
    """Sans connexion projet, l'environnement parent est transmis à l'identique.

    ⚠️ Contrat CHANGÉ délibérément (décision 0007, phase B+) : `_subprocess_env` ne rend plus
    `None` (« hériter implicitement »), car le fichier sidecar des replis doit être désigné à
    CHAQUE run, connexion projet ou non. L'héritage reste entier — on passe explicitement
    l'environnement parent — donc le comportement historique est préservé, pas le `None`.
    """
    monkeypatch.setenv("UNE_VARIABLE_PARENTE", "héritée")
    env = BehaveRunner()._subprocess_env(tmp_path)
    assert env["UNE_VARIABLE_PARENTE"] == "héritée"
    assert "PATH" in env


def test_runner_designe_toujours_le_sidecar_des_replis(tmp_path):
    # Sans cette variable, le helper ne consigne rien et B+ redevient aveugle (0007 B+).
    env = BehaveRunner()._subprocess_env(tmp_path)
    assert env[FIELD_FALLBACK_FILE_ENV] == str(tmp_path / FIELD_FALLBACK_FILENAME)


def test_connexion_atteint_reellement_le_sous_processus_behave(tmp_path, monkeypatch):
    """Preuve du câblage : l'env du projet est bien remis à subprocess.run (pas seulement calculé)."""
    import subprocess as sp
    generated = tmp_path / "generated"
    generated.mkdir()
    (generated / "m.feature").write_text("# language: fr\nFonctionnalité: x\n", encoding="utf-8")

    captured = {}

    def fake_run(cmd, **kwargs):
        captured.update(kwargs)
        return sp.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("testpilot.execution.behave_runner.subprocess.run", fake_run)
    runner = BehaveRunner(generated_dir=generated, connection={"ODOO_DB": "db_du_projet"})
    runner.real_run("m")

    assert captured["env"]["ODOO_DB"] == "db_du_projet"


# ── Résolution depuis le cas (chemin réel du run UI) ──────────────────────────
def test_resolve_connection_depuis_le_cas(conn, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", ":memory:")
    pid = ProjectRepo(conn).create(name="Portail client", connector_type="odoo",
                                   base_url="http://client:8069", database="db_client",
                                   username="admin", password="secret")
    mid = ModuleRepo(conn).create(project_id=pid, name="Demande matériel")
    cid = CaseRepo(conn).create(title="Cas", module_id=mid, feature_slug="demande")

    env = run_service.resolve_connection(conn, cid)
    assert env["ODOO_URL"] == "http://client:8069"
    assert env["ODOO_DB"] == "db_client"


def test_resolve_connection_isole_deux_projets(conn):
    """Deux projets = deux instances : chaque cas doit viser la sienne."""
    p1 = ProjectRepo(conn).create(name="App A", connector_type="odoo", base_url="http://a:8069",
                                  database="db_a", username="u", password="p")
    p2 = ProjectRepo(conn).create(name="App B", connector_type="odoo", base_url="http://b:8069",
                                  database="db_b", username="u", password="p")
    m1 = ModuleRepo(conn).create(project_id=p1, name="M")
    m2 = ModuleRepo(conn).create(project_id=p2, name="M")
    c1 = CaseRepo(conn).create(title="A", module_id=m1, feature_slug="a")
    c2 = CaseRepo(conn).create(title="B", module_id=m2, feature_slug="b")

    assert run_service.resolve_connection(conn, c1)["ODOO_DB"] == "db_a"
    assert run_service.resolve_connection(conn, c2)["ODOO_DB"] == "db_b"


def test_resolve_connection_projet_sans_connexion_REFUSE(conn):
    """⚠️ **Ce test disait l'inverse jusqu'au 2026-07-24** : il figeait le repli sur la config
    globale comme un comportement voulu (« → config globale »).

    C'était le plus dangereux des défauts connus : l'écran affichait un projet, le navigateur
    testait l'instance par défaut de la machine, et **rien ne pouvait le trahir** — une campagne
    verte contre la mauvaise application. Le repli devient un refus explicite ; `project_env`
    garde la traduction sans jugement pour la ligne de commande (test ci-dessus).
    """
    from testpilot.connectors.runtime_env import ConnexionIncomplete

    pid = ProjectRepo(conn).create(name="Sans connexion")  # aucun paramètre saisi
    mid = ModuleRepo(conn).create(project_id=pid, name="M")
    cid = CaseRepo(conn).create(title="C", module_id=mid, feature_slug="c")
    with pytest.raises(ConnexionIncomplete):
        run_service.resolve_connection(conn, cid)


# ── Connecteur d'exploration (génération) ─────────────────────────────────────
def test_connector_from_project_utilise_la_connexion_du_projet():
    c = OdooConnector.from_project({"base_url": "http://client:8069", "database": "db_client",
                                    "username": "u", "password": "p"})
    assert c._url == "http://client:8069"
    assert c._database == "db_client"


def test_connector_from_project_retombe_sur_config_si_vide():
    c = OdooConnector.from_project({"base_url": "", "database": ""})
    assert c._url == config.ODOO_URL
    assert c._database == config.ODOO_DB
