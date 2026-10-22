"""Édition DIRECTE du script généré (Gherkin + Python) — réservée au rôle Dev (2026-08-07).

Le miroir de `update_metier` (`tests/test_champs_metier.py`) : ici c'est le contenu TECHNIQUE
qui change, le métier qui est recopié tel quel. Deux différences assumées et vérifiées ici :

1. Contrairement à l'édition du métier, la nouvelle version n'est PAS auto-approuvée — une main
   humaine sur un script généré, sans dry-run, est un geste plus risqué.
2. Le RUNNER lit le script SUR DISQUE, jamais depuis la base — l'édition doit donc réécrire
   `{slug}.feature`/`{slug}_steps.py`, pas seulement la ligne en base.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import access
from testpilot.api import app as app_mod
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, ModuleRepo, ProjectRepo, UserRepo, VersionRepo


@pytest.fixture
def conn(tmp_path, monkeypatch):
    from testpilot import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "GENERATED_DIR", tmp_path / "generated")
    c = get_initialized_db(tmp_path / "script.db")
    yield c
    c.close()


def _cas_avec_script(conn) -> tuple[int, str]:
    cid = CaseRepo(conn).create(title="Cas", feature_slug="cas-a")
    vid = VersionRepo(conn).create(
        test_case_id=cid, spec_content="s", spec_hash="h",
        feature_content="Fonctionnalité: X\n  Scénario: Y\n    Alors ok",
        steps_content="from behave import then\n@then('ok')\ndef _(context): pass",
        title="Cas", preconditions="", test_steps="[]", expected_result="ok")
    CaseRepo(conn).set_current_version(cid, vid)
    return cid, "cas-a"


# ── 1. Le repository ─────────────────────────────────────────────────────────

def test_editer_le_script_cree_une_NOUVELLE_version(conn):
    cid, slug = _cas_avec_script(conn)
    avant = CaseRepo(conn).get(cid)["current_version_id"]

    vid = CaseRepo(conn).update_script(
        cid, feature_content="Fonctionnalité: X\n  Scénario: Z\n    Alors corrigé",
        steps_content="from behave import then\n@then('corrigé')\ndef _(context): pass")

    assert vid is not None and vid != avant
    assert CaseRepo(conn).get(cid)["current_version_id"] == vid


def test_editer_le_script_recopie_le_METIER_sans_le_toucher(conn):
    cid, _ = _cas_avec_script(conn)
    vid = CaseRepo(conn).update_script(cid, feature_content="Fonctionnalité: X\n  Scénario: Z",
                                       steps_content="# rien")
    nouvelle = VersionRepo(conn).get(vid)
    assert nouvelle["expected_result"] == "ok"   # inchangé, recopié de la version précédente


def test_rien_ne_change_rend_None_pas_de_version_fantome(conn):
    cid, _ = _cas_avec_script(conn)
    version = VersionRepo(conn).get(CaseRepo(conn).get(cid)["current_version_id"])

    vid = CaseRepo(conn).update_script(cid, feature_content=version["feature_content"],
                                       steps_content=version["steps_content"])
    assert vid is None


def test_l_edition_reecrit_les_fichiers_SUR_DISQUE(conn):
    """Le point qui compte le plus : le runner lit sur disque, pas la base."""
    cid, slug = _cas_avec_script(conn)
    CaseRepo(conn).update_script(
        cid, feature_content="Fonctionnalité: X\n  Scénario: Corrigé",
        steps_content="# script corrigé")

    assert (config.GENERATED_DIR / f"{slug}.feature").read_text(encoding="utf-8") \
        == "Fonctionnalité: X\n  Scénario: Corrigé"
    assert (config.GENERATED_DIR / f"{slug}_steps.py").read_text(encoding="utf-8") \
        == "# script corrigé"


# ── 2. La route — réservée au rôle Dev ────────────────────────────────────────

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "script_api.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "GENERATED_DIR", tmp_path / "generated")
    return TestClient(app_mod.app)


def _compte_et_connexion(client, username: str, role: str):
    conn = get_initialized_db(config.DB_PATH)
    try:
        UserRepo(conn).create(username=username, password_hash=access.hacher_mot_de_passe("mdp"),
                              role=role)
    finally:
        conn.close()
    r = client.post("/api/auth/login", json={"username": username, "password": "mdp"})
    assert r.status_code == 200, r.text


def _projet_module_cas(client) -> tuple[int, int]:
    # La création d'un projet est Admin-only. Le projet est donc une précondition du test ;
    # ProjectRepo synchronise les membres existants selon leur rôle global.
    conn = get_initialized_db(config.DB_PATH)
    try:
        pid = ProjectRepo(conn).create(name="Recette", base_url="http://x", database="db",
                                       username="qa", password="p")
    finally:
        conn.close()
    mid = client.post(f"/api/projects/{pid}/modules", json={"name": "M"}).json()["id"]
    cid = client.post(f"/api/modules/{mid}/cases/manual", json={
        "title": "Cas", "test_steps": ["a"], "expected_result": "ok"}).json()["id"]
    return pid, cid


def test_un_testeur_ne_peut_pas_editer_le_script(client):
    _compte_et_connexion(client, "Awa", access.ROLE_TESTEUR)
    _, cid = _projet_module_cas(client)

    r = client.patch(f"/api/cases/{cid}/script",
                     json={"feature_content": "x", "steps_content": "y"})
    assert r.status_code == 403


def test_un_dev_peut_editer_le_script(client):
    _compte_et_connexion(client, "Awa", access.ROLE_DEV)
    _, cid = _projet_module_cas(client)

    r = client.patch(f"/api/cases/{cid}/script",
                     json={"feature_content": "Fonctionnalité: X", "steps_content": "# s"})
    assert r.status_code == 200
    assert r.json()["version_created"] is True


# ── Étape 5 : le test modifié à la main ne contourne plus les contrôles en silence ─────────────────────────────

_FEATURE_PROPRE = ("# language: fr\nFonctionnalité: X\n  Scénario: Y\n"
                   "    Alors une erreur de validation est affichée dans le formulaire\n")


def _avis(client, cid) -> list[dict]:
    corps = client.get(f"/api/cases/{cid}").json()
    return corps.get("lint_warnings") or corps.get("avis") or []


def test_falsifiable_un_script_modifie_qui_interroge_l_oracle_a_la_main_est_signale(client):
    """Avant : seule la relecture humaine le gardait, sans savoir quoi regarder. Interroger l'oracle à la main est refusé à
    l'IA (VH-06 : faux rouge et erreurs du test mesurés) ; écrit à la main, il est désormais SIGNALÉ (jamais refusé)."""
    _compte_et_connexion(client, "Awa", access.ROLE_DEV)
    _, cid = _projet_module_cas(client)
    steps = ("from behave import then\n@then('le serveur a enregistré la commande')\n"
             "def step(context):\n    constater(context.oracle('etat')['commandes'])\n")
    r = client.patch(f"/api/cases/{cid}/script", json={"feature_content": _FEATURE_PROPRE, "steps_content": steps})
    assert r.status_code == 200 and r.json()["version_created"]

    conn = get_initialized_db(config.DB_PATH)
    try:
        from testpilot.api.services import generation_service
        cas = CaseRepo(conn).get(cid)
        versions = VersionRepo(conn).list_for_case(cid)
        avis = generation_service.lint_warnings_for_version(conn, cas, versions, cas["current_version_id"])
        signal = [a for a in avis if a["kind"] == "controles_ecriture_contournes"]
        assert len(signal) == 1 and "oracle" in signal[0]["message"]
        # Une édition du MÉTIER recopie le script sans le revérifier : le signal suit.
        vid = CaseRepo(conn).update_metier(cid, title="Cas", preconditions="", test_steps='["a"]',
                                           expected_result="ok, précisé")
        versions = VersionRepo(conn).list_for_case(cid)
        assert any(a["kind"] == "controles_ecriture_contournes"
                   for a in generation_service.lint_warnings_for_version(conn, CaseRepo(conn).get(cid), versions, vid))
    finally:
        conn.close()


def test_un_script_modifie_qui_passe_les_controles_n_est_pas_signale(client):
    _compte_et_connexion(client, "Awa", access.ROLE_DEV)
    _, cid = _projet_module_cas(client)
    r = client.patch(f"/api/cases/{cid}/script", json={"feature_content": _FEATURE_PROPRE, "steps_content": ""})
    assert r.status_code == 200
    conn = get_initialized_db(config.DB_PATH)
    try:
        from testpilot.api.services import generation_service
        cas = CaseRepo(conn).get(cid)
        avis = generation_service.lint_warnings_for_version(conn, cas, VersionRepo(conn).list_for_case(cid),
                                                            cas["current_version_id"])
        assert not [a for a in avis if a["kind"] == "controles_ecriture_contournes"]
    finally:
        conn.close()
