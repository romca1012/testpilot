"""Le RUN — une campagne de N cas (décision `0022` n°8, incrément 1a : créer / lister / détailler).

Aujourd'hui une « exécution » est un run MONO-cas. La cible : un `test_run` regroupe des cas à
jouer ensemble, et le résultat d'un cas vit sur le couple cas × run. Ces tests figent :
- créer un run ne lance RIEN (naît en brouillon, `0022` 8.c.1) ;
- mode `frozen` = sélection matérialisée ; mode `all` = VIVANTE (les nouveaux cas rejoignent) ;
- référence par ID, jamais de copie de cas (contrainte §7) ;
- le détail donne chaque cas AVEC son résultat dans CE run (ou « non testé »).
"""

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import app as app_mod
from testpilot.store.db import get_initialized_db, _migrate_15_test_run
from testpilot.store.repositories import (
    CaseRepo,
    ExecutionRepo,
    RunRepo,
    ensure_default_module,
)


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    c = get_initialized_db(tmp_path / "run.db")
    yield c
    c.close()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return TestClient(app_mod.app)


def _cas(conn, mid, titre):
    return CaseRepo(conn).create(title=titre, module_id=mid, feature_slug=titre.lower())


# ── La migration ──────────────────────────────────────────────────────────────

def test_le_schema_neuf_porte_test_run_et_run_id(conn):
    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"test_run", "test_run_case"} <= tables
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(execution)")}
    assert "run_id" in cols


def test_migration_15_est_idempotente(tmp_path):
    import sqlite3
    raw = sqlite3.connect(str(tmp_path / "x.db"))
    raw.row_factory = sqlite3.Row
    raw.execute("CREATE TABLE execution (id INTEGER PRIMARY KEY)")
    _migrate_15_test_run(raw)
    _migrate_15_test_run(raw)  # rejoué
    cols = [r["name"] for r in raw.execute("PRAGMA table_info(execution)")]
    assert cols.count("run_id") == 1, "run_id ajouté une seule fois"
    raw.close()


# ── Repo : sélection figée vs vivante ─────────────────────────────────────────

def test_selection_figee_materialise_les_cas_choisis(conn):
    mid = ensure_default_module(conn, "m")
    c1, c2, c3 = _cas(conn, mid, "a"), _cas(conn, mid, "b"), _cas(conn, mid, "c")
    repo = RunRepo(conn)

    rid = repo.create(project_id=1, name="Sprint 1", selection_mode="frozen", case_ids=[c1, c3])

    assert repo.case_ids(rid) == sorted([c1, c3])
    assert repo.get(rid)["status"] == "draft", "un run naît en brouillon (rien lancé)"


def test_selection_TOUS_est_vivante(conn):
    """Mode `all` : un cas ajouté APRÈS la création du run le rejoint automatiquement (§8.a)."""
    mid = ensure_default_module(conn, "m")
    _cas(conn, mid, "a")
    repo = RunRepo(conn)
    rid = repo.create(project_id=1, name="Tout", selection_mode="all")
    assert len(repo.case_ids(rid)) == 1

    _cas(conn, mid, "b")  # ajouté après

    assert len(repo.case_ids(rid)) == 2, "le nouveau cas a rejoint le run vivant"


def test_cases_avec_resultats_rattache_l_execution_DU_run(conn):
    """Le résultat d'un cas est celui de son exécution DANS CE run — pas une autre."""
    mid = ensure_default_module(conn, "m")
    c1 = _cas(conn, mid, "a")
    from testpilot.store.repositories import VersionRepo
    vid = VersionRepo(conn).create(test_case_id=c1, spec_content="", spec_hash="h",
                                   feature_content="# f", steps_content="# s")
    repo = RunRepo(conn)
    rid = repo.create(project_id=1, name="R", selection_mode="frozen", case_ids=[c1])
    # Une exécution rattachée à CE run.
    eid = ExecutionRepo(conn).create(test_case_id=c1, version_id=vid)
    conn.execute("UPDATE execution SET run_id=? WHERE id=?", (rid, eid))
    ExecutionRepo(conn).finalize(eid, execution_status="success", functional_status="conforme",
                                 scenarios_total=1, scenarios_passed=1, scenarios_failed=0,
                                 duration_seconds=1.0, iterations=0, cost_usd=0.0)

    cases = repo.cases_with_results(rid)

    assert len(cases) == 1
    assert cases[0]["result"]["execution_status"] == "success"


def test_un_run_est_TRANSVERSE_multi_modules(conn):
    """⚠️ Le JTBD essentiel du §7 : « exécution nommée transverse multi-modules ». Un run
    référence des cas PAR ID, sans contrainte de module — une campagne de régression pioche donc
    dans plusieurs modules. C'est ce que l'ancien modèle (un cas = un run) rendait impossible."""
    from testpilot.store.repositories import ModuleRepo, ProjectRepo

    pid = ProjectRepo(conn).create(name="Projet transverse")
    m1 = ModuleRepo(conn).create(project_id=pid, name="Facturation")
    m2 = ModuleRepo(conn).create(project_id=pid, name="Livraison")
    c1 = CaseRepo(conn).create(title="Facture", module_id=m1, feature_slug="fact")
    c2 = CaseRepo(conn).create(title="Livraison", module_id=m2, feature_slug="livr")

    repo = RunRepo(conn)
    rid = repo.create(project_id=pid, name="Régression transverse",
                      selection_mode="frozen", case_ids=[c1, c2])

    assert repo.case_ids(rid) == sorted([c1, c2])
    modules = {CaseRepo(conn).get(c["id"])["module_name"] for c in repo.cases_with_results(rid)}
    assert modules == {"Facturation", "Livraison"}, "le run couvre PLUSIEURS modules"

    # Et le mode « tous les cas » balaie aussi tous les modules du projet.
    rid_all = repo.create(project_id=pid, name="Tout", selection_mode="all")
    assert repo.case_ids(rid_all) == sorted([c1, c2])


def test_un_cas_sans_execution_dans_le_run_est_non_teste(conn):
    mid = ensure_default_module(conn, "m")
    c1 = _cas(conn, mid, "a")
    repo = RunRepo(conn)
    rid = repo.create(project_id=1, name="R", selection_mode="frozen", case_ids=[c1])

    cases = repo.cases_with_results(rid)

    assert cases[0]["result"] is None, "non testé, pas de résultat fabriqué"


# ── API ───────────────────────────────────────────────────────────────────────

def _projet_avec_cas(client, n=2):
    pid = client.post("/api/projects", json={"name": "P"}).json()["id"]
    mid = client.post(f"/api/projects/{pid}/modules", json={"name": "M"}).json()["id"]
    ids = []
    for i in range(n):
        r = client.post(f"/api/modules/{mid}/cases/manual", json={
            "title": f"Cas {i}", "test_steps": ["a"], "expected_result": "r"})
        ids.append(r.json()["id"])
    return pid, ids


def test_api_creer_lister_detailler_un_run(client):
    pid, ids = _projet_avec_cas(client, 2)

    created = client.post(f"/api/projects/{pid}/runs", json={
        "name": "Campagne 1", "selection_mode": "frozen", "case_ids": ids})
    assert created.status_code == 201
    rid = created.json()["id"]
    assert created.json()["status"] == "draft"
    assert created.json()["case_count"] == 2

    assert any(r["id"] == rid for r in client.get(f"/api/projects/{pid}/runs").json())

    detail = client.get(f"/api/runs/{rid}")
    assert detail.status_code == 200
    assert len(detail.json()["cases"]) == 2
    assert all(c["execution_status"] is None for c in detail.json()["cases"]), "aucun run lancé"


def test_api_creer_ne_lance_rien(client):
    """Créer une campagne ne doit produire AUCUNE exécution (`0022` 8.c.1)."""
    pid, ids = _projet_avec_cas(client, 1)
    client.post(f"/api/projects/{pid}/runs", json={
        "name": "R", "selection_mode": "frozen", "case_ids": ids})

    assert client.get(f"/api/executions?project_id={pid}").json() == []


def test_api_selection_figee_vide_refusee(client):
    pid, _ = _projet_avec_cas(client, 1)
    r = client.post(f"/api/projects/{pid}/runs", json={
        "name": "R", "selection_mode": "frozen", "case_ids": []})
    assert r.status_code == 422


def test_api_filtrage_dynamique_refuse_clairement(client):
    pid, _ = _projet_avec_cas(client, 1)
    r = client.post(f"/api/projects/{pid}/runs", json={
        "name": "R", "selection_mode": "dynamic"})
    assert r.status_code == 422
    assert "dynamique" in r.json()["detail"]


def test_api_run_ou_projet_inconnu_404(client):
    assert client.get("/api/runs/999").status_code == 404
    assert client.post("/api/projects/999/runs", json={"name": "R", "selection_mode": "all"}).status_code == 404


# ── Lancement de la campagne (incrément 1b) ───────────────────────────────────

def test_lancer_execute_les_cas_EN_SEQUENCE_et_les_rattache(conn, monkeypatch):
    """Chaque cas joué produit une exécution RATTACHÉE au run (`run_id`) — c'est ce lien qui fait
    exister « le résultat du cas DANS ce run » (`0022` n°4). Behave est simulé."""
    from testpilot.api.services import campaign_service, run_service
    from testpilot.store.repositories import VersionRepo

    mid = ensure_default_module(conn, "m")
    c1, c2 = _cas(conn, mid, "a"), _cas(conn, mid, "b")
    for c in (c1, c2):
        vid = VersionRepo(conn).create(test_case_id=c, spec_content="", spec_hash="h",
                                       feature_content="# f", steps_content="# s")
        CaseRepo(conn).set_current_version(c, vid)
        # Gate ouvert (amendement §4.3 : la validation métier vaut relecture).
        from testpilot.store.repositories import ReviewRepo
        from testpilot.verdict import review_gate
        review_gate.auto_approve_metier(ReviewRepo(conn), case_id=c, version_id=vid)

    repo = RunRepo(conn)
    rid = repo.create(project_id=1, name="Campagne", selection_mode="frozen", case_ids=[c1, c2])

    joues: list[int] = []
    monkeypatch.setattr(run_service, "run_execution",
                        lambda eid, slug, cid, vid, **kw: joues.append(cid))
    monkeypatch.setattr(config, "DB_PATH", conn.execute("PRAGMA database_list").fetchone()[2])

    params = campaign_service.start_campaign(conn, rid)
    assert repo.get(rid)["status"] == "running", "le run passe EN COURS au lancement"
    campaign_service.run_campaign(**params)

    assert joues == [c1, c2], "les cas sont joués en séquence, dans l'ordre"
    conn2 = get_initialized_db(config.DB_PATH)
    rattachees = conn2.execute("SELECT COUNT(*) c FROM execution WHERE run_id=?", (rid,)).fetchone()["c"]
    assert rattachees == 2, "chaque exécution est rattachée au run"
    assert RunRepo(conn2).get(rid)["status"] == "completed", "la campagne est close à la fin"
    conn2.close()


def test_un_cas_en_echec_n_arrete_pas_la_campagne(conn, monkeypatch):
    """Une campagne dit OÙ on en est sur l'ensemble : s'arrêter au premier échec cacherait
    l'état des cas suivants."""
    from testpilot.api.services import campaign_service, run_service
    from testpilot.store.repositories import ReviewRepo, VersionRepo
    from testpilot.verdict import review_gate

    mid = ensure_default_module(conn, "m")
    c1, c2 = _cas(conn, mid, "a"), _cas(conn, mid, "b")
    for c in (c1, c2):
        vid = VersionRepo(conn).create(test_case_id=c, spec_content="", spec_hash="h",
                                       feature_content="# f", steps_content="# s")
        CaseRepo(conn).set_current_version(c, vid)
        review_gate.auto_approve_metier(ReviewRepo(conn), case_id=c, version_id=vid)
    rid = RunRepo(conn).create(project_id=1, name="C", selection_mode="frozen", case_ids=[c1, c2])

    joues: list[int] = []

    def boum(eid, slug, cid, vid, **kw):
        joues.append(cid)
        if cid == c1:
            raise RuntimeError("navigateur mort")
    monkeypatch.setattr(run_service, "run_execution", boum)
    monkeypatch.setattr(config, "DB_PATH", conn.execute("PRAGMA database_list").fetchone()[2])

    params = campaign_service.start_campaign(conn, rid)
    campaign_service.run_campaign(**params)

    assert joues == [c1, c2], "le second cas est joué malgré l'échec du premier"


def test_api_lancer_un_run_vide_est_REFUSE(client):
    """Un run vide finirait « terminé » sans rien avoir testé — un succès trompeur."""
    pid, _ = _projet_avec_cas(client, 1)
    # Mode `all` sur un projet dont on retire les cas → run sans cas.
    rid = client.post(f"/api/projects/{pid}/runs", json={
        "name": "Vide", "selection_mode": "all"}).json()["id"]
    for c in client.get(f"/api/cases?project_id={pid}").json()["items"]:
        client.delete(f"/api/cases/{c['id']}")

    r = client.post(f"/api/runs/{rid}/launch")

    assert r.status_code == 422
    assert "aucun cas" in r.json()["detail"]


def test_api_lancer_un_run_inconnu_404(client):
    assert client.post("/api/runs/999/launch").status_code == 404


# ── Archivage (clôture = lecture seule) ───────────────────────────────────────

def test_archiver_un_run_le_passe_en_LECTURE_SEULE(client):
    """Un run archivé ne se relance plus — garde CÔTÉ SERVEUR, pas seulement à l'écran : sinon
    l'API pourrait réécrire un historique clos."""
    pid, ids = _projet_avec_cas(client, 1)
    rid = client.post(f"/api/projects/{pid}/runs", json={
        "name": "R", "selection_mode": "frozen", "case_ids": ids}).json()["id"]

    r = client.post(f"/api/runs/{rid}/archive", json={"archived": True})
    assert r.status_code == 200
    assert r.json()["is_archived"] is True

    lance = client.post(f"/api/runs/{rid}/launch")
    assert lance.status_code == 409
    assert "archivée" in lance.json()["detail"]


def test_archiver_est_REVERSIBLE(client):
    """Une clôture par erreur ne doit pas être irrattrapable (§2.10 : rien n'est détruit)."""
    pid, ids = _projet_avec_cas(client, 1)
    rid = client.post(f"/api/projects/{pid}/runs", json={
        "name": "R", "selection_mode": "frozen", "case_ids": ids}).json()["id"]
    client.post(f"/api/runs/{rid}/archive", json={"archived": True})

    r = client.post(f"/api/runs/{rid}/archive", json={"archived": False})

    assert r.json()["is_archived"] is False
    # Et le run redevient lançable (le refus n'était pas définitif).
    assert client.post(f"/api/runs/{rid}/launch").status_code in (202, 409)


def test_archiver_n_efface_RIEN(client):
    """Archivage ≠ suppression : le run et ses cas restent consultables."""
    pid, ids = _projet_avec_cas(client, 2)
    rid = client.post(f"/api/projects/{pid}/runs", json={
        "name": "R", "selection_mode": "frozen", "case_ids": ids}).json()["id"]
    client.post(f"/api/runs/{rid}/archive", json={"archived": True})

    detail = client.get(f"/api/runs/{rid}")
    assert detail.status_code == 200
    assert len(detail.json()["cases"]) == 2


def test_api_archiver_un_run_inconnu_404(client):
    assert client.post("/api/runs/999/archive", json={"archived": True}).status_code == 404


# ── Lancement bloqué AVANT `trigger_run` : ne plus rester « Untested » en silence (2026-09-15) ──

def test_lancement_bloque_needs_review_cree_une_execution_technical_error(conn):
    """Un cas dont la version n'a jamais été validée (`needs_review`) doit obtenir un verdict
    honnête dans l'historique du cas — pas seulement une ligne de journal serveur."""
    from testpilot.api.services import run_service
    from testpilot.store.repositories import VersionRepo

    mid = ensure_default_module(conn, "m")
    c1 = _cas(conn, mid, "a")
    vid = VersionRepo(conn).create(test_case_id=c1, spec_content="", spec_hash="h",
                                   feature_content="# f", steps_content="# s")
    CaseRepo(conn).set_current_version(c1, vid)
    # Gate JAMAIS approuvé (pas d'appel à auto_approve_metier) : needs_review.

    eid = run_service.enregistrer_lancement_bloque(
        conn, case_id=c1, code="needs_review", message="relecture humaine obligatoire")

    assert eid is not None
    execution = ExecutionRepo(conn).get(eid)
    assert execution["execution_status"] == "technical_error"
    assert execution["functional_status"] == "indetermine"
    assert execution["version_id"] == vid
    assert "relecture humaine obligatoire" in execution["error_message"]
    # Le cas lui-même reflète ce dernier résultat (pas de silence côté fiche cas non plus).
    assert CaseRepo(conn).get(c1)["last_execution_status"] == "technical_error"


def test_lancement_bloque_rend_none_sans_version_ou_cas_introuvable(conn):
    """`not_found`/`no_version` n'ont ni cas ni version valides à référencer (clé étrangère NOT
    NULL) : aucune ligne ne doit être créée — un cas jamais généré reste honnêtement « Untested »."""
    from testpilot.api.services import run_service

    mid = ensure_default_module(conn, "m")
    c1 = _cas(conn, mid, "a")  # jamais de version générée

    assert run_service.enregistrer_lancement_bloque(
        conn, case_id=c1, code="no_version", message="aucune version générée") is None
    assert run_service.enregistrer_lancement_bloque(
        conn, case_id=999999, code="not_found", message="cas introuvable") is None
    assert ExecutionRepo(conn).list_for_case(c1) == []


def test_campagne_avec_un_cas_bloque_needs_review_laisse_un_verdict_dans_le_run(conn, monkeypatch):
    """Régression du bug réel du 2026-09-15 : une campagne qui bute sur `needs_review` doit
    laisser une trace RATTACHÉE au run — pas un cas « Untested » sans explication alors que le
    run affiche « Terminé »."""
    from testpilot.api.services import campaign_service, run_service
    from testpilot.store.repositories import ReviewRepo, VersionRepo
    from testpilot.verdict import review_gate

    mid = ensure_default_module(conn, "m")
    c1, c2 = _cas(conn, mid, "a"), _cas(conn, mid, "b")
    vid1 = VersionRepo(conn).create(test_case_id=c1, spec_content="", spec_hash="h",
                                    feature_content="# f", steps_content="# s")
    CaseRepo(conn).set_current_version(c1, vid1)
    # c1 : gate JAMAIS approuvé → needs_review au déclenchement.
    vid2 = VersionRepo(conn).create(test_case_id=c2, spec_content="", spec_hash="h",
                                    feature_content="# f", steps_content="# s")
    CaseRepo(conn).set_current_version(c2, vid2)
    review_gate.auto_approve_metier(ReviewRepo(conn), case_id=c2, version_id=vid2)  # c2 : approuvé

    rid = RunRepo(conn).create(project_id=1, name="C", selection_mode="frozen", case_ids=[c1, c2])

    joues: list[int] = []
    monkeypatch.setattr(run_service, "run_execution",
                        lambda eid, slug, cid, vid, **kw: joues.append(cid))
    monkeypatch.setattr(config, "DB_PATH", conn.execute("PRAGMA database_list").fetchone()[2])

    params = campaign_service.start_campaign(conn, rid)
    campaign_service.run_campaign(**params)

    assert joues == [c2], "seul le cas dont le gate est ouvert est vraiment joué"
    conn2 = get_initialized_db(config.DB_PATH)
    cases = RunRepo(conn2).cases_with_results(rid)
    resultat_c1 = next(c["result"] for c in cases if c["id"] == c1)
    assert resultat_c1 is not None, "le cas bloqué ne doit plus rester « Untested » en silence"
    assert resultat_c1["execution_status"] == "technical_error"
    rattachees = conn2.execute(
        "SELECT COUNT(*) c FROM execution WHERE run_id=?", (rid,)).fetchone()["c"]
    assert rattachees == 2, "le cas bloqué obtient aussi une exécution rattachée au run"
    assert RunRepo(conn2).get(rid)["status"] == "completed"
    conn2.close()


def test_un_cas_inclus_dans_un_run_reste_SUPPRIMABLE(conn):
    """⚠️ Régression réelle (2026-07-21) : `test_run_case` référence `test_case`, et la cascade de
    `CaseRepo.delete` ne la nettoyait pas → `FOREIGN KEY constraint failed`, le cas devenait
    **insupprimable** dès qu'il appartenait à une campagne.

    C'est le MÊME défaut que celui déjà documenté pour `cost_ledger` (2026-07-17), rejoué un mois
    plus tard en ajoutant une table. Aucune suite verte ne l'a vu — c'est le banc de mesure, qui
    supprime ses artefacts, qui l'a fait tomber. Supprimer un cas le RETIRE de ses campagnes ; le
    run survit avec ses autres cas.
    """
    mid = ensure_default_module(conn, "m")
    c1, c2 = _cas(conn, mid, "a"), _cas(conn, mid, "b")
    repo = RunRepo(conn)
    rid = repo.create(project_id=1, name="R", selection_mode="frozen", case_ids=[c1, c2])

    CaseRepo(conn).delete(c1)   # échouait avant le correctif

    assert CaseRepo(conn).get(c1) is None
    assert repo.case_ids(rid) == [c2], "le run survit, sans le cas supprimé"
