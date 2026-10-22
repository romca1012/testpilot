"""Étape 5 du plan unique (F27) — un cas listé par la spécification ne disparaît plus EN SILENCE au découpage.

Mesuré deux fois (2026-10-01, Portail Sapian, module Parc IT) : PI-11, listé sous « Cas à couvrir », n'a été rédigé dans
aucun lot ; seul un rapprochement manuel l'a révélé. Gardé ici, sans IA : une user story écartée (citation introuvable)
est NOMMÉE, et une spécification qui énumère plus de cas qu'il n'en est proposé est SIGNALÉE sur l'écran de validation —
jamais bloquant (une personne relit), jamais lu dans le texte des cas proposés.
"""

from __future__ import annotations

import json

import pytest

from testpilot.analysis.plan import TestPlan
from testpilot.api.services import generation_service
from testpilot.generation import decoupage

SPEC = """# Gestion du parc
Contexte : un back-office et un portail.

## Cas à couvrir
- PI-10 Consulter un équipement
- PI-11 Modifier un statut depuis le portail
  - le statut passe à « En réparation »
- PI-12 Exporter la liste

## Hors périmètre
- la facturation
"""


@pytest.mark.parametrize("spec, attendu", [
    (SPEC, 3),
    ("Scénarios à couvrir :\n1. Créer\n2) Supprimer\n\nAutre texte.", 2),
    ("**Cas de test à couvrir**\n* a\n* b\n* c\n* d\n", 4),
    ("Une spécification sans liste de cas.", None),
    ("## Cas à couvrir\n\nRien encore.", 0),
])
def test_cas_listes_dans_la_spec(spec, attendu):
    assert decoupage.cas_listes_dans_la_spec(spec) == attendu


def _plan(spec):
    return TestPlan(module_name="m", models=[], scenarios=[], personas=["u"], portal_routes=[], risks=[],
                    connector_type="web", cost_usd=0.0, raw_spec=spec)


class _IA:
    def __init__(self, payload):
        self.payload = payload

    def call_simple(self, **_):
        return self.payload


def test_falsifiable_une_story_ecartee_est_nommee():
    payload = json.dumps({"stories": [
        {"user_story": "Consulter", "citation": "PI-10 Consulter un équipement", "cases": [{"title": "Voir", "brief": "b"}]},
        {"user_story": "Modifier un statut", "citation": "texte jamais écrit dans la spec",
         "cases": [{"title": "Changer le statut", "brief": "b"}]}]}, ensure_ascii=False)
    ecartees: list[str] = []
    stories = decoupage.propose_decoupage(_plan(SPEC), llm=_IA(payload), ecartees=ecartees)
    assert [s.user_story for s in stories] == ["Consulter"]
    assert ecartees == ["Modifier un statut"]


def test_couverture_du_decoupage():
    assert generation_service._couverture_du_decoupage(SPEC, 2, ["Modifier un statut"]) == {
        "cas_listes": 3, "cas_proposes": 2, "stories_ecartees": ["Modifier un statut"]}
    assert generation_service._couverture_du_decoupage(SPEC, 3, []) == {}
    assert generation_service._couverture_du_decoupage("pas de liste", 1, []) == {}


def test_le_job_en_attente_de_validation_porte_la_couverture(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from testpilot import config
    from testpilot.analysis import spec_analyzer as sa
    from testpilot.api.app import app
    from testpilot.generation import metier_writer
    from testpilot.store.db import get_initialized_db
    from testpilot.store.repositories import ModuleRepo, ProjectRepo

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    conn = get_initialized_db(tmp_path / "t.db")
    pid = ProjectRepo(conn).create(name="P", connector_type="web", base_url="http://app.test")
    mid = ModuleRepo(conn).create(project_id=pid, name="M")
    monkeypatch.setattr(sa.SpecAnalyzer, "analyze_spec_content", lambda self, slug, content: _plan(content))

    def faux_decoupage(plan, *, ecartees=None, **kw):
        ecartees.append("Modifier un statut")
        return [decoupage.StoryPlan(user_story="Consulter", cases=[decoupage.CaseBrief(title="Voir", brief="b")])]
    monkeypatch.setattr(decoupage, "propose_decoupage", faux_decoupage)
    monkeypatch.setattr(metier_writer, "propose_metier", lambda plan, **kw: metier_writer.MetierDraft(
        title="Voir", preconditions="", steps=["Ouvrir"], expected_result="Affiché"))

    job_id, params = generation_service.start_generation(conn, mid, spec_content=SPEC, title="T")
    generation_service.run_generation(job_id, **params)
    conn.close()

    corps = TestClient(app).get(f"/api/modules/jobs/{job_id}").json()
    assert corps["status"] == "awaiting_metier"
    assert corps["couverture"] == {"cas_listes": 3, "cas_proposes": 1, "stories_ecartees": ["Modifier un statut"]}
