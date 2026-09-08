"""Déplacer / copier un cas entre Sections (migration 28, étape 2, 2026-08-06) — parité TestRail.

Ce que ces tests figent :
- déplacer un cas EXÉCUTÉ garde exactement le même historique (même `id`, mêmes résultats) ;
- copier un cas produit un cas RÉELLEMENT NEUF, sans le moindre résultat hérité ;
- copier recopie le script (Gherkin + steps) SUR DISQUE, pas seulement en base — sinon le cas
  copié semblerait exécutable et échouerait au premier run, fichier introuvable ;
- une collision de titre dans la Section cible se résout par un suffixe « (copie) », jamais un
  refus silencieux.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import app as app_mod
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import (
    CaseGroupRepo,
    CaseRepo,
    ExecutionRepo,
    ModuleRepo,
    ProjectRepo,
    ResultRepo,
    RunRepo,
    VersionRepo,
)
from testpilot.verdict.status import MODE_AUTOMATIQUE


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "GENERATED_DIR", tmp_path / "generated")
    c = get_initialized_db(tmp_path / "deplacer_copier.db")
    yield c
    c.close()


@pytest.fixture
def decor(conn):
    """Un module avec deux Sections, et un cas EXÉCUTÉ (avec un vrai résultat) dans la première."""
    pid = ProjectRepo(conn).create(name="Portail")
    mid = ModuleRepo(conn).create(project_id=pid, name="Demandes")
    groupes = CaseGroupRepo(conn)
    section_a = groupes.create(module_id=mid, title="Section A")
    section_b = groupes.create(module_id=mid, title="Section B")

    cases = CaseRepo(conn)
    cid = cases.create(title="Cas nominal", module_id=mid, group_id=section_a,
                       feature_slug="cas_nominal")
    vid = VersionRepo(conn).create(
        test_case_id=cid, spec_content="spec", spec_hash="h",
        feature_content="# language: fr\nFonctionnalité: X\n  Scénario: Y\n    Alors ok",
        steps_content="from behave import then\n@then('ok')\ndef _(context): pass",
        title="Cas nominal", test_steps="[]", expected_result="ok")
    cases.set_current_version(cid, vid)

    run_id = RunRepo(conn).create(project_id=pid, name="Campagne", case_ids=[cid],
                                  mode=MODE_AUTOMATIQUE)
    eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid)
    conn.execute("UPDATE execution SET run_id=? WHERE id=?", (run_id, eid))
    conn.commit()
    ExecutionRepo(conn).finalize(
        eid, execution_status="success", functional_status="conforme", scenarios_total=1,
        scenarios_passed=1, scenarios_failed=0, cost_usd=0.0, iterations=1, duration_seconds=0.1)

    return {"module": mid, "section_a": section_a, "section_b": section_b, "cas": cid,
            "run": run_id, "version": vid}


# ── Déplacer ─────────────────────────────────────────────────────────────────

def test_deplacer_garde_le_MEME_id_et_tout_l_historique(conn, decor):
    resultat_avant = ResultRepo(conn).dernier(decor["run"], decor["cas"])
    assert resultat_avant is not None

    CaseRepo(conn).deplacer(decor["cas"], decor["section_b"])

    cas = CaseRepo(conn).get(decor["cas"])
    assert cas["id"] == decor["cas"]              # même id
    assert cas["group_id"] == decor["section_b"]   # nouvelle Section
    resultat_apres = ResultRepo(conn).dernier(decor["run"], decor["cas"])
    assert resultat_apres == resultat_avant        # historique INCHANGÉ


def test_deplacer_vers_une_section_d_un_AUTRE_module_ajuste_le_module(conn, decor):
    autre_module = ModuleRepo(conn).create(project_id=1, name="Autre module")
    autre_section = CaseGroupRepo(conn).create(module_id=autre_module, title="Ailleurs")

    CaseRepo(conn).deplacer(decor["cas"], autre_section)

    cas = CaseRepo(conn).get(decor["cas"])
    assert cas["module_id"] == autre_module


def test_deplacer_vide_l_enveloppe_automatique_devenue_orpheline(conn):
    """Un cas SANS Section explicite (auto-enveloppé, comme un cas généré par l'IA) : le
    déplacer doit nettoyer l'enveloppe qu'il laisse derrière lui — même règle qu'à la suppression."""
    pid = ProjectRepo(conn).create(name="Portail2")
    mid = ModuleRepo(conn).create(project_id=pid, name="Demandes2")
    cible = CaseGroupRepo(conn).create(module_id=mid, title="Cible")
    cid = CaseRepo(conn).create(title="Cas seul", module_id=mid)   # auto-enveloppé
    enveloppe_id = CaseRepo(conn).get(cid)["group_id"]

    CaseRepo(conn).deplacer(cid, cible)

    assert CaseGroupRepo(conn).get(enveloppe_id) is None   # résidu nettoyé


def test_deplacer_refuse_si_le_titre_existe_deja_dans_la_section_cible(conn, decor):
    CaseRepo(conn).create(title="Cas nominal", module_id=decor["module"],
                          group_id=decor["section_b"])

    from testpilot.store.repositories import DuplicateName
    with pytest.raises(DuplicateName):
        CaseRepo(conn).deplacer(decor["cas"], decor["section_b"])


# ── Copier ───────────────────────────────────────────────────────────────────

def test_copier_produit_un_cas_NEUF_sans_historique(conn, decor):
    nouveau_id = CaseRepo(conn).copier(decor["cas"], decor["section_b"])

    assert nouveau_id != decor["cas"]
    nouveau = CaseRepo(conn).get(nouveau_id)
    assert nouveau["group_id"] == decor["section_b"]
    assert nouveau["title"] == "Cas nominal"
    # Aucun résultat hérité : le cas copié n'a jamais tourné.
    assert ResultRepo(conn).dernier(decor["run"], nouveau_id) is None
    assert ExecutionRepo(conn).list_for_case(nouveau_id) == []
    # L'ORIGINAL, lui, garde tout son historique intact.
    assert ResultRepo(conn).dernier(decor["run"], decor["cas"]) is not None


def test_copier_clone_le_script_SUR_DISQUE_pas_seulement_en_base(conn, decor):
    nouveau_id = CaseRepo(conn).copier(decor["cas"], decor["section_b"])

    nouveau = CaseRepo(conn).get(nouveau_id)
    version = VersionRepo(conn).get(nouveau["current_version_id"])
    assert version["feature_content"] == "# language: fr\nFonctionnalité: X\n  Scénario: Y\n    Alors ok"

    slug = nouveau["feature_slug"]
    assert slug and slug != "cas_nominal"   # un NOUVEAU slug, jamais celui de l'original
    assert (config.GENERATED_DIR / f"{slug}.feature").exists()
    assert (config.GENERATED_DIR / f"{slug}_steps.py").exists()
    contenu = (config.GENERATED_DIR / f"{slug}.feature").read_text(encoding="utf-8")
    assert "Fonctionnalité: X" in contenu


def test_copier_vers_une_section_avec_un_titre_pris_ajoute_un_suffixe(conn, decor):
    CaseRepo(conn).create(title="Cas nominal", module_id=decor["module"],
                          group_id=decor["section_b"])

    nouveau_id = CaseRepo(conn).copier(decor["cas"], decor["section_b"])

    nouveau = CaseRepo(conn).get(nouveau_id)
    assert nouveau["title"] == "Cas nominal (copie)"


def test_copier_un_cas_sans_gherkin_ne_fabrique_aucun_fichier(conn):
    """Un cas de saisie manuelle, jamais automatisé (`create_manual`) : la copie ne doit
    inventer NI script NI fichier — recopier un slug pour un cas sans Gherkin mentirait sur ce
    qui est exécutable."""
    pid = ProjectRepo(conn).create(name="Portail3")
    mid = ModuleRepo(conn).create(project_id=pid, name="Demandes3")
    cible = CaseGroupRepo(conn).create(module_id=mid, title="Cible3")
    cid = CaseRepo(conn).create_manual(module_id=mid, title="Cas manuel",
                                       test_steps="[]", expected_result="ok")

    nouveau_id = CaseRepo(conn).copier(cid, cible)

    nouveau = CaseRepo(conn).get(nouveau_id)
    assert nouveau["feature_slug"] == ""


# ── API ──────────────────────────────────────────────────────────────────────

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "GENERATED_DIR", tmp_path / "generated")
    return TestClient(app_mod.app)


def test_deplacer_par_l_api(client):
    pid = client.post("/api/projects", json={"name": "Portail"}).json()["id"]
    mid = client.post(f"/api/projects/{pid}/modules", json={"name": "Demandes"}).json()["id"]
    section_b = client.post(f"/api/modules/{mid}/groups", json={"title": "B"}).json()["id"]
    cid = client.post(f"/api/modules/{mid}/groups", json={"title": "A"}).json()["id"]
    # Un cas via la génération manuelle n'existe pas ici sans passer par le flux complet ; on
    # vérifie donc le contrat d'erreur (cas introuvable), le succès étant déjà couvert côté repo.
    r = client.post("/api/cases/999999/deplacer", json={"group_id": section_b})
    assert r.status_code == 404


def test_copier_par_l_api_refuse_une_section_introuvable(client):
    pid = client.post("/api/projects", json={"name": "Portail"}).json()["id"]
    mid = client.post(f"/api/projects/{pid}/modules", json={"name": "Demandes"}).json()["id"]
    section = client.post(f"/api/modules/{mid}/groups", json={"title": "A"}).json()["id"]

    r = client.post(f"/api/cases/999999/copier", json={"group_id": section})
    assert r.status_code == 404


def test_deplacer_par_l_api_rend_409_PAS_404_sur_collision_de_titre(client):
    """Régression : `DuplicateName` hérite de `ValueError` — un `except ValueError` placé AVANT
    `except DuplicateName` l'avale et renvoie 404 (« introuvable ») au lieu de 409 (« nom déjà
    pris »), ce que la seule mesure au niveau repo (`test_deplacer_refuse_si_le_titre_existe_deja
    _dans_la_section_cible`) ne peut pas attraper — elle ne passe jamais par la route HTTP."""
    pid = client.post("/api/projects", json={"name": "Portail"}).json()["id"]
    mid = client.post(f"/api/projects/{pid}/modules", json={"name": "Demandes"}).json()["id"]
    section_a = client.post(f"/api/modules/{mid}/groups", json={"title": "A"}).json()["id"]
    section_b = client.post(f"/api/modules/{mid}/groups", json={"title": "B"}).json()["id"]
    cid = client.post(f"/api/modules/{mid}/cases/manual", json={
        "title": "Cas nominal", "test_steps": ["étape"], "expected_result": "ok",
    }).json()["id"]
    # Un cas du même titre existe déjà dans la section cible.
    client.post(f"/api/modules/{mid}/cases/manual", json={
        "title": "Cas nominal", "test_steps": ["étape"], "expected_result": "ok",
    })
    # Le premier cas manuel atterrit dans sa propre enveloppe auto-créée (section_a n'est pas
    # forcément la sienne) : on le déplace explicitement dans `section_a` pour partir d'un état
    # connu, PUIS on tente de le déplacer dans `section_b`, qui porte déjà « Cas nominal ».
    client.post(f"/api/cases/{cid}/deplacer", json={"group_id": section_a})
    homonyme = client.post(f"/api/modules/{mid}/cases/manual", json={
        "title": "Cas nominal", "test_steps": ["étape"], "expected_result": "ok",
    }).json()["id"]
    client.post(f"/api/cases/{homonyme}/deplacer", json={"group_id": section_b})

    r = client.post(f"/api/cases/{cid}/deplacer", json={"group_id": section_b})

    assert r.status_code == 409
    assert r.json()["code"] == "nom_deja_pris"
