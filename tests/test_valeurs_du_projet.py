"""Lot PT-03 — la monnaie et l'écriture des nombres DÉCLARÉES par un projet (onglet « Valeurs attendues »).

Ce que ces tests gardent :
1. les deux réglages s'enregistrent par la route existante du projet, se relisent, se retirent ; une valeur inconnue est refusée
   AVANT toute écriture ;
2. seul ce qui est déclaré part vers le sous-processus du test — rien de déclaré = rien de transmis (règle R1 : sans réglage,
   le comportement est celui d'avant) ;
3. le paquet applicatif et le harnais Behave, qui ne dépendent pas l'un de l'autre, parlent bien des mêmes noms et des mêmes
   monnaies (constantes dupliquées : un test d'accord, comme pour le contexte navigateur).
"""

import sys

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import app as app_mod
from testpilot.connectors import runtime_env
from testpilot.parametres import valeurs

sys.path.insert(0, str(config.BEHAVE_RUNTIME_DIR / "steps_library"))
import _base_helpers as H  # noqa: E402
import _lecture_nombre as ln  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return TestClient(app_mod.app)


def _projet(client, connecteur: str = "web") -> int:
    corps = {"name": f"Projet {connecteur}", "connector_type": connecteur, "base_url": "https://recette.exemple.test",
             "database": "recette" if connecteur == "odoo" else "", "username": "testeur", "password": "secret"}
    return client.post("/api/projects", json=corps).json()["id"]


# ── 1. Enregistrer, relire, retirer, refuser ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("connecteur", ["odoo", "web"])
def test_un_projet_ne_declare_rien_par_defaut_puis_enregistre_ses_deux_reglages(client, connecteur):
    pid = _projet(client, connecteur)
    assert (client.get("/api/projects").json()[0]["devise"], client.get("/api/projects").json()[0]["format_nombre"]) == ("", "")

    r = client.patch(f"/api/projects/{pid}", json={"devise": " xof ", "format_nombre": " Espace_Virgule "})

    assert r.status_code == 200
    assert (r.json()["devise"], r.json()["format_nombre"]) == ("XOF", "espace_virgule")
    relu = client.get("/api/projects").json()[0]
    assert (relu["devise"], relu["format_nombre"]) == ("XOF", "espace_virgule")


def test_falsifiable_un_autre_reglage_ne_touche_pas_a_la_monnaie_et_une_valeur_vide_la_retire(client):
    pid = _projet(client)
    client.patch(f"/api/projects/{pid}", json={"devise": "EUR", "format_nombre": "virgule_point"})

    assert client.patch(f"/api/projects/{pid}", json={"browser_locale": "en-GB"}).json()["devise"] == "EUR"
    r = client.patch(f"/api/projects/{pid}", json={"devise": ""})

    assert (r.json()["devise"], r.json()["format_nombre"]) == ("", "virgule_point")


@pytest.mark.parametrize("corps, mot", [
    ({"devise": "EURO"}, "monnaie inconnue"),
    ({"devise": "ZZZ"}, "monnaie inconnue"),
    ({"devise": "€"}, "monnaie inconnue"),
    ({"format_nombre": "1 234,56"}, "écriture des nombres inconnue"),
    ({"format_nombre": "espace"}, "écriture des nombres inconnue"),
])
def test_falsifiable_une_valeur_inconnue_est_refusee_avant_toute_ecriture(client, corps, mot):
    pid = _projet(client)
    client.patch(f"/api/projects/{pid}", json={"devise": "EUR", "format_nombre": "espace_virgule"})

    r = client.patch(f"/api/projects/{pid}", json={"name": "Renommé", **corps})

    assert r.status_code == 422 and mot in r.json()["detail"]
    relu = client.get("/api/projects").json()[0]
    assert (relu["name"], relu["devise"], relu["format_nombre"]) == ("Projet web", "EUR", "espace_virgule"), "rien n'est écrit à moitié"


def test_le_catalogue_servi_a_l_ecran_est_celui_de_la_validation(client):
    r = client.get("/api/settings/options/valeurs-du-projet")

    assert r.status_code == 200
    assert set(r.json()["devises"]) == valeurs.CODES_DEVISE and r.json()["devises"] == sorted(r.json()["devises"])
    assert r.json()["formats_nombre"] == [{"cle": "espace_virgule", "libelle": "1 234,56"},
                                          {"cle": "virgule_point", "libelle": "1,234.56"},
                                          {"cle": "point_virgule", "libelle": "1.234,56"}]
    autre = _projet(client, "odoo")
    for cle in ("espace_virgule", "virgule_point", "point_virgule", ""):
        assert client.patch(f"/api/projects/{autre}", json={"format_nombre": cle}).json()["format_nombre"] == cle
    pid = _projet(client)
    for code in ("EUR", "XOF", "JPY"):
        assert client.patch(f"/api/projects/{pid}", json={"devise": code}).status_code == 200


# ── 2. Ce qui part vers le test ───────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("connecteur", ["odoo", "web"])
def test_falsifiable_rien_de_declare_arrive_vide_au_test_jamais_herite_du_serveur(connecteur, monkeypatch, tmp_path):
    """Revue du 2026-10-13 : le sous-processus part de l'environnement du serveur et relit `.env`. Une variable ABSENTE y
    prendrait la valeur du serveur — la monnaie d'un projet qui n'a rien déclaré serait décidée par l'installation."""
    from testpilot.execution.behave_runner import BehaveRunner

    monkeypatch.setenv(valeurs.ENV_DEVISE, "EUR")
    monkeypatch.setenv(valeurs.ENV_FORMAT_NOMBRE, "virgule_point")
    env = runtime_env.project_env({"connector_type": connecteur, "base_url": "https://app.exemple.test", "username": "u",
                                   "password": "p", "database": "d", "devise": "", "format_nombre": ""})

    assert valeurs.ENV_DEVISE not in env and valeurs.ENV_FORMAT_NOMBRE not in env, "rien de déclaré, rien dans la connexion"
    transmis = BehaveRunner(connection=env, connector_type=connecteur, generated_dir=tmp_path)._subprocess_env(tmp_path)
    assert (transmis[valeurs.ENV_DEVISE], transmis[valeurs.ENV_FORMAT_NOMBRE]) == ("", ""), "la valeur du serveur ne passe pas"
    # … et le harnais, qui lit ces variables, n'y voit alors aucune déclaration.
    monkeypatch.setenv(valeurs.ENV_DEVISE, transmis[valeurs.ENV_DEVISE])
    monkeypatch.setenv(valeurs.ENV_FORMAT_NOMBRE, transmis[valeurs.ENV_FORMAT_NOMBRE])
    assert H._valeurs_du_projet() == ("", None, None)


@pytest.mark.parametrize("connecteur", ["odoo", "web"])
def test_ce_qui_est_declare_est_transmis_au_test(connecteur):
    env = runtime_env.project_env({"connector_type": connecteur, "base_url": "https://app.exemple.test", "username": "u",
                                   "password": "p", "database": "d", "devise": "XOF", "format_nombre": "espace_virgule"})

    assert (env[valeurs.ENV_DEVISE], env[valeurs.ENV_FORMAT_NOMBRE]) == ("XOF", "espace_virgule")


def test_falsifiable_une_valeur_enregistree_mais_inconnue_n_est_pas_transmise():
    """Base éditée à la main : une monnaie inventée ne doit pas devenir « la monnaie du projet » pour un constat."""
    assert valeurs.env({"devise": "ZZZ", "format_nombre": "tiret"}) == {}
    assert valeurs.env(None) == {}
    assert set(valeurs.JAMAIS_HERITEES) == {valeurs.ENV_DEVISE, valeurs.ENV_FORMAT_NOMBRE}


def test_ce_que_le_projet_declare_passe_le_lanceur_sans_etre_ecrase(tmp_path, monkeypatch):
    from testpilot.execution.behave_runner import BehaveRunner

    monkeypatch.setenv(valeurs.ENV_DEVISE, "EUR")       # ce que dirait le serveur
    env = runtime_env.project_env({"connector_type": "web", "base_url": "https://app.exemple.test", "devise": "XOF",
                                   "format_nombre": "point_virgule"})
    transmis = BehaveRunner(connection=env, connector_type="web", generated_dir=tmp_path)._subprocess_env(tmp_path)

    assert (transmis[valeurs.ENV_DEVISE], transmis[valeurs.ENV_FORMAT_NOMBRE]) == ("XOF", "point_virgule")


# ── 3. Le harnais et l'application parlent de la même chose ───────────────────────────────────────────────────────────────


def test_accord_des_constantes_dupliquees_entre_l_application_et_le_harnais():
    assert (H._ENV_DEVISE_DU_PROJET, H._ENV_FORMAT_NOMBRE_DU_PROJET) == (valeurs.ENV_DEVISE, valeurs.ENV_FORMAT_NOMBRE)
    assert set(H._SEPARATEURS_DU_FORMAT) == set(valeurs.LIBELLES_FORMAT_NOMBRE)
    assert valeurs.CODES_DEVISE == ln._CODES_ISO, "une monnaie déclarable doit être une monnaie que le lecteur reconnaît à l'écran"
    # L'exemple montré à l'écran dit bien ce que la clé fait lire.
    for cle, exemple in valeurs.LIBELLES_FORMAT_NOMBRE.items():
        decimal, milliers = H._SEPARATEURS_DU_FORMAT[cle]
        assert ln.lire_nombre(exemple, separateur_decimal=decimal).valeur == ln.Decimal("1234.56")
        # Un séparateur que l'exemple ne MONTRE pas n'est pas déclaré : l'outil ne tranche rien pour lui.
        autres_signes = ({".", ","} - {decimal}) & set(exemple)
        assert decimal in exemple and autres_signes == ({milliers} if milliers else set())


@pytest.mark.parametrize("declare, attendu", [
    ({}, ("", None, None)),
    ({"TESTPILOT_PROJET_DEVISE": "XOF", "TESTPILOT_PROJET_FORMAT_NOMBRE": "espace_virgule"}, ("XOF", ",", None)),
    ({"TESTPILOT_PROJET_DEVISE": " eur ", "TESTPILOT_PROJET_FORMAT_NOMBRE": "VIRGULE_POINT"}, ("EUR", ".", ",")),
    ({"TESTPILOT_PROJET_FORMAT_NOMBRE": "point_virgule"}, ("", ",", ".")),
    ({"TESTPILOT_PROJET_DEVISE": "ZZZ", "TESTPILOT_PROJET_FORMAT_NOMBRE": "tiret"}, ("", None, None)),
    ({"TESTPILOT_PROJET_DEVISE": "$"}, ("", None, None)),
    ({"TESTPILOT_PROJET_DEVISE": "", "TESTPILOT_PROJET_FORMAT_NOMBRE": ""}, ("", None, None)),
])
def test_falsifiable_le_harnais_ne_retient_qu_une_declaration_qu_il_reconnait(monkeypatch, declare, attendu):
    for nom in (valeurs.ENV_DEVISE, valeurs.ENV_FORMAT_NOMBRE):
        monkeypatch.delenv(nom, raising=False)
    for nom, valeur in declare.items():
        monkeypatch.setenv(nom, valeur)

    assert H._valeurs_du_projet() == attendu
