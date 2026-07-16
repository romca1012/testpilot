"""Décision 0013 — un humain peut CONFIRMER ou INFIRMER un diagnostic.

Constat qui a ouvert le chantier : **aucun** diagnostic n'était jamais tranché (les 8 produits
avaient `confirmed_by = NULL`), faute de toute surface pour le faire. Un `pending_human` attendait
une confirmation impossible ; un `not_required` était définitif et IRRÉVOCABLE, même faux. Or
§4.4 dit « faux-positif acceptable », pas « faux-positif irréversible » : il l'est parce qu'un
humain le corrige.

Invariants figés ici :
  - `defect_origin` (déduction de la MACHINE) n'est JAMAIS réécrit — sinon on perdrait l'écart
    machine/humain, seul matériau d'un audit de la taxonomie ;
  - les deux axes du run ne sont JAMAIS recalculés (§4.2) : un avis ne réécrit pas ce qui s'est
    passé ;
  - aucun blocage : le gate reste le seul verrou (§4.3).
"""

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import app as app_mod
from testpilot.store.db import _SCHEMA_VERSION, _column_names, get_initialized_db
from testpilot.store.repositories import (
    CaseRepo,
    ExecutionRepo,
    ModuleRepo,
    ProjectRepo,
    RepairRepo,
    VersionRepo,
)


@pytest.fixture
def conn(tmp_path):
    c = get_initialized_db(tmp_path / "r.db")
    yield c
    c.close()


def _diagnostic(conn, *, origin="vrai_bug", statut="not_required", cause="assertion_mismatch"):
    pid = ProjectRepo(conn).create(name="P")
    mid = ModuleRepo(conn).create(project_id=pid, name="M")
    cid = CaseRepo(conn).create(title="Cas", module_id=mid, feature_slug="cas")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="s", spec_hash="h",
                                   feature_content="f", steps_content="st")
    eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid)
    rid = RepairRepo(conn).create(execution_id=eid, attempt_number=1, failure_signature="sig",
                                  cause_category=cause, defect_origin=origin,
                                  confirmation_status=statut)
    return pid, cid, eid, rid


# ── La couche humaine n'écrase jamais la machine ──────────────────────────────

def test_infirmer_ne_reecrit_PAS_le_diagnostic_machine(conn):
    """LE point de conception : l'humain JUGE, il ne corrige pas.

    Si `defect_origin` était écrasé, on ne pourrait plus mesurer si la taxonomie s'améliore ou
    dérive — précisément la donnée qui manque pour son audit.
    """
    _, _, _, rid = _diagnostic(conn, origin="vrai_bug")
    RepairRepo(conn).set_human_verdict(rid, verdict="overturned", origin="test_a_reparer",
                                       comment="spec périmée : le test ne remplit pas tous les"
                                               " champs requis", reviewer="qa")
    row = RepairRepo(conn).get(rid)
    assert row["defect_origin"] == "vrai_bug"        # la machine, INTACTE
    assert row["human_verdict"] == "overturned"      # le jugement, à côté
    assert row["human_origin"] == "test_a_reparer"
    assert "spec périmée" in row["human_comment"]
    assert row["confirmed_by"] == "qa" and row["confirmed_at"]


def test_confirmer_laisse_aussi_le_diagnostic_intact(conn):
    _, _, _, rid = _diagnostic(conn, origin="test_a_reparer", statut="pending_human")
    RepairRepo(conn).set_human_verdict(rid, verdict="confirmed", reviewer="qa",
                                       comment="oui, le sélecteur est faux")
    row = RepairRepo(conn).get(rid)
    assert row["defect_origin"] == "test_a_reparer"
    assert row["human_verdict"] == "confirmed"
    assert row["confirmation_status"] == "confirmed"


def test_infirmer_sans_dire_ce_que_c_est_est_refuse(conn):
    """« Ce n'est pas ça » sans dire ce que c'est efface une information sans en produire."""
    _, _, _, rid = _diagnostic(conn)
    with pytest.raises(ValueError, match="origine réelle"):
        RepairRepo(conn).set_human_verdict(rid, verdict="overturned", reviewer="qa")


def test_verdict_et_origine_inconnus_refuses(conn):
    _, _, _, rid = _diagnostic(conn)
    with pytest.raises(ValueError, match="verdict inconnu"):
        RepairRepo(conn).set_human_verdict(rid, verdict="peut-être", reviewer="qa")
    with pytest.raises(ValueError, match="origine inconnue"):
        RepairRepo(conn).set_human_verdict(rid, verdict="overturned", origin="bof", reviewer="qa")


# ── La file : `not_required` en fait partie, c'est tout l'objet ───────────────

def test_un_not_required_peut_etre_arbitre(conn):
    """Le cas 6 en vrai : classé `vrai_bug`/`not_required`, donc IRRÉVOCABLE jusqu'ici."""
    pid, _, _, rid = _diagnostic(conn, origin="vrai_bug", statut="not_required")
    repo = RepairRepo(conn)
    assert [r["id"] for r in repo.list_to_arbitrate(project_id=pid, pending_only=False)] == [rid]
    # …mais il n'est PAS dans la file « pending » (il n'exige pas de confirmation).
    assert repo.list_to_arbitrate(project_id=pid, pending_only=True) == []


def test_un_diagnostic_arbitre_sort_de_la_file(conn):
    pid, _, _, rid = _diagnostic(conn, statut="pending_human", origin="test_a_reparer")
    repo = RepairRepo(conn)
    assert len(repo.list_to_arbitrate(project_id=pid)) == 1
    repo.set_human_verdict(rid, verdict="confirmed", reviewer="qa")
    assert repo.list_to_arbitrate(project_id=pid) == []


def test_la_file_est_scopee_projet(conn):
    pid1, _, _, _ = _diagnostic(conn, statut="pending_human")
    # Un second projet, avec son propre diagnostic.
    pid2 = ProjectRepo(conn).create(name="P2")
    mid2 = ModuleRepo(conn).create(project_id=pid2, name="M2")
    cid2 = CaseRepo(conn).create(title="C2", module_id=mid2, feature_slug="c2")
    vid2 = VersionRepo(conn).create(test_case_id=cid2, spec_content="", spec_hash="",
                                    feature_content="", steps_content="")
    eid2 = ExecutionRepo(conn).create(test_case_id=cid2, version_id=vid2)
    RepairRepo(conn).create(execution_id=eid2, attempt_number=1, failure_signature="s",
                            cause_category="ui_timeout", defect_origin="test_a_reparer",
                            confirmation_status="pending_human")
    repo = RepairRepo(conn)
    # Aucun mélange inter-projets (§4.8).
    assert len(repo.list_to_arbitrate(project_id=pid1, pending_only=False)) == 1
    assert len(repo.list_to_arbitrate(project_id=pid2, pending_only=False)) == 1
    assert len(repo.list_to_arbitrate(pending_only=False)) == 2


def test_la_file_porte_le_contexte(conn):
    """Trancher sans savoir de quel cas il s'agit serait trancher à l'aveugle."""
    pid, cid, eid, _ = _diagnostic(conn)
    row = RepairRepo(conn).list_to_arbitrate(project_id=pid, pending_only=False)[0]
    assert row["case_title"] == "Cas" and row["module_name"] == "M" and row["project_name"] == "P"
    assert row["test_case_id"] == cid and row["execution_id"] == eid


# ── Migration 8 ───────────────────────────────────────────────────────────────

def test_migration_8_ajoute_la_couche_humaine(tmp_path):
    db = tmp_path / "m.db"
    conn = get_initialized_db(db)
    for col in ("human_verdict", "human_origin", "human_comment"):
        conn.execute(f"ALTER TABLE repair_attempt DROP COLUMN {col}")
    conn.execute("PRAGMA user_version = 7")
    conn.commit()
    conn.close()

    conn = get_initialized_db(db)   # réouverture → migration 8
    cols = _column_names(conn, "repair_attempt")
    assert {"human_verdict", "human_origin", "human_comment"} <= cols
    assert "defect_origin" in cols   # la déduction machine survit à la migration
    assert conn.execute("PRAGMA user_version").fetchone()[0] == _SCHEMA_VERSION
    conn.close()


def test_les_diagnostics_existants_restent_non_tranches(conn):
    # La migration ne décide à la place de personne : '' = pas encore jugé.
    _, _, _, rid = _diagnostic(conn)
    assert RepairRepo(conn).get(rid)["human_verdict"] == ""


# ── API ───────────────────────────────────────────────────────────────────────

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    return TestClient(app_mod.app)


def test_api_file_et_arbitrage(client):
    conn = get_initialized_db(config.DB_PATH)
    pid, _, eid, rid = _diagnostic(conn, origin="vrai_bug", statut="not_required")
    avant = ExecutionRepo(conn).get(eid)
    conn.close()

    # `pending` ne montre pas un not_required ; `all` si.
    assert client.get(f"/api/repairs?project_id={pid}&status=pending").json() == []
    file_all = client.get(f"/api/repairs?project_id={pid}&status=all").json()
    assert len(file_all) == 1
    assert file_all[0]["defect_origin"] == "vrai_bug"
    assert file_all[0]["human_verdict"] == ""

    resp = client.post(f"/api/repairs/{rid}/verdict", json={
        "verdict": "overturned", "origin": "test_a_reparer",
        "comment": "spec périmée", "reviewer": "romaric"})
    assert resp.status_code == 200
    corps = resp.json()
    assert corps["defect_origin"] == "vrai_bug"        # machine intacte
    assert corps["human_origin"] == "test_a_reparer"   # jugement à côté
    assert corps["confirmed_by"] == "romaric"

    # Les DEUX AXES du run n'ont pas bougé (§4.2) : un avis ne réécrit pas l'exécution.
    conn = get_initialized_db(config.DB_PATH)
    apres = ExecutionRepo(conn).get(eid)
    conn.close()
    assert apres["execution_status"] == avant["execution_status"]
    assert apres["functional_status"] == avant["functional_status"]


def test_api_409_si_deja_arbitre(client):
    conn = get_initialized_db(config.DB_PATH)
    _, _, _, rid = _diagnostic(conn, statut="pending_human", origin="test_a_reparer")
    conn.close()
    body = {"verdict": "confirmed", "reviewer": "a"}
    assert client.post(f"/api/repairs/{rid}/verdict", json=body).status_code == 200
    # Écraser en silence effacerait le jugement d'un autre relecteur.
    resp = client.post(f"/api/repairs/{rid}/verdict", json={"verdict": "confirmed", "reviewer": "b"})
    assert resp.status_code == 409


def test_api_422_si_infirmation_sans_origine(client):
    conn = get_initialized_db(config.DB_PATH)
    _, _, _, rid = _diagnostic(conn)
    conn.close()
    resp = client.post(f"/api/repairs/{rid}/verdict",
                       json={"verdict": "overturned", "reviewer": "qa"})
    assert resp.status_code == 422


def test_api_404_si_inconnu(client):
    assert client.post("/api/repairs/999/verdict",
                       json={"verdict": "confirmed", "reviewer": "qa"}).status_code == 404


def test_reviewer_vide_devient_anonyme(client):
    """Champ LIBRE (aucune authentification, cohérent avec le gate) — mais jamais vide en base :
    « anonyme » dit la vérité, une chaîne vide laisserait croire à une donnée manquante."""
    conn = get_initialized_db(config.DB_PATH)
    _, _, _, rid = _diagnostic(conn, statut="pending_human", origin="test_a_reparer")
    conn.close()
    resp = client.post(f"/api/repairs/{rid}/verdict", json={"verdict": "confirmed", "reviewer": "  "})
    assert resp.json()["confirmed_by"] == "anonyme"
