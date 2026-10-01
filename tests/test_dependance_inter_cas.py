"""F26(b) — Portail Sapian - Integration, 2026-10-01 : une précondition qui suppose l'état laissé
par un AUTRE cas du même groupe (jamais garanti — scénarios Behave indépendants) a produit, sur la
même spécification, un cas rendu correctement autonome (C132) et un cas qui a improvisé une
recherche par préfixe sur un enregistrement réel (C131 avant correctif). Une règle en prose
ajoutée aux deux prompts a réduit le risque sans l'éliminer (C133/C134, spec sœur, ont de nouveau
agi sur un enregistrement réel observé pendant l'inspection, sans jamais le créer).

Ce fichier teste le remplacement : une sortie structurée (`depend_dun_autre_cas_du_groupe`,
`etat_a_creer_par_ce_cas`) + un contrôle 100% déterministe en Python (`verifier_dependance_inter_cas`)
qui rejette le cas AVANT la génération technique plutôt que de laisser un jugement du modèle
s'auto-approuver.
"""
from __future__ import annotations

import pytest

from testpilot.generation.metier_writer import (
    MetierDraft,
    _SEUIL_SIMILARITE_ETAT_PRECONDITION,
    verifier_dependance_inter_cas,
)

_PRECONDITION_C131_ORIGINALE = (
    "Un équipement a été créé lors du test précédent et une agence de recette avec au moins "
    "un utilisateur associé est disponible dans le système.")


def _draft(*, depend=True, etat="", preconditions=_PRECONDITION_C131_ORIGINALE) -> MetierDraft:
    return MetierDraft(title="t", preconditions=preconditions, steps=["s"], expected_result="r",
                       depend_dun_autre_cas_du_groupe=depend, etat_a_creer_par_ce_cas=etat)


# ── Le seuil lui-même : mesuré le 2026-10-01, pas choisi sans preuve (voir le commentaire de
# `_SEUIL_SIMILARITE_ETAT_PRECONDITION` dans metier_writer.py pour le détail des 6 exemples) ──────

def test_le_seuil_mesure_est_0_6_pas_0_9():
    """Verrouille la valeur retenue : si quelqu'un la change, ce test force à relire pourquoi
    0.9 avait été invalidé (4 paraphrases suspectes passaient à tort en dessous de 0.9)."""
    assert _SEUIL_SIMILARITE_ETAT_PRECONDITION == 0.6


@pytest.mark.parametrize("etat_suspect", [
    "Un équipement a déjà été créé par un cas antérieur et une agence de recette avec au moins "
    "un utilisateur associé est disponible dans le système.",
    "Le test précédent a déjà créé un équipement, et il existe une agence de recette avec au "
    "moins un utilisateur associé dans le système.",
    "Avant ce scénario, un autre cas a généré un équipement ; une agence de recette avec au "
    "moins un utilisateur associé est disponible dans le système.",
    "Un matériel a été généré pendant le scénario antérieur et une agence de recette comptant "
    "au moins un utilisateur associé reste disponible dans le système.",
])
def test_falsifiable_une_paraphrase_qui_garde_le_meme_sens_passif_est_rejetee(etat_suspect):
    """Le cœur du défaut mesuré : reformuler la précondition avec d'autres mots n'est PAS créer
    l'état soi-même. Ces 4 exemples passaient À TORT avec un seuil à 0.9 (ratios mesurés entre
    0.69 et 0.87) — ce test est le contre-essai qui aurait échoué avant la correction du seuil."""
    assert verifier_dependance_inter_cas(_draft(etat=etat_suspect)) is not None


@pytest.mark.parametrize("etat_correct", [
    "Créer un équipement avec une référence unique au Parc IT avant de l'utiliser.",
    "Ce cas crée lui-même l'équipement (type, numéro de série, marque, modèle) puis l'ouvre "
    "pour procéder à l'affectation, sans dépendre d'un autre cas.",
])
def test_une_action_de_creation_reellement_differente_est_acceptee(etat_correct):
    assert verifier_dependance_inter_cas(_draft(etat=etat_correct)) is None


def test_falsifiable_un_copier_coller_exact_est_rejete():
    assert verifier_dependance_inter_cas(
        _draft(etat=_PRECONDITION_C131_ORIGINALE)) is not None


def test_falsifiable_depend_vrai_sans_etat_decrit_est_rejete():
    """`etat_a_creer_par_ce_cas` vide alors que `depend_dun_autre_cas_du_groupe` est vrai : le
    modèle a reconnu la dépendance mais n'a proposé aucune façon de s'en affranchir."""
    assert verifier_dependance_inter_cas(_draft(etat="")) is not None


def test_un_cas_qui_ne_depend_de_rien_n_est_jamais_controle():
    """`depend_dun_autre_cas_du_groupe` faux (cas normal, immense majorité) : aucun contrôle,
    quelle que soit la précondition — le contrôle ne s'applique qu'au périmètre qu'il vise."""
    assert verifier_dependance_inter_cas(
        _draft(depend=False, etat="", preconditions="n'importe quoi")) is None


def test_un_cas_qui_ne_depend_de_rien_avec_un_etat_non_vide_n_est_pas_controle_non_plus():
    """Repli défensif : même si `etat_a_creer_par_ce_cas` est rempli par erreur pendant que
    `depend_dun_autre_cas_du_groupe` est faux, le contrôle reste inactif — seul le premier champ
    décide s'il s'applique."""
    assert verifier_dependance_inter_cas(
        _draft(depend=False, etat="valeur résiduelle sans rapport")) is None


# ── Intégration : `propose_metier` remplit bien les deux nouveaux champs depuis le JSON structuré ──

def test_propose_metier_remplit_les_deux_nouveaux_champs(monkeypatch):
    from testpilot.analysis.plan import TestPlan
    from testpilot.generation import metier_writer

    class _FauxLLM:
        def call_json(self, **kw):
            return {"title": "t", "preconditions": "p", "steps": ["s"], "expected_result": "r",
                    "depend_dun_autre_cas_du_groupe": True,
                    "etat_a_creer_par_ce_cas": "créer son propre enregistrement"}

    plan = TestPlan(module_name="m", models=[], scenarios=[], personas=[], portal_routes=[],
                    risks=[], raw_spec="spec")
    draft = metier_writer.propose_metier(plan, llm=_FauxLLM())
    assert draft.depend_dun_autre_cas_du_groupe is True
    assert draft.etat_a_creer_par_ce_cas == "créer son propre enregistrement"


def test_as_dict_porte_desormais_les_deux_champs_migration_58():
    """Revu le 2026-10-01 (F26(b), migration 58) : C138 (rejeu réel, Portail Sapian - Integration)
    a montré que `verifier_dependance_inter_cas` seul ne suffit pas — un cas peut passer ce
    contrôle puis, à la génération du Gherkin (étape séparée, round-trip par la base), finir par
    référencer un enregistrement réel plutôt que de créer le sien, faute de signal survivant
    jusqu'à `write_feature_file`. `as_dict()` porte donc maintenant les deux champs, persistés par
    `VersionRepo.create` et relus dans `ToolContext` (`tools/write.py::verifier_entite_a_creer`)."""
    draft = _draft(depend=True, etat="créer...")
    d = draft.as_dict()
    assert d["depend_dun_autre_cas_du_groupe"] is True
    assert d["etat_a_creer_par_ce_cas"] == "créer..."
    assert {"title", "preconditions", "steps", "expected_result",
           "depend_dun_autre_cas_du_groupe", "etat_a_creer_par_ce_cas"} == set(d)


# ── Intégration : `run_generation` rejette le LOT ENTIER, jamais une approbation silencieuse ────

_PROJET_CONNECTE = {"name": "P", "connector_type": "odoo", "base_url": "http://recette:8069",
                    "database": "db", "username": "qa", "password": "p"}


@pytest.fixture
def conn(tmp_path, monkeypatch):
    from testpilot import config
    from testpilot.store.db import get_initialized_db

    path = tmp_path / "dependance.db"
    monkeypatch.setattr(config, "DB_PATH", path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    c = get_initialized_db(path)
    yield c
    c.close()


def _module(conn) -> int:
    from testpilot.store.repositories import ModuleRepo, ProjectRepo
    pid = ProjectRepo(conn).create(**_PROJET_CONNECTE)
    return ModuleRepo(conn).create(project_id=pid, name="M")


def _plan(spec="La spec complète."):
    from testpilot.analysis.plan import TestPlan
    return TestPlan(module_name="m", models=[], scenarios=[], personas=["u"], portal_routes=[],
                    risks=[], connector_type="odoo", cost_usd=0.0, raw_spec=spec)


def _prepare_decoupage_un_cas(monkeypatch, *, brief="Cas A"):
    from testpilot.analysis import spec_analyzer as sa
    from testpilot.generation import decoupage

    monkeypatch.setattr(sa.SpecAnalyzer, "analyze_spec_content",
                        lambda self, slug, content: _plan(content))

    def faux_decoupage(plan, *, cost_tracker=None, **kw):
        return [decoupage.StoryPlan(
                    user_story="Story",
                    cases=[decoupage.CaseBrief(title="Cas A", brief=brief)])]
    monkeypatch.setattr(decoupage, "propose_decoupage", faux_decoupage)


def test_falsifiable_un_lot_avec_dependance_mal_geree_echoue_explicitement(conn, monkeypatch):
    """Le cas de référence F26(b) : `depend_dun_autre_cas_du_groupe=True` sans action de création
    réelle (`etat_a_creer_par_ce_cas` vide) — le job entier échoue, jamais une approbation
    silencieuse qui laisserait le cas atteindre la génération technique."""
    from testpilot.api.services import generation_service
    from testpilot.generation import metier_writer

    mid = _module(conn)
    _prepare_decoupage_un_cas(monkeypatch)

    def faux_metier(plan, *, brief="", cost_tracker=None, **kw):
        return metier_writer.MetierDraft(
            title=brief, preconditions=_PRECONDITION_C131_ORIGINALE, steps=["Étape"],
            expected_result="Verdict", depend_dun_autre_cas_du_groupe=True,
            etat_a_creer_par_ce_cas="")
    monkeypatch.setattr(metier_writer, "propose_metier", faux_metier)

    job_id, params = generation_service.start_generation(
        conn, mid, spec_content="Une spec", title="T")
    generation_service.run_generation(job_id, **params)

    job = generation_service.get_job(conn, job_id)
    assert job["status"] == "failed"
    assert "dépend d'un autre cas du groupe" in job["error"]
    assert "Cas A" in job["error"]


def test_un_lot_dont_la_dependance_est_correctement_resolue_reussit(conn, monkeypatch):
    """Contre-essai : `depend_dun_autre_cas_du_groupe=True` avec un `etat_a_creer_par_ce_cas`
    réellement différent de la précondition — le job aboutit normalement."""
    from testpilot.api.services import generation_service
    from testpilot.generation import metier_writer

    mid = _module(conn)
    _prepare_decoupage_un_cas(monkeypatch)

    def faux_metier(plan, *, brief="", cost_tracker=None, **kw):
        return metier_writer.MetierDraft(
            title=brief, preconditions=_PRECONDITION_C131_ORIGINALE, steps=["Étape"],
            expected_result="Verdict", depend_dun_autre_cas_du_groupe=True,
            etat_a_creer_par_ce_cas="Créer un équipement avec une référence unique avant usage.")
    monkeypatch.setattr(metier_writer, "propose_metier", faux_metier)

    job_id, params = generation_service.start_generation(
        conn, mid, spec_content="Une spec", title="T")
    generation_service.run_generation(job_id, **params)

    job = generation_service.get_job(conn, job_id)
    assert job["status"] == "awaiting_metier"
    assert len(job["cases"]) == 1
