"""Lot PT-03, puis décision A44 (porteur, 2026-10-16) — l'onglet « Valeurs attendues » est retiré.

L'écriture des nombres et les unités ne sont plus déclarées par le projet : l'outil relève lui-même la façon dont
l'application écrit ses nombres, et la comparaison se comporte partout comme « Non déclarée ». Ce que ces tests gardent :
1. plus rien de ce qui avait été enregistré n'atteint un test, et plus aucune route ne permet de le déclarer ;
2. le lanceur pose toujours VIDES les variables du harnais, même si le serveur en a dans son environnement : l'installation
   ne décide jamais de l'écriture des nombres d'un projet ;
3. aucune monnaie du projet (A38) ;
4. le harnais (`behave_runtime`, inchangé tant que la mesure en cours l'emploie) lit toujours ces variables de façon sûre :
   ses tests restent, jusqu'au retrait de ce code mort.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import app as app_mod
from testpilot.connectors import runtime_env
from testpilot.parametres import valeurs

sys.path.insert(0, str(config.BEHAVE_RUNTIME_DIR / "steps_library"))
import _base_helpers as H  # noqa: E402
import _lecture_nombre as ln  # noqa: E402

ANCIENNE_VARIABLE_DE_MONNAIE = "TESTPILOT_PROJET_DEVISE"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return TestClient(app_mod.app)


def _projet(client, connecteur: str = "web") -> int:
    corps = {"name": f"Projet {connecteur}", "connector_type": connecteur, "base_url": "https://recette.exemple.test",
             "database": "recette" if connecteur == "odoo" else "", "username": "testeur", "password": "secret"}
    return client.post("/api/projects", json=corps).json()["id"]


# ── 1. Plus rien ne se déclare, plus rien n'atteint un test (A44) ─────────────────────────────────────────────────────────


def test_falsifiable_plus_aucune_route_ne_declare_l_ecriture_des_nombres_ni_les_unites(client):
    pid = _projet(client)

    client.patch(f"/api/projects/{pid}", json={"format_nombre": "point_virgule"})

    assert "format_nombre" not in client.get("/api/projects").json()[0]
    assert client.get(f"/api/projects/{pid}/units").status_code in (404, 405)
    assert client.post(f"/api/projects/{pid}/units", json={"nom": "palette"}).status_code in (404, 405)
    assert client.get("/api/settings/options/valeurs-du-projet").status_code in (404, 405)


@pytest.mark.parametrize("connecteur", ["odoo", "web"])
def test_falsifiable_ce_qui_avait_ete_enregistre_n_atteint_plus_aucun_test(client, connecteur, tmp_path):
    """Une écriture des nombres et une unité enregistrées AVANT A44 restent en base, inutilisées : un test est joué comme
    « Non déclarée »."""
    from testpilot.execution.behave_runner import BehaveRunner
    from testpilot.store.db import get_initialized_db
    from testpilot.store.repositories import ProjectRepo, TestUnitRepo

    pid = _projet(client, connecteur)
    conn = get_initialized_db(config.DB_PATH)
    try:
        conn.execute("UPDATE project SET format_nombre='point_virgule' WHERE id=?", (pid,))
        conn.commit()
        TestUnitRepo(conn).creer(pid, nom="palette", ecritures=["palettes"])
        env = runtime_env.env_du_projet(conn, ProjectRepo(conn).get(pid))
    finally:
        conn.close()

    assert valeurs.ENV_FORMAT_NOMBRE not in env and valeurs.ENV_UNITES not in env
    transmis = BehaveRunner(connection=env, connector_type=connecteur, generated_dir=tmp_path)._subprocess_env(tmp_path)
    assert transmis[valeurs.ENV_FORMAT_NOMBRE] == "" and transmis[valeurs.ENV_UNITES] == ""


@pytest.mark.parametrize("connecteur", ["odoo", "web"])
def test_falsifiable_l_installation_ne_decide_jamais_de_l_ecriture_des_nombres(connecteur, monkeypatch, tmp_path):
    from testpilot.execution.behave_runner import BehaveRunner

    monkeypatch.setenv(valeurs.ENV_FORMAT_NOMBRE, "virgule_point")     # restée dans le `.env` d'un serveur
    monkeypatch.setenv(valeurs.ENV_UNITES, '[{"nom": "palette"}]')
    env = runtime_env.project_env({"connector_type": connecteur, "base_url": "https://app.exemple.test", "username": "u",
                                   "password": "p", "database": "d"})

    transmis = BehaveRunner(connection=env, connector_type=connecteur, generated_dir=tmp_path)._subprocess_env(tmp_path)

    assert transmis[valeurs.ENV_FORMAT_NOMBRE] == "" and transmis[valeurs.ENV_UNITES] == ""
    assert set(valeurs.JAMAIS_HERITEES) == {valeurs.ENV_FORMAT_NOMBRE, valeurs.ENV_UNITES}


def test_accord_des_noms_de_variables_entre_l_application_et_le_harnais():
    assert H._ENV_FORMAT_NOMBRE_DU_PROJET == valeurs.ENV_FORMAT_NOMBRE
    assert H._ENV_UNITES_DU_PROJET == valeurs.ENV_UNITES


# ── 2. Le harnais lit ces variables de façon sûre (code conservé tant que la mesure en cours l'emploie) ───────────────────


@pytest.mark.parametrize("declare, attendu", [
    ({}, (None, None)),
    ({"TESTPILOT_PROJET_FORMAT_NOMBRE": "espace_virgule"}, (",", None)),
    ({"TESTPILOT_PROJET_FORMAT_NOMBRE": "VIRGULE_POINT"}, (".", ",")),
    ({"TESTPILOT_PROJET_FORMAT_NOMBRE": "point_virgule"}, (",", ".")),
    ({"TESTPILOT_PROJET_FORMAT_NOMBRE": "tiret"}, (None, None)),
    ({"TESTPILOT_PROJET_FORMAT_NOMBRE": ""}, (None, None)),
])
def test_falsifiable_le_harnais_ne_retient_qu_une_declaration_qu_il_reconnait(monkeypatch, declare, attendu):
    monkeypatch.delenv(valeurs.ENV_FORMAT_NOMBRE, raising=False)
    for nom, valeur in declare.items():
        monkeypatch.setenv(nom, valeur)

    assert H._valeurs_du_projet() == attendu


# ── 3 bis. Aucune monnaie du projet (A38) ─────────────────────────────────────────────────────────────────────────────────


def test_falsifiable_une_monnaie_envoyee_n_est_ni_enregistree_ni_renvoyee(client):
    pid = _projet(client)

    r = client.patch(f"/api/projects/{pid}", json={"devise": "EUR", "format_nombre": "espace_virgule"})

    assert r.status_code == 200 and "devise" not in r.json()
    assert "devise" not in client.get("/api/projects").json()[0]


def test_falsifiable_une_monnaie_venue_de_l_installation_n_est_jamais_lue(monkeypatch, tmp_path):
    """Une ancienne variable `TESTPILOT_PROJET_DEVISE` restée dans le `.env` d'un serveur ne doit rien décider : un montant
    attendu sans unité ne conclut toujours pas."""
    from testpilot.execution.behave_runner import BehaveRunner

    monkeypatch.setenv(ANCIENNE_VARIABLE_DE_MONNAIE, "EUR")
    env = runtime_env.project_env({"connector_type": "web", "base_url": "https://app.exemple.test", "devise": "EUR"})

    assert ANCIENNE_VARIABLE_DE_MONNAIE not in env
    BehaveRunner(connection=env, connector_type="web", generated_dir=tmp_path)._subprocess_env(tmp_path)
    assert H._valeurs_du_projet() == (None, None)
    lu, voulu = ln.lire_nombre("129,51 €", avec_unite=True), ln.lire_nombre("129,51", avec_unite=True)
    assert ln.comparer_valeurs(lu, voulu).etat == ln.UNITE_NON_VERIFIABLE


@pytest.mark.parametrize("valeur", ["", "pas du json", "{}", '[{"ecritures": ["x"]}]', '[42]', '"palette"',
                                    '[{"nom": "palette", "ecritures": "abc"}]', '[{"nom": null}]', '[{"nom": "p", "ecritures": [1]}]',
                                    '[{"nom": "palette"}, {"nom": 7}]'])
def test_falsifiable_une_declaration_d_unites_illisible_vaut_aucune_unite(monkeypatch, valeur):
    assert H._ENV_UNITES_DU_PROJET == valeurs.ENV_UNITES
    monkeypatch.setenv(valeurs.ENV_UNITES, valeur)

    assert H._unites_du_projet() == {}


def test_le_lecteur_charge_par_l_application_est_celui_du_harnais():
    from testpilot.api.services.lecteur_de_nombres import lecteur

    assert Path(lecteur().__file__).samefile(Path(ln.__file__))
    assert lecteur() is lecteur()


def test_falsifiable_une_ecriture_revendiquee_par_deux_unites_n_en_designe_aucune(monkeypatch):
    """Base éditée à la main, ou deux enregistrements concurrents : la dernière unité gagnait en silence, et « 12 paquet »
    valait « 12 pal »."""
    monkeypatch.setenv(valeurs.ENV_UNITES, '[{"nom": "palette", "ecritures": ["pal", "palettes"]}, {"nom": "paquet", "ecritures": ["pal"]}]')

    unites = H._unites_du_projet()

    assert unites == {"palette": "palette", "palettes": "palette", "paquet": "paquet"}
    lu = lambda texte: ln.lire_nombre(texte, avec_unite=True, unites_declarees=unites)   # noqa: E731
    assert ln.comparer_valeurs(lu("12 paquet"), lu("12 pal")).etat == ln.UNITE_NON_VERIFIABLE
    assert ln.comparer_valeurs(lu("12 palette"), lu("12 pal")).etat == ln.UNITE_NON_VERIFIABLE
