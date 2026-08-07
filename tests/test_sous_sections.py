"""Sous-sections (`case_group.parent_group_id`, migration 28, 2026-08-06) — parité TestRail :
une Section peut désormais en contenir d'autres, une vraie hiérarchie, décidée explicitement par
le porteur plutôt qu'un simple libellé.

Ce que ces tests figent :
- une seule profondeur d'imbrication (pas de sous-sous-section) ;
- une sous-section ne peut se rattacher qu'à une Section du MÊME module ;
- supprimer/purger une Section refuse tant qu'elle porte des sous-sections, même vides — même
  discipline que pour les cas ;
- `parent_group_id` voyage jusqu'à l'API, c'est ce qui permet à l'écran de reconstruire l'arbre.
"""

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import app as app_mod
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import (
    CaseGroupRepo,
    ModuleRepo,
    NotEmpty,
    ProfondeurInvalide,
    ProjectRepo,
)


@pytest.fixture
def conn(tmp_path):
    c = get_initialized_db(tmp_path / "sous_sections.db")
    yield c
    c.close()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    return TestClient(app_mod.app)


def _module(conn) -> int:
    pid = ProjectRepo(conn).create(name="Portail")
    return ModuleRepo(conn).create(project_id=pid, name="Demandes")


# ── Repo ─────────────────────────────────────────────────────────────────────

def test_cree_une_sous_section_sous_une_section(conn):
    mid = _module(conn)
    repo = CaseGroupRepo(conn)
    section = repo.create(module_id=mid, title="Notifications")

    sous_section = repo.create(module_id=mid, title="Email", parent_group_id=section)

    assert repo.get(sous_section)["parent_group_id"] == section
    assert repo.count_children(section) == 1


def test_une_sous_section_ne_peut_PAS_avoir_sa_propre_sous_section(conn):
    """Une seule profondeur — parité TestRail par défaut, décision explicite du porteur."""
    mid = _module(conn)
    repo = CaseGroupRepo(conn)
    section = repo.create(module_id=mid, title="Notifications")
    sous_section = repo.create(module_id=mid, title="Email", parent_group_id=section)

    with pytest.raises(ProfondeurInvalide):
        repo.create(module_id=mid, title="Email HTML", parent_group_id=sous_section)


def test_une_sous_section_doit_appartenir_au_MEME_module_que_son_parent(conn):
    repo = CaseGroupRepo(conn)
    pid = ProjectRepo(conn).create(name="Portail")
    m1 = ModuleRepo(conn).create(project_id=pid, name="Demandes")
    m2 = ModuleRepo(conn).create(project_id=pid, name="Autre module")
    section = repo.create(module_id=m1, title="Notifications")

    with pytest.raises(ValueError):
        repo.create(module_id=m2, title="Email", parent_group_id=section)


def test_parent_introuvable_leve_une_erreur_claire(conn):
    mid = _module(conn)
    with pytest.raises(ValueError):
        CaseGroupRepo(conn).create(module_id=mid, title="Email", parent_group_id=999)


def test_supprimer_une_section_REFUSE_tant_qu_elle_porte_des_sous_sections(conn):
    """Même discipline que pour les cas : pas de cascade silencieuse, même si la sous-section
    elle-même est vide."""
    mid = _module(conn)
    repo = CaseGroupRepo(conn)
    section = repo.create(module_id=mid, title="Notifications")
    sous_section = repo.create(module_id=mid, title="Email", parent_group_id=section)

    with pytest.raises(NotEmpty):
        repo.delete(section)

    repo.delete(sous_section)   # la sous-section, elle, est vide : ça passe
    repo.delete(section)        # et maintenant la section peut partir


def test_purger_une_section_REFUSE_tant_qu_elle_porte_des_sous_sections(conn):
    mid = _module(conn)
    repo = CaseGroupRepo(conn)
    section = repo.create(module_id=mid, title="Notifications")
    repo.create(module_id=mid, title="Email", parent_group_id=section)

    with pytest.raises(NotEmpty):
        repo.purger(section)


# ── Déplacer une Section (glisser-déposer, étape 2bis) ────────────────────────

def test_deplacer_imbrique_une_section_top_level_sous_une_autre(conn):
    mid = _module(conn)
    repo = CaseGroupRepo(conn)
    cible = repo.create(module_id=mid, title="Notifications")
    section = repo.create(module_id=mid, title="Email")

    repo.deplacer(section, cible)

    assert repo.get(section)["parent_group_id"] == cible


def test_deplacer_promeut_une_sous_section_au_premier_niveau(conn):
    mid = _module(conn)
    repo = CaseGroupRepo(conn)
    section = repo.create(module_id=mid, title="Notifications")
    sous = repo.create(module_id=mid, title="Email", parent_group_id=section)

    repo.deplacer(sous, None)

    assert repo.get(sous)["parent_group_id"] is None


def test_deplacer_reparente_une_sous_section_vers_une_AUTRE_section(conn):
    mid = _module(conn)
    repo = CaseGroupRepo(conn)
    a = repo.create(module_id=mid, title="Notifications")
    b = repo.create(module_id=mid, title="Facturation")
    sous = repo.create(module_id=mid, title="Email", parent_group_id=a)

    repo.deplacer(sous, b)

    assert repo.get(sous)["parent_group_id"] == b


def test_deplacer_refuse_une_section_qui_a_des_ENFANTS_sous_une_autre(conn):
    """Elle romprait la limite d'une seule profondeur si on la laissait faire."""
    mid = _module(conn)
    repo = CaseGroupRepo(conn)
    cible = repo.create(module_id=mid, title="Notifications")
    parent = repo.create(module_id=mid, title="Facturation")
    repo.create(module_id=mid, title="Email", parent_group_id=parent)

    with pytest.raises(ProfondeurInvalide):
        repo.deplacer(parent, cible)


def test_deplacer_refuse_sous_une_sous_section(conn):
    mid = _module(conn)
    repo = CaseGroupRepo(conn)
    section = repo.create(module_id=mid, title="Notifications")
    sous = repo.create(module_id=mid, title="Email", parent_group_id=section)
    autre = repo.create(module_id=mid, title="Facturation")

    with pytest.raises(ProfondeurInvalide):
        repo.deplacer(autre, sous)


def test_deplacer_refuse_une_cible_d_un_AUTRE_module(conn):
    repo = CaseGroupRepo(conn)
    pid = ProjectRepo(conn).create(name="Portail")
    m1 = ModuleRepo(conn).create(project_id=pid, name="Demandes")
    m2 = ModuleRepo(conn).create(project_id=pid, name="Autre module")
    section = repo.create(module_id=m1, title="Notifications")
    cible = repo.create(module_id=m2, title="Ailleurs")

    with pytest.raises(ValueError):
        repo.deplacer(section, cible)


def test_deplacer_refuse_l_auto_parentage(conn):
    mid = _module(conn)
    repo = CaseGroupRepo(conn)
    section = repo.create(module_id=mid, title="Notifications")

    with pytest.raises(ValueError):
        repo.deplacer(section, section)


def test_deplacer_une_section_introuvable_leve_une_erreur_claire(conn):
    mid = _module(conn)
    cible = CaseGroupRepo(conn).create(module_id=mid, title="Notifications")

    with pytest.raises(ValueError):
        CaseGroupRepo(conn).deplacer(999, cible)


# ── API ──────────────────────────────────────────────────────────────────────

def test_list_groups_expose_parent_group_id(client):
    pid = client.post("/api/projects", json={"name": "Portail"}).json()["id"]
    mid = client.post(f"/api/projects/{pid}/modules", json={"name": "Demandes"}).json()["id"]
    section = client.post(f"/api/modules/{mid}/groups",
                          json={"title": "Notifications"}).json()["id"]
    sous = client.post(f"/api/modules/{mid}/groups",
                       json={"title": "Email", "parent_group_id": section}).json()

    assert sous["parent_group_id"] == section

    groupes = client.get(f"/api/projects/{pid}/groups").json()
    par_id = {g["id"]: g for g in groupes}
    assert par_id[section]["parent_group_id"] is None
    assert par_id[sous["id"]]["parent_group_id"] == section


def test_creer_une_sous_sous_section_par_l_api_rend_422(client):
    pid = client.post("/api/projects", json={"name": "Portail"}).json()["id"]
    mid = client.post(f"/api/projects/{pid}/modules", json={"name": "Demandes"}).json()["id"]
    section = client.post(f"/api/modules/{mid}/groups",
                          json={"title": "Notifications"}).json()["id"]
    sous = client.post(f"/api/modules/{mid}/groups",
                       json={"title": "Email", "parent_group_id": section}).json()["id"]

    r = client.post(f"/api/modules/{mid}/groups",
                    json={"title": "Email HTML", "parent_group_id": sous})

    assert r.status_code == 422
    assert r.json()["code"] == "profondeur_invalide"


def test_supprimer_une_section_par_l_api_refuse_avec_409_si_sous_sections(client):
    pid = client.post("/api/projects", json={"name": "Portail"}).json()["id"]
    mid = client.post(f"/api/projects/{pid}/modules", json={"name": "Demandes"}).json()["id"]
    section = client.post(f"/api/modules/{mid}/groups",
                          json={"title": "Notifications"}).json()["id"]
    client.post(f"/api/modules/{mid}/groups", json={"title": "Email", "parent_group_id": section})

    r = client.delete(f"/api/groups/{section}")

    assert r.status_code == 409


def test_deplacer_une_section_par_l_api(client):
    pid = client.post("/api/projects", json={"name": "Portail"}).json()["id"]
    mid = client.post(f"/api/projects/{pid}/modules", json={"name": "Demandes"}).json()["id"]
    cible = client.post(f"/api/modules/{mid}/groups",
                        json={"title": "Notifications"}).json()["id"]
    section = client.post(f"/api/modules/{mid}/groups", json={"title": "Email"}).json()["id"]

    r = client.post(f"/api/groups/{section}/deplacer", json={"parent_group_id": cible})

    assert r.status_code == 200
    assert r.json()["parent_group_id"] == cible


def test_deplacer_une_section_par_l_api_rend_422_si_imbrication_invalide(client):
    pid = client.post("/api/projects", json={"name": "Portail"}).json()["id"]
    mid = client.post(f"/api/projects/{pid}/modules", json={"name": "Demandes"}).json()["id"]
    cible = client.post(f"/api/modules/{mid}/groups",
                        json={"title": "Notifications"}).json()["id"]
    parent = client.post(f"/api/modules/{mid}/groups", json={"title": "Facturation"}).json()["id"]
    client.post(f"/api/modules/{mid}/groups", json={"title": "Email", "parent_group_id": parent})

    r = client.post(f"/api/groups/{parent}/deplacer", json={"parent_group_id": cible})

    assert r.status_code == 422
    assert r.json()["code"] == "profondeur_invalide"


def test_deplacer_une_section_introuvable_par_l_api_rend_404(client):
    pid = client.post("/api/projects", json={"name": "Portail"}).json()["id"]
    mid = client.post(f"/api/projects/{pid}/modules", json={"name": "Demandes"}).json()["id"]
    cible = client.post(f"/api/modules/{mid}/groups",
                        json={"title": "Notifications"}).json()["id"]

    r = client.post("/api/groups/999999/deplacer", json={"parent_group_id": cible})

    assert r.status_code == 404
