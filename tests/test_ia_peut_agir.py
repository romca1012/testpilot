"""Décision A45 (porteur, 2026-10-16) — pour Odoo, « L'IA peut agir » ne suffit pas : le projet doit AUSSI se déclarer
instance de test. La protection de la production (`ODOO_ENV=prod`) n'agit que pour toute l'installation ; une base de
production visée par un seul projet n'est protégée que par cette seconde condition.

Falsifiable : chaque test échoue si la règle se contente de la case cochée, si un connecteur inconnu est traité comme le
web, ou si l'API / la génération ignorent la déclaration.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import app as app_mod
from testpilot.connectors.odoo import OdooConnector
from testpilot.generation.tools import essai
from testpilot.parametres.ia_peut_agir import ia_peut_ecrire


@pytest.mark.parametrize("projet, attendu", [
    ({"connector_type": "odoo", "calibration_writes_enabled": 1, "instance_de_test": 0}, False),
    ({"connector_type": "odoo", "calibration_writes_enabled": 1, "instance_de_test": 1}, True),
    ({"connector_type": "odoo", "calibration_writes_enabled": 0, "instance_de_test": 1}, False),
    ({"connector_type": "web", "calibration_writes_enabled": 1}, True),
    ({"connector_type": "web", "calibration_writes_enabled": 0}, False),
    ({"connector_type": "", "calibration_writes_enabled": 1}, False),         # inconnu : la règle la plus stricte
    ({"connector_type": "autre", "calibration_writes_enabled": 1}, False),
    ({"calibration_writes_enabled": 1}, False),
    (None, False),
])
def test_falsifiable_la_regle(projet, attendu):
    assert ia_peut_ecrire(projet) is attendu


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return TestClient(app_mod.app)


def test_falsifiable_l_api_ne_declare_jamais_d_office_et_enregistre_la_declaration(client):
    pid = client.post("/api/projects", json={"name": "Odoo", "connector_type": "odoo", "base_url": "https://odoo.test",
                                             "database": "d", "username": "u", "password": "p"}).json()["id"]
    projet = client.get("/api/projects").json()[0]
    assert projet["calibration_writes_enabled"] is True and projet["instance_de_test"] is False

    assert client.patch(f"/api/projects/{pid}", json={"instance_de_test": True}).json()["instance_de_test"] is True
    assert client.patch(f"/api/projects/{pid}", json={"description": "x"}).json()["instance_de_test"] is True, (
        "absent du corps : inchangé")
    assert client.patch(f"/api/projects/{pid}", json={"instance_de_test": False}).json()["instance_de_test"] is False


def test_falsifiable_la_generation_odoo_ne_recoit_l_autorisation_qu_avec_la_declaration(monkeypatch, tmp_path):
    """`GenerationAgent.generate` construit le contexte des outils : l'autorisation transmise suit la règle, pas la case
    seule. Le test s'arrête à la construction du contexte (aucun appel au modèle de langage)."""
    from testpilot.analysis.plan import TestPlan
    from testpilot.generation import agent as agent_mod

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    vus = []

    def _contexte(**kw):
        vus.append(kw["calibration_writes_enabled"])
        raise RuntimeError("arrêt du test")

    monkeypatch.setattr(agent_mod, "ToolContext", _contexte)
    plan = TestPlan(module_name="m", models=[], scenarios=[], personas=[], portal_routes=[], risks=[])
    for instance in (0, 1):
        projet = {"id": 1, "connector_type": "odoo", "calibration_writes_enabled": 1, "instance_de_test": instance}
        with pytest.raises(RuntimeError, match="arrêt du test"):
            agent_mod.GenerationAgent(llm=object(), connector=None, dry_runner=None).generate(plan, projet=projet)
    assert vus == [False, True]


def test_falsifiable_l_essai_web_reste_soumis_a_la_regle():
    projet = {"connector_type": "web", "base_url": "http://app.test", "calibration_writes_enabled": 0,
              "bac_a_sable_reset": "http://app.test/reset"}
    assert essai.construire(projet, dry_runner=object()) is None


def test_falsifiable_odoo_refuse_une_soumission_sans_modele_avant_d_ouvrir_le_formulaire():
    """A45 : sans `model`, la donnée créée ne serait pas supprimée — rien n'est soumis, le navigateur n'est pas ouvert."""
    conn = OdooConnector("http://localhost:9999", "db", "admin", "admin")
    conn._run_in_browser = lambda *a, **kw: (_ for _ in ()).throw(AssertionError("le formulaire ne doit pas être ouvert"))

    for modele in ("", "   "):
        resultat = conn.attempt_form_submission("/nouveau-ticket", {"name": "x"}, modele)
        assert resultat["submitted"] is False and resultat["cleaned_up"] is False
        assert "`model` requis" in resultat["error"]


@pytest.mark.parametrize("instance, attendu", [(0, False), (1, True)])
def test_falsifiable_la_correction_apres_generation_suit_aussi_la_regle(instance, attendu, monkeypatch, tmp_path):
    """Revue du 2026-10-16 (2e passe) : la correction lancée après une génération (`run_automation` →
    `_finaliser_version_generee` → `correction_agent`) reçoit l'autorisation calculée par la règle, jamais la case seule.
    Le générateur est doublé (aucun appel au modèle de langage)."""
    import json
    from types import SimpleNamespace

    from testpilot.analysis.plan import TestPlan
    from testpilot.api.services import generation_service as service
    from testpilot.generation.agent import GenerationAgent
    from testpilot.store.db import get_initialized_db
    from testpilot.store.repositories import CaseGroupRepo, CaseRepo, ModuleRepo, ProjectRepo, VersionRepo, \
        ensure_default_module

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "correction.db")
    monkeypatch.setattr(config, "GENERATED_DIR", tmp_path / "generated")
    conn = get_initialized_db()
    mid = ensure_default_module(conn, "parc")
    pid = ModuleRepo(conn).get(mid)["project_id"]
    conn.execute("UPDATE project SET connector_type='odoo', calibration_writes_enabled=1, instance_de_test=? WHERE id=?",
                 (instance, pid))
    conn.commit()
    assert ProjectRepo(conn).get(pid)["connector_type"] == "odoo"
    gid = CaseGroupRepo(conn).create(module_id=mid, title="Parc", spec_content="Créer un équipement")
    cid = CaseRepo(conn).create(title="Créer équipement", module_id=mid, group_id=gid, feature_slug="equipement")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="c", spec_hash="h", feature_content="f",
                                   steps_content="s", title="Créer équipement", preconditions="",
                                   test_steps=json.dumps(["Créer"]), expected_result="Créé")
    CaseRepo(conn).set_current_version(cid, vid)

    monkeypatch.setattr("testpilot.connectors.factory.build_connector",
                        lambda p: SimpleNamespace(connect=lambda: None, disconnect=lambda: None, rules=lambda: ""))
    monkeypatch.setattr("testpilot.analysis.spec_analyzer.SpecAnalyzer.analyze_spec_content",
                        lambda self, slug, content: TestPlan(module_name=slug, models=[], scenarios=[], personas=[],
                                                             portal_routes=[], risks=[], raw_spec=content))
    monkeypatch.setattr(GenerationAgent, "generate", lambda self, plan, **kw: SimpleNamespace(
        success=True, version_id=vid, cost_usd=0.0, error=None, stopped_reason=None))
    transmis = []
    monkeypatch.setattr(service, "_finaliser_version_generee",
                        lambda *a, **kw: transmis.append(kw["calibration_writes_enabled"]))

    job, params = service.start_automation(conn, cid)
    service.run_automation(job, **params)
    conn.close()

    assert transmis == [attendu]


def test_falsifiable_changer_d_application_retire_la_declaration(client):
    """Décision A47 (porteur, 2026-10-16) : « Instance de test » vaut pour UNE application. Changer l'adresse, la base ou
    le connecteur la décoche — même si le corps la renvoie cochée (l'ancienne fenêtre renvoie ce qu'elle a lu). La même
    application écrite autrement (casse, barre finale) ne la retire pas ; « L'IA peut agir » n'est jamais touchée."""
    pid = client.post("/api/projects", json={"name": "Odoo", "connector_type": "odoo",
                                             "base_url": "https://odoo-recette.exemple.test", "database": "recette",
                                             "username": "u", "password": "p"}).json()["id"]

    def declarer():
        assert client.patch(f"/api/projects/{pid}", json={"instance_de_test": True}).json()["instance_de_test"] is True

    def patch(corps):
        return client.patch(f"/api/projects/{pid}", json=corps).json()

    declarer()
    projet = patch({"base_url": "HTTPS://odoo-recette.exemple.test/", "database": "recette", "description": "x"})
    assert projet["instance_de_test"] is True, "même application, écrite autrement"

    projet = patch({"base_url": "https://odoo.exemple.test", "instance_de_test": True})
    assert projet["instance_de_test"] is False and projet["calibration_writes_enabled"] is True

    declarer()
    assert patch({"database": "production"})["instance_de_test"] is False

    declarer()
    assert patch({"connector_type": "web"})["instance_de_test"] is False


def test_falsifiable_un_reglage_qui_ne_change_pas_l_application_garde_la_declaration(client):
    """A47, sens inverse : seuls le connecteur, l'adresse et la base identifient l'application. Le nom, la version, le
    compte ou le navigateur ne retirent pas la déclaration — sinon chaque réglage obligerait à redéclarer."""
    pid = client.post("/api/projects", json={"name": "Odoo", "connector_type": "odoo", "base_url": "https://o.test",
                                             "database": "recette", "username": "u", "password": "p"}).json()["id"]
    client.patch(f"/api/projects/{pid}", json={"instance_de_test": True})

    for corps in ({"name": "Odoo recette"}, {"connector_version": "17"}, {"username": "autre"},
                  {"browser_locale": "en-US"}, {"calibration_writes_enabled": False}):
        assert client.patch(f"/api/projects/{pid}", json=corps).json()["instance_de_test"] is True, corps
