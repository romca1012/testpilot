"""Décision 0014, étape 2 — le GATE autorise un budget de réparation (option C).

Le nœud du chantier : **réparer exige d'exécuter**, or §4.3 impose le gate humain avant la
première exécution d'une version générée par IA. Trois issues étaient possibles :
  A. réparer avant le gate → la boucle exécuterait du code IA non relu (§4.3 contourné) ;
  B. un gate par itération → ce n'est plus une boucle, c'est un ping-pong (le §6 veut une
     réparation « invisible pour l'utilisateur ») ;
  C. **le gate autorise explicitement N tentatives** ← retenu.

Le garde-fou n'est donc ni contourné ni consultatif : il **décide**, une fois, en connaissance
de cause. Ces tests figent cette propriété.
"""

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import app as app_mod
from testpilot.store.db import _SCHEMA_VERSION, _column_names, get_initialized_db
from testpilot.store.repositories import CaseRepo, ReviewRepo, VersionRepo


@pytest.fixture
def conn(tmp_path):
    c = get_initialized_db(tmp_path / "b.db")
    yield c
    c.close()


def _cas(conn):
    cid = CaseRepo(conn).create(title="Cas", feature_slug="cas")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="s", spec_hash="h",
                                   feature_content="f", steps_content="st")
    CaseRepo(conn).set_current_version(cid, vid)
    return cid, vid


# ── Le budget par défaut ──────────────────────────────────────────────────────

def test_approbation_sans_avis_recoit_le_defaut(conn):
    """Défaut = 2, pas 0 (arbitrage du porteur) : le §6 veut une réparation « invisible pour
    l'utilisateur » ; un défaut à 0 la rendrait opt-in à chaque relecture — donc visible et
    manuelle, soit le ping-pong écarté avec l'option B."""
    cid, vid = _cas(conn)
    ReviewRepo(conn).create(test_case_id=cid, version_id=vid, decision="approved", reviewer="qa")
    assert ReviewRepo(conn).repair_budget_for_version(vid) == config.REPAIR_BUDGET_DEFAULT
    assert config.REPAIR_BUDGET_DEFAULT == 2


def test_le_relecteur_peut_interdire_la_reparation(conn):
    cid, vid = _cas(conn)
    ReviewRepo(conn).create(test_case_id=cid, version_id=vid, decision="approved",
                            reviewer="qa", repair_budget=0)
    assert ReviewRepo(conn).repair_budget_for_version(vid) == 0


def test_le_relecteur_peut_elargir_le_budget(conn):
    cid, vid = _cas(conn)
    ReviewRepo(conn).create(test_case_id=cid, version_id=vid, decision="approved",
                            reviewer="qa", repair_budget=5)
    assert ReviewRepo(conn).repair_budget_for_version(vid) == 5


def test_un_budget_negatif_est_ramene_a_zero(conn):
    # -1 n'a pas de sens ; l'interpréter comme « interdit » plutôt que planter ou boucler.
    cid, vid = _cas(conn)
    ReviewRepo(conn).create(test_case_id=cid, version_id=vid, decision="approved",
                            reviewer="qa", repair_budget=-3)
    assert ReviewRepo(conn).repair_budget_for_version(vid) == 0


# ── Le budget n'existe QUE si le gate est franchi ─────────────────────────────

def test_version_non_relue_na_aucun_budget(conn):
    """LE test de l'option C : sans relecture, pas d'exécution (§4.3) — donc pas de réparation.
    Si ce test tombait, la boucle pourrait réparer une version que personne n'a relue."""
    _, vid = _cas(conn)
    assert ReviewRepo(conn).repair_budget_for_version(vid) == 0


def test_version_rejetee_na_aucun_budget(conn):
    cid, vid = _cas(conn)
    ReviewRepo(conn).create(test_case_id=cid, version_id=vid, decision="rejected",
                            reviewer="qa", repair_budget=5)   # même si un budget est passé
    assert ReviewRepo(conn).repair_budget_for_version(vid) == 0


def test_la_derniere_decision_fait_foi(conn):
    """Rejetée puis ré-approuvée : c'est la décision la plus RÉCENTE qui vaut, sinon un vieux
    refus interdirait une réparation que l'humain vient d'autoriser."""
    cid, vid = _cas(conn)
    r = ReviewRepo(conn)
    r.create(test_case_id=cid, version_id=vid, decision="approved", reviewer="a", repair_budget=4)
    r.create(test_case_id=cid, version_id=vid, decision="rejected", reviewer="b")
    assert r.repair_budget_for_version(vid) == 0
    r.create(test_case_id=cid, version_id=vid, decision="approved", reviewer="c", repair_budget=1)
    assert r.repair_budget_for_version(vid) == 1


# ── Migration 9 ───────────────────────────────────────────────────────────────

def test_migration_9_ajoute_le_budget(tmp_path):
    db = tmp_path / "m.db"
    conn = get_initialized_db(db)
    conn.execute("ALTER TABLE review_decision DROP COLUMN repair_budget")
    conn.execute("PRAGMA user_version = 8")
    conn.commit()
    conn.close()

    conn = get_initialized_db(db)   # réouverture → migration 9
    assert "repair_budget" in _column_names(conn, "review_decision")
    assert conn.execute("PRAGMA user_version").fetchone()[0] == _SCHEMA_VERSION
    conn.close()


def test_les_approbations_existantes_heritent_du_defaut(tmp_path):
    """Choix assumé : le défaut est la POLITIQUE appliquée à toute approbation qui ne dit rien
    du budget. Rétro-appliquer 0 aurait prétendu que ces relecteurs avaient refusé la
    réparation — ce qu'ils n'ont pas fait : la question ne leur était pas posée."""
    db = tmp_path / "old.db"
    conn = get_initialized_db(db)
    cid, vid = _cas(conn)
    ReviewRepo(conn).create(test_case_id=cid, version_id=vid, decision="approved", reviewer="qa")
    # Simule une base d'AVANT le budget.
    conn.execute("ALTER TABLE review_decision DROP COLUMN repair_budget")
    conn.execute("PRAGMA user_version = 8")
    conn.commit()
    conn.close()

    conn = get_initialized_db(db)
    assert ReviewRepo(conn).repair_budget_for_version(vid) == config.REPAIR_BUDGET_DEFAULT
    conn.close()


# ── API ───────────────────────────────────────────────────────────────────────

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    return TestClient(app_mod.app)


def _seed(approved=False):
    conn = get_initialized_db(config.DB_PATH)
    cid, vid = _cas(conn)
    conn.close()
    return cid, vid


def test_api_le_gate_expose_le_budget_et_son_defaut(client):
    cid, _ = _seed()
    gate = client.get(f"/api/cases/{cid}").json()["gate"]
    # Pas encore relu : aucun budget, mais le défaut est proposé au relecteur.
    assert gate["allowed"] is False
    assert gate["repair_budget"] == 0
    assert gate["repair_budget_default"] == config.REPAIR_BUDGET_DEFAULT


def test_api_approbation_sans_budget_prend_le_defaut(client):
    cid, _ = _seed()
    resp = client.post(f"/api/cases/{cid}/review", json={"approved": True})
    assert resp.status_code == 200
    corps = resp.json()
    assert corps["gate"]["allowed"] is True
    # La réponse renvoie le budget RETENU, pas celui envoyé (le champ était vide).
    assert corps["repair_budget"] == config.REPAIR_BUDGET_DEFAULT
    assert client.get(f"/api/cases/{cid}").json()["gate"]["repair_budget"] == config.REPAIR_BUDGET_DEFAULT


def test_api_approbation_qui_interdit_la_reparation(client):
    cid, _ = _seed()
    corps = client.post(f"/api/cases/{cid}/review",
                        json={"approved": True, "repair_budget": 0}).json()
    assert corps["gate"]["allowed"] is True      # le cas reste exécutable…
    assert corps["repair_budget"] == 0           # …mais rien ne sera réparé
