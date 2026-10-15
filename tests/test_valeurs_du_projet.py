"""Lot PT-03 — l'écriture des nombres DÉCLARÉE par un projet (onglet « Valeurs attendues »), et rien d'autre (A38).

Ce que ces tests gardent :
1. le réglage s'enregistre par la route existante du projet, se relit, se retire ; une valeur inconnue est refusée AVANT
   toute écriture ;
2. seul ce qui est déclaré part vers le sous-processus du test — rien de déclaré = rien de transmis (règle R1 : sans réglage,
   le comportement est celui d'avant) ;
3. le paquet applicatif et le harnais Behave, qui ne dépendent pas l'un de l'autre, parlent bien des mêmes noms (constantes
   dupliquées : un test d'accord, comme pour le contexte navigateur) ;
4. aucune monnaie du projet (A38, porteur, 2026-10-15 : aucune base toute faite) : ni enregistrée, ni transmise, ni lue.
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


# ── 1. Enregistrer, relire, retirer, refuser ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("connecteur", ["odoo", "web"])
def test_un_projet_ne_declare_rien_par_defaut_puis_enregistre_son_ecriture_des_nombres(client, connecteur):
    pid = _projet(client, connecteur)
    assert client.get("/api/projects").json()[0]["format_nombre"] == ""

    r = client.patch(f"/api/projects/{pid}", json={"format_nombre": " Espace_Virgule "})

    assert r.status_code == 200 and r.json()["format_nombre"] == "espace_virgule"
    assert client.get("/api/projects").json()[0]["format_nombre"] == "espace_virgule"


def test_falsifiable_un_autre_reglage_ne_touche_pas_a_l_ecriture_et_une_valeur_vide_la_retire(client):
    pid = _projet(client)
    client.patch(f"/api/projects/{pid}", json={"format_nombre": "virgule_point"})

    assert client.patch(f"/api/projects/{pid}", json={"browser_locale": "en-GB"}).json()["format_nombre"] == "virgule_point"
    assert client.patch(f"/api/projects/{pid}", json={"format_nombre": ""}).json()["format_nombre"] == ""


@pytest.mark.parametrize("valeur", ["1 234,56", "espace", "EUR"])
def test_falsifiable_une_valeur_inconnue_est_refusee_avant_toute_ecriture(client, valeur):
    pid = _projet(client)
    client.patch(f"/api/projects/{pid}", json={"format_nombre": "espace_virgule"})

    r = client.patch(f"/api/projects/{pid}", json={"name": "Renommé", "format_nombre": valeur})

    assert r.status_code == 422 and "écriture des nombres inconnue" in r.json()["detail"]
    relu = client.get("/api/projects").json()[0]
    assert (relu["name"], relu["format_nombre"]) == ("Projet web", "espace_virgule"), "rien n'est écrit à moitié"


def test_le_catalogue_servi_a_l_ecran_est_celui_de_la_validation(client):
    r = client.get("/api/settings/options/valeurs-du-projet")

    assert r.status_code == 200
    assert r.json() == {"formats_nombre": [{"cle": "espace_virgule", "libelle": "1 234,56"},
                                           {"cle": "virgule_point", "libelle": "1,234.56"},
                                           {"cle": "point_virgule", "libelle": "1.234,56"}]}, "aucune monnaie proposée (A38)"
    autre = _projet(client, "odoo")
    for cle in ("espace_virgule", "virgule_point", "point_virgule", ""):
        assert client.patch(f"/api/projects/{autre}", json={"format_nombre": cle}).json()["format_nombre"] == cle


# ── 2. Ce qui part vers le test ───────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("connecteur", ["odoo", "web"])
def test_falsifiable_rien_de_declare_arrive_vide_au_test_jamais_herite_du_serveur(connecteur, monkeypatch, tmp_path):
    """Revue du 2026-10-13 : le sous-processus part de l'environnement du serveur et relit `.env`. Une variable ABSENTE y
    prendrait la valeur du serveur — l'écriture des nombres d'un projet qui n'a rien déclaré serait décidée par l'installation."""
    from testpilot.execution.behave_runner import BehaveRunner

    monkeypatch.setenv(valeurs.ENV_FORMAT_NOMBRE, "virgule_point")
    env = runtime_env.project_env({"connector_type": connecteur, "base_url": "https://app.exemple.test", "username": "u",
                                   "password": "p", "database": "d", "format_nombre": ""})

    assert valeurs.ENV_FORMAT_NOMBRE not in env, "rien de déclaré, rien dans la connexion"
    transmis = BehaveRunner(connection=env, connector_type=connecteur, generated_dir=tmp_path)._subprocess_env(tmp_path)
    assert transmis[valeurs.ENV_FORMAT_NOMBRE] == "", "la valeur du serveur ne passe pas"
    monkeypatch.setenv(valeurs.ENV_FORMAT_NOMBRE, transmis[valeurs.ENV_FORMAT_NOMBRE])
    assert H._valeurs_du_projet() == (None, None)


@pytest.mark.parametrize("connecteur", ["odoo", "web"])
def test_ce_qui_est_declare_est_transmis_au_test(connecteur):
    env = runtime_env.project_env({"connector_type": connecteur, "base_url": "https://app.exemple.test", "username": "u",
                                   "password": "p", "database": "d", "format_nombre": "espace_virgule"})

    assert env[valeurs.ENV_FORMAT_NOMBRE] == "espace_virgule"


def test_falsifiable_une_valeur_enregistree_mais_inconnue_n_est_pas_transmise():
    assert valeurs.env({"format_nombre": "tiret"}) == {}
    assert valeurs.env(None) == {}
    assert set(valeurs.JAMAIS_HERITEES) == {valeurs.ENV_FORMAT_NOMBRE, valeurs.ENV_UNITES}


def test_ce_que_le_projet_declare_passe_le_lanceur_sans_etre_ecrase(tmp_path, monkeypatch):
    from testpilot.execution.behave_runner import BehaveRunner

    monkeypatch.setenv(valeurs.ENV_FORMAT_NOMBRE, "virgule_point")       # ce que dirait le serveur
    env = runtime_env.project_env({"connector_type": "web", "base_url": "https://app.exemple.test",
                                   "format_nombre": "point_virgule"})
    transmis = BehaveRunner(connection=env, connector_type="web", generated_dir=tmp_path)._subprocess_env(tmp_path)

    assert transmis[valeurs.ENV_FORMAT_NOMBRE] == "point_virgule"


# ── 3. Le harnais et l'application parlent de la même chose ───────────────────────────────────────────────────────────────


def test_accord_des_constantes_dupliquees_entre_l_application_et_le_harnais():
    assert H._ENV_FORMAT_NOMBRE_DU_PROJET == valeurs.ENV_FORMAT_NOMBRE
    assert set(H._SEPARATEURS_DU_FORMAT) == set(valeurs.LIBELLES_FORMAT_NOMBRE)
    # L'exemple montré à l'écran dit bien ce que la clé fait lire.
    for cle, exemple in valeurs.LIBELLES_FORMAT_NOMBRE.items():
        decimal, milliers = H._SEPARATEURS_DU_FORMAT[cle]
        assert ln.lire_nombre(exemple, separateur_decimal=decimal).valeur == ln.Decimal("1234.56")
        # Un séparateur que l'exemple ne MONTRE pas n'est pas déclaré : l'outil ne tranche rien pour lui.
        autres_signes = ({".", ","} - {decimal}) & set(exemple)
        assert decimal in exemple and autres_signes == ({milliers} if milliers else set())


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


# ── 4. Les unités AJOUTÉES par le projet (« palette » ; « palettes », « Palettes ») ───────────────────────────────────────


def test_un_projet_declare_modifie_et_retire_ses_unites(client):
    pid = _projet(client)
    assert client.get(f"/api/projects/{pid}/units").json() == []

    r = client.post(f"/api/projects/{pid}/units", json={"nom": " palette ", "ecritures": ["palettes", "Palettes", "palette", " "]})

    assert r.status_code == 201 and r.json()["nom"] == "palette" and r.json()["ecritures"] == ["palettes", "Palettes"]
    uid = r.json()["id"]
    r = client.put(f"/api/projects/{pid}/units/{uid}", json={"nom": "palette", "ecritures": ["palettes"]})
    assert r.json() == {"id": uid, "nom": "palette", "ecritures": ["palettes"]}
    assert client.get(f"/api/projects/{pid}/units").json() == [{"id": uid, "nom": "palette", "ecritures": ["palettes"]}]
    assert client.delete(f"/api/projects/{pid}/units/{uid}").status_code == 204
    assert client.get(f"/api/projects/{pid}/units").json() == []
    assert client.delete(f"/api/projects/{pid}/units/{uid}").status_code == 404
    assert client.put(f"/api/projects/{pid}/units/{uid}", json={"nom": "palette"}).status_code == 404


@pytest.mark.parametrize("corps", [
    {"nom": "kg"}, {"nom": "€"}, {"nom": "USD"}, {"nom": ""}, {"nom": "2x"},
    {"nom": "palette", "ecritures": ["kg"]}, {"nom": "palette", "ecritures": ["une unité beaucoup trop longue pour être lue"]},
])
def test_falsifiable_une_unite_que_l_outil_connait_deja_ou_ne_saurait_pas_lire_est_refusee(client, corps):
    """L'écran ne peut pas accepter ce que le test ne saura pas lire : c'est le lecteur de nombres lui-même qui valide."""
    pid = _projet(client)

    r = client.post(f"/api/projects/{pid}/units", json=corps)

    assert r.status_code == 422 and "unité refusée" in r.json()["detail"]
    assert client.get(f"/api/projects/{pid}/units").json() == []


def test_falsifiable_une_ecriture_ne_designe_qu_une_unite_du_projet(client):
    pid, autre = _projet(client), _projet(client, "odoo")
    client.post(f"/api/projects/{pid}/units", json={"nom": "palette", "ecritures": ["palettes"]})

    assert client.post(f"/api/projects/{pid}/units", json={"nom": "carton", "ecritures": ["palettes"]}).status_code == 409
    assert client.post(f"/api/projects/{pid}/units", json={"nom": "palettes"}).status_code == 409
    carton = client.post(f"/api/projects/{pid}/units", json={"nom": "carton"}).json()["id"]
    assert client.put(f"/api/projects/{pid}/units/{carton}", json={"nom": "palette"}).status_code == 409
    # La casse COMPTE (comme pour le constat) et un autre projet ne gêne pas.
    assert client.post(f"/api/projects/{pid}/units", json={"nom": "Palette"}).status_code == 201
    assert client.post(f"/api/projects/{autre}/units", json={"nom": "palette"}).status_code == 201
    assert client.put(f"/api/projects/{autre}/units/{carton}", json={"nom": "x"}).status_code == 404, "pas l'unité d'un autre projet"


def test_les_unites_du_projet_arrivent_au_test_et_seulement_les_siennes(client, tmp_path, monkeypatch):
    import json

    from testpilot.execution.behave_runner import BehaveRunner
    from testpilot.store.db import get_initialized_db
    from testpilot.store.repositories import ProjectRepo

    pid, autre = _projet(client), _projet(client, "odoo")
    client.post(f"/api/projects/{pid}/units", json={"nom": "palette", "ecritures": ["palettes", "Palettes"]})
    client.post(f"/api/projects/{autre}/units", json={"nom": "carton"})
    conn = get_initialized_db(config.DB_PATH)
    try:
        env = runtime_env.env_du_projet(conn, ProjectRepo(conn).get(pid))
        sans_unite = client.post("/api/projects", json={"name": "Sans unité", "connector_type": "odoo", "database": "d",
                                                        "base_url": "https://recette.exemple.test", "username": "u",
                                                        "password": "p"}).json()["id"]
        sans = runtime_env.env_du_projet(conn, ProjectRepo(conn).get(sans_unite))
    finally:
        conn.close()

    assert json.loads(env[valeurs.ENV_UNITES]) == [{"nom": "palette", "ecritures": ["palettes", "Palettes"]}]
    assert valeurs.ENV_UNITES not in sans
    # Le harnais en fait « écriture -> nom » ; un projet sans unité n'hérite pas de celles du serveur.
    monkeypatch.setenv(valeurs.ENV_UNITES, env[valeurs.ENV_UNITES])
    assert H._unites_du_projet() == {"palette": "palette", "palettes": "palette", "Palettes": "palette"}
    transmis = BehaveRunner(connection=sans, connector_type="odoo", generated_dir=tmp_path)._subprocess_env(tmp_path)
    assert transmis[valeurs.ENV_UNITES] == ""


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


def test_falsifiable_les_unites_arrivent_par_tous_les_chemins_qui_lancent_un_test(client):
    """Revue du 2026-10-13 (bloquant) : seules les exécutions de la génération recevaient les unités ; une campagne ou une
    ré-exécution ne les recevait pas — le même test, sur la même application, rendait deux verdicts."""
    import json

    from testpilot.api.services import run_service
    from testpilot.store.db import get_initialized_db
    from testpilot.store.repositories import CaseRepo, ModuleRepo, ProjectRepo

    pid = _projet(client)
    client.patch(f"/api/projects/{pid}", json={"format_nombre": "virgule_point"})
    client.post(f"/api/projects/{pid}/units", json={"nom": "palette", "ecritures": ["palettes", "Palettes"]})
    attendu = [{"nom": "palette", "ecritures": ["palettes", "Palettes"]}]
    conn = get_initialized_db(config.DB_PATH)
    try:
        projet = ProjectRepo(conn).get(pid)
        cas = CaseRepo(conn).create(title="Cas", module_id=ModuleRepo(conn).create(project_id=pid, name="M"), feature_slug="cas")
        chemins = {"génération": runtime_env.env_du_projet(conn, projet),
                   "campagne": run_service.resolve_connection(conn, cas),
                   "mesure": runtime_env.verifier_connexion_du_projet(conn, projet)}
    finally:
        conn.close()

    for nom, env in chemins.items():
        assert json.loads(env[valeurs.ENV_UNITES]) == attendu, nom
        assert env[valeurs.ENV_FORMAT_NOMBRE] == "virgule_point", nom


def test_falsifiable_les_listes_d_unites_restent_petites(client):
    pid = _projet(client)

    trop = client.post(f"/api/projects/{pid}/units", json={"nom": "palette", "ecritures": [f"p{'a' * i}" for i in range(1, 22)]})

    assert trop.status_code == 422 and "20 autres écritures au plus" in trop.json()["detail"]


# ── 5. Qui a le droit de déclarer : l'administrateur du projet, et lui seul ───────────────────────────────────────────────


@pytest.fixture
def equipe(client):
    """Un projet créé par un admin, avec un `dev`, un `testeur` et un `lecture_seule` membres du projet."""
    from testpilot.api import access
    from testpilot.store.db import get_initialized_db
    from testpilot.store.repositories import UserRepo

    def utilisateur(nom: str, role: str) -> int:
        c = get_initialized_db(config.DB_PATH)
        try:
            return UserRepo(c).create(username=nom, password_hash=access.hacher_mot_de_passe("mdp"), role=role)
        finally:
            c.close()

    utilisateur("Root", access.ROLE_ADMIN)
    ids = {nom: utilisateur(nom, role) for nom, role in (("Dev", access.ROLE_DEV), ("Testeuse", access.ROLE_TESTEUR),
                                                         ("Lecteur", access.ROLE_LECTURE_SEULE))}
    _se_connecter(client, "Root")
    pid = _projet(client)
    for nom, role in (("Dev", "dev"), ("Testeuse", "testeur"), ("Lecteur", "lecture_seule")):
        assert client.post(f"/api/projects/{pid}/members", json={"user_id": ids[nom], "role": role}).status_code == 201
    uid = client.post(f"/api/projects/{pid}/units", json={"nom": "palette"}).json()["id"]
    return pid, uid


def _se_connecter(client, nom):
    assert client.post("/api/auth/login", json={"username": nom, "password": "mdp"}).status_code == 200


@pytest.mark.parametrize("nom", ["Dev", "Testeuse", "Lecteur"])
def test_falsifiable_seul_l_administrateur_du_projet_declare_ses_valeurs(client, equipe, nom):
    """Une déclaration change des verdicts : elle vient de la personne qui administre le projet, pas d'un autre membre."""
    pid, uid = equipe
    _se_connecter(client, nom)

    assert client.get(f"/api/projects/{pid}/units").json() == [{"id": uid, "nom": "palette", "ecritures": []}], "tout membre lit"
    assert client.post(f"/api/projects/{pid}/units", json={"nom": "carton"}).status_code == 403
    assert client.put(f"/api/projects/{pid}/units/{uid}", json={"nom": "palette", "ecritures": ["kg"]}).status_code == 403
    assert client.delete(f"/api/projects/{pid}/units/{uid}").status_code == 403
    assert client.patch(f"/api/projects/{pid}", json={"format_nombre": "point_virgule"}).status_code == 403
