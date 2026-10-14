"""Lot PT-02a — le TABLEAU des données de test d'un projet : variables × jeux de données (décisions A26 à A31).

Ce que ces tests gardent :
1. un projet sans donnée de test n'a rien (ni variable, ni jeu) ; la première variable crée le jeu « Par défaut » ;
2. un nom ou une valeur qui casserait le texte d'un test est refusé AVANT toute écriture ;
3. une case vide ne s'enregistre pas (elle reprendra « Par défaut », A27) ;
4. qui a le droit de quoi (A30) : tout membre lit, testeur et plus modifie, l'administrateur du projet supprime ;
5. supprimer = corbeille, restaurable (A31), et l'outil sait dire quels tests utilisent une variable ;
6. les données d'un projet ne se mêlent jamais à celles d'un autre.
"""

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import access
from testpilot.api import app as app_mod
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, ModuleRepo, TestDataRepo, UserRepo, VersionRepo


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return TestClient(app_mod.app)


def _projet(client, nom: str = "Boutique") -> int:
    return client.post("/api/projects", json={"name": nom, "connector_type": "web", "base_url": "https://recette.exemple.test",
                                              "username": "testeur", "password": "secret"}).json()["id"]


def _url(pid: int, suite: str = "") -> str:
    return f"/api/projects/{pid}/donnees-de-test{suite}"


def _variable(client, pid: int, nom: str) -> int:
    r = client.post(_url(pid, "/variables"), json={"nom": nom})
    assert r.status_code == 201, r.text
    return next(v["id"] for v in r.json()["variables"] if v["nom"] == nom.strip().lower())


def _jeu(client, pid: int, nom: str) -> int:
    r = client.post(_url(pid, "/jeux"), json={"nom": nom})
    assert r.status_code == 201, r.text
    return next(j["id"] for j in r.json()["jeux"] if j["nom"] == nom)


# ── 1. Le tableau ─────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_un_projet_sans_donnee_de_test_n_a_ni_variable_ni_jeu(client):
    assert client.get(_url(_projet(client))).json() == {"variables": [], "jeux": []}


def test_la_premiere_variable_cree_le_jeu_par_defaut_et_le_tableau_se_remplit(client):
    pid = _projet(client)
    client_id, ville_id = _variable(client, pid, "client"), _variable(client, pid, " Ville ")
    grosse = _jeu(client, pid, "Grosse commande")
    t = client.get(_url(pid)).json()
    defaut = t["jeux"][0]

    assert [v["nom"] for v in t["variables"]] == ["client", "ville"]
    assert [(j["nom"], j["est_defaut"]) for j in t["jeux"]] == [("Par défaut", True), ("Grosse commande", False)]

    client.put(_url(pid, f"/jeux/{defaut['id']}/valeurs"), json={"valeurs": {str(client_id): "Martin SARL", str(ville_id): " Lyon "}})
    r = client.put(_url(pid, f"/jeux/{grosse}/valeurs"), json={"valeurs": {str(client_id): "Durand Industrie", str(ville_id): "  "}})

    assert r.status_code == 200
    jeux = {j["nom"]: j["valeurs"] for j in r.json()["jeux"]}
    assert jeux["Par défaut"] == {str(client_id): "Martin SARL", str(ville_id): "Lyon"}
    assert jeux["Grosse commande"] == {str(client_id): "Durand Industrie"}, "une case vide ne s'enregistre pas : elle reprendra « Par défaut »"


def test_falsifiable_ecrire_une_case_ne_touche_pas_aux_autres_et_une_valeur_vide_la_vide(client):
    pid = _projet(client)
    a, b = _variable(client, pid, "a"), _variable(client, pid, "b")
    defaut = client.get(_url(pid)).json()["jeux"][0]["id"]
    client.put(_url(pid, f"/jeux/{defaut}/valeurs"), json={"valeurs": {str(a): "1", str(b): "2"}})

    r = client.put(_url(pid, f"/jeux/{defaut}/valeurs"), json={"valeurs": {str(a): ""}})

    assert r.json()["jeux"][0]["valeurs"] == {str(b): "2"}


def test_les_niveaux_rendus_au_remplacement_suivent_le_tableau(client):
    """Ce que le lancement lira (PT-02b) : le jeu par défaut, puis le jeu choisi."""
    pid = _projet(client)
    c, v = _variable(client, pid, "client"), _variable(client, pid, "ville")
    grosse = _jeu(client, pid, "Grosse commande")
    defaut = client.get(_url(pid)).json()["jeux"][0]["id"]
    client.put(_url(pid, f"/jeux/{defaut}/valeurs"), json={"valeurs": {str(c): "Martin SARL", str(v): "Lyon"}})
    client.put(_url(pid, f"/jeux/{grosse}/valeurs"), json={"valeurs": {str(c): "Durand Industrie"}})
    conn = get_initialized_db(config.DB_PATH)
    try:
        depot = TestDataRepo(conn)
        assert depot.niveaux(pid) == (["client", "ville"], [("Par défaut", {"client": "Martin SARL", "ville": "Lyon"})])
        assert depot.niveaux(pid, grosse)[1] == [("Par défaut", {"client": "Martin SARL", "ville": "Lyon"}),
                                                  ("Grosse commande", {"client": "Durand Industrie"})]
        with pytest.raises(ValueError):
            depot.niveaux(pid, 9999)
        assert depot.niveaux(_projet(client, "Vide")) == ([], [])
    finally:
        conn.close()


# ── 2. Ce qui est refusé ──────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("nom", ["", "nom client", "2clients", "client-2", "{{client}}", "x" * 41])
def test_falsifiable_un_nom_de_variable_mal_forme_est_refuse(client, nom):
    pid = _projet(client)

    assert client.post(_url(pid, "/variables"), json={"nom": nom}).status_code == 422
    assert client.get(_url(pid)).json() == {"variables": [], "jeux": []}, "rien n'est créé, pas même le jeu par défaut"


@pytest.mark.parametrize("valeur", ['Société "Alpha"', "a | b", "ligne 1\nligne 2", "{{autre}}", "x" * 501])
def test_falsifiable_une_valeur_qui_casserait_le_texte_du_test_est_refusee_sans_rien_ecrire(client, valeur):
    pid = _projet(client)
    a, b = _variable(client, pid, "a"), _variable(client, pid, "b")
    defaut = client.get(_url(pid)).json()["jeux"][0]["id"]

    r = client.put(_url(pid, f"/jeux/{defaut}/valeurs"), json={"valeurs": {str(a): "bonne", str(b): valeur}})

    assert r.status_code == 422
    assert client.get(_url(pid)).json()["jeux"][0]["valeurs"] == {}, "pas même la bonne valeur : rien à moitié"


def test_falsifiable_les_doublons_et_le_jeu_par_defaut_sont_proteges(client):
    pid = _projet(client)
    _variable(client, pid, "client")
    grosse = _jeu(client, pid, "Grosse commande")
    defaut = client.get(_url(pid)).json()["jeux"][0]["id"]

    assert client.post(_url(pid, "/variables"), json={"nom": "CLIENT"}).status_code == 409
    assert client.post(_url(pid, "/jeux"), json={"nom": "grosse  commande"}).status_code == 409
    assert client.post(_url(pid, "/jeux"), json={"nom": "par défaut"}).status_code == 409
    assert client.post(_url(pid, "/jeux"), json={"nom": "  "}).status_code == 422
    assert client.patch(_url(pid, f"/jeux/{defaut}"), json={"nom": "Autre"}).status_code == 422
    assert client.delete(_url(pid, f"/jeux/{defaut}")).status_code == 422
    assert client.patch(_url(pid, f"/jeux/{grosse}"), json={"nom": "Très grosse commande"}).status_code == 200
    assert client.put(_url(pid, f"/jeux/{grosse}/valeurs"), json={"valeurs": {"9999": "x"}}).status_code == 422
    assert client.put(_url(pid, "/jeux/9999/valeurs"), json={"valeurs": {}}).status_code == 404


def test_falsifiable_les_donnees_d_un_projet_ne_se_melent_pas_a_celles_d_un_autre(client):
    a, b = _projet(client, "A"), _projet(client, "B")
    va = _variable(client, a, "client")
    vb = _variable(client, b, "client")
    jeu_b = _jeu(client, b, "Export")

    assert client.put(_url(a, f"/jeux/{jeu_b}/valeurs"), json={"valeurs": {str(va): "x"}}).status_code == 404
    assert client.put(_url(b, f"/jeux/{jeu_b}/valeurs"), json={"valeurs": {str(va): "x"}}).status_code == 422
    assert client.patch(_url(a, f"/variables/{vb}"), json={"description": "x"}).status_code == 404
    assert client.delete(_url(a, f"/jeux/{jeu_b}")).status_code == 404
    assert [j["nom"] for j in client.get(_url(a)).json()["jeux"]] == ["Par défaut"]


# ── 3. Corbeille et usages (A31) ──────────────────────────────────────────────────────────────────────────────────────────


def _cas_qui_ecrit(pid: int, feature: str) -> int:
    conn = get_initialized_db(config.DB_PATH)
    try:
        cid = CaseRepo(conn).create(title="Commande", module_id=ModuleRepo(conn).create(project_id=pid, name="Ventes"),
                                    feature_slug="commande")
        vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="", feature_content=feature, steps_content="")
        conn.execute("UPDATE test_case SET current_version_id=? WHERE id=?", (vid, cid))
        conn.commit()
        return cid
    finally:
        conn.close()


def test_l_outil_dit_quels_tests_utilisent_une_variable(client):
    pid = _projet(client)
    ville, pays = _variable(client, pid, "ville"), _variable(client, pid, "pays")
    cid = _cas_qui_ecrit(pid, 'Fonctionnalité: X\n  Scénario: Y\n    Quand je saisis "{{ Ville }}" et 10 % de {remise}\n')

    assert client.get(_url(pid, f"/variables/{ville}/usages")).json() == [{"id": cid, "title": "Commande"}]
    assert client.get(_url(pid, f"/variables/{pays}/usages")).json() == []
    assert client.get(_url(pid, "/variables/9999/usages")).status_code == 404


def test_supprimer_met_a_la_corbeille_et_restaurer_rend_tout(client):
    pid = _projet(client)
    ville = _variable(client, pid, "ville")
    export = _jeu(client, pid, "Export")
    client.put(_url(pid, f"/jeux/{export}/valeurs"), json={"valeurs": {str(ville): "Lille"}})

    assert client.delete(_url(pid, f"/variables/{ville}")).status_code == 204
    assert client.delete(_url(pid, f"/jeux/{export}")).status_code == 204
    assert client.delete(_url(pid, f"/variables/{ville}")).status_code == 404, "déjà à la corbeille"

    t = client.get(_url(pid)).json()
    assert t["variables"] == [] and [j["nom"] for j in t["jeux"]] == ["Par défaut"]
    corbeille = {(e["type"], e["titre"]) for e in client.get(f"/api/projects/{pid}/corbeille").json()}
    assert corbeille == {("variable", "ville"), ("jeu_de_donnees", "Export")}
    # Un nom à la corbeille est réutilisable ; restaurer l'ancien est alors refusé, sans rien casser.
    _variable(client, pid, "ville")
    assert client.post(f"/api/corbeille/variable/{ville}/restaurer").status_code == 409
    assert client.post(f"/api/corbeille/jeu_de_donnees/{export}/restaurer").status_code in (200, 204)
    assert [j["nom"] for j in client.get(_url(pid)).json()["jeux"]] == ["Par défaut", "Export"]


def test_falsifiable_la_valeur_d_une_variable_restauree_revient_avec_elle(client):
    pid = _projet(client)
    ville = _variable(client, pid, "ville")
    defaut = client.get(_url(pid)).json()["jeux"][0]["id"]
    client.put(_url(pid, f"/jeux/{defaut}/valeurs"), json={"valeurs": {str(ville): "Lyon"}})
    client.delete(_url(pid, f"/variables/{ville}"))
    assert client.get(_url(pid)).json()["jeux"][0]["valeurs"] == {}, "la valeur d'une variable supprimée ne se montre pas"

    assert client.post(f"/api/corbeille/variable/{ville}/restaurer").status_code in (200, 204)

    assert client.get(_url(pid)).json()["jeux"][0]["valeurs"] == {str(ville): "Lyon"}


def test_purger_detruit_la_variable_et_ses_valeurs_seulement_depuis_la_corbeille(client):
    pid = _projet(client)
    ville = _variable(client, pid, "ville")
    defaut = client.get(_url(pid)).json()["jeux"][0]["id"]
    client.put(_url(pid, f"/jeux/{defaut}/valeurs"), json={"valeurs": {str(ville): "Lyon"}})

    assert client.delete(f"/api/corbeille/variable/{ville}").status_code == 409, "pas à la corbeille : on ne détruit pas"
    client.delete(_url(pid, f"/variables/{ville}"))
    assert client.delete(f"/api/corbeille/variable/{ville}").status_code in (200, 204)

    conn = get_initialized_db(config.DB_PATH)
    try:
        assert conn.execute("SELECT COUNT(*) FROM test_variable").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM test_dataset_value").fetchone()[0] == 0
    finally:
        conn.close()


# ── 4. Qui a le droit de quoi (A30) ───────────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def equipe(client):
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
    ville = _variable(client, pid, "ville")
    export = _jeu(client, pid, "Export")
    return pid, ville, export


def _se_connecter(client, nom):
    assert client.post("/api/auth/login", json={"username": nom, "password": "mdp"}).status_code == 200


@pytest.mark.parametrize("nom", ["Testeuse", "Dev"])
def test_une_testeuse_ajoute_et_modifie_mais_ne_supprime_pas(client, equipe, nom):
    """A30 : le tableau se modifie comme les tests. La suppression reste à l'administrateur du projet, qui seul restaure."""
    pid, ville, export = equipe
    _se_connecter(client, nom)

    assert client.post(_url(pid, "/variables"), json={"nom": "pays"}).status_code == 201
    assert client.post(_url(pid, "/jeux"), json={"nom": "Client étranger"}).status_code == 201
    assert client.put(_url(pid, f"/jeux/{export}/valeurs"), json={"valeurs": {str(ville): "Lille"}}).status_code == 200
    assert client.patch(_url(pid, f"/jeux/{export}"), json={"nom": "Export UE"}).status_code == 200
    assert client.delete(_url(pid, f"/variables/{ville}")).status_code == 403
    assert client.delete(_url(pid, f"/jeux/{export}")).status_code == 403


def test_falsifiable_un_lecteur_consulte_sans_rien_modifier(client, equipe):
    pid, ville, export = equipe
    _se_connecter(client, "Lecteur")

    assert [v["nom"] for v in client.get(_url(pid)).json()["variables"]] == ["ville"]
    assert client.get(_url(pid, f"/variables/{ville}/usages")).status_code == 200
    assert client.post(_url(pid, "/variables"), json={"nom": "pays"}).status_code == 403
    assert client.post(_url(pid, "/jeux"), json={"nom": "X"}).status_code == 403
    assert client.put(_url(pid, f"/jeux/{export}/valeurs"), json={"valeurs": {str(ville): "x"}}).status_code == 403
    assert client.patch(_url(pid, f"/variables/{ville}"), json={"description": "x"}).status_code == 403
    fichier = {"file": ("d.xlsx", b"x", "application/octet-stream")}
    assert client.post(_url(pid, "/import/apercu"), files=fichier).status_code == 403
    assert client.post(_url(pid, "/import"), files=fichier).status_code == 403
    assert client.get(_url(pid, "/export")).status_code == 200


def test_l_administrateur_du_projet_supprime(client, equipe):
    pid, ville, export = equipe   # connecté en « Root »

    assert client.delete(_url(pid, f"/variables/{ville}")).status_code == 204
    assert client.delete(_url(pid, f"/jeux/{export}")).status_code == 204


# ── Revue du 2026-10-14 ───────────────────────────────────────────────────────────────────────────────────────────────────


def test_falsifiable_la_requete_des_tests_concernes_passe_aussi_sur_postgresql():
    """Écrit dans la requête, « LIKE '%{{%' » était lu par psycopg comme un marqueur : 500, et la suppression d'une variable
    ne s'ouvrait plus. La requête passe ici par la conversion réelle vers PostgreSQL."""
    psycopg_queries = pytest.importorskip("psycopg._queries")
    from testpilot.store.portable_connection import _adapter_sql

    requetes = []

    class Espion:
        def execute(self, sql, params=()):
            requetes.append((sql, params))
            return []

    TestDataRepo(Espion()).usages(1, "ville")

    assert requetes
    from psycopg.adapt import Transformer

    for sql, params in requetes:
        psycopg_queries.PostgresQuery(Transformer()).convert(_adapter_sql(sql)[0], params)   # lève sur un « % » mal placé


def test_falsifiable_une_restauration_suit_les_regles_de_la_creation(client, monkeypatch):
    """Casse comprise (« Export » et « export »), et plafond du nombre de jeux."""
    from testpilot.store import repositories

    pid = _projet(client)
    _variable(client, pid, "ville")
    export = _jeu(client, pid, "Export")
    client.delete(_url(pid, f"/jeux/{export}"))
    _jeu(client, pid, "export")
    assert client.post(f"/api/corbeille/jeu_de_donnees/{export}/restaurer").status_code == 409
    assert [j["nom"] for j in client.get(_url(pid)).json()["jeux"]] == ["Par défaut", "export"]

    autre = _jeu(client, pid, "Autre")
    client.delete(_url(pid, f"/jeux/{autre}"))
    monkeypatch.setattr(repositories.TestDatasetRepo, "plafond", 2)
    assert client.post(f"/api/corbeille/jeu_de_donnees/{autre}/restaurer").status_code == 409


@pytest.mark.parametrize("valeurs", [{"01": "un"}, {" 1": "un"}, {"x": "un"}, {"-1": "un"}])
def test_falsifiable_une_case_est_designee_une_seule_fois_par_l_identifiant_de_sa_variable(client, valeurs):
    pid = _projet(client)
    _variable(client, pid, "ville")
    defaut = client.get(_url(pid)).json()["jeux"][0]["id"]

    assert client.put(_url(pid, f"/jeux/{defaut}/valeurs"), json={"valeurs": valeurs}).status_code == 422


def test_falsifiable_renommer_une_variable_est_refuse_en_clair(client):
    pid = _projet(client)
    ville = _variable(client, pid, "ville")

    assert client.patch(_url(pid, f"/variables/{ville}"), json={"nom": "commune"}).status_code == 422
    assert [v["nom"] for v in client.get(_url(pid)).json()["variables"]] == ["ville"]


def test_falsifiable_le_depot_revalide_les_valeurs_qu_on_lui_donne(client):
    pid = _projet(client)
    ville = _variable(client, pid, "ville")
    conn = get_initialized_db(config.DB_PATH)
    try:
        depot = TestDataRepo(conn)
        with pytest.raises(ValueError):
            depot.poser_valeurs(pid, depot.jeux(pid)[0]["id"], {ville: 'Société "Alpha"'})
    finally:
        conn.close()


def test_falsifiable_une_testeuse_ne_restaure_ni_ne_purge_et_un_autre_projet_ne_lui_montre_rien(client, equipe):
    pid, ville, export = equipe
    client.delete(_url(pid, f"/jeux/{export}"))   # par « Root », l'administrateur
    autre = _projet(client, "Autre")
    _se_connecter(client, "Testeuse")

    assert client.post(f"/api/corbeille/jeu_de_donnees/{export}/restaurer").status_code == 403
    assert client.delete(f"/api/corbeille/jeu_de_donnees/{export}").status_code == 403
    assert client.get(_url(autre)).status_code in (403, 404), "la testeuse n'est pas membre de l'autre projet"
