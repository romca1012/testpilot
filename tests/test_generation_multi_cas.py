"""Génération multi-cas (§9, 2026-08-05) : une spécification → ses user stories → l'ensemble
minimal de cas nécessaires pour couvrir chacune.

Ces tests portent sur l'ORCHESTRATION de `generation_service.resume_generation` (une Section par
story, répétition du pipeline mono-cas déjà testé) — pas sur la génération Gherkin elle-même
(connecteur, dry-run, agent technique), neutralisée ici via `GenerationAgent.generate` pour
n'exercer que `_persist` (déjà couvert en détail par `test_generation_deux_passes.py`).

Ce que ces tests figent :
- deux user stories produisent DEUX Sections (`case_group`) distinctes ;
- une Section porte plusieurs cas quand la story le justifie — jamais un nombre fixe ;
- `refs` de chaque cas = le nom de sa story ;
- `case_group.spec_content` porte le texte réel dès la création de la Section ;
- le découpage ET chaque passe métier sont comptés au ledger (orphelins, avant tout cas créé) ;
- la reprise fonctionne avec une liste de cas RÉDUITE par rapport à la proposition initiale —
  aucune trace des cas retirés n'apparaît.
"""

import json

import pytest

from testpilot import config
from testpilot.analysis.plan import TestPlan
from testpilot.api.services import generation_service
from testpilot.generation import agent as agent_mod
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import (
    CaseGroupRepo,
    CaseRepo,
    CostRepo,
    ModuleRepo,
    ProjectRepo,
)

_PROJET_CONNECTE = {"name": "P", "connector_type": "odoo", "base_url": "http://recette:8069",
                    "database": "db", "username": "qa", "password": "p"}


@pytest.fixture(autouse=True)
def _jobs_propres():
    generation_service._JOBS.clear()
    yield
    generation_service._JOBS.clear()


@pytest.fixture
def conn(tmp_path, monkeypatch):
    path = tmp_path / "multi.db"
    monkeypatch.setattr(config, "DB_PATH", path)
    c = get_initialized_db(path)
    yield c
    c.close()


def _module(conn) -> int:
    pid = ProjectRepo(conn).create(**_PROJET_CONNECTE)
    return ModuleRepo(conn).create(project_id=pid, name="M")


def _plan(spec="La spec complète.") -> TestPlan:
    return TestPlan(module_name="m", models=[], scenarios=[], personas=["u"], portal_routes=[],
                    risks=[], connector_type="odoo", cost_usd=0.0, raw_spec=spec)


def _neutraliser_pipeline_technique(monkeypatch, *, cout_par_cas=0.02):
    """Neutralise analyse + connecteur + runner + boucle ReAct — mais garde `_persist` (le VRAI
    code), pour exercer la persistance réelle (Section, refs, spec_content, coût)."""
    from testpilot.analysis import spec_analyzer as sa

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
        result = GenerationResult(success=True, module_name=plan.module_name,
                                  stopped_reason="done", dry_run_passed=True, iterations=1,
                                  cost_usd=cout_par_cas, feature_content="# f",
                                  steps_content="# s", spec_hash="h", awaiting_review=True)
        reel_persist(self, plan, result, case_id=case_id, title=title, author=author,
                    module_id=module_id, metier=metier, group_id=group_id, refs=refs)
        return result

    monkeypatch.setattr(agent_mod.GenerationAgent, "generate", faux_generate)


def _cas(titre: str) -> dict:
    return {"title": titre, "preconditions": "", "steps": [f"Étape de {titre}"],
           "expected_result": f"Verdict de {titre}"}


def _sections(*stories: tuple[str, list[dict]]) -> list[dict]:
    return [{"title": titre, "cases": cas} for titre, cas in stories]


def _resume(job_id: str, **kw):
    """Appelle `resume_generation` comme le fait la route : le job existe TOUJOURS déjà à ce
    stade (créé par `start_generation`, mis à jour par `validate_metier`) — jamais appelé à
    froid en production. On reproduit cette précondition ici plutôt que de l'assouplir dans le
    code de production pour un usage que la vraie route ne fait jamais."""
    generation_service._JOBS.setdefault(job_id, {"status": "running", "case_ids": [], "error": ""})
    generation_service.resume_generation(job_id, **kw)


# ── Sections et nombre variable de cas ────────────────────────────────────────

def test_deux_user_stories_produisent_DEUX_sections_distinctes(conn, monkeypatch):
    mid = _module(conn)
    _neutraliser_pipeline_technique(monkeypatch)

    _resume(
        "job1", module_id=mid, title="Spec", spec_content="LE TEXTE", author="qa",
        sections=_sections(
            ("Connexion", [_cas("Connexion réussie")]),
            ("Réinitialisation du mot de passe", [_cas("Lien valide"), _cas("Lien expiré")]),
        ))

    groupes = CaseGroupRepo(conn).list_for_module(mid)
    assert {g["title"] for g in groupes} == {"Connexion", "Réinitialisation du mot de passe"}
    assert len(groupes) == 2


def test_une_section_EN_DOUBLE_est_ignoree_SANS_faire_echouer_les_AUTRES(conn, monkeypatch):
    """L'unicité des titres, qui se vérifiait AVANT tout appel LLM dans l'ancien modèle mono-cas
    (`start_generation`), ne peut plus l'être : les titres réels ne sont connus qu'APRÈS le
    découpage. Elle se vérifie donc désormais À LA PERSISTANCE de chaque Section
    (`CaseGroupRepo.ensure_title_free`) — et une collision ne doit PAS faire échouer tout le job :
    seule la Section en collision est ignorée, les autres sont créées normalement."""
    mid = _module(conn)
    _neutraliser_pipeline_technique(monkeypatch)
    CaseGroupRepo(conn).create(module_id=mid, title="Connexion", spec_content="")

    _resume(
        "job1", module_id=mid, title="Spec", spec_content="LE TEXTE", author="qa",
        sections=_sections(
            ("Connexion", [_cas("Connexion réussie")]),            # collision → ignorée
            ("Réinitialisation du mot de passe", [_cas("Lien valide")]),  # doit quand même passer
        ))

    groupes = {g["title"] for g in CaseGroupRepo(conn).list_for_module(mid)}
    assert groupes == {"Connexion", "Réinitialisation du mot de passe"}, (
        "une seule Section « Connexion » doit exister — la nouvelle n'a pas dû être créée")
    cas = CaseRepo(conn).list_all(module_id=mid)
    assert {c["title"] for c in cas} == {"Lien valide"}, (
        "le cas de la Section en collision ne doit PAS avoir été créé")

    job = generation_service.get_job("job1")
    assert job["status"] == "done", "d'autres Sections ont réussi — le job entier ne doit pas échouer"
    assert "Connexion" in job["error"], "la collision doit être rapportée, pas avalée en silence"


def test_une_section_porte_plusieurs_cas_QUAND_la_story_le_justifie(conn, monkeypatch):
    """Le nombre de cas par Section n'est jamais fixé d'avance — ici 1 et 2, jamais un compte
    imposé par défaut (pas systématiquement 3)."""
    mid = _module(conn)
    _neutraliser_pipeline_technique(monkeypatch)

    _resume(
        "job2", module_id=mid, title="Spec", spec_content="LE TEXTE", author="qa",
        sections=_sections(
            ("Connexion", [_cas("Connexion réussie")]),
            ("Réinitialisation", [_cas("Lien valide"), _cas("Lien expiré")]),
        ))

    cas = CaseRepo(conn).list_all(module_id=mid)
    par_groupe: dict[int, list] = {}
    for c in cas:
        par_groupe.setdefault(c["group_id"], []).append(c)
    assert sorted(len(v) for v in par_groupe.values()) == [1, 2]


# ── refs = nom de la story ─────────────────────────────────────────────────────

def test_refs_de_chaque_cas_est_le_nom_de_sa_story(conn, monkeypatch):
    mid = _module(conn)
    _neutraliser_pipeline_technique(monkeypatch)

    _resume(
        "job3", module_id=mid, title="Spec", spec_content="LE TEXTE", author="qa",
        sections=_sections(
            ("Connexion", [_cas("Connexion réussie")]),
            ("Réinitialisation", [_cas("Lien valide"), _cas("Lien expiré")]),
        ))

    cas = CaseRepo(conn).list_all(module_id=mid)
    refs_par_titre = {c["title"]: c["refs"] for c in cas}
    assert refs_par_titre == {
        "Connexion réussie": "Connexion",
        "Lien valide": "Réinitialisation",
        "Lien expiré": "Réinitialisation",
    }


# ── Le texte de la spec vit sur la Section ─────────────────────────────────────

def test_case_group_spec_content_porte_le_texte_REEL_apres_creation(conn, monkeypatch):
    mid = _module(conn)
    _neutraliser_pipeline_technique(monkeypatch)

    _resume(
        "job4", module_id=mid, title="Spec", spec_content="LE VRAI TEXTE SOURCE", author="qa",
        sections=_sections(("Connexion", [_cas("Connexion réussie")])))

    groupe = CaseGroupRepo(conn).list_for_module(mid)[0]
    assert CaseGroupRepo(conn).get(groupe["id"])["spec_content"] == "LE VRAI TEXTE SOURCE"


# ── Le coût : découpage + N passes métier + N générations ────────────────────

def test_le_cout_de_chaque_cas_genere_est_enregistre_au_ledger(conn, monkeypatch):
    mid = _module(conn)
    _neutraliser_pipeline_technique(monkeypatch, cout_par_cas=0.05)

    _resume(
        "job5", module_id=mid, title="Spec", spec_content="LE TEXTE", author="qa",
        sections=_sections(
            ("Connexion", [_cas("Connexion réussie")]),
            ("Réinitialisation", [_cas("Lien valide"), _cas("Lien expiré")])))

    # 3 cas générés à 0,05 $ + l'analyse partagée (neutralisée à $0, donc aucune ligne orpheline
    # supplémentaire — `_record_generation_cost` n'écrit jamais une ligne à $0).
    assert CostRepo(conn).monthly_total_usd() == pytest.approx(0.15)
    for c in CaseRepo(conn).list_all(module_id=mid):
        phases = {r["phase"] for r in CostRepo(conn).breakdown_for_case(c["id"])}
        assert "generation" in phases


def test_le_decoupage_et_les_N_passes_metier_sont_comptes_AU_LEDGER_avant_tout_cas(conn, monkeypatch):
    """`run_generation` (la passe 4a) enregistre le coût du découpage ET de chaque passe métier —
    en lignes ORPHELINES, puisqu'aucun cas n'existe encore à ce stade (ils naissent tous ensemble
    à la validation, §9b)."""
    from testpilot.analysis import spec_analyzer as sa
    from testpilot.generation import decoupage, metier_writer

    mid = _module(conn)
    monkeypatch.setattr(sa.SpecAnalyzer, "analyze_spec_content",
                        lambda self, slug, content: _plan(content))

    def faux_decoupage(plan, *, cost_tracker=None, **kw):
        if cost_tracker is not None:
            cost_tracker.total_cost = 0.01
        return [decoupage.StoryPlan(
                    user_story="Connexion",
                    cases=[decoupage.CaseBrief(title="Connexion réussie", brief="b"),
                          decoupage.CaseBrief(title="Connexion refusée", brief="b2")])]
    monkeypatch.setattr(decoupage, "propose_decoupage", faux_decoupage)

    def faux_metier(plan, *, brief="", cost_tracker=None, **kw):
        if cost_tracker is not None:
            cost_tracker.total_cost += 0.02
        return metier_writer.MetierDraft(title=brief, preconditions="", steps=["Étape"],
                                         expected_result="Verdict")
    monkeypatch.setattr(metier_writer, "propose_metier", faux_metier)

    job_id, params = generation_service.start_generation(
        conn, mid, spec_content="Une spec", title="T")
    generation_service.run_generation(job_id, **params)

    assert generation_service._JOBS[job_id]["status"] == "awaiting_metier"
    phases = {r["phase"] for r in conn.execute(
        "SELECT DISTINCT phase FROM cost_ledger WHERE test_case_id IS NULL")}
    assert "decoupage" in phases
    assert "metier" in phases
    # Deux passes métier (une par cas planifié) à 0,02 $ + le découpage à 0,01 $.
    assert CostRepo(conn).monthly_total_usd() == pytest.approx(0.05)


# ── La reprise avec une liste RÉDUITE ─────────────────────────────────────────

def test_la_reprise_avec_une_liste_REDUITE_ne_laisse_AUCUNE_TRACE_des_cas_retires(conn, monkeypatch):
    """L'utilisateur a supprimé un cas à la validation : SEULE la structure réduite arrive à
    `resume_generation` (jamais la proposition complète) — rien ne doit trahir l'existence du cas
    écarté, ni dans les cas créés, ni dans les Sections."""
    mid = _module(conn)
    _neutraliser_pipeline_technique(monkeypatch)
    # La proposition initiale portait 2 cas ("Connexion réussie" ET "Mot de passe oublié
    # abandonné en cours") ; l'humain n'a retenu que le premier. C'est CETTE structure réduite,
    # et RIEN d'autre, qui est passée ici.
    _resume(
        "job6", module_id=mid, title="Spec", spec_content="LE TEXTE", author="qa",
        sections=_sections(("Connexion", [_cas("Connexion réussie")])))

    cas = CaseRepo(conn).list_all(module_id=mid)
    assert [c["title"] for c in cas] == ["Connexion réussie"]
    assert "abandonné" not in json.dumps(cas, ensure_ascii=False)


def test_bout_en_bout_valide_PUIS_reprise_AVEC_une_story_reduite(conn, monkeypatch):
    """De bout en bout : le job propose 2 cas pour une story, l'humain n'en valide qu'UN via
    `validate_metier` — c'est cette structure réduite, et RIEN d'autre, que `resume_generation`
    reçoit et persiste."""
    mid = _module(conn)
    _neutraliser_pipeline_technique(monkeypatch)
    job_id = "job7"
    generation_service._JOBS[job_id] = {
        "status": "awaiting_metier", "case_ids": [], "error": "",
        "sections": [{"title": "Connexion",
                     "cases": [_cas("Connexion réussie"), _cas("Connexion via SSO")]}],
        "_resume": {"module_id": mid, "title": "Spec", "author": "qa",
                   "spec_content": "LE TEXTE"},
    }

    # L'écran de validation envoie la structure ÉDITÉE : un seul cas retenu sur les deux proposés.
    params = generation_service.validate_metier(
        job_id, [{"title": "Connexion", "cases": [_cas("Connexion réussie")]}])
    generation_service.resume_generation(job_id, **params)

    cas = CaseRepo(conn).list_all(module_id=mid)
    assert [c["title"] for c in cas] == ["Connexion réussie"]
    assert generation_service._JOBS[job_id]["status"] == "done"
    assert len(generation_service._JOBS[job_id]["case_ids"]) == 1


def test_validate_metier_ELIMINE_une_section_entierement_videe_par_l_humain():
    """Si l'humain supprime TOUS les cas d'une story, la Section correspondante disparaît de la
    structure validée plutôt que de créer une Section vide — sans bloquer les autres Sections."""
    job_id = "jobX"
    generation_service._JOBS[job_id] = {
        "status": "awaiting_metier", "case_ids": [], "error": "",
        "sections": [
            {"title": "Connexion", "cases": [_cas("Connexion réussie")]},
            {"title": "Story vidée", "cases": [_cas("Cas abandonné")]},
        ],
        "_resume": {"module_id": 1, "title": "T", "author": "qa", "spec_content": "s"},
    }

    params = generation_service.validate_metier(job_id, [
        {"title": "Connexion", "cases": [_cas("Connexion réussie")]},
        {"title": "Story vidée", "cases": []},
    ])

    assert [s["title"] for s in params["sections"]] == ["Connexion"]


def test_validate_metier_REFUSE_si_PLUS_AUCUN_cas_n_est_retenu():
    """Toutes les Sections vidées : rien à générer, on le dit plutôt que de démarrer un job vide."""
    job_id = "jobY"
    generation_service._JOBS[job_id] = {
        "status": "awaiting_metier", "case_ids": [], "error": "",
        "sections": [{"title": "Connexion", "cases": [_cas("Connexion réussie")]}],
        "_resume": {"module_id": 1, "title": "T", "author": "qa", "spec_content": "s"},
    }

    with pytest.raises(generation_service.GenerationError) as exc:
        generation_service.validate_metier(job_id, [{"title": "Connexion", "cases": []}])
    assert exc.value.code == "invalid_metier"
