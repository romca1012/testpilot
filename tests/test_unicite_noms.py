"""Unicité des noms : un nom réutilisé à sa portée = une info dupliquée qui devrait être regroupée.

Portées : projet = GLOBAL ; module = par PROJET (deux projets peuvent avoir « Facturation », ce
n'est pas une duplication) ; titre de cas = par MODULE ; `feature_slug` = GLOBAL.

Deux couches, complémentaires et non redondantes :
  - garde APPLICATIVE des repos (`casefold`, Unicode) → `DuplicateName` → HTTP 409 ;
  - index UNIQUE en base (`COLLATE NOCASE`, ASCII seulement) → filet de dernier recours.
C'est le premier qui attrape « CAFÉ » vs « Café ».
"""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import app as app_mod
from testpilot.store.db import _migrate_5_unicite_noms, get_initialized_db
from testpilot.store.repositories import (
    CaseGroupRepo,
    CaseRepo,
    DuplicateName,
    ModuleRepo,
    ProjectRepo,
)


@pytest.fixture
def conn(tmp_path):
    c = get_initialized_db(tmp_path / "u.db")
    yield c
    c.close()


# ── Projet : unique GLOBALEMENT ───────────────────────────────────────────────

def test_projet_meme_nom_refuse(conn):
    ProjectRepo(conn).create(name="Portail Sapian")
    with pytest.raises(DuplicateName, match="Portail Sapian"):
        ProjectRepo(conn).create(name="Portail Sapian")


def test_projet_casse_et_espaces_refuses(conn):
    ProjectRepo(conn).create(name="Portail Sapian")
    for variante in ("portail sapian", "PORTAIL SAPIAN", "  Portail   Sapian  "):
        with pytest.raises(DuplicateName):
            ProjectRepo(conn).create(name=variante)


def test_projet_accents_refuses_la_ou_NOCASE_echouerait(conn):
    """Le cas que l'index base ne peut PAS attraper : `COLLATE NOCASE` est ASCII seulement.

    Sans la garde applicative (`casefold`), « CAFÉ » passerait à côté de « Café » — d'où les
    deux couches.
    """
    ProjectRepo(conn).create(name="Café Métier")
    with pytest.raises(DuplicateName):
        ProjectRepo(conn).create(name="CAFÉ MÉTIER")


def test_renommage_vers_un_nom_pris_refuse(conn):
    pid = ProjectRepo(conn).create(name="Alpha")
    ProjectRepo(conn).create(name="Beta")
    with pytest.raises(DuplicateName):
        ProjectRepo(conn).rename(pid, name="Beta")


def test_renommer_un_projet_en_lui_meme_reste_possible(conn):
    """Un projet n'entre pas en conflit avec lui-même — sinon corriger une casse ou une
    description deviendrait impossible."""
    pid = ProjectRepo(conn).create(name="Alpha", description="x")
    ProjectRepo(conn).rename(pid, name="Alpha", description="corrigée")
    ProjectRepo(conn).rename(pid, name="ALPHA")   # simple correction de casse
    assert ProjectRepo(conn).get(pid)["name"] == "ALPHA"


# ── Module : unique PAR PROJET ────────────────────────────────────────────────

def test_module_meme_nom_dans_le_meme_projet_refuse(conn):
    pid = ProjectRepo(conn).create(name="P")
    ModuleRepo(conn).create(project_id=pid, name="Facturation")
    with pytest.raises(DuplicateName):
        ModuleRepo(conn).create(project_id=pid, name="facturation")


def test_meme_nom_de_module_dans_DEUX_projets_est_legitime(conn):
    # Deux projets peuvent avoir « Facturation » : ce n'est PAS une duplication.
    p1 = ProjectRepo(conn).create(name="P1")
    p2 = ProjectRepo(conn).create(name="P2")
    ModuleRepo(conn).create(project_id=p1, name="Facturation")
    ModuleRepo(conn).create(project_id=p2, name="Facturation")   # ne doit pas lever


# ── Cas : titre unique PAR MODULE, slug unique GLOBALEMENT ────────────────────

def test_cas_meme_titre_dans_le_meme_module_refuse(conn):
    pid = ProjectRepo(conn).create(name="P")
    mid = ModuleRepo(conn).create(project_id=pid, name="M")
    CaseRepo(conn).create(title="Validation champ requis", module_id=mid, feature_slug="a")
    with pytest.raises(DuplicateName, match="Validation champ requis"):
        CaseRepo(conn).create(title="validation champ requis", module_id=mid, feature_slug="b")


def test_meme_titre_dans_DEUX_modules_est_legitime(conn):
    pid = ProjectRepo(conn).create(name="P")
    m1 = ModuleRepo(conn).create(project_id=pid, name="M1")
    m2 = ModuleRepo(conn).create(project_id=pid, name="M2")
    CaseRepo(conn).create(title="Cas nominal", module_id=m1, feature_slug="a")
    CaseRepo(conn).create(title="Cas nominal", module_id=m2, feature_slug="b")   # ne doit pas lever


def test_slug_en_double_refuse_meme_dans_un_autre_module(conn):
    """Le slug nomme `{slug}.feature` dans un répertoire COMMUN : deux cas au même slug
    écriraient dans le MÊME fichier, l'un écrasant les tests de l'autre. Portée globale."""
    pid = ProjectRepo(conn).create(name="P")
    m1 = ModuleRepo(conn).create(project_id=pid, name="M1")
    m2 = ModuleRepo(conn).create(project_id=pid, name="M2")
    CaseRepo(conn).create(title="A", module_id=m1, feature_slug="collision")
    with pytest.raises(DuplicateName, match="collision"):
        CaseRepo(conn).create(title="B", module_id=m2, feature_slug="collision")


def test_slug_vide_ne_collisionne_pas(conn):
    # Pas de slug = pas de fichier = pas de collision possible. L'index base est partiel.
    pid = ProjectRepo(conn).create(name="P")
    mid = ModuleRepo(conn).create(project_id=pid, name="M")
    CaseRepo(conn).create(title="A", module_id=mid, feature_slug="")
    CaseRepo(conn).create(title="B", module_id=mid, feature_slug="")   # ne doit pas lever


def test_cas_sans_module_na_pas_de_portee_dunicite(conn):
    # Sans module, « doublon dans un module » n'a pas de sens : on ne bloque pas.
    CaseRepo(conn).create(title="Orphelin", module_id=None, feature_slug="o1")
    CaseRepo(conn).create(title="Orphelin", module_id=None, feature_slug="o2")


def test_renommer_un_cas_vers_un_titre_pris_refuse(conn):
    """Depuis la migration 13, l'unicité du titre est PAR SPÉCIFICATION (plus par module). On crée
    donc les deux cas dans LA MÊME spécification pour que le conflit s'y produise."""
    pid = ProjectRepo(conn).create(name="P")
    mid = ModuleRepo(conn).create(project_id=pid, name="M")
    gid = CaseGroupRepo(conn).create(module_id=mid, title="Spéc")
    CaseRepo(conn).create(title="A", module_id=mid, group_id=gid, feature_slug="a")
    cid = CaseRepo(conn).create(title="B", module_id=mid, group_id=gid, feature_slug="b")
    with pytest.raises(DuplicateName):
        CaseRepo(conn).rename(cid, "A")
    CaseRepo(conn).rename(cid, "B corrigé")   # un vrai renommage passe
    assert CaseRepo(conn).get(cid)["title"] == "B corrigé"


def test_deux_cas_de_MEME_titre_dans_deux_specifications_passent(conn):
    """Le pendant de la décision : par groupe, plus par module. Deux spécifications d'un même
    module peuvent chacune avoir un « Nominal »."""
    pid = ProjectRepo(conn).create(name="P")
    mid = ModuleRepo(conn).create(project_id=pid, name="M")
    g1 = CaseGroupRepo(conn).create(module_id=mid, title="Demande")
    g2 = CaseGroupRepo(conn).create(module_id=mid, title="Retour")
    CaseRepo(conn).create(title="Nominal", module_id=mid, group_id=g1, feature_slug="dn")
    CaseRepo(conn).create(title="Nominal", module_id=mid, group_id=g2, feature_slug="rn")  # OK


# ── L'index base : le filet quand on court-circuite les repos ─────────────────

def test_index_base_refuse_un_doublon_insere_en_direct(conn):
    """Écriture SQL directe (script, migration douteuse) : l'index UNIQUE doit tenir."""
    ProjectRepo(conn).create(name="Unique")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO project (name, created_at) VALUES ('unique', '2026-01-01')")


def test_migration_5_idempotente(conn):
    _migrate_5_unicite_noms(conn)   # rejouée sur une base déjà à la cible
    _migrate_5_unicite_noms(conn)
    noms = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'uq_%'")}
    # Idempotence de la migration 5 : ses PROPRES index sont présents, sans erreur ni doublon.
    # On assert un SOUS-ENSEMBLE, pas un jeu exact : `conn` applique aussi la migration 13, qui
    # ajoute l'unicité par groupe (uq_case_group_title, uq_group_module_title). ⚠️ En vrai, la
    # migration 5 ne se rejoue JAMAIS après la 13 (garde `version < N`) — ce test la rejoue seule,
    # ce qui ressuscite uq_case_module_title ; c'est un artefact du test, pas de la production.
    assert {"uq_project_name", "uq_module_project_name",
            "uq_case_module_title", "uq_case_feature_slug"} <= noms


# ── API : 409 + message clair ─────────────────────────────────────────────────

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    return TestClient(app_mod.app)


def _projet(nom: str) -> dict:
    return {"name": nom, "description": "", "connector_type": "odoo",
            "base_url": "http://x", "database": "d", "username": "u", "password": "p"}


def test_api_409_a_la_creation_dun_projet_en_double(client):
    assert client.post("/api/projects", json=_projet("Portail Sapian")).status_code == 201
    resp = client.post("/api/projects", json=_projet("portail sapian"))
    assert resp.status_code == 409
    # Le message est affiché tel quel à l'utilisateur : il doit nommer le conflit.
    assert "Portail Sapian" in resp.json()["detail"]


def test_api_409_au_renommage(client):
    pid = client.post("/api/projects", json=_projet("Alpha")).json()["id"]
    client.post("/api/projects", json=_projet("Beta"))
    resp = client.patch(f"/api/projects/{pid}", json=_projet("Beta"))
    assert resp.status_code == 409


def test_api_409_module_en_double(client):
    pid = client.post("/api/projects", json=_projet("P")).json()["id"]
    body = {"name": "Facturation", "description": ""}
    assert client.post(f"/api/projects/{pid}/modules", json=body).status_code == 201
    resp = client.post(f"/api/projects/{pid}/modules", json=body)
    assert resp.status_code == 409
    assert "Facturation" in resp.json()["detail"]


def test_api_409_cas_en_double_AVANT_de_lancer_la_generation(client):
    """Le titre est validé à l'ENTRÉE : sinon on paierait un appel LLM de plusieurs minutes
    pour finir en job « failed » au moment de l'insertion."""
    pid = client.post("/api/projects", json=_projet("P")).json()["id"]
    mid = client.post(f"/api/projects/{pid}/modules", json={"name": "M", "description": ""}).json()["id"]

    conn = get_initialized_db(config.DB_PATH)
    CaseRepo(conn).create(title="Cas existant", module_id=mid, feature_slug="existant")
    conn.close()

    resp = client.post(f"/api/modules/{mid}/cases",
                       json={"spec_content": "# spec", "title": "cas existant", "author": "qa"})
    assert resp.status_code == 409
    assert "Cas existant" in resp.json()["detail"]
