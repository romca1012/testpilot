"""Lot PT-04a — plusieurs environnements par projet (décisions A48 à A50 du porteur, 2026-10-16).

Ce que ces tests gardent :
1. un environnement ajouté déclare sa NATURE, sans défaut (A48) ; l'environnement par défaut est le projet, seul son nom change ;
2. une exécution par jeu ET par environnement, dans un plan ; 50 au plus ; « Production » refusé à la création ;
3. au lancement, l'environnement est relu et FIGÉ : devenu « Production » ou supprimé entre-temps, rien ne part ;
4. chaque cas est joué contre l'adresse, la base et l'oracle de SON environnement — jamais celui du projet par erreur ;
   sans oracle déclaré pour l'environnement, pas d'oracle (celui du projet interrogerait une autre application) ;
   la garde du harnais (`ODOO_ENV=prod`) est posée pour un environnement « Production », en second verrou ;
5. pas de réparation automatique sur un environnement ajouté (A50) ;
6. un projet sans environnement ajouté ne voit rien changer (R1) ;
7. une planification retient ses environnements ; un seul à la corbeille, et rien ne part (comme les jeux, A36).
"""

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import app as app_mod
from testpilot.api.services import campaign_service, environnements_service, run_service, scheduler_service
from testpilot.parametres import environnements as env
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, ModuleRepo, RunRepo, VersionRepo

APP = "https://recette.exemple.test"
PREPROD = "https://preprod.exemple.test"


# ── 1. Les règles pures ────────────────────────────────────────────────────────────────────────────────────────────────────

def test_falsifiable_la_nature_n_a_pas_de_defaut():
    with pytest.raises(env.EnvironnementInvalide, match="Test ou Production"):
        env.valider(nom="Préproduction", base_url=PREPROD, nature="")
    with pytest.raises(env.EnvironnementInvalide):
        env.valider(nom="Préproduction", base_url=PREPROD, nature="prod")
    assert env.valider(nom=" Préproduction ", base_url=PREPROD, nature="test")["nom"] == "Préproduction"


@pytest.mark.parametrize("champs, attendu", [
    ({"nom": "", "base_url": PREPROD}, "nom est requis"),
    ({"nom": "P", "base_url": ""}, "adresse est requise"),
    ({"nom": "P", "base_url": "preprod.exemple.test"}, "http"),
    ({"nom": "P", "base_url": PREPROD, "oracle_base_url": "ftp://x"}, "oracle"),
    ({"nom": "x" * 61, "base_url": PREPROD}, "60 caractères"),
])
def test_une_declaration_invalide_est_refusee_en_le_disant(champs, attendu):
    with pytest.raises(env.EnvironnementInvalide, match=attendu):
        env.valider(nature="test", **champs)


def test_falsifiable_un_projet_vu_sur_un_environnement():
    projet = {"id": 1, "connector_type": "odoo", "base_url": APP, "database": "recette", "connector_version": "17",
              "oracle_type": "http", "oracle_base_url": APP + "/api", "username": "u"}
    sur = env.projet_sur(projet, {"base_url": PREPROD, "database": "preprod", "connector_version": "16",
                                  "oracle_base_url": PREPROD + "/api"})
    assert (sur["base_url"], sur["database"], sur["connector_version"], sur["oracle_base_url"]) == (
        PREPROD, "preprod", "16", PREPROD + "/api")
    assert sur["username"] == "u" and projet["base_url"] == APP, "comptes gardés (A49), projet non modifié"

    sans_oracle = env.projet_sur(projet, {"base_url": PREPROD})
    assert sans_oracle["oracle_type"] == "" and sans_oracle["oracle_base_url"] == "", (
        "jamais l'oracle du projet contre une autre application")
    assert env.projet_sur(projet, None) is projet


def test_un_environnement_fige_illisible_n_est_jamais_remplace_par_le_defaut():
    assert env.lire_fige("") is None
    for illisible in ("{", "[]", '{"id": "x"}', '{"id": 3}', '{"id": true, "base_url": "x"}'):
        with pytest.raises(env.EnvironnementInvalide):
            env.lire_fige(illisible)
    assert env.lire_fige(env.figer({"nom": "P", "base_url": PREPROD, "nature": "test"}, environment_id=3))["id"] == 3


# ── 2. Déclarer ────────────────────────────────────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return TestClient(app_mod.app)


@pytest.fixture
def relu(monkeypatch):
    """La relecture humaine n'est pas l'objet de ces tests : le cas est exécutable."""
    monkeypatch.setattr(run_service, "gate_du_cas", lambda *a, **kw: SimpleNamespace(allowed=True, reason=""))


def _projet(client, **plus) -> int:
    corps = {"name": "Boutique", "connector_type": "web", "base_url": APP, "username": "u", "password": "p", **plus}
    return client.post("/api/projects", json=corps).json()["id"]


def _ajouter(client, pid, nom="Préproduction", nature="test", **plus):
    return client.post(f"/api/projects/{pid}/environnements",
                       json={"nom": nom, "base_url": PREPROD, "nature": nature, **plus})


def _id(client, pid, nom):
    return next(e["id"] for e in client.get(f"/api/projects/{pid}/environnements").json() if e["nom"] == nom)


def test_falsifiable_le_defaut_est_le_projet_et_seul_son_nom_change(client):
    pid = _projet(client)

    liste = client.get(f"/api/projects/{pid}/environnements").json()
    assert [(e["id"], e["nom"], e["base_url"], e["nature_libelle"], e["est_defaut"]) for e in liste] == [
        (0, "Par défaut", APP, "Test", True)]

    r = client.patch(f"/api/projects/{pid}/environnements/0", json={"nom": "Recette", "base_url": "https://ailleurs.test"})
    assert r.status_code == 200 and r.json()[0]["nom"] == "Recette"
    assert r.json()[0]["base_url"] == APP, "l'adresse du défaut se règle dans « Identité et application »"
    assert client.delete(f"/api/projects/{pid}/environnements/0").status_code == 422


def test_ajouter_modifier_et_mettre_a_la_corbeille(client):
    pid = _projet(client)

    assert _ajouter(client, pid, nature="").status_code == 422, "nature obligatoire, sans défaut (A48)"
    r = _ajouter(client, pid, database="preprod")
    assert r.status_code == 201 and [e["nom"] for e in r.json()] == ["Par défaut", "Préproduction"]
    assert _ajouter(client, pid, nom="PRÉPRODUCTION").status_code == 422, "homonyme (casse comprise)"
    assert _ajouter(client, pid, nom="par défaut").status_code == 422, "le nom du défaut est pris aussi"

    eid = _id(client, pid, "Préproduction")
    r = client.patch(f"/api/projects/{pid}/environnements/{eid}",
                     json={"nom": "Préprod", "base_url": PREPROD, "nature": "production"})
    assert r.status_code == 200 and r.json()[1]["nature_libelle"] == "Production"

    assert client.delete(f"/api/projects/{pid}/environnements/{eid}").status_code == 204
    assert len(client.get(f"/api/projects/{pid}/environnements").json()) == 1
    corbeille = client.get(f"/api/projects/{pid}/corbeille").json()
    assert [(c["type"], c["titre"]) for c in corbeille] == [("environnement", "Préprod")]
    assert client.post(f"/api/corbeille/environnement/{eid}/restaurer").status_code == 204
    assert len(client.get(f"/api/projects/{pid}/environnements").json()) == 2


# ── 3. Créer les exécutions ────────────────────────────────────────────────────────────────────────────────────────────────

def _cas(pid: int) -> int:
    conn = get_initialized_db(config.DB_PATH)
    try:
        module = conn.execute("SELECT id FROM module WHERE project_id=? ORDER BY id", (pid,)).fetchone()
        module_id = module["id"] if module else ModuleRepo(conn).create(project_id=pid, name="Ventes")
        rang = conn.execute("SELECT COUNT(*) FROM test_case WHERE module_id=?", (module_id,)).fetchone()[0]
        cid = CaseRepo(conn).create(title=f"Commande {rang}", module_id=module_id, feature_slug=f"commande_{rang}")
        vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="",
                                       feature_content="Fonctionnalité: X\n  Scénario: Y\n    Alors ok\n", steps_content="")
        conn.execute("UPDATE test_case SET current_version_id=? WHERE id=?", (vid, cid))
        conn.commit()
        return cid
    finally:
        conn.close()


def _creer(client, pid, cid, **plus):
    return client.post(f"/api/projects/{pid}/runs", json={"name": "Nuit", "selection_mode": "frozen", "case_ids": [cid], **plus})


def test_sans_environnement_demande_la_creation_est_celle_d_avant(client):
    pid = _projet(client)
    cid = _cas(pid)
    _ajouter(client, pid)

    r = _creer(client, pid, cid)

    assert r.status_code == 201 and r.json()["environment_id"] is None and r.json()["plan_id"] is None


def test_falsifiable_un_plan_par_environnement_et_par_jeu(client):
    pid = _projet(client)
    cid = _cas(pid)
    client.patch(f"/api/projects/{pid}/environnements/0", json={"nom": "Recette"})
    _ajouter(client, pid)
    eid = _id(client, pid, "Préproduction")
    base = f"/api/projects/{pid}/donnees-de-test"
    client.post(f"{base}/variables", json={"nom": "client"})
    client.post(f"{base}/jeux", json={"nom": "Pro"})
    jeux = {j["nom"]: j["id"] for j in client.get(base).json()["jeux"]}

    r = _creer(client, pid, cid, environment_ids=[0, eid], dataset_ids=list(jeux.values()))

    assert r.status_code == 201
    plan = client.get(f"/api/plans/{r.json()['plan_id']}").json()
    assert sorted((x["name"], x["environment_id"]) for x in plan["runs"]) == sorted([
        ("Nuit — Par défaut — Recette", None), ("Nuit — Pro — Recette", None),
        ("Nuit — Par défaut — Préproduction", eid), ("Nuit — Pro — Préproduction", eid)])


def test_falsifiable_la_production_et_l_inconnu_sont_refuses_sans_rien_creer(client):
    pid = _projet(client)
    cid = _cas(pid)
    _ajouter(client, pid, nom="Prod", nature="production")
    prod = _id(client, pid, "Prod")

    r = _creer(client, pid, cid, environment_ids=[0, prod])
    assert r.status_code == 422 and "production" in r.json()["detail"]
    assert _creer(client, pid, cid, environment_ids=[999]).status_code == 422
    assert _creer(client, pid, cid, environment_ids=[prod], mode="manuelle").status_code == 422
    assert client.get(f"/api/projects/{pid}/runs").json() == []


def test_cinquante_executions_au_plus_en_tout(client, monkeypatch):
    from testpilot.api.routes import runs
    monkeypatch.setattr(runs, "JEUX_PAR_LANCEMENT_MAX", 3)
    pid = _projet(client)
    cid = _cas(pid)
    _ajouter(client, pid)
    base = f"/api/projects/{pid}/donnees-de-test"
    client.post(f"{base}/variables", json={"nom": "client"})
    client.post(f"{base}/jeux", json={"nom": "Pro"})
    jeux = [j["id"] for j in client.get(base).json()["jeux"]]

    r = _creer(client, pid, cid, environment_ids=[0, _id(client, pid, "Préproduction")], dataset_ids=jeux)

    assert r.status_code == 422 and "3 exécutions au plus" in r.json()["detail"]
    assert client.get(f"/api/projects/{pid}/runs").json() == []


# ── 4. Lancer et jouer ─────────────────────────────────────────────────────────────────────────────────────────────────────

def _run_sur(client, pid, cid, eid):
    return _creer(client, pid, cid, environment_ids=[eid]).json()["id"]


def test_falsifiable_au_lancement_l_environnement_est_fige_puis_joue(client, monkeypatch, relu):
    pid = _projet(client)
    cid = _cas(pid)
    _ajouter(client, pid, oracle_base_url="")
    eid = _id(client, pid, "Préproduction")
    run_id = _run_sur(client, pid, cid, eid)
    monkeypatch.setattr(run_service, "run_execution", lambda *a, **kw: joues.append(kw.get("environnement")))
    joues = []

    conn = get_initialized_db(config.DB_PATH)
    try:
        params = campaign_service.start_campaign(conn, run_id)
        # modifié après le lancement : la campagne joue ce qui a été figé
        conn.execute("UPDATE project_environment SET base_url='https://autre.test' WHERE id=?", (eid,))
        conn.commit()
        campaign_service.run_campaign(params["run_id"], params["case_ids"])
        cible = conn.execute("SELECT target_url FROM execution WHERE run_id=?", (run_id,)).fetchone()[0]
    finally:
        conn.close()

    assert cible == PREPROD, "l'exécution a été créée contre l'environnement figé, pas contre le projet"
    assert [j["base_url"] for j in joues] == [PREPROD]
    assert client.get(f"/api/projects/{pid}/runs").json()[0]["environnement"] == "Préproduction"


@pytest.mark.parametrize("changement", ["production", "corbeille"])
def test_falsifiable_un_environnement_devenu_injouable_ne_part_pas(client, changement):
    pid = _projet(client)
    cid = _cas(pid)
    _ajouter(client, pid)
    eid = _id(client, pid, "Préproduction")
    run_id = _run_sur(client, pid, cid, eid)
    if changement == "production":
        client.patch(f"/api/projects/{pid}/environnements/{eid}",
                     json={"nom": "Préproduction", "base_url": PREPROD, "nature": "production"})
    else:
        client.delete(f"/api/projects/{pid}/environnements/{eid}")

    r = client.post(f"/api/runs/{run_id}/launch")

    assert r.status_code == 409 and r.json()["code"] == "environnement_refuse"
    conn = get_initialized_db(config.DB_PATH)
    try:
        assert RunRepo(conn).get(run_id)["status"] == "draft"
    finally:
        conn.close()


def test_falsifiable_un_run_jamais_fige_n_est_pas_joue_sur_le_defaut(client, monkeypatch):
    pid = _projet(client)
    cid = _cas(pid)
    _ajouter(client, pid)
    run_id = _run_sur(client, pid, cid, _id(client, pid, "Préproduction"))
    monkeypatch.setattr(run_service, "trigger_run", lambda *a, **kw: pytest.fail("aucun cas ne doit être joué"))

    campaign_service.run_campaign(run_id, [cid])   # lancé sans passer par `start_campaign` : rien n'est figé


def test_falsifiable_la_connexion_d_un_cas_vise_son_environnement(client, monkeypatch):
    from testpilot.connectors import oracle_config, runtime_env
    monkeypatch.setattr(runtime_env, "_verifier_oracle_joignable", lambda projet: None)   # aucun réseau dans ce test
    pid = _projet(client)
    conn = get_initialized_db(config.DB_PATH)
    try:
        conn.execute("UPDATE project SET oracle_type='http', oracle_base_url=? WHERE id=?", (APP + "/etat", pid))
        conn.commit()
    finally:
        conn.close()
    cid = _cas(pid)
    conn = get_initialized_db(config.DB_PATH)
    try:
        sur_preprod = run_service.resolve_connection(conn, cid, {"base_url": PREPROD, "nature": "test"})
        avec_oracle = run_service.resolve_connection(conn, cid, {"base_url": PREPROD, "nature": "test",
                                                                 "oracle_base_url": PREPROD + "/etat"})
        sur_prod = run_service.resolve_connection(conn, cid, {"base_url": PREPROD, "nature": "production"})
        par_defaut = run_service.resolve_connection(conn, cid)
    finally:
        conn.close()

    assert sur_preprod["WEB_URL"] == PREPROD and "ODOO_ENV" not in sur_preprod
    assert oracle_config.ENV_ORACLE not in sur_preprod, "jamais l'oracle de la recette pendant un test en préproduction"
    assert json.loads(avec_oracle[oracle_config.ENV_ORACLE])["base_url"] == PREPROD + "/etat"
    assert sur_prod["ODOO_ENV"] == "prod", "second verrou : la garde du harnais refuse de jouer"
    assert par_defaut["WEB_URL"] == APP and "ODOO_ENV" not in par_defaut
    assert json.loads(par_defaut[oracle_config.ENV_ORACLE])["base_url"] == APP + "/etat"


def test_falsifiable_pas_de_reparation_sur_un_environnement_ajoute(client, monkeypatch, relu):
    pid = _projet(client)
    cid = _cas(pid)
    conn = get_initialized_db(config.DB_PATH)
    try:
        eid = run_service.trigger_run(conn, cid)[0]
    finally:
        conn.close()
    reparations = []
    monkeypatch.setattr(run_service, "_execute_and_persist", lambda *a, **kw: object())
    monkeypatch.setattr(run_service, "_maybe_repair", lambda *a, **kw: reparations.append(1))
    monkeypatch.setattr(run_service, "_assurer_script_sur_disque", lambda *a, **kw: None)

    run_service.run_execution(eid, "commande", cid, 0, environnement={"base_url": PREPROD, "nature": "test"})
    assert reparations == []
    run_service.run_execution(eid, "commande", cid, 0)
    assert reparations == [1], "sur l'environnement par défaut, la réparation reste possible"


def test_un_projet_sans_environnement_ajoute_ne_voit_rien_change(client):
    pid = _projet(client)
    cid = _cas(pid)
    run_id = _creer(client, pid, cid).json()["id"]
    conn = get_initialized_db(config.DB_PATH)
    try:
        campaign_service.start_campaign(conn, run_id)
        run = RunRepo(conn).get(run_id)
        assert run["environnement_fige"] == "" and environnements_service.environnement_du_run(conn, run_id) is None
    finally:
        conn.close()


# ── 5. Planifier ───────────────────────────────────────────────────────────────────────────────────────────────────────────

def _planifier(client, pid, cid, **plus):
    return client.post(f"/api/projects/{pid}/schedules", json={
        "name": "Nuit", "selection_mode": "frozen", "case_ids": [cid], "frequency": "daily", "hour": 2, "minute": 0, **plus})


def test_falsifiable_une_planification_joue_ses_environnements(client, monkeypatch):
    pid = _projet(client)
    cid = _cas(pid)
    _ajouter(client, pid)
    eid = _id(client, pid, "Préproduction")
    _ajouter(client, pid, nom="Prod", nature="production")

    assert _planifier(client, pid, cid, environment_ids=[_id(client, pid, "Prod")]).status_code == 422
    r = _planifier(client, pid, cid, environment_ids=[0, eid])
    assert r.status_code == 201 and r.json()["environment_ids"] == [0, eid]

    lances = []
    monkeypatch.setattr(scheduler_service, "_lancer", lambda conn, run_id, acteur: lances.append(run_id))
    conn = get_initialized_db(config.DB_PATH)
    try:
        crees = scheduler_service.tick(conn, now=datetime(2026, 10, 17, 3, 0, tzinfo=timezone.utc))
        envs_lances = [RunRepo(conn).get(i)["environment_id"] for i in lances]
    finally:
        conn.close()
    assert len(crees) == 1 and sorted(envs_lances, key=lambda x: x or 0) == [None, eid]


def test_falsifiable_un_environnement_de_la_planification_a_la_corbeille_rien_ne_part(client, monkeypatch):
    pid = _projet(client)
    cid = _cas(pid)
    _ajouter(client, pid)
    eid = _id(client, pid, "Préproduction")
    _planifier(client, pid, cid, environment_ids=[0, eid])
    client.delete(f"/api/projects/{pid}/environnements/{eid}")
    monkeypatch.setattr(scheduler_service, "_lancer", lambda *a: pytest.fail("rien ne doit partir"))

    conn = get_initialized_db(config.DB_PATH)
    try:
        assert scheduler_service.tick(conn, now=datetime(2026, 10, 17, 3, 0, tzinfo=timezone.utc)) == []
        assert conn.execute("SELECT COUNT(*) FROM test_run").fetchone()[0] == 0
    finally:
        conn.close()


def test_les_ids_d_une_planification_illisibles_ne_jouent_jamais_le_defaut():
    assert env.ids_lus("") == [] and env.ids_lus("[0, 3]") == [0, 3]
    with pytest.raises(env.EnvironnementInvalide):
        env.ids_lus(json.dumps(["x"]), strict=True)


# ── 6. Revue du 2026-10-16 ─────────────────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("changement", ["production", "corbeille"])
def test_falsifiable_une_relance_ou_une_reprise_revérifie_l_environnement(client, monkeypatch, relu, changement):
    """Bloquant de la revue : une campagne déjà lancée (environnement figé) puis relancée, ou reprise après un redémarrage,
    ne joue plus sur un environnement passé en « Production » ou mis à la corbeille entre-temps (A48)."""
    pid = _projet(client)
    cid = _cas(pid)
    _ajouter(client, pid)
    eid = _id(client, pid, "Préproduction")
    run_id = _run_sur(client, pid, cid, eid)
    conn = get_initialized_db(config.DB_PATH)
    try:
        params = campaign_service.start_campaign(conn, run_id)
        RunRepo(conn).set_status(run_id, "completed", completed=True)
    finally:
        conn.close()
    if changement == "production":
        client.patch(f"/api/projects/{pid}/environnements/{eid}",
                     json={"nom": "Préproduction", "base_url": PREPROD, "nature": "production"})
    else:
        client.delete(f"/api/projects/{pid}/environnements/{eid}")

    r = client.post(f"/api/runs/{run_id}/launch")
    assert r.status_code == 409 and r.json()["code"] == "environnement_refuse"

    monkeypatch.setattr(run_service, "trigger_run", lambda *a, **kw: pytest.fail("aucun cas ne doit être joué à la reprise"))
    campaign_service.run_campaign(params["run_id"], params["case_ids"])


def test_falsifiable_le_harnais_recoit_la_connexion_de_l_environnement(client, monkeypatch, relu):
    """`run_execution` construit le runner avec la connexion de l'environnement — et un runner qui n'apprend rien."""
    pid = _projet(client)
    cid = _cas(pid)
    conn = get_initialized_db(config.DB_PATH)
    try:
        eid = run_service.trigger_run(conn, cid, environnement={"base_url": PREPROD, "nature": "test"})[0]
        trigger = conn.execute("SELECT trigger FROM execution WHERE id=?", (eid,)).fetchone()[0]
    finally:
        conn.close()
    construits = []

    class _Runner:
        def __init__(self, **kw):
            construits.append(kw)
            self.connection = kw["connection"]

    monkeypatch.setattr(run_service, "BehaveRunner", _Runner)
    monkeypatch.setattr(run_service, "_execute_and_persist", lambda *a, **kw: object())
    monkeypatch.setattr(run_service, "_assurer_script_sur_disque", lambda *a, **kw: None)

    run_service.run_execution(eid, "commande", cid, 0, environnement={"base_url": PREPROD, "nature": "test"})
    run_service.run_execution(eid, "commande", cid, 0)

    assert [k["connection"]["WEB_URL"] for k in construits] == [PREPROD, APP]
    assert [k.get("environnement_ajoute", False) for k in construits] == [True, False]
    assert trigger == "rerun", "le premier jet d'une version se mesure sur l'environnement par défaut (A50)"


def test_un_runner_sur_un_environnement_ajoute_n_apprend_rien():
    from testpilot.execution.behave_runner import BehaveRunner
    assert BehaveRunner(environnement_ajoute=True).sans_apprentissage is True
    assert BehaveRunner().sans_apprentissage is False


def test_falsifiable_un_lancement_bloque_porte_la_cible_de_l_environnement(client):
    pid = _projet(client)
    cid = _cas(pid)   # jamais relu : la relecture humaine bloque son lancement
    conn = get_initialized_db(config.DB_PATH)
    try:
        eid = run_service.enregistrer_lancement_bloque(conn, case_id=cid, code="needs_review", message="à relire",
                                                       environnement={"base_url": PREPROD, "nature": "test"})
        cible = conn.execute("SELECT target_url FROM execution WHERE id=?", (eid,)).fetchone()[0]
    finally:
        conn.close()
    assert cible == PREPROD


def test_un_environnement_odoo_declare_sa_base(client):
    pid = _projet(client, connector_type="odoo", database="recette")

    r = _ajouter(client, pid)
    assert r.status_code == 422 and "base est requise" in r.json()["detail"]
    assert _ajouter(client, pid, database="preprod").status_code == 201


def test_une_restauration_ne_reprend_pas_le_nom_du_defaut(client):
    pid = _projet(client)
    _ajouter(client, pid, nom="Recette")
    eid = _id(client, pid, "Recette")
    client.delete(f"/api/projects/{pid}/environnements/{eid}")
    client.patch(f"/api/projects/{pid}/environnements/0", json={"nom": "Recette"})

    r = client.post(f"/api/corbeille/environnement/{eid}/restaurer")
    assert r.status_code == 409 and "par défaut" in r.json()["detail"]


# ── 7. Le harnais ne sort pas de l'environnement joué (revue du 2026-10-16, bloquant) ──────────────────────────────────────

def _helpers():
    import sys
    sys.path.insert(0, str(config.BEHAVE_RUNTIME_DIR / "steps_library"))
    import _base_helpers
    return _base_helpers


def test_falsifiable_une_url_absolue_d_une_autre_origine_est_refusee():
    h = _helpers()
    assert h.url_dans_l_application(PREPROD + "/", "/shop") == PREPROD + "/shop"
    assert h.url_dans_l_application(PREPROD, "shop") == PREPROD + "/shop"
    assert h.url_dans_l_application(PREPROD, PREPROD + "/shop?x=1") == PREPROD + "/shop?x=1"
    for ailleurs in (APP + "/shop", "http://preprod.exemple.test/shop", "https://preprod.exemple.test:8443/shop"):
        with pytest.raises(h.NavigationImpossibleError):
            h.url_dans_l_application(PREPROD, ailleurs)


def test_falsifiable_les_steps_de_navigation_odoo_n_ouvrent_pas_l_environnement_d_origine():
    import sys
    h = _helpers()
    sys.path.insert(0, str(config.BEHAVE_RUNTIME_DIR / "steps_library" / "odoo"))
    import _odoo_steps
    ouvertes = []
    contexte = SimpleNamespace(odoo_url=PREPROD, page=SimpleNamespace(url="https://preprod.exemple.test/odoo",
                                                                      goto=lambda u, **kw: ouvertes.append(u)))

    for appel in (lambda: _odoo_steps.step_navigate_url(contexte, APP + "/shop"), lambda: h.navigate(contexte, APP + "/shop")):
        with pytest.raises(h.NavigationImpossibleError):
            appel()
    _odoo_steps.step_navigate_url(contexte, "/shop")
    assert ouvertes == [PREPROD + "/shop"]


def test_falsifiable_une_adresse_d_une_autre_application_est_reperee_dans_la_structure():
    steps = 'from behave import when\n@when("x")\ndef s(context):\n    context.page.goto("https://recette.exemple.test/shop")\n'
    feature = 'Fonctionnalité: X\n  Scénario: Y\n    Quand j\'ouvre la page "https://recette.exemple.test/a"\n'
    assert env.adresses_d_une_autre_application(feature, steps, PREPROD) == [APP + "/shop", APP + "/a"]
    assert env.adresses_d_une_autre_application(feature, steps, "HTTPS://Recette.Exemple.Test:443/") == []
    assert env.adresses_d_une_autre_application('Quand j\'ouvre "/shop"', "x = '/shop'", PREPROD) == []
    # Un commentaire ou une docstring de prose n'est pas une constante passée au navigateur… mais une docstring EST une
    # constante : prudence assumée, elle bloque (jamais un vert), et aucun test généré n'en écrit avec une adresse.
    assert env.adresses_d_une_autre_application("", "# https://recette.exemple.test/x\n", PREPROD) == []


def test_falsifiable_sur_un_environnement_ajoute_un_test_qui_ecrit_l_adresse_d_origine_n_est_pas_joue(client, monkeypatch, relu):
    pid = _projet(client)
    cid = _cas(pid)
    conn = get_initialized_db(config.DB_PATH)
    try:
        vid = conn.execute("SELECT current_version_id FROM test_case WHERE id=?", (cid,)).fetchone()[0]
        conn.execute("UPDATE test_case_version SET steps_content=? WHERE id=?",
                     ('def s(context):\n    context.page.goto("https://recette.exemple.test/shop")\n', vid))
        conn.commit()
        eid = run_service.trigger_run(conn, cid, environnement={"base_url": PREPROD, "nature": "test", "nom": "Préprod"})[0]
    finally:
        conn.close()
    monkeypatch.setattr(run_service, "_execute_and_persist", lambda *a, **kw: pytest.fail("le test ne doit pas être joué"))
    monkeypatch.setattr(run_service, "_assurer_script_sur_disque", lambda *a, **kw: None)

    run_service.run_execution(eid, "commande", cid, vid, environnement={"base_url": PREPROD, "nature": "test", "nom": "Préprod"})

    conn = get_initialized_db(config.DB_PATH)
    try:
        ligne = conn.execute("SELECT execution_status, functional_status, error_message FROM execution WHERE id=?",
                             (eid,)).fetchone()
    finally:
        conn.close()
    assert ligne["execution_status"] == "blocked" and ligne["functional_status"] != "conforme"
    assert "https://recette.exemple.test/shop" in ligne["error_message"]


def test_falsifiable_une_campagne_en_cours_s_arrete_si_l_environnement_devient_production(client, monkeypatch, relu):
    pid = _projet(client)
    cid = _cas(pid)
    cid2 = _cas(pid)
    _ajouter(client, pid)
    eid = _id(client, pid, "Préproduction")
    run_id = client.post(f"/api/projects/{pid}/runs", json={"name": "N", "selection_mode": "frozen", "case_ids": [cid, cid2],
                                                            "environment_ids": [eid]}).json()["id"]
    conn = get_initialized_db(config.DB_PATH)
    try:
        params = campaign_service.start_campaign(conn, run_id)
    finally:
        conn.close()
    joues = []

    def _jouer(*a, **kw):
        joues.append(a[2])
        # pendant le premier cas, l'administrateur déclare l'environnement en production
        c = get_initialized_db(config.DB_PATH)
        c.execute("UPDATE project_environment SET nature='production' WHERE id=?", (eid,))
        c.commit()
        c.close()

    monkeypatch.setattr(run_service, "run_execution", _jouer)
    campaign_service.run_campaign(params["run_id"], params["case_ids"])

    assert len(joues) == 1, "le second cas n'est pas joué contre un environnement devenu production"
