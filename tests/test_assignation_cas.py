"""« Assigné à » — qui SUPERVISE un cas dans une campagne (inspiré de TestRail).

⚠️ **Ce que ce fichier protège.** La table `run_case_assignment` existe depuis la migration 25
(2026-08-04), mais rien ne l'alimentait jusqu'ici (trouvé en auditant la traçabilité de
l'application, 2026-09-14) — `RunDetail.vue` affichait un « — » figé en le disant explicitement
dans son propre commentaire. Ce que ces tests figent :

1. assigner puis relire rend la BONNE personne, sans jamais dupliquer la ligne (une par cas×run) ;
2. une chaîne vide RETIRE l'assignation — jamais une ligne « assigné à rien » ;
3. ça marche pour une campagne AUTOMATIQUE COMME MANUELLE (contrairement à la saisie d'un
   résultat) — superviser un résultat de machine est le même geste humain ;
4. un cas hors campagne, ou une campagne archivée, refusent — même garde que `add_result`.
"""
import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api.app import app
from testpilot.api.deps import get_conn
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, ModuleRepo, ProjectRepo, RunRepo
from testpilot.verdict.status import MODE_AUTOMATIQUE, MODE_MANUELLE


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "assignation.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    c = get_initialized_db(tmp_path / "assignation.db")
    yield c
    c.close()


@pytest.fixture
def client(conn):
    app.dependency_overrides[get_conn] = lambda: conn
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def campagne(conn):
    """Une campagne AUTOMATIQUE par défaut — le point même de ce chantier : l'assignation ne
    dépend pas du mode, contrairement à la saisie manuelle d'un résultat."""
    pid = ProjectRepo(conn).create(name="Portail")
    mid = ModuleRepo(conn).create(project_id=pid, name="Demandes")
    cid = CaseRepo(conn).create(title="Nominal", module_id=mid, feature_slug="nominal")
    hors = CaseRepo(conn).create(title="Hors campagne", module_id=mid, feature_slug="hors")
    rid = RunRepo(conn).create(project_id=pid, name="Recette", case_ids=[cid],
                               mode=MODE_AUTOMATIQUE)
    return {"run": rid, "cas": cid, "hors": hors, "projet": pid}


def _assigne(client, run_id, case_id, assigned_to):
    return client.put(f"/api/runs/{run_id}/cases/{case_id}/assignment",
                      json={"assigned_to": assigned_to})


# ── Le geste nominal ─────────────────────────────────────────────────────────

def test_assigner_puis_relire_le_run_rend_la_bonne_personne(client, campagne):
    r = _assigne(client, campagne["run"], campagne["cas"], "alice")
    assert r.status_code == 200
    assert r.json()["assigned_to"] == "alice"

    detail = client.get(f"/api/runs/{campagne['run']}").json()
    cas = next(c for c in detail["cases"] if c["id"] == campagne["cas"])
    assert cas["assigned_to"] == "alice"


def test_reassigner_REMPLACE_jamais_ne_duplique(client, campagne, conn):
    _assigne(client, campagne["run"], campagne["cas"], "alice")
    _assigne(client, campagne["run"], campagne["cas"], "bob")

    lignes = conn.execute(
        "SELECT assigned_to FROM run_case_assignment WHERE run_id=? AND case_id=?",
        (campagne["run"], campagne["cas"])).fetchall()
    assert len(lignes) == 1, "une seule ligne par (run, cas) — jamais un doublon"
    assert lignes[0]["assigned_to"] == "bob"


def test_une_chaine_vide_RETIRE_l_assignation(client, campagne, conn):
    _assigne(client, campagne["run"], campagne["cas"], "alice")
    r = _assigne(client, campagne["run"], campagne["cas"], "")
    assert r.status_code == 200
    assert r.json()["assigned_to"] == ""

    ligne = conn.execute(
        "SELECT * FROM run_case_assignment WHERE run_id=? AND case_id=?",
        (campagne["run"], campagne["cas"])).fetchone()
    assert ligne is None, "retirer une assignation SUPPRIME la ligne, jamais un « assigné à rien »"


def test_marche_aussi_sur_une_campagne_MANUELLE(client, conn):
    """⚠️ Aucune restriction de mode, contrairement à `add_result` : superviser un cas manuel ou
    automatique est le même geste humain."""
    pid = ProjectRepo(conn).create(name="P")
    mid = ModuleRepo(conn).create(project_id=pid, name="M")
    cid = CaseRepo(conn).create(title="C", module_id=mid, feature_slug="c")
    rid = RunRepo(conn).create(project_id=pid, name="R", case_ids=[cid], mode=MODE_MANUELLE)

    r = _assigne(client, rid, cid, "alice")
    assert r.status_code == 200
    assert r.json()["assigned_to"] == "alice"


def test_qui_a_assigne_est_trace(client, campagne, conn):
    _assigne(client, campagne["run"], campagne["cas"], "alice")
    ligne = conn.execute(
        "SELECT assigned_by, assigned_at FROM run_case_assignment WHERE run_id=? AND case_id=?",
        (campagne["run"], campagne["cas"])).fetchone()
    assert ligne["assigned_at"]  # horodaté, jamais vide


# ── Refus ──────────────────────────────────────────────────────────────────

def test_un_cas_hors_campagne_est_refuse(client, campagne):
    r = _assigne(client, campagne["run"], campagne["hors"], "alice")
    assert r.status_code >= 400


def test_une_campagne_archivee_refuse_l_assignation(client, campagne, conn):
    RunRepo(conn).archive(campagne["run"], True)
    r = _assigne(client, campagne["run"], campagne["cas"], "alice")
    assert r.status_code >= 400


def test_une_campagne_inconnue_est_refusee(client):
    r = _assigne(client, 999999, 1, "alice")
    assert r.status_code >= 400
