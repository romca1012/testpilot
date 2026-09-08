"""Lot 1 du chemin de déploiement (2026-07-24) : **savoir contre quoi on teste**.

Deux défauts jumeaux, tous deux invisibles à l'écran — la pire espèce :

1. **Le repli silencieux.** Un projet sans connexion complète faisait tourner ses tests contre la
   configuration globale de la machine (`localhost:10017` / `admin`). L'interface affichait un
   projet, le navigateur en testait un autre, et **rien ne pouvait le trahir** : une campagne
   entière pouvait être verte contre la mauvaise application.
2. **La cible non tracée.** `execution` n'enregistrait aucune adresse : deux runs verts du même
   cas, l'un contre la recette et l'autre contre une démo, étaient **indiscernables** dans
   l'historique. Sur un serveur partagé par plusieurs testeurs, c'est tout le référentiel qui
   devient invérifiable.

⚠️ Ces tests exercent le **refus** et l'**écriture**, jamais un vrai run : ils ne touchent aucune
application réelle et ne dépensent rien.
"""

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import app as app_mod
from testpilot.api.services import campaign_service, generation_service, run_service
from testpilot.connectors.runtime_env import (
    ConnexionIncomplete,
    cible_de,
    project_env,
    verifier_connexion,
)
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import (
    CaseRepo,
    ExecutionRepo,
    ModuleRepo,
    ProjectRepo,
    ReviewRepo,
    RunRepo,
    VersionRepo,
)

_COMPLETE = {"connector_type": "odoo", "name": "Recette", "base_url": "http://recette:8069",
             "database": "recette_db", "username": "qa", "password": "secret"}


@pytest.fixture
def conn(tmp_path):
    c = get_initialized_db(tmp_path / "cible.db")
    yield c
    c.close()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return TestClient(app_mod.app)


def _projet(conn, **champs) -> int:
    params = {"name": "Recette", "connector_type": "odoo", "base_url": "http://recette:8069",
              "database": "recette_db", "username": "qa", "password": "secret"}
    params.update(champs)
    return ProjectRepo(conn).create(**params)


def _cas_pret(conn, project_id: int) -> int:
    """Un cas avec une version APPROUVÉE — tout est prêt sauf, éventuellement, la connexion."""
    mid = ModuleRepo(conn).create(project_id=project_id, name="Demandes")
    cid = CaseRepo(conn).create(title="Créer une demande", module_id=mid, feature_slug="demande")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="",
                                   feature_content="Scenario: x", steps_content="")
    CaseRepo(conn).set_current_version(cid, vid)
    ReviewRepo(conn).create(test_case_id=cid, version_id=vid, decision="approved",
                            reviewer="validation-metier", comment="")
    return cid


# ── 1. Le refus, au lieu du repli silencieux ──────────────────────────────────

def test_une_connexion_complete_donne_ses_variables():
    assert verifier_connexion(_COMPLETE) == {
        "ODOO_URL": "http://recette:8069", "ODOO_DB": "recette_db",
        "ODOO_USER": "qa", "ODOO_PASSWORD": "secret"}


@pytest.mark.parametrize("manquant", ["base_url", "database", "username", "password"])
def test_chaque_element_manquant_fait_REFUSER(manquant):
    """Aucun des quatre n'est facultatif : il suffit d'un pour ne plus savoir ce qu'on teste."""
    projet = dict(_COMPLETE, **{manquant: ""})
    with pytest.raises(ConnexionIncomplete) as err:
        verifier_connexion(projet)
    # Le message nomme ce qui manque, EN LANGAGE MÉTIER (§8 : pas un nom de colonne brut).
    assert "incomplète" in err.value.message()
    assert "Recette" in err.value.message()
    assert manquant not in err.value.message()


def test_le_message_dit_QUOI_corriger_et_pas_seulement_que_ca_echoue():
    with pytest.raises(ConnexionIncomplete) as err:
        verifier_connexion(dict(_COMPLETE, password="", username=""))
    message = err.value.message()
    assert "l'utilisateur" in message and "le mot de passe" in message
    assert "écran Projets" in message


def test_projet_absent_ou_connecteur_inconnu_refusent_aussi():
    with pytest.raises(ConnexionIncomplete):
        verifier_connexion(None)
    with pytest.raises(ConnexionIncomplete):
        verifier_connexion(dict(_COMPLETE, connector_type="sap"))


def test_project_env_reste_un_traducteur_SANS_jugement():
    """La CLI s'en sert délibérément avec un `.env` de machine : elle ne doit pas se mettre à
    lever. Seule `verifier_connexion` juge — c'est la séparation qui rend la garde applicable
    à l'API sans casser la ligne de commande."""
    assert project_env(dict(_COMPLETE, password="")) == {
        "ODOO_URL": "http://recette:8069", "ODOO_DB": "recette_db", "ODOO_USER": "qa"}


# ── 2. Le refus atteint bien les portes d'entrée ──────────────────────────────

def test_lancer_un_cas_sans_connexion_est_REFUSE(conn):
    pid = _projet(conn, password="")
    cid = _cas_pret(conn, pid)
    with pytest.raises(run_service.RunError) as err:
        run_service.trigger_run(conn, cid)
    assert err.value.code == "no_connection"
    # ⚠️ Et AUCUNE ligne d'exécution n'a été ouverte : un refus ne laisse pas de trace d'un test
    # qui n'a pas eu lieu (sinon l'historique compterait des runs fantômes).
    assert ExecutionRepo(conn).list_for_case(cid) == []


def test_lancer_une_campagne_sans_connexion_est_REFUSE_avant_de_la_passer_en_cours(conn):
    pid = _projet(conn, base_url="")
    cid = _cas_pret(conn, pid)
    rid = RunRepo(conn).create(project_id=pid, name="Campagne", description="", refs="",
                               selection_mode="frozen", case_ids=[cid])
    with pytest.raises(campaign_service.CampaignError) as err:
        campaign_service.start_campaign(conn, rid)
    assert err.value.code == "no_connection"
    # Le run reste en brouillon : un refus ne doit pas laisser une campagne bloquée « en cours ».
    assert RunRepo(conn).get(rid)["status"] == "draft"


def test_generer_un_cas_sans_connexion_est_REFUSE_avant_toute_depense(conn):
    """La garde est AVANT le premier appel LLM : refuser après aurait coûté de l'argent pour rien."""
    pid = _projet(conn, database="")
    mid = ModuleRepo(conn).create(project_id=pid, name="Demandes")
    with pytest.raises(generation_service.GenerationError) as err:
        generation_service.start_generation(conn, mid, spec_content="Une spec", title="Cas")
    assert err.value.code == "no_connection"


def test_l_api_repond_409_avec_le_message_actionnable(client):
    """Bout en bout : le refus arrive à l'écran, avec ce qu'il faut corriger."""
    pid = client.post("/api/projects", json={"name": "Sans mot de passe",
                                             "base_url": "http://x:8069",
                                             "database": "db", "username": "qa"}).json()["id"]
    mid = client.post(f"/api/projects/{pid}/modules", json={"name": "M"}).json()["id"]
    resp = client.post(f"/api/modules/{mid}/cases", json={"spec_content": "Une spec"})
    assert resp.status_code == 409
    assert "le mot de passe" in resp.json()["detail"]


# ── 3. La cible, inscrite dans l'historique ───────────────────────────────────

def test_la_cible_est_ecrite_a_l_ouverture_de_l_execution(conn):
    pid = _projet(conn)
    cid = _cas_pret(conn, pid)
    eid, _, _, _ = run_service.trigger_run(conn, cid)
    ligne = ExecutionRepo(conn).get(eid)
    assert ligne["target_url"] == "http://recette:8069"
    assert ligne["target_database"] == "recette_db"
    assert ligne["target_username"] == "qa"


def test_le_mot_de_passe_n_est_JAMAIS_inscrit(conn):
    """Un secret n'a rien à faire dans une ligne d'historique qu'on lit, exporte et affiche."""
    assert "secret" not in str(cible_de(_COMPLETE))
    assert set(cible_de(_COMPLETE)) == {"target_url", "target_database", "target_username"}

    pid = _projet(conn)
    cid = _cas_pret(conn, pid)
    eid, _, _, _ = run_service.trigger_run(conn, cid)
    assert "secret" not in str(dict(ExecutionRepo(conn).get(eid)))


def test_une_execution_ancienne_dit_ne_pas_savoir_plutot_que_de_deviner(conn):
    """La migration ne RECONSTITUE pas la cible des exécutions passées.

    ⚠️ C'est la leçon de la migration 17 : classer sur l'état instantané (« la configuration
    d'aujourd'hui ») aurait donné à une supposition l'apparence d'une mesure. Vide = « on ne
    sait pas », ce qui est la vérité.
    """
    pid = _projet(conn)
    cid = _cas_pret(conn, pid)
    # Une ligne écrite « à l'ancienne », sans cible.
    conn.execute("INSERT INTO execution (test_case_id, version_id, trigger, started_at)"
                 " VALUES (?,?,?,datetime('now'))", (cid, CaseRepo(conn).get(cid)["current_version_id"], "first_run"))
    conn.commit()
    ligne = conn.execute("SELECT * FROM execution ORDER BY id DESC LIMIT 1").fetchone()
    assert ligne["target_url"] == ""


def test_la_campagne_dit_contre_quoi_elle_a_tourne(conn):
    """La cible remonte sur l'écran d'une CAMPAGNE — celui qu'on lit pour décider d'un go/no-go.

    ⚠️ Lue sur les **exécutions de la campagne**, jamais sur la connexion actuelle du projet :
    afficher la cible d'aujourd'hui sur des résultats d'hier serait exactement le mensonge que la
    migration 20 sert à empêcher.
    """
    pid = _projet(conn)
    cid = _cas_pret(conn, pid)
    rid = RunRepo(conn).create(project_id=pid, name="Campagne", description="", refs="",
                               selection_mode="frozen", case_ids=[cid])
    eid, _, _, _ = run_service.trigger_run(conn, cid)
    conn.execute("UPDATE execution SET run_id=? WHERE id=?", (rid, eid))
    conn.commit()

    cibles = RunRepo(conn).cibles_du_run(rid)
    assert cibles == [{"target_url": "http://recette:8069", "target_database": "recette_db"}]


def test_deux_cibles_dans_une_campagne_sont_SIGNALEES_pas_arbitrees(conn):
    """Si la connexion a changé en cours de campagne, ses résultats ne sont plus comparables.
    En choisir une au hasard donnerait à la campagne une cohérence qu'elle n'a pas."""
    pid = _projet(conn)
    cid = _cas_pret(conn, pid)
    rid = RunRepo(conn).create(project_id=pid, name="Campagne", description="", refs="",
                               selection_mode="frozen", case_ids=[cid])
    vid = CaseRepo(conn).get(cid)["current_version_id"]
    for url in ("http://recette:8069", "http://demo:8069"):
        eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid,
                                         cible={"target_url": url, "target_database": "db"})
        conn.execute("UPDATE execution SET run_id=? WHERE id=?", (rid, eid))
    conn.commit()

    assert len(RunRepo(conn).cibles_du_run(rid)) == 2


def test_la_cible_remonte_jusqu_a_l_api_et_au_rapport(client):
    """Écrite mais non exposée, elle ne servirait à rien : c'est l'écran qui doit la dire."""
    from testpilot.api.services import report_service
    from testpilot.store.db import get_initialized_db as _db

    pid = client.post("/api/projects", json={"name": "Recette", "base_url": "http://recette:8069",
                                             "database": "recette_db", "username": "qa",
                                             "password": "secret"}).json()["id"]
    mid = client.post(f"/api/projects/{pid}/modules", json={"name": "M"}).json()["id"]
    cid = client.post(f"/api/modules/{mid}/cases/manual",
                      json={"title": "Cas manuel", "preconditions": "", "test_steps": ["a"],
                            "expected_result": "ok"}).json()["id"]

    conn = _db(config.DB_PATH)
    try:
        eid = ExecutionRepo(conn).create(
            test_case_id=cid, version_id=CaseRepo(conn).get(cid)["current_version_id"],
            cible=cible_de(_COMPLETE))
        rapport = report_service.build_report_for_execution(conn, eid)
    finally:
        conn.close()

    assert rapport.target_url == "http://recette:8069"
    assert "secret" not in report_service.report_mod.render_html(rapport)

    detail = client.get(f"/api/executions/{eid}").json()
    assert detail["target_url"] == "http://recette:8069"
    assert detail["target_database"] == "recette_db"
    assert "password" not in detail
