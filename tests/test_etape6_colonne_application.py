"""Étape 6 du plan unique (IT-4, A55) — une colonne `{{client}}` remplie avec des enregistrements qui EXISTENT dans
l'application, relevés au lancement et figés avec lui (A29) ; interrupteur `TESTPILOT_COLONNE_DEPUIS_L_APPLICATION` éteint
tant que le porteur n'a pas tranché combien et lesquels (A105).

Gardé ici : éteint, une source déclarée ne change rien ; allumé, une itération par enregistrement relevé, figée (une relance
reprend les mêmes, même si l'application a changé) ; une colonne vide, illisible ou une application injoignable : rien n'est
lancé (jamais joué avec d'autres valeurs que celles annoncées) ; une valeur qui casserait le texte du test est écartée ; la
source est validée à la saisie (requête d'oracle DÉCLARÉE, modèle et champ Odoo pour Odoo seulement).
"""

from __future__ import annotations

import json

import pytest

from testpilot import config
from testpilot.api.services import campaign_service, colonnes_application_service as svc, donnees_de_test_service as service
from testpilot.generation import interrupteurs
from testpilot.parametres import colonne_application as ca
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, ExecutionRepo, ModuleRepo, ProjectRepo, RunRepo, TestDataRepo, VersionRepo

FEATURE = """# language: fr
Fonctionnalité: Commande
  Scénario: Passer une commande
    Quand je choisis le client "{{client}}"
    Alors la page affiche le texte "Commande enregistrée"
"""
SOURCE = {"type": "oracle", "requete": "etat", "chemin": "clients", "cle": "nom", "nombre": 3}


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "GENERATED_DIR", tmp_path / "generated")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "db.sqlite")
    conn = get_initialized_db(config.DB_PATH)
    yield conn
    conn.close()


def _projet(conn, feature: str = FEATURE):
    pid = ProjectRepo(conn).create(name="Boutique", connector_type="web", base_url="http://app")
    cid = CaseRepo(conn).create(title="Commande", module_id=ModuleRepo(conn).create(project_id=pid, name="Ventes"),
                                feature_slug="commande")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="", feature_content=feature,
                                   steps_content="from behave import then\n")
    conn.execute("UPDATE test_case SET current_version_id=? WHERE id=?", (vid, cid))
    conn.commit()
    depot = TestDataRepo(conn)
    client = depot.creer_variable(pid, nom="client")
    depot.poser_valeurs(pid, depot.jeux(pid)[0]["id"], {client: "Client saisi"})
    depot.poser_la_source(pid, client, SOURCE)
    run_id = RunRepo(conn).create(project_id=pid, name="Campagne", case_ids=[cid])
    return pid, cid, vid, run_id


def _jouer(conn, run_id, cid, vid):
    eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid)
    conn.execute("UPDATE execution SET run_id=? WHERE id=?", (run_id, eid))
    conn.commit()
    script = service.preparer_le_script(conn, eid, cid, vid, "commande")
    texte = conn.execute("SELECT parametres_joues FROM execution WHERE id=?", (eid,)).fetchone()[0]
    return script, (json.loads(texte) if texte else {})


def _lecteur(valeurs):
    lus = []

    def lire(projet, source):
        lus.append((projet["id"], source["requete"]))
        return list(valeurs)
    return lire, lus


# ── Le module pur ──────────────────────────────────────────────────────────────────────────────────────────────────────

def test_falsifiable_valeurs_retenues_ecarte_ce_qui_casserait_le_test_et_les_non_valeurs():
    brutes = ["Dupont SARL", 'Le "Bon" Coin', "A|B", "", None, True, {"x": 1}, 42, "Dupont SARL", "Martin", "Leroy", "Zed"]
    assert ca.valeurs_retenues(brutes, 3) == ["Dupont SARL", "42", "Martin"]


def test_valeurs_de_la_reponse_ne_devine_jamais_une_forme():
    reponse = {"clients": [{"nom": "Dupont"}, {"autre": 1}, {"nom": "Martin"}]}
    assert ca.valeurs_de_la_reponse(reponse, "clients", "nom") == ["Dupont", "Martin"]
    with pytest.raises(ca.ColonneImpossible):
        ca.valeurs_de_la_reponse(reponse, "commandes", "nom")
    with pytest.raises(ca.ColonneImpossible):
        ca.valeurs_de_la_reponse({"clients": {"nom": "x"}}, "clients", "nom")


@pytest.mark.parametrize("source, connecteur, message", [
    ({**SOURCE, "requete": "inconnue"}, "web", "requête de lecture"),
    ({"type": "odoo", "modele": "res.partner", "champ": "name"}, "web", "Odoo"),
    ({"type": "odoo", "modele": "res.partner; drop", "champ": "name"}, "odoo", "noms techniques"),
    ({**SOURCE, "nombre": 0}, "web", "de 1 à"),
    ({"type": "sql"}, "web", "source inconnue"),
])
def test_falsifiable_une_source_qui_ne_peut_pas_etre_lue_est_refusee_a_la_saisie(source, connecteur, message):
    with pytest.raises(ca.SourceInvalide, match=message):
        ca.valider_source(source, connector_type=connecteur, requetes_declarees=["etat"])


def test_une_source_valide_est_normalisee_et_vide_la_retire():
    assert ca.valider_source(SOURCE, connector_type="web", requetes_declarees=["etat"]) == SOURCE
    assert ca.valider_source({"type": "odoo", "modele": "res.partner", "champ": "name"}, connector_type="odoo") == {
        "type": "odoo", "modele": "res.partner", "champ": "name", "nombre": ca.NOMBRE_PAR_DEFAUT}
    assert ca.valider_source({}, connector_type="web") == {}


def test_etendre_les_figes_une_iteration_par_valeur_et_jamais_au_dela_du_maximum():
    figes = {"jeu": "Par défaut", "connues": ["client", "ville"],
             "valeurs": {"client": {"valeur": "Client saisi", "origine": "Par défaut"},
                         "ville": {"valeur": "Lyon", "origine": "Par défaut"}}}
    etendus = ca.etendre_les_figes(figes, {"client": ["Dupont", "Martin"]}, maximum=50)
    assert [j["valeurs"]["client"]["valeur"] for j in etendus["jeux"]] == ["Dupont", "Martin"]
    assert all(j["valeurs"]["ville"]["valeur"] == "Lyon" for j in etendus["jeux"]), "les autres valeurs sont gardées"
    assert etendus["jeux"][0]["valeurs"]["client"]["origine"] == ca.ORIGINE
    with pytest.raises(ca.ColonneImpossible, match="aucun enregistrement"):
        ca.etendre_les_figes(figes, {"client": []}, maximum=50)
    with pytest.raises(ca.ColonneImpossible, match="au plus"):
        ca.etendre_les_figes(figes, {"client": ["a", "b", "c"]}, maximum=2)


# ── Au lancement ───────────────────────────────────────────────────────────────────────────────────────────────────────

def test_falsifiable_eteint_une_source_declaree_ne_change_rien(base, monkeypatch):
    monkeypatch.delenv(interrupteurs.ENV_COLONNE_DEPUIS_L_APPLICATION, raising=False)
    lire, lus = _lecteur(["Dupont"])
    monkeypatch.setattr(svc, "lire_les_valeurs", lire)
    pid, cid, vid, run_id = _projet(base)
    service.figer_pour_la_campagne(base, RunRepo(base).get(run_id))
    figes = json.loads(RunRepo(base).get(run_id)["parametres_figes"])
    assert lus == [] and "colonnes_de_l_application" not in figes and figes["valeurs"]["client"]["valeur"] == "Client saisi"


def test_falsifiable_allume_une_iteration_par_client_reel_figee_au_lancement(base, monkeypatch):
    monkeypatch.setenv(interrupteurs.ENV_COLONNE_DEPUIS_L_APPLICATION, "1")
    lire, lus = _lecteur(["Dupont SARL", "Martin", "Leroy", "Zed"])
    monkeypatch.setattr(svc, "lire_les_valeurs", lire)
    pid, cid, vid, run_id = _projet(base)
    service.figer_pour_la_campagne(base, RunRepo(base).get(run_id))

    lire2, _ = _lecteur(["Tout autre client"])   # l'application change APRÈS le lancement
    monkeypatch.setattr(svc, "lire_les_valeurs", lire2)
    service.figer_pour_la_campagne(base, RunRepo(base).get(run_id))   # une relance reprend ce qui est figé

    figes = json.loads(RunRepo(base).get(run_id)["parametres_figes"])
    assert figes["colonnes_de_l_application"] == {"client": ["Dupont SARL", "Martin", "Leroy"]}
    assert lus == [(pid, "etat")]
    script, joues = _jouer(base, run_id, cid, vid)
    assert [it["valeurs"]["client"]["valeur"] for it in joues["iterations"]] == ["Dupont SARL", "Martin", "Leroy"]
    assert script.blocage == "" and "Martin" in (script.dossier / "commande.feature").read_text(encoding="utf-8")


# ── Revue du 2026-10-22 : B1, B2, C1, C2, C5 ───────────────────────────────────────────────────────────────────────────

def _allume(monkeypatch, valeurs=("Dupont SARL", "Martin", "Leroy")):
    monkeypatch.setenv(interrupteurs.ENV_COLONNE_DEPUIS_L_APPLICATION, "1")
    lire, lus = _lecteur(list(valeurs))
    monkeypatch.setattr(svc, "lire_les_valeurs", lire)
    return lus


def test_falsifiable_un_test_qui_n_emploie_pas_la_variable_n_annonce_aucun_client(base, monkeypatch):
    """B1 : le test écrit « Acme » en dur — joué UNE fois, sous le nom du jeu de base ; jamais « client : Dupont … »."""
    _allume(monkeypatch)
    pid, cid, vid, run_id = _projet(base, FEATURE.replace('"{{client}}"', '"Acme"'))
    service.figer_pour_la_campagne(base, RunRepo(base).get(run_id))
    script, joues = _jouer(base, run_id, cid, vid)
    assert "iterations" not in joues and "client :" not in json.dumps(joues, ensure_ascii=False)


def test_falsifiable_une_variable_relevee_dans_un_alors_bloque_le_cas(base, monkeypatch):
    """B2 : « Alors … {{client}} » comparerait l'application à elle-même (un défaut stocké et affiché sortirait conforme)."""
    _allume(monkeypatch)
    pid, cid, vid, run_id = _projet(base, FEATURE.replace('"Commande enregistrée"', '"Commande de {{client}}"'))
    service.figer_pour_la_campagne(base, RunRepo(base).get(run_id))
    script, _ = _jouer(base, run_id, cid, vid)
    assert "jamais à vérifier" in script.blocage and script.dossier is None


def test_falsifiable_une_ligne_du_cas_qui_fixe_la_colonne_n_est_pas_multipliee_et_le_plafond_vaut_apres(base, monkeypatch):
    """B1 (lignes) et C2 : une ligne du cas fixe `client` — elle n'est pas multipliée par les clients relevés."""
    from testpilot.store.repositories import CaseDataRepo

    _allume(monkeypatch)
    pid, cid, vid, run_id = _projet(base)
    client = TestDataRepo(base).variables(pid)[0]["id"]
    CaseDataRepo(base).remplacer(cid, pid, [{"nom": f"Classe {i}", "valeurs": {client: f"Fixé {i}"}} for i in range(20)])
    service.figer_pour_la_campagne(base, RunRepo(base).get(run_id))
    script, joues = _jouer(base, run_id, cid, vid)
    assert script.blocage == ""
    assert [it["valeurs"]["client"]["valeur"] for it in joues["iterations"]] == [f"Fixé {i}" for i in range(20)]


def test_falsifiable_une_requete_devenue_une_ecriture_n_est_jamais_jouee(monkeypatch):
    """C1 : la méthode de la requête a changé depuis la saisie (POST) — rien n'est envoyé à l'application."""
    appels = []
    monkeypatch.setattr("testpilot.connectors.oracle_http.OracleHttp.executer", lambda self, nom: appels.append(nom))
    projet = {"oracle_type": "http", "oracle_base_url": "http://oracle", "oracle_auth": "{}",
              "oracle_queries": json.dumps([{"name": "etat", "method": "POST", "path": "/commandes"}])}
    with pytest.raises(ca.ColonneImpossible, match="lecture"):
        svc.lire_les_valeurs(projet, SOURCE)
    assert appels == []


def test_la_colonne_est_relevee_sur_l_application_de_l_environnement_de_la_campagne(base, monkeypatch):
    """C5 : figée sur « Recette », la campagne relève l'oracle de Recette — jamais celui du projet par défaut."""
    monkeypatch.setenv(interrupteurs.ENV_COLONNE_DEPUIS_L_APPLICATION, "1")
    vus = []
    monkeypatch.setattr(svc, "lire_les_valeurs", lambda projet, source: vus.append(projet.get("oracle_base_url")) or ["Dupont"])
    recette = {"base_url": "http://recette", "oracle_base_url": "http://oracle-recette"}
    monkeypatch.setattr("testpilot.api.services.environnements_service.environnement_du_run", lambda conn, run_id: recette)
    monkeypatch.setattr("testpilot.parametres.environnements.projet_sur", lambda projet, env: {**projet, **(env or {})})
    pid, cid, vid, run_id = _projet(base)
    service.figer_pour_la_campagne(base, RunRepo(base).get(run_id))
    assert vus == ["http://oracle-recette"]


@pytest.mark.parametrize("panne", [[], ca.ColonneImpossible("l'oracle n'a pas répondu")], ids=["aucun-client", "injoignable"])
def test_falsifiable_une_colonne_qui_ne_se_remplit_pas_empeche_le_lancement(base, monkeypatch, panne):
    monkeypatch.setenv(interrupteurs.ENV_COLONNE_DEPUIS_L_APPLICATION, "1")

    def lire(projet, source):
        if isinstance(panne, Exception):
            raise panne
        return panne
    monkeypatch.setattr(svc, "lire_les_valeurs", lire)
    monkeypatch.setattr("testpilot.connectors.runtime_env.verifier_connexion", lambda *a, **k: {})
    pid, cid, vid, run_id = _projet(base)

    with pytest.raises(campaign_service.CampaignError) as refus:
        campaign_service.start_campaign(base, run_id)
    assert refus.value.code == "column_from_app"
    assert RunRepo(base).get(run_id)["status"] != "running"
    assert not (RunRepo(base).get(run_id)["parametres_figes"] or "").strip(), "rien n'est figé"


# ── À la saisie (API) ──────────────────────────────────────────────────────────────────────────────────────────────────

def test_api_la_source_est_validee_enregistree_puis_retiree(base):
    from fastapi.testclient import TestClient

    from testpilot.api.app import app

    pid = ProjectRepo(base).create(name="Boutique", connector_type="web", base_url="http://app")
    base.execute("UPDATE project SET oracle_queries=? WHERE id=?",
                 (json.dumps([{"name": "etat", "method": "GET", "path": "/__etat"}]), pid))
    base.commit()
    vid = TestDataRepo(base).creer_variable(pid, nom="client")
    client = TestClient(app)
    url = f"/api/projects/{pid}/donnees-de-test/variables/{vid}/source"

    refus = client.put(url, json={"source": {**SOURCE, "requete": "autre"}})
    assert refus.status_code == 422 and "requête de lecture" in refus.json()["detail"]
    ok = client.put(url, json={"source": SOURCE})
    assert ok.status_code == 200
    assert json.loads(ok.json()["variables"][0]["source_application"]) == SOURCE
    assert client.put(url, json={"source": {}}).json()["variables"][0]["source_application"] == ""


# ── La lecture de l'application ─────────────────────────────────────────────────────────────────────────────────────────

def test_le_lecteur_oracle_lit_la_requete_declaree_d_un_vrai_serveur():
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class _Oracle(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            corps = json.dumps({"clients": [{"nom": "Dupont"}, {"nom": "Martin"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(corps)))
            self.end_headers()
            self.wfile.write(corps)

    serveur = ThreadingHTTPServer(("127.0.0.1", 0), _Oracle)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    try:
        projet = {"oracle_type": "http", "oracle_base_url": f"http://127.0.0.1:{serveur.server_address[1]}",
                  "oracle_auth": "{}", "oracle_queries": json.dumps([{"name": "etat", "method": "GET", "path": "/__etat"}])}
        assert svc.lire_les_valeurs(projet, SOURCE) == ["Dupont", "Martin"]
        with pytest.raises(ca.ColonneImpossible, match="plus d'oracle"):
            svc.lire_les_valeurs({}, SOURCE)
    finally:
        serveur.shutdown()


def test_le_lecteur_odoo_lit_le_champ_dans_l_ordre_d_odoo_et_se_deconnecte(monkeypatch):
    from testpilot.connectors import odoo

    etat = {"deconnecte": False}

    class _Odoo:
        def connect(self):
            pass

        def search(self, modele, filtres, limit=0):
            return [7, 3]

        def read(self, modele, ids, champs):
            return [{"id": 3, "name": "Martin"}, {"id": 7, "name": "Dupont"}]

        def disconnect(self):
            etat["deconnecte"] = True

    monkeypatch.setattr(odoo.OdooConnector, "from_project", classmethod(lambda cls, projet, **kw: _Odoo()))
    source = {"type": "odoo", "modele": "res.partner", "champ": "name", "nombre": 2}
    assert svc.lire_les_valeurs({"connector_type": "odoo"}, source) == ["Dupont", "Martin"]
    assert etat["deconnecte"]
