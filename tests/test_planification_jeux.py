"""Lot PT-02b (A28, A35) — une planification joue les jeux de données choisis, comme un lancement à la main.

Ce que ces tests gardent :
1. une planification sans jeu se déclenche comme avant (une exécution, aucun jeu posé) ;
2. plusieurs jeux : à chaque déclenchement, une exécution PAR jeu regroupées dans un plan, toutes lancées ; la première
   joue tous les tests, les autres seulement ceux qui écrivent des variables (A35) ; un jeu sans test à variables ne
   laisse pas d'exécution vide derrière lui ;
3. un seul jeu mis à la corbeille depuis : RIEN n'est lancé (décision du porteur, A36) — jamais le jeu « Par défaut » ni
   les autres jeux à la place ; une première exécution qui ne part pas ne laisse aucun brouillon ;
4. à la création : mêmes jeux admis qu'à la main (du projet, vivants, 50 au plus).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import app as app_mod
from testpilot.api.services import scheduler_service
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import (
    CaseRepo, ModuleRepo, PlanRepo, ProjectRepo, RunRepo, ScheduledRunRepo, TestDataRepo, VersionRepo,
)

MAINTENANT = datetime(2026, 10, 14, 2, 5, tzinfo=timezone.utc)
AVEC_VARIABLE = "Fonctionnalité: X\n  Scénario: Y\n    Alors le client {{client}} est servi\n"
SANS_VARIABLE = "Fonctionnalité: X\n  Scénario: Y\n    Alors ok\n"


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "p.db")
    c = get_initialized_db(config.DB_PATH)
    yield c
    c.close()


@pytest.fixture(autouse=True)
def _pas_de_vrai_thread_de_fond(monkeypatch):
    """Comme `test_plans_et_planifications.py` : on vérifie le DÉCLENCHEMENT, jamais une vraie exécution."""
    from testpilot.guardrails import durable_jobs
    monkeypatch.setattr(durable_jobs, "submit_immediat", lambda conn, **kwargs: "job-factice")


def _cas(conn, mid: int, titre: str, feature: str) -> int:
    cid = CaseRepo(conn).create(title=titre, module_id=mid, feature_slug=titre.lower())
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="", feature_content=feature,
                                   steps_content="# steps\n")
    CaseRepo(conn).set_current_version(cid, vid)
    conn.commit()
    return cid


def _projet(conn, *jeux: str, avec_variables: bool = True):
    pid = ProjectRepo(conn).create(name="Boutique", base_url="http://x", database="db", username="u", password="p")
    mid = ModuleRepo(conn).create(project_id=pid, name="Ventes")
    avec = _cas(conn, mid, "Commande", AVEC_VARIABLE if avec_variables else SANS_VARIABLE)
    sans = _cas(conn, mid, "Accueil", SANS_VARIABLE)
    depot = TestDataRepo(conn)
    variable = depot.creer_variable(pid, nom="client")
    depot.poser_valeurs(pid, depot.jeux(pid)[0]["id"], {variable: "Martin"})
    for nom in jeux:
        depot.creer_jeu(pid, nom=nom)
    return pid, avec, sans, {j["nom"]: j["id"] for j in depot.jeux(pid)}


def _planifier(conn, pid: int, dataset_ids: list[int]) -> int:
    return ScheduledRunRepo(conn).create(project_id=pid, name="Nocturne", selection_mode="all", frequency="daily",
                                         hour=2, minute=0, dataset_ids=dataset_ids)


def test_sans_jeu_la_planification_se_declenche_comme_avant(conn):
    pid, *_ = _projet(conn)
    _planifier(conn, pid, [])

    [run_id] = scheduler_service.tick(conn, now=MAINTENANT)

    run = RunRepo(conn).get(run_id)
    assert (run["dataset_id"], run["plan_id"], run["status"]) == (None, None, "running")


def test_un_jeu_une_execution_qui_le_porte(conn):
    pid, avec, sans, jeux = _projet(conn, "Grosse commande")
    _planifier(conn, pid, [jeux["Grosse commande"]])

    [run_id] = scheduler_service.tick(conn, now=MAINTENANT)

    run = RunRepo(conn).get(run_id)
    assert (run["dataset_id"], run["plan_id"], run["seulement_variables"]) == (jeux["Grosse commande"], None, 0)


def test_falsifiable_plusieurs_jeux_une_execution_par_jeu_toutes_lancees(conn):
    pid, avec, sans, jeux = _projet(conn, "Grosse commande")
    _planifier(conn, pid, [jeux["Grosse commande"], jeux["Par défaut"]])

    [premier] = scheduler_service.tick(conn, now=MAINTENANT)

    plan_id = RunRepo(conn).get(premier)["plan_id"]
    runs = {r["name"]: r for r in PlanRepo(conn).runs_of_plan(plan_id)}
    assert set(runs) == {"Nocturne — 2026-10-14 — Par défaut", "Nocturne — 2026-10-14 — Grosse commande"}
    assert runs["Nocturne — 2026-10-14 — Par défaut"]["id"] == premier, "« Par défaut » en tête, même demandé en second"
    assert {r["status"] for r in runs.values()} == {"running"}
    assert RunRepo(conn).case_ids(premier) == sorted([avec, sans])
    assert RunRepo(conn).case_ids(runs["Nocturne — 2026-10-14 — Grosse commande"]["id"]) == [avec], "A35"


def test_falsifiable_un_jeu_sans_test_a_variables_ne_laisse_pas_d_execution_vide(conn):
    pid, avec, sans, jeux = _projet(conn, "Grosse commande", avec_variables=False)
    _planifier(conn, pid, [jeux["Par défaut"], jeux["Grosse commande"]])

    [premier] = scheduler_service.tick(conn, now=MAINTENANT)

    runs = PlanRepo(conn).runs_of_plan(RunRepo(conn).get(premier)["plan_id"])
    assert [r["id"] for r in runs] == [premier]
    assert RunRepo(conn).get(premier)["status"] == "running"


def test_falsifiable_un_seul_jeu_a_la_corbeille_rien_n_est_lance(conn):
    """Décision du porteur (2026-10-14, A36) : ni les autres jeux, ni « Par défaut » — la planification attend d'être
    corrigée."""
    pid, avec, sans, jeux = _projet(conn, "Grosse commande", "Export")
    _planifier(conn, pid, [jeux["Par défaut"], jeux["Grosse commande"], jeux["Export"]])
    TestDataRepo(conn).supprimer_jeu(pid, jeux["Export"], par="admin")

    assert scheduler_service.tick(conn, now=MAINTENANT) == []
    assert RunRepo(conn).list_for_project(pid) == []


def test_le_jeu_restaure_la_planification_repart(conn):
    pid, avec, sans, jeux = _projet(conn, "Export")
    _planifier(conn, pid, [jeux["Par défaut"], jeux["Export"]])
    depot = TestDataRepo(conn)
    depot.supprimer_jeu(pid, jeux["Export"], par="admin")
    assert scheduler_service.tick(conn, now=MAINTENANT) == []

    conn.execute("UPDATE test_dataset SET deleted_at='', deleted_by='' WHERE id=?", (jeux["Export"],))   # restauré
    conn.commit()

    assert len(scheduler_service.tick(conn, now=MAINTENANT.replace(minute=30))) == 1


def test_falsifiable_tous_les_jeux_a_la_corbeille_rien_n_est_lance(conn):
    """Jamais le jeu « Par défaut » joué à la place des jeux choisis."""
    pid, avec, sans, jeux = _projet(conn, "Grosse commande", "Export")
    _planifier(conn, pid, [jeux["Grosse commande"], jeux["Export"]])
    for nom in ("Grosse commande", "Export"):
        TestDataRepo(conn).supprimer_jeu(pid, jeux[nom], par="admin")

    assert scheduler_service.tick(conn, now=MAINTENANT) == []
    assert RunRepo(conn).list_for_project(pid) == []


def test_falsifiable_une_premiere_execution_qui_ne_part_pas_ne_laisse_aucun_brouillon(conn, monkeypatch):
    pid, avec, sans, jeux = _projet(conn, "Grosse commande")
    _planifier(conn, pid, [jeux["Par défaut"], jeux["Grosse commande"]])

    def refus(*a, **k):
        raise scheduler_service.campaign_service.CampaignError("no_connection", "connexion incomplète")
    monkeypatch.setattr(scheduler_service.campaign_service, "start_campaign", refus)

    assert scheduler_service.tick(conn, now=MAINTENANT) == []
    assert RunRepo(conn).list_for_project(pid) == []
    assert conn.execute("SELECT COUNT(*) FROM test_plan WHERE project_id=?", (pid,)).fetchone()[0] == 0


def test_des_jeux_illisibles_ne_lancent_rien(conn):
    pid, *_ = _projet(conn)
    sid = _planifier(conn, pid, [])
    conn.execute("UPDATE scheduled_run SET dataset_ids='{pas une liste' WHERE id=?", (sid,))
    conn.commit()

    assert scheduler_service.tick(conn, now=MAINTENANT) == []
    assert RunRepo(conn).list_for_project(pid) == []


@pytest.mark.parametrize("historique", ["lancee", "resultat", "execution", "assignation"])
def test_falsifiable_une_execution_qui_a_un_historique_n_est_jamais_supprimee(conn, historique):
    from testpilot.store.repositories import AssignmentRepo, ExecutionRepo

    pid, avec, *_ = _projet(conn)
    run_id = RunRepo(conn).create(project_id=pid, name="R", case_ids=[avec])
    if historique == "lancee":
        conn.execute("UPDATE test_run SET status='running', launched_at='2026-10-14' WHERE id=?", (run_id,))
    elif historique in ("resultat", "execution"):
        version = conn.execute("SELECT current_version_id FROM test_case WHERE id=?", (avec,)).fetchone()[0]
        eid = ExecutionRepo(conn).create(test_case_id=avec, version_id=version)
        conn.execute("UPDATE execution SET run_id=? WHERE id=?", (run_id, eid))
        if historique == "resultat":
            conn.execute("UPDATE execution SET run_id=NULL WHERE id=?", (eid,))
            conn.execute("INSERT INTO test_result (run_id, case_id, mode, execution_id, created_at)"
                         " VALUES (?, ?, 'automatique', ?, '2026-10-14')", (run_id, avec, eid))
    else:
        AssignmentRepo(conn).set(run_id, avec, assigned_to="testeur", assigned_by="admin")
    conn.commit()

    assert RunRepo(conn).supprimer_brouillon(run_id) is False
    assert RunRepo(conn).get(run_id) is not None


def test_un_brouillon_intact_est_supprime(conn):
    pid, avec, *_ = _projet(conn)
    run_id = RunRepo(conn).create(project_id=pid, name="R", case_ids=[avec])

    assert RunRepo(conn).supprimer_brouillon(run_id) is True
    assert RunRepo(conn).get(run_id) is None


def test_falsifiable_une_suivante_qui_ne_part_pas_reste_dans_le_plan_les_autres_continuent(conn, monkeypatch):
    """Un échec autre que « rien à jouer » : le brouillon reste visible dans le plan, c'est le signal qu'un jeu n'a pas été
    joué ; les autres jeux partent quand même."""
    pid, avec, sans, jeux = _projet(conn, "Grosse commande", "Export")
    _planifier(conn, pid, [jeux["Par défaut"], jeux["Grosse commande"], jeux["Export"]])
    vrai = scheduler_service.campaign_service.start_campaign

    def refuse_grosse_commande(conn_, run_id, **kw):
        if RunRepo(conn_).get(run_id)["name"].endswith("Grosse commande"):
            raise scheduler_service.campaign_service.CampaignError("dataset_missing", "jeu à la corbeille")
        return vrai(conn_, run_id, **kw)
    monkeypatch.setattr(scheduler_service.campaign_service, "start_campaign", refuse_grosse_commande)

    [premier] = scheduler_service.tick(conn, now=MAINTENANT)

    statuts = {r["name"].split(" — ")[-1]: r["status"]
               for r in PlanRepo(conn).runs_of_plan(RunRepo(conn).get(premier)["plan_id"])}
    assert statuts == {"Par défaut": "running", "Grosse commande": "draft", "Export": "running"}


def test_falsifiable_une_erreur_sur_une_suivante_ne_relance_pas_la_planification(conn, monkeypatch):
    """Revue du 2026-10-14 : sans `mark_triggered` après la première, chaque passage de l'horloge relançait une nouvelle
    première exécution, contre la vraie application, toute la journée."""
    from testpilot.guardrails import durable_jobs

    pid, avec, sans, jeux = _projet(conn, "Grosse commande")
    _planifier(conn, pid, [jeux["Par défaut"], jeux["Grosse commande"]])
    appels = []

    def soumettre(conn_, **kw):
        appels.append(kw)
        if len(appels) == 2:
            raise RuntimeError("database is locked")
        return "job-factice"
    monkeypatch.setattr(durable_jobs, "submit_immediat", soumettre)

    premier = scheduler_service.tick(conn, now=MAINTENANT)
    encore = scheduler_service.tick(conn, now=MAINTENANT.replace(minute=30))

    assert len(premier) == 1 and encore == [], "déclenchée une seule fois ce jour-là"
    assert len(appels) == 2


# ── Création par l'API ───────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return TestClient(app_mod.app)


def _corps(**plus):
    return {"name": "Nocturne", "selection_mode": "all", "frequency": "daily", "hour": 2, "minute": 0, **plus}


def test_les_jeux_choisis_sont_gardes_et_rendus(client):
    pid = client.post("/api/projects", json={"name": "B", "connector_type": "web", "base_url": "https://a.test",
                                              "username": "u", "password": "p"}).json()["id"]
    base = f"/api/projects/{pid}/donnees-de-test"
    client.post(f"{base}/variables", json={"nom": "client"})
    client.post(f"{base}/jeux", json={"nom": "Export"})
    jeux = [j["id"] for j in client.get(base).json()["jeux"]]

    r = client.post(f"/api/projects/{pid}/schedules", json=_corps(dataset_ids=jeux + [jeux[0]]))

    assert r.status_code == 201, r.text
    assert r.json()["dataset_ids"] == jeux, "sans doublon, dans l'ordre"
    assert client.get(f"/api/projects/{pid}/schedules").json()[0]["dataset_ids"] == jeux


@pytest.mark.parametrize("cas", ["autre_projet", "corbeille"])
def test_falsifiable_un_jeu_invalide_est_refuse_a_la_creation(client, cas):
    pid = client.post("/api/projects", json={"name": "B", "connector_type": "web", "base_url": "https://a.test",
                                              "username": "u", "password": "p"}).json()["id"]
    base = f"/api/projects/{pid}/donnees-de-test"
    client.post(f"{base}/variables", json={"nom": "client"})
    client.post(f"{base}/jeux", json={"nom": "Export"})
    export = next(j["id"] for j in client.get(base).json()["jeux"] if j["nom"] == "Export")
    if cas == "corbeille":
        client.delete(f"{base}/jeux/{export}")
    else:
        pid = client.post("/api/projects", json={"name": "Autre", "connector_type": "web", "base_url": "https://b.test",
                                                  "username": "u", "password": "p"}).json()["id"]

    r = client.post(f"/api/projects/{pid}/schedules", json=_corps(dataset_ids=[export]))

    assert r.status_code == 422, r.text
    assert client.get(f"/api/projects/{pid}/schedules").json() == []
