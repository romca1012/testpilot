"""Lot 05 (D5) — de la confiance calculée à ce que l'écran lit : persistance, API, campagne stricte.

Le calcul pur est dans `test_confiance_verdict.py`, le runtime dans `test_confiance_runtime.py`. Ici : `run_service`
écrit `execution.confiance`, l'API expose « à confirmer » calculé par le serveur, et la campagne stricte ne rejoue pas.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import app as app_mod
from testpilot.api.services import campaign_service, run_service
from testpilot.execution.behave_result import (
    MODE_STRICT_ENV, BehaveFailure, BehaveResult, BehaveScenario,
)
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import (
    CaseRepo, ExecutionRepo, ModuleRepo, ProjectRepo, ResultRepo, RunRepo, VersionRepo,
)
from testpilot.verdict.status import MODE_MANUELLE


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "conf.db")
    c = get_initialized_db(tmp_path / "conf.db")
    yield c
    c.close()


@pytest.fixture
def client(conn):
    return TestClient(app_mod.app)


def _decor(conn, nombre_cas=3):
    pid = ProjectRepo(conn).create(name="Portail")
    mid = ModuleRepo(conn).create(project_id=pid, name="Demandes")
    cas = []
    for i in range(nombre_cas):
        cid = CaseRepo(conn).create(title=f"Cas {i}", module_id=mid, feature_slug=f"cas{i}")
        vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="",
                                       feature_content="# f", steps_content="# s")
        cas.append((cid, vid))
    run = RunRepo(conn).create(project_id=pid, name="Campagne", case_ids=[c for c, _ in cas])
    return pid, cas, run


def _resultat(conn, run, cas, *, execution="success", fonctionnel="conforme", confiance="nominale"):
    cid, vid = cas
    eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid)
    conn.execute("UPDATE execution SET run_id=? WHERE id=?", (run, eid))
    conn.commit()
    ExecutionRepo(conn).finalize(
        eid, execution_status=execution, functional_status=fonctionnel, scenarios_total=1,
        scenarios_passed=1, scenarios_failed=0, cost_usd=0.0, iterations=1, duration_seconds=0.1,
        confiance=confiance)
    return eid


def test_finalize_ecrit_la_confiance_et_le_defaut_est_nominal(conn):
    _, cas, run = _decor(conn, 2)
    e1 = _resultat(conn, run, cas[0], confiance="auto_resolue")
    e2 = _resultat(conn, run, cas[1])

    lue = {r["id"]: r["confiance"] for r in conn.execute("SELECT id, confiance FROM execution")}
    assert lue[e1] == "auto_resolue" and lue[e2] == "nominale"


def test_falsifiable_seuls_les_verts_non_nominaux_comptent_comme_a_confirmer(conn):
    """Un échec obtenu par repli, un vert nominal et un résultat manuel ne sont JAMAIS « à confirmer »."""
    pid, cas, run = _decor(conn, 4)
    _resultat(conn, run, cas[0], confiance="auto_resolue")                               # vert à confirmer
    _resultat(conn, run, cas[1])                                                          # vert nominal
    _resultat(conn, run, cas[2], fonctionnel="non_conforme", confiance="apres_retry")     # échec : pas un vert
    manuel = RunRepo(conn).create(project_id=pid, name="Manuelle", case_ids=[cas[3][0]], mode=MODE_MANUELLE)
    ResultRepo(conn).saisir(run_id=manuel, case_id=cas[3][0], statut="passed")

    assert RunRepo(conn).verts_a_confirmer(run) == 1
    assert RunRepo(conn).verts_a_confirmer(manuel) == 0


def test_seul_le_dernier_resultat_du_cas_compte(conn):
    """Le cas relancé et vert nominal n'est plus « à confirmer » : c'est le dernier résultat qui fait foi."""
    _, cas, run = _decor(conn, 1)
    _resultat(conn, run, cas[0], confiance="apres_retry")
    assert RunRepo(conn).verts_a_confirmer(run) == 1

    _resultat(conn, run, cas[0])

    assert RunRepo(conn).verts_a_confirmer(run) == 0


def test_l_api_expose_a_confirmer_sans_changer_le_statut(conn, client):
    """`Réussi — à confirmer` qualifie un `passed` : le statut de lecture reste `passed`, le serveur calcule la réserve."""
    _, cas, run = _decor(conn, 2)
    _resultat(conn, run, cas[0], confiance="auto_resolue")
    _resultat(conn, run, cas[1])

    corps = client.get(f"/api/runs/{run}").json()

    par_titre = {c["title"]: c for c in corps["cases"]}
    a_confirmer = par_titre["Cas 0"]
    assert (a_confirmer["statut"], a_confirmer["confiance"], a_confirmer["a_confirmer"]) == (
        "passed", "auto_resolue", True)
    nominal = par_titre["Cas 1"]
    assert (nominal["statut"], nominal["confiance"], nominal["a_confirmer"]) == ("passed", "nominale", False)
    assert corps["run"]["verts_a_confirmer"] == 1
    assert (a_confirmer["execution_status"], a_confirmer["functional_status"]) == ("success", "conforme")


def test_l_api_cree_une_campagne_stricte(conn, client):
    pid, cas, _ = _decor(conn, 1)

    cree = client.post(f"/api/projects/{pid}/runs", json={
        "name": "Stricte", "selection_mode": "frozen", "case_ids": [cas[0][0]], "strict": True}).json()
    ordinaire = client.post(f"/api/projects/{pid}/runs", json={
        "name": "Ordinaire", "selection_mode": "frozen", "case_ids": [cas[0][0]]}).json()

    assert cree["strict"] is True and ordinaire["strict"] is False


def test_falsifiable_le_lancement_transmet_le_drapeau_strict_a_chaque_cas(conn, monkeypatch):
    """Sans transmission, une campagne « stricte » rejouerait ses cas en mode normal — la promesse serait creuse."""
    _, cas, _ = _decor(conn, 1)
    vus = []
    monkeypatch.setattr(run_service, "trigger_run", lambda conn_, cid, **k: (1, "slug", cid, 1))
    monkeypatch.setattr(run_service, "run_execution", lambda *a, **k: vus.append(k))

    campaign_service.run_campaign(1, [cas[0][0]], strict=True)
    campaign_service.run_campaign(1, [cas[0][0]])

    assert vus[0].get("strict") is True
    assert "strict" not in vus[1], "une campagne ordinaire garde l'appel d'avant"


def test_start_campaign_rend_le_drapeau_de_la_campagne(conn):
    pid, cas, _ = _decor(conn, 1)
    stricte = RunRepo(conn).create(project_id=pid, name="S", case_ids=[cas[0][0]], strict=True)
    ordinaire = RunRepo(conn).create(project_id=pid, name="O", case_ids=[cas[0][0]])
    monkey = pytest.MonkeyPatch()
    try:
        # La connexion du projet n'est pas l'objet du test : `verifier_connexion` est neutralisée.
        monkey.setattr("testpilot.connectors.runtime_env.verifier_connexion", lambda projet: None)
        assert campaign_service.start_campaign(conn, stricte)["strict"] is True
        assert campaign_service.start_campaign(conn, ordinaire)["strict"] is False
    finally:
        monkey.undo()


# ── run_service : la campagne stricte ne rejoue pas, et la confiance atteint la base ──────────────────────────────


class _RunnerFactice:
    """Un runner de test : le premier run échoue sur un timeout d'interface, le suivant réussit."""

    def __init__(self, *, premier_echec_timeout: bool, paliers=()):
        self.connection = {}
        self.appels = 0
        self._premier_echec = premier_echec_timeout
        self._paliers = list(paliers)

    def dry_run(self, module):
        return BehaveResult(success=True, returncode=0, dry_run=True)

    def real_run(self, module):
        self.appels += 1
        if self._premier_echec and self.appels == 1:
            return BehaveResult(
                success=False, returncode=1, failed=1,
                failures=[BehaveFailure("S", "Quand je clique", "ui_timeout", "timeout")],
                scenarios=[BehaveScenario("S", "failed", constats_reussis=0)])
        return BehaveResult(success=True, returncode=0, passed=1,
                            scenarios=[BehaveScenario("S", "passed", constats_reussis=1)],
                            selector_tiers=self._paliers)


def _executer(conn, monkeypatch, runner, **options):
    _, cas, _ = _decor(conn, 1)
    cid, vid = cas[0]
    eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid)
    monkeypatch.setattr(run_service, "_expliquer", lambda *a, **k: "")
    run_service._execute_and_persist(conn, eid, cid, "cas0", runner, **options)
    return conn.execute("SELECT execution_status, functional_status, confiance FROM execution WHERE id=?",
                        (eid,)).fetchone()


def test_un_vert_apres_retry_est_persiste_apres_retry(conn, monkeypatch):
    runner = _RunnerFactice(premier_echec_timeout=True)

    ligne = _executer(conn, monkeypatch, runner)

    assert runner.appels == 2
    assert tuple(ligne) == ("success", "conforme", "apres_retry")


def test_falsifiable_la_campagne_stricte_ne_rejoue_pas_et_coupe_le_repli(conn, monkeypatch):
    """Sans `strict` le même run est rejoué (test précédent) ; avec, il reste un échec technique — jamais un vert rejoué."""
    runner = _RunnerFactice(premier_echec_timeout=True)

    ligne = _executer(conn, monkeypatch, runner, strict=True)

    assert runner.appels == 1, "le mode strict ne rejoue pas"
    assert ligne["execution_status"] != "success"
    assert runner.connection[MODE_STRICT_ENV] == "1", "le sous-processus reçoit le mode strict"


def test_un_vert_par_resolution_adaptative_est_persiste_auto_resolue(conn, monkeypatch):
    runner = _RunnerFactice(premier_echec_timeout=False,
                            paliers=[{"ident": "sujet", "tier": "adaptive", "scenario": "S"}])

    ligne = _executer(conn, monkeypatch, runner)

    assert tuple(ligne) == ("success", "conforme", "auto_resolue")


def test_un_run_ordinaire_ne_pose_pas_le_mode_strict(conn, monkeypatch):
    runner = _RunnerFactice(premier_echec_timeout=False)

    _executer(conn, monkeypatch, runner)

    assert MODE_STRICT_ENV not in runner.connection


# ── Les autres écrans qui montrent un vert : activité, test dans sa campagne, exécutions du cas ─────────────────


def test_falsifiable_le_fil_d_activite_et_la_fiche_du_test_qualifient_le_vert_et_pas_le_reste(conn, client):
    """Un `Passed` nominal, un `Passed` par repli et un échec par repli : seul le deuxième est « à confirmer »."""
    _, cas, run = _decor(conn, 3)
    _resultat(conn, run, cas[0], confiance="auto_resolue")
    _resultat(conn, run, cas[1])
    _resultat(conn, run, cas[2], fonctionnel="non_conforme", confiance="auto_resolue")

    evenements = {e["case_title"]: e for e in client.get(f"/api/runs/{run}/activite").json()["events"]}
    assert evenements["Cas 0"]["a_confirmer"] is True
    assert evenements["Cas 1"]["a_confirmer"] is False
    assert evenements["Cas 2"]["a_confirmer"] is False, "un échec obtenu par repli reste un échec"

    fiche = client.get(f"/api/runs/{run}/tests/{cas[0][0]}").json()
    assert (fiche["statut"], fiche["confiance"], fiche["a_confirmer"]) == ("passed", "auto_resolue", True)
    assert fiche["results"][-1]["a_confirmer"] is True
    autre = client.get(f"/api/runs/{run}/tests/{cas[1][0]}").json()
    assert autre["a_confirmer"] is False


def test_le_meme_cas_dans_une_autre_campagne_garde_sa_reserve(conn, client):
    """« Le même cas ailleurs » ne doit pas montrer `Passed` nu pour un vert obtenu par repli dans l'autre campagne."""
    pid, cas, run = _decor(conn, 1)
    autre_run = RunRepo(conn).create(project_id=pid, name="Autre campagne", case_ids=[cas[0][0]])
    _resultat(conn, autre_run, cas[0], confiance="apres_retry")
    _resultat(conn, run, cas[0])

    fiche = client.get(f"/api/runs/{run}/tests/{cas[0][0]}").json()

    ailleurs = [h for h in fiche["historique_du_cas"] if h["run_id"] == autre_run]
    assert ailleurs and ailleurs[0]["a_confirmer"] is True
    assert fiche["a_confirmer"] is False


def test_les_executions_du_cas_portent_la_reserve(conn, client):
    _, cas, run = _decor(conn, 1)
    _resultat(conn, run, cas[0], confiance="auto_resolue")

    lignes = client.get(f"/api/executions?limit=10").json()

    assert lignes and lignes[0]["a_confirmer"] is True and lignes[0]["confiance"] == "auto_resolue"
