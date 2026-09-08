"""Automatiser un cas manuel : générer son test technique DEPUIS son métier (décision `0022` n°6).

Le bouton « Automatiser avec l'IA » (page d'un cas) ne concerne QUE les cas saisis à la main —
ceux qui ont un document métier mais pas de Gherkin. L'IA lit ce métier et écrit le test technique
sur le MÊME cas (nouvelle version), qui devient alors exécutable.

Ces tests figent la MÉCANIQUE (préparation, slug, re-versioning), pas l'appel LLM — simulé.
"""

import json

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import app as app_mod
from testpilot.api.services import generation_service
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, VersionRepo, ensure_default_module


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    c = get_initialized_db(tmp_path / "a.db")
    yield c
    c.close()


def _cas_manuel(conn):
    mid = ensure_default_module(conn, "m")
    cid = CaseRepo(conn).create_manual(
        module_id=mid, title="Connexion valide", preconditions="Un compte existe.",
        test_steps=json.dumps(["Ouvrir la page", "Saisir les identifiants", "Valider"]),
        expected_result="Accès au tableau de bord.")
    return mid, cid


# ── Préparation (start_automation) ────────────────────────────────────────────

def test_prepare_construit_le_metier_et_attribue_un_slug(conn):
    """Un cas manuel naît sans feature_slug ; l'automatisation lui en donne un (un run le retrouve
    par ce champ). Le métier passé à la génération vient du cas."""
    _, cid = _cas_manuel(conn)
    assert CaseRepo(conn).get(cid)["feature_slug"] == "", "manuel = pas de .feature au départ"

    job_id, params = generation_service.start_automation(conn, cid)

    assert params["case_id"] == cid
    assert params["metier"]["title"] == "Connexion valide"
    assert params["metier"]["steps"] == ["Ouvrir la page", "Saisir les identifiants", "Valider"]
    assert CaseRepo(conn).get(cid)["feature_slug"], "un slug a été attribué"
    # La spec reconstruite depuis le métier porte les étapes (matière pour l'analyse).
    assert "Saisir les identifiants" in params["spec_content"]


def test_prepare_refuse_un_cas_sans_metier_complet(conn):
    """Sans étapes ni résultat, il n'y a rien à automatiser — on le dit (422), on ne devine pas."""
    mid = ensure_default_module(conn, "m")
    # Cas créé directement sans version métier (cas de bord).
    cid = CaseRepo(conn).create(title="Vide", module_id=mid, feature_slug="")

    with pytest.raises(generation_service.GenerationError) as exc:
        generation_service.start_automation(conn, cid)
    assert exc.value.code == "invalid_metier"


def test_prepare_cas_inconnu(conn):
    with pytest.raises(generation_service.GenerationError) as exc:
        generation_service.start_automation(conn, 999)
    assert exc.value.code == "not_found"


# ── Exécution (run_automation) — LLM simulé ───────────────────────────────────

def test_automatiser_cree_une_version_AVEC_gherkin_sur_le_meme_cas(conn, monkeypatch):
    """Après automatisation, le cas manuel a une NOUVELLE version portant le Gherkin — il devient
    exécutable, sans changer d'identité. C'est le pont manuel → automatisé (`0022` n°6)."""
    from testpilot.analysis import spec_analyzer as sa
    from testpilot.analysis.plan import TestPlan
    from testpilot.generation import agent as agent_mod

    _, cid = _cas_manuel(conn)
    versions_avant = len(VersionRepo(conn).list_for_case(cid))

    # Analyse neutralisée (pas de LLM) + agent qui « écrit » un Gherkin déterministe.
    monkeypatch.setattr(sa.SpecAnalyzer, "analyze_spec_content",
                        lambda self, slug, content: TestPlan(
                            module_name=slug, models=[], scenarios=[], personas=["u"],
                            portal_routes=[], risks=[], connector_type="odoo", cost_usd=0.0,
                            raw_spec=content))

    def faux_generate(self, plan, *, case_id=None, metier=None, author="", projet=None, **kw):
        # Reproduit ce que fait la vraie génération : une version avec Gherkin sur le cas.
        from testpilot.store.repositories import VersionRepo as VR
        vid = VR(self.case_repo.conn).create(
            test_case_id=case_id, spec_content="", spec_hash="h",
            feature_content="# language: fr\nScénario: auto\n  Quand j'agis\n",
            steps_content="# steps", change_summary="Automatisation",
            title=metier["title"], preconditions=metier["preconditions"],
            test_steps=json.dumps(metier["steps"]), expected_result=metier["expected_result"])
        self.case_repo.set_current_version(case_id, vid)
        from testpilot.generation.state import GenerationResult
        r = GenerationResult(success=True, module_name=plan.module_name, stopped_reason="done",
                             dry_run_passed=True, iterations=1, cost_usd=0.05,
                             feature_content="x", steps_content="y", spec_hash="h",
                             awaiting_review=True)
        r.case_id = case_id
        return r
    monkeypatch.setattr(agent_mod.GenerationAgent, "generate", faux_generate)
    # Connecteur/runner neutralisés (pas de vraie instance).
    monkeypatch.setattr("testpilot.connectors.odoo.OdooConnector.from_project",
                        lambda project: type("C", (), {"connect": lambda s: None,
                                                       "disconnect": lambda s: None})())
    monkeypatch.setattr("testpilot.execution.behave_runner.BehaveRunner",
                        lambda **kw: object())
    monkeypatch.setattr(config, "DB_PATH", conn.execute("PRAGMA database_list").fetchone()[2])

    job_id, params = generation_service.start_automation(conn, cid)
    generation_service.run_automation(job_id, **params)

    assert generation_service.get_job(conn, job_id)["status"] == "done"
    conn2 = get_initialized_db(config.DB_PATH)
    versions = VersionRepo(conn2).list_for_case(cid)
    assert len(versions) == versions_avant + 1, "une nouvelle version a été créée"
    courante = VersionRepo(conn2).get(CaseRepo(conn2).get(cid)["current_version_id"])
    assert courante["feature_content"].strip(), "la version courante a un Gherkin"
    assert courante["title"] == "Connexion valide", "le métier est conservé"
    conn2.close()


# ── API ───────────────────────────────────────────────────────────────────────

def test_api_automate_demarre_un_job(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    client = TestClient(app_mod.app)
    conn = get_initialized_db(config.DB_PATH)
    _, cid = _cas_manuel(conn)
    conn.close()
    # La tâche de fond est neutralisée : on teste le déclenchement, pas la génération.
    monkeypatch.setattr(generation_service, "run_automation", lambda *a, **k: None)

    r = client.post(f"/api/cases/{cid}/automate")

    assert r.status_code == 202
    assert r.json()["status"] == "running"
    assert r.json()["job_id"]


def test_api_automate_cas_inconnu_404(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    client = TestClient(app_mod.app)

    assert client.post("/api/cases/999/automate").status_code == 404


# ── Amendement §4.3 (2026-07-21) : la validation métier vaut relecture ─────────

def test_une_version_produite_est_AUTO_APPROUVEE_sans_clic_humain(conn):
    """Amendement §4.3 : plus de gate humain séparé — la validation du métier à la création vaut
    relecture. Une version approuvée automatiquement ouvre le gate (le run n'est plus bloqué),
    et c'est TRACÉ (reviewer explicite), jamais silencieux."""
    from testpilot.store.repositories import CaseRepo, ReviewRepo, VersionRepo
    from testpilot.verdict import review_gate

    mid = ensure_default_module(conn, "m")
    cid = CaseRepo(conn).create(title="C", module_id=mid, feature_slug="c1")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="h",
                                   feature_content="# f", steps_content="# s")

    # Avant : le gate bloque (aucune relecture).
    assert review_gate.evaluate_gate(ReviewRepo(conn), vid).allowed is False

    review_gate.auto_approve_metier(ReviewRepo(conn), case_id=cid, version_id=vid)

    decision = review_gate.evaluate_gate(ReviewRepo(conn), vid)
    assert decision.allowed is True, "le run n'est plus bloqué"
    # L'approbation est tracée : on sait d'où elle vient.
    latest = ReviewRepo(conn).latest_for_version(vid)
    assert latest["reviewer"] == "validation-metier"
