"""Lot 07c (C3) — le contexte navigateur FIGÉ : langue, fuseau, fenêtre décidés par le PROJET, jamais par la machine.

Le module est pur (`connectors/contexte_navigateur.py`) ; il est transmis au sous-processus par `runtime_env.project_env`, lu par le
harnais Behave (`environment.contexte_navigateur_fige`) et appliqué à l'exploration par les connecteurs — le MÊME contexte des deux
côtés (l'agent doit voir ce que le test verra). La preuve dans un vrai navigateur est dans `test_contexte_navigateur_reel.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import app as app_mod
from testpilot.connectors import contexte_navigateur as cn
from testpilot.connectors.generic_web import GenericWebConnector
from testpilot.connectors.odoo import OdooConnector
from testpilot.connectors.runtime_env import project_env

RACINE = Path(__file__).resolve().parents[1]


def _harnais():
    sys.path.insert(0, str(RACINE))
    from behave_runtime import environment
    return environment


# ── Le module pur ─────────────────────────────────────────────────────────────────────────────────────────────


def test_les_defauts_sont_fr_paris_1440x900():
    contexte = cn.ContexteNavigateur()

    assert contexte.kwargs() == {"locale": "fr-FR", "timezone_id": "Europe/Paris",
                                 "viewport": {"width": 1440, "height": 900}}


def test_un_reglage_vide_retombe_sur_le_defaut_champ_par_champ():
    contexte = cn.resoudre("en-US", "", "")

    assert (contexte.locale, contexte.timezone_id, contexte.viewport) == ("en-US", "Europe/Paris", "1440x900")


@pytest.mark.parametrize("locale,tz,viewport,attendu", [
    ("fr_FR", "", "", "langue"),
    ("", "Mars/Olympus", "", "fuseau"),
    ("", "", "grand", "taille"),
    ("", "", "100x900", "hors bornes"),
    ("", "", "1440x99999", "hors bornes"),
])
def test_erreurs_dit_en_francais_ce_qui_est_mal_forme(locale, tz, viewport, attendu):
    problemes = cn.erreurs(locale, tz, viewport)

    assert problemes and attendu in " ".join(problemes)


def test_un_reglage_valide_ou_vide_n_a_aucune_erreur():
    assert cn.erreurs("", "", "") == []
    assert cn.erreurs("en-US", "America/New_York", "1920x1080") == []


def test_falsifiable_une_valeur_invalide_lue_de_la_base_retombe_sur_le_defaut_sans_planter():
    """Une base éditée à la main ne doit pas faire planter une campagne : on retombe sur le défaut."""
    contexte = cn.depuis_projet({"browser_locale": "fr_FR", "browser_timezone": "Mars/Olympus",
                                 "browser_viewport": "zzz"})

    assert contexte == cn.ContexteNavigateur()


def test_le_contexte_d_un_projet_se_lit_dans_ses_colonnes():
    contexte = cn.depuis_projet({"browser_locale": "en-GB", "browser_timezone": "Europe/London",
                                 "browser_viewport": "1920x1080"})

    assert contexte.kwargs() == {"locale": "en-GB", "timezone_id": "Europe/London",
                                 "viewport": {"width": 1920, "height": 1080}}


# ── Vers le sous-processus ────────────────────────────────────────────────────────────────────────────────────


def test_project_env_transmet_toujours_le_contexte_defauts_compris():
    """Même un projet SANS réglage reçoit un contexte figé : le navigateur ne retombe jamais sur la langue de la machine."""
    env = project_env({"connector_type": "web", "base_url": "https://app.example"})

    assert env[cn.ENV_LOCALE] == "fr-FR" and env[cn.ENV_TIMEZONE] == "Europe/Paris" and env[cn.ENV_VIEWPORT] == "1440x900"


def test_project_env_transmet_les_reglages_du_projet_pour_les_deux_connecteurs():
    reglages = {"browser_locale": "en-US", "browser_timezone": "America/New_York", "browser_viewport": "1280x720"}

    web = project_env({"connector_type": "web", "base_url": "https://a.example", **reglages})
    odoo = project_env({"connector_type": "odoo", "base_url": "https://o.example", "database": "d", **reglages})

    for env in (web, odoo):
        assert (env[cn.ENV_LOCALE], env[cn.ENV_TIMEZONE], env[cn.ENV_VIEWPORT]) == (
            "en-US", "America/New_York", "1280x720")


def test_le_harnais_lit_le_meme_contexte_que_le_projet_l_a_ecrit(monkeypatch):
    """Le contrat de bout en bout, sans navigateur : ce que `project_env` écrit, `environment` le relit à l'identique."""
    reglages = {"browser_locale": "es-ES", "browser_timezone": "Europe/Madrid", "browser_viewport": "1366x768"}
    for cle, valeur in project_env({"connector_type": "web", "base_url": "https://a.example", **reglages}).items():
        monkeypatch.setenv(cle, valeur)

    assert _harnais().contexte_navigateur_fige() == cn.depuis_projet(reglages).kwargs()


def test_le_harnais_sans_variable_retombe_sur_les_memes_defauts(monkeypatch):
    for cle in (cn.ENV_LOCALE, cn.ENV_TIMEZONE, cn.ENV_VIEWPORT):
        monkeypatch.delenv(cle, raising=False)

    assert _harnais().contexte_navigateur_fige() == cn.ContexteNavigateur().kwargs()


def test_les_noms_de_variables_sont_les_memes_des_deux_cotes():
    """Le harnais ne dépend pas du paquet applicatif : ses constantes sont dupliquées, ce test les tient d'accord."""
    harnais = _harnais()

    assert (harnais._ENV_LOCALE, harnais._ENV_TIMEZONE, harnais._ENV_VIEWPORT) == (
        cn.ENV_LOCALE, cn.ENV_TIMEZONE, cn.ENV_VIEWPORT)
    assert (harnais._DEFAUT_LOCALE, harnais._DEFAUT_TIMEZONE, harnais._DEFAUT_VIEWPORT) == (
        cn.DEFAUT_LOCALE, cn.DEFAUT_TIMEZONE, (cn.DEFAUT_LARGEUR, cn.DEFAUT_HAUTEUR))


# ── L'exploration utilise le MÊME contexte ───────────────────────────────────────────────────────────────────


class _NavigateurEspion:
    def __init__(self):
        self.contextes = []

    def new_context(self, **kwargs):
        self.contextes.append(kwargs)
        raise RuntimeError("arrêt volontaire : seul l'appel à new_context est observé")


REGLAGES = {"browser_locale": "en-GB", "browser_timezone": "Europe/London", "browser_viewport": "1920x1080"}
ATTENDU = {"locale": "en-GB", "timezone_id": "Europe/London", "viewport": {"width": 1920, "height": 1080}}


def test_le_connecteur_web_explore_avec_le_contexte_du_projet():
    connecteur = GenericWebConnector.from_project({"base_url": "https://a.example", **REGLAGES})
    espion = connecteur._browser = _NavigateurEspion()
    connecteur._page = object()   # `_ensure_page` est court-circuité : seul le contexte de la tentative de connexion compte

    with pytest.raises(RuntimeError):
        connecteur._attempt_login_sync("u", "p")

    assert espion.contextes == [ATTENDU]


def test_le_connecteur_odoo_explore_avec_le_contexte_du_projet():
    connecteur = OdooConnector.from_project({"base_url": "https://o.example", "database": "d", **REGLAGES})
    espion = connecteur._browser = _NavigateurEspion()
    connecteur._page = object()

    with pytest.raises(RuntimeError):
        connecteur._attempt_login_sync("u", "p")

    assert espion.contextes == [ATTENDU]


def test_falsifiable_sans_reglage_l_exploration_prend_les_defauts_pas_ceux_de_la_machine():
    connecteur = GenericWebConnector.from_project({"base_url": "https://a.example"})
    espion = connecteur._browser = _NavigateurEspion()
    connecteur._page = object()

    with pytest.raises(RuntimeError):
        connecteur._attempt_login_sync("u", "p")

    assert espion.contextes == [cn.ContexteNavigateur().kwargs()], "un `new_context()` nu prendrait la langue de la machine"


# ── L'API : saisie, validation, valeurs effectives ───────────────────────────────────────────────────────────


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return TestClient(app_mod.app)


def _creer(client, **extra):
    return client.post("/api/projects", json={"name": "Portail", "connector_type": "web",
                                              "base_url": "https://a.example", **extra})


def test_un_projet_sans_reglage_expose_les_valeurs_effectives_par_defaut(client):
    corps = _creer(client).json()

    assert corps["browser_locale"] == "" and corps["browser_viewport"] == ""
    assert corps["browser_effectif"] == {"locale": "fr-FR", "timezone": "Europe/Paris", "viewport": "1440x900"}


def test_un_projet_cree_avec_un_contexte_le_garde(client):
    corps = _creer(client, **REGLAGES).json()

    assert corps["browser_effectif"] == {"locale": "en-GB", "timezone": "Europe/London", "viewport": "1920x1080"}


@pytest.mark.parametrize("champ,valeur", [("browser_locale", "fr_FR"), ("browser_timezone", "Mars/Olympus"),
                                          ("browser_viewport", "grand")])
def test_falsifiable_un_reglage_mal_forme_est_refuse_en_422_a_la_creation_et_a_l_edition(client, champ, valeur):
    assert _creer(client, **{champ: valeur}).status_code == 422
    projet = _creer(client).json()

    edition = client.patch(f"/api/projects/{projet['id']}", json={champ: valeur})

    assert edition.status_code == 422


def test_l_edition_change_le_contexte_et_une_chaine_vide_revient_au_defaut(client):
    projet = _creer(client, **REGLAGES).json()

    intact = client.patch(f"/api/projects/{projet['id']}", json={"name": "Portail 2"}).json()   # `None` = n'y touche pas
    remis = client.patch(f"/api/projects/{projet['id']}", json={"browser_locale": "", "browser_timezone": "",
                                                                "browser_viewport": ""}).json()

    assert intact["browser_effectif"]["locale"] == "en-GB"
    assert remis["browser_effectif"] == {"locale": "fr-FR", "timezone": "Europe/Paris", "viewport": "1440x900"}


def test_garde_aucun_new_context_nu_dans_les_connecteurs_ni_le_harnais():
    """Un `new_context()` sans réglage reprendrait la langue et le fuseau de la machine — exactement ce que le lot 07c supprime.
    Toute création de contexte de l'exploration ou de l'exécution doit passer par le contexte figé du projet."""
    import re

    fichiers = [RACINE / "behave_runtime" / "environment.py",
                *(p for p in (RACINE / "src" / "testpilot" / "connectors").glob("*.py")
                  if p.name != "contexte_navigateur.py")]
    nus = []
    for fichier in fichiers:
        for numero, ligne in enumerate(fichier.read_text(encoding="utf-8").splitlines(), 1):
            if ligne.strip().startswith(("#", '"""')):
                continue
            if re.search(r"\.new_context\(\s*\)", ligne):
                nus.append(f"{fichier.name}:{numero}")

    assert not nus, f"new_context() sans contexte figé : {nus}"
