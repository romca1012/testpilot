"""Le budget de coût par appel LLM (`COST_LIMIT_PER_RUN_USD`) est PAR CAS, pas cumulé sur tout un
lot de génération multi-cas.

Avant ce correctif, `run_generation` (passe métier) et `resume_generation` (passe Gherkin)
réutilisaient un SEUL `CostTracker` pour TOUS les cas d'un même lot : le coût cumulait d'un cas à
l'autre jusqu'à dépasser le plafond, après quoi TOUS les cas suivants du lot échouaient en cascade
dès leur premier appel — indépendamment de leur propre coût réel. Une spécification à plusieurs
user stories (le but même de la génération multi-cas) pouvait ainsi voir ses derniers cas échouer
systématiquement, sans lien avec leur complexité individuelle.

Audit du 2026-08-07, défaut classé bloquant (B2).
"""

from __future__ import annotations

import pytest

from testpilot import config
from testpilot.analysis.plan import TestPlan
from testpilot.api.services import generation_service
from testpilot.generation import agent as agent_mod
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, GenerationJobRepo, ModuleRepo, ProjectRepo

_PROJET_CONNECTE = {"name": "P", "connector_type": "odoo", "base_url": "http://recette:8069",
                    "database": "db", "username": "qa", "password": "p"}
# Un appel « réaliste » à ce tarif (claude-sonnet-5 : 3$/M in, 15$/M out) : ~0,045 $. Sous le
# plafond de test (0,06 $) pris ISOLÉMENT, mais DEUX fois cumulés (0,09 $) le dépasseraient — le
# point exact que ces tests vérifient.
_INPUT_TOKENS, _OUTPUT_TOKENS = 10_000, 1_000
_COUT_PAR_APPEL = 0.045


@pytest.fixture
def conn(tmp_path, monkeypatch):
    path = tmp_path / "budget.db"
    monkeypatch.setattr(config, "DB_PATH", path)
    monkeypatch.setattr(config, "COST_LIMIT_PER_RUN_USD", 0.06)
    c = get_initialized_db(path)
    yield c
    c.close()


def _module(conn) -> int:
    pid = ProjectRepo(conn).create(**_PROJET_CONNECTE)
    return ModuleRepo(conn).create(project_id=pid, name="M")


def _plan(spec="La spec complète.") -> TestPlan:
    return TestPlan(module_name="m", models=[], scenarios=[], personas=["u"], portal_routes=[],
                    risks=[], connector_type="odoo", cost_usd=0.0, raw_spec=spec)


def test_deux_cas_du_MEME_lot_ne_partagent_pas_leur_budget_metier(conn, monkeypatch):
    """`run_generation` : deux cas, chacun avec un appel métier qui coûte ISOLÉMENT moins que le
    plafond — avec l'ancien tracker partagé, le second aurait dépassé le cumul et fait échouer
    TOUT le job. Avec le correctif, les deux réussissent."""
    from testpilot.analysis import spec_analyzer as sa
    from testpilot.generation import decoupage, metier_writer

    mid = _module(conn)
    monkeypatch.setattr(sa.SpecAnalyzer, "analyze_spec_content",
                        lambda self, slug, content: _plan(content))

    def faux_decoupage(plan, *, cost_tracker=None, **kw):
        # `run_generation` ne passe que `brief.brief` à `propose_metier` (pas `brief.title`) : le
        # titre final du cas vient du DOCUMENT MÉTIER rédigé, ici notre `faux_metier` ci-dessous —
        # les deux valeurs sont donc alignées pour que ce test reste lisible.
        return [decoupage.StoryPlan(
                    user_story="Connexion",
                    cases=[decoupage.CaseBrief(title="Cas A", brief="Cas A"),
                          decoupage.CaseBrief(title="Cas B", brief="Cas B")])]
    monkeypatch.setattr(decoupage, "propose_decoupage", faux_decoupage)

    def faux_metier(plan, *, brief="", cost_tracker=None, **kw):
        # Un vrai appel, avec le VRAI mécanisme de plafonnement (`track_call` lève si dépassé) —
        # pas une simulation qui contournerait la logique vérifiée ici.
        cost_tracker.track_call(model="claude-sonnet-5", input_tokens=_INPUT_TOKENS,
                                output_tokens=_OUTPUT_TOKENS, label="metier")
        return metier_writer.MetierDraft(title=brief, preconditions="", steps=["Étape"],
                                         expected_result="Verdict")
    monkeypatch.setattr(metier_writer, "propose_metier", faux_metier)

    job_id, params = generation_service.start_generation(
        conn, mid, spec_content="Une spec", title="T")
    generation_service.run_generation(job_id, **params)

    job = generation_service.get_job(conn, job_id)
    # Avant le correctif : "failed" (CostLimitExceeded sur le 2e cas, non rattrapé).
    assert job["status"] == "awaiting_metier"
    assert len(job["cases"]) == 2
    assert {c["title"] for c in job["cases"]} == {"Cas A", "Cas B"}


def test_deux_cas_du_MEME_lot_ne_partagent_pas_leur_budget_gherkin(conn, monkeypatch):
    """`resume_generation` : même invariant, côté écriture du Gherkin (`agent.cost_tracker`,
    réutilisé sur TOUS les `agent.generate()` du lot avant le correctif)."""
    from testpilot.analysis import spec_analyzer as sa

    mid = _module(conn)
    monkeypatch.setattr(sa.SpecAnalyzer, "analyze_spec_content",
                        lambda self, slug, content: _plan(content))
    monkeypatch.setattr("testpilot.connectors.odoo.OdooConnector.from_project",
                        lambda project: type("C", (), {"connect": lambda s: None,
                                                       "disconnect": lambda s: None})())
    monkeypatch.setattr("testpilot.execution.behave_runner.BehaveRunner", lambda **kw: object())

    reel_persist = agent_mod.GenerationAgent._persist

    def faux_generate(self, plan, *, case_id=None, title="", author="", module_id=None,
                      metier=None, group_id=None, projet=None, refs=""):
        from testpilot.generation.state import GenerationResult
        # Le VRAI mécanisme de plafonnement, sur LE tracker de l'agent — c'est lui qu'on vérifie.
        self.cost_tracker.track_call(model="claude-sonnet-5", input_tokens=_INPUT_TOKENS,
                                     output_tokens=_OUTPUT_TOKENS, label="generation")
        result = GenerationResult(success=True, module_name=plan.module_name,
                                  stopped_reason="done", dry_run_passed=True, iterations=1,
                                  cost_usd=self.cost_tracker.total_cost, feature_content="# f",
                                  steps_content="# s", spec_hash="h", awaiting_review=True)
        reel_persist(self, plan, result, case_id=case_id, title=title, author=author,
                    module_id=module_id, metier=metier, group_id=group_id, refs=refs)
        return result
    monkeypatch.setattr(agent_mod.GenerationAgent, "generate", faux_generate)

    cases = [
        {"title": "Cas A", "preconditions": "", "steps": ["Étape"], "expected_result": "Verdict",
         "user_story": "Connexion"},
        {"title": "Cas B", "preconditions": "", "steps": ["Étape"], "expected_result": "Verdict",
         "user_story": "Connexion"},
    ]
    job_id = "job-test"
    # Le job existe TOUJOURS déjà à ce stade en production (créé par `start_generation`, mis à
    # jour par `validate_metier`) — reproduit ici plutôt qu'assoupli côté production.
    GenerationJobRepo(conn).creer(job_id, module_id=mid)

    generation_service.resume_generation(job_id, module_id=mid, title="T", spec_content="s",
                                         author="qa", cases=cases, group_id=None)

    module_cases = CaseRepo(conn).list_all(module_id=mid)
    # Avant le correctif : un seul cas créé, le second perdu à `CostLimitExceeded`.
    assert {c["title"] for c in module_cases} == {"Cas A", "Cas B"}
