"""Génération en DEUX PASSES avec pause humaine — décision `0022` n°5.

Avant : un seul appel produisait le Gherkin, et les champs métier créés par la migration 14
restaient **vides sur tout cas généré**. L'écran en dérivait un aperçu depuis le Gherkin — un
texte qui avait l'air rédigé sans l'être. Le chantier A était fait à moitié : la moitié
« stocker » existait, la moitié « produire » n'existait pas.

Ce que ces tests figent :
- passe 4a → le job S'ARRÊTE en `awaiting_metier` et ne crée AUCUN cas ;
- le document corrigé par l'humain FAIT FOI (pas la proposition de l'IA) ;
- le Gherkin est écrit DEPUIS ce document (le prompt le porte, et lui seul) ;
- le métier se fige DANS la version, avec le technique (décision n°10) ;
- un titre ne porte jamais de préfixe de classement, une étape jamais de mot-clé Gherkin.
"""

import json

import pytest
from fastapi.testclient import TestClient

# ⚠️ Une connexion COMPLÈTE est requise depuis le 2026-07-24 : générer un cas fait observer
# l'application du projet (dry-run, smoke-check). Sans elle, la génération observait l'instance
# par défaut de la machine et écrivait un test taillé pour elle. Ces tests portent sur la pause
# métier, pas sur ce refus (couvert par `tests/test_cible_et_repli_silencieux.py`).
_PROJET_CONNECTE = {"name": "P", "base_url": "http://recette:8069", "database": "db",
                    "username": "qa", "password": "p"}

from testpilot import config
from testpilot.analysis.plan import ScenarioIntent, TestPlan
from testpilot.api import app as app_mod
from testpilot.api.services import generation_service
from testpilot.generation import metier_writer
from testpilot.generation.metier_writer import MetierDraft, propose_metier
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, VersionRepo, ensure_default_module


def _plan(spec="La spec complète du module."):
    return TestPlan(module_name="demande_materiel", models=[], scenarios=[
        ScenarioIntent(name="Nominal", type="nominal", action="a", persona="p",
                       preconditions=[], expected_outcome="ok", models_involved=[]),
    ], personas=["utilisateur"], portal_routes=[], risks=[], connector_type="odoo",
        cost_usd=0.0, raw_spec=spec)


class FakeLLM:
    """Rend un texte fixe pour `call_simple` (la passe métier n'utilise pas d'outil)."""

    def __init__(self, payload):
        self.payload = payload
        self.prompts: list[str] = []

    def call_simple(self, *, user_content="", **_):
        self.prompts.append(user_content)
        return self.payload


_BON_JSON = json.dumps({
    "title": "Réception et délivrance d'une commande",
    "preconditions": "Un utilisateur connecté disposant d'un catalogue.",
    "steps": ["Ouvrir le formulaire", "Saisir la raison", "Envoyer la demande"],
    "expected_result": "La demande est enregistrée et visible dans la liste.",
}, ensure_ascii=False)


# ── La passe métier elle-même ─────────────────────────────────────────────────

def test_propose_metier_rend_un_document_complet():
    draft = propose_metier(_plan(), llm=FakeLLM(_BON_JSON))

    assert draft.title == "Réception et délivrance d'une commande"
    assert draft.steps == ["Ouvrir le formulaire", "Saisir la raison", "Envoyer la demande"]
    assert draft.expected_result.startswith("La demande est enregistrée")
    assert draft.complete


def test_le_titre_ne_porte_JAMAIS_de_prefixe_de_classement():
    """⚠️ `[NOMINAL] …` est interdit (décision `0022` n°3) : un titre est une PHRASE MÉTIER, pas
    une case de classement. Le préfixe est un artefact du prompt « triptyque » d'avant — on le
    retire au lieu de faire confiance au modèle, qui le remet régulièrement.

    ⚠️ Ce nettoyage SURVIT au retrait du champ `angle` (migration 26), et c'est le point du test :
    plus rien ne demande d'angle au modèle, mais il en propose encore — il l'a appris ainsi."""
    payload = json.dumps({**json.loads(_BON_JSON), "title": "[NOMINAL] Création d'une demande"})

    draft = propose_metier(_plan(), llm=FakeLLM(payload))

    assert draft.title == "Création d'une demande"


def test_les_etapes_ne_portent_JAMAIS_de_mot_cle_gherkin():
    """Consigne du porteur : pas de Given/When/Then à l'écran. Une étape est une action lisible."""
    payload = json.dumps({**json.loads(_BON_JSON),
                          "steps": ["Étant donné que j'ouvre le formulaire",
                                    "Quand je saisis la raison",
                                    "3. Alors j'envoie"]})

    draft = propose_metier(_plan(), llm=FakeLLM(payload))

    assert draft.steps == ["j'ouvre le formulaire", "je saisis la raison", "j'envoie"]


def test_une_reponse_illisible_ne_FABRIQUE_aucun_contenu():
    """Un brouillon vide et signalé, jamais un titre plausible inventé.

    Inventer donnerait à un document non rédigé l'air d'être rédigé — le piège que l'arbitrage
    A.1 de la migration 14 a déjà refusé en ne dérivant pas le métier du Gherkin.
    """
    draft = propose_metier(_plan(), llm=FakeLLM("désolé, je ne peux pas"))

    assert draft.title == "" and draft.steps == [] and not draft.complete


def test_les_trois_champs_obligatoires_decident_de_la_completude():
    """Titre + étapes + résultat attendu (décision `0022` n°3.c) — préconditions facultatives."""
    assert not MetierDraft(title="T", steps=["a"]).complete          # pas de résultat
    assert not MetierDraft(title="T", expected_result="r").complete  # pas d'étape
    assert not MetierDraft(steps=["a"], expected_result="r").complete  # pas de titre
    assert MetierDraft(title="T", steps=["a"], expected_result="r").complete  # sans préconditions


# ── Le prompt de la passe 4b ──────────────────────────────────────────────────

def test_le_prompt_du_gherkin_porte_le_metier_et_ABANDONNE_les_scenarios_deduits():
    """Deux périmètres concurrents dans le même prompt, c'est le non-validé qui risque de gagner
    (il est plus détaillé). Le document signé par un humain doit être le SEUL."""
    from testpilot.generation import prompt as prompt_mod

    metier = {"title": "Réception d'une commande", "preconditions": "Utilisateur connecté",
              "steps": ["Ouvrir", "Envoyer"], "expected_result": "La demande est enregistrée."}

    msg = prompt_mod.build_initial_message(_plan(), None, metier)

    assert "Réception d'une commande" in msg
    assert "1. Ouvrir" in msg and "2. Envoyer" in msg
    assert "UN SEUL scénario" in msg
    assert "## Scénarios à couvrir" not in msg, "le périmètre déduit doit disparaître"


def test_sans_metier_le_prompt_reste_CELUI_D_AVANT():
    """Le chemin CLI et les cas legacy n'ont pas de passe métier : ils ne doivent rien perdre."""
    from testpilot.generation import prompt as prompt_mod

    msg = prompt_mod.build_initial_message(_plan(), None, None)

    assert "## Scénarios à couvrir" in msg


# ── La persistance : le métier se fige DANS la version ────────────────────────

def test_le_metier_valide_est_ecrit_DANS_la_version(tmp_path):
    """Décision `0022` n°10 : une version = LE CAS ENTIER, métier ET technique figés ensemble.

    C'est ce couple qui rend l'historique diffable et permet au gate d'approuver d'un seul geste.
    Échoue sur le code d'avant : `_persist` ne passait aucun champ métier.
    """
    from testpilot.generation.agent import GenerationAgent
    from testpilot.generation.state import GenerationResult

    conn = get_initialized_db(tmp_path / "p.db")
    mid = ensure_default_module(conn, "demande_materiel")
    agent = GenerationAgent(case_repo=CaseRepo(conn), version_repo=VersionRepo(conn))
    result = GenerationResult(success=True, module_name="demande_materiel", stopped_reason="done",
                              dry_run_passed=True, iterations=1, cost_usd=0.0,
                              feature_content="# feature", steps_content="# steps",
                              spec_hash="h1", awaiting_review=True)
    metier = {"title": "Réception d'une commande", "preconditions": "Utilisateur connecté",
              "steps": ["Ouvrir", "Envoyer"], "expected_result": "La demande est enregistrée."}

    agent._persist(_plan(), result, case_id=None, title="ignoré", author="ui",
                   module_id=mid, metier=metier)

    version = VersionRepo(conn).get(result.version_id)
    assert version["preconditions"] == "Utilisateur connecté"
    assert json.loads(version["test_steps"]) == ["Ouvrir", "Envoyer"]
    assert version["expected_result"] == "La demande est enregistrée."
    # Le titre du CAS vient du document validé, pas de l'argument d'appel.
    assert CaseRepo(conn).get(result.case_id)["title"] == "Réception d'une commande"
    conn.close()


def test_sans_metier_les_champs_restent_VIDES_et_non_des_listes_fabriquees(tmp_path):
    """`""` et non `"[]"` : « jamais rédigé » et « rédigé vide » ne sont pas le même fait, et
    c'est ce champ qui décide si l'écran montre le document ou son repli dérivé."""
    from testpilot.generation.agent import GenerationAgent
    from testpilot.generation.state import GenerationResult

    conn = get_initialized_db(tmp_path / "q.db")
    mid = ensure_default_module(conn, "demande_materiel")
    agent = GenerationAgent(case_repo=CaseRepo(conn), version_repo=VersionRepo(conn))
    result = GenerationResult(success=True, module_name="demande_materiel", stopped_reason="done",
                              dry_run_passed=True, iterations=1, cost_usd=0.0,
                              feature_content="# f", steps_content="# s", spec_hash="h",
                              awaiting_review=True)

    agent._persist(_plan(), result, case_id=None, title="Cas legacy", author="cli", module_id=mid)

    version = VersionRepo(conn).get(result.version_id)
    assert version["test_steps"] == ""
    assert version["preconditions"] == ""
    assert CaseRepo(conn).get(result.case_id)["title"] == "Cas legacy"
    conn.close()


# ── Le job : la PAUSE ─────────────────────────────────────────────────────────

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    return TestClient(app_mod.app)


@pytest.fixture
def stub_passe_metier(monkeypatch):
    """Neutralise analyse + LLM : on teste la MÉCANIQUE de pause, pas le modèle."""
    from testpilot.analysis import spec_analyzer as sa

    monkeypatch.setattr(sa.SpecAnalyzer, "analyze_spec_content",
                        lambda self, slug, content: _plan(content))
    monkeypatch.setattr(metier_writer, "LLMAdapter", lambda: FakeLLM(_BON_JSON))
    monkeypatch.setattr(metier_writer, "propose_metier",
                        lambda plan, **kw: propose_metier(plan, llm=FakeLLM(_BON_JSON)),
                        raising=False)


def test_la_passe_4a_S_ARRETE_et_ne_cree_AUCUN_cas(client, stub_passe_metier, monkeypatch):
    """⚠️ Le cœur de la décision : le job n'ira nulle part tant qu'un humain n'a pas signé.

    Et rien n'est persisté à ce stade — un cas qui n'aurait que son métier serait une coquille
    sans Gherkin, ce que `0006` refuse.
    """
    from testpilot.analysis import spec_analyzer as sa
    monkeypatch.setattr(sa.SpecAnalyzer, "analyze_spec_content",
                        lambda self, slug, content: _plan(content))
    monkeypatch.setattr(metier_writer, "propose_metier",
                        lambda plan, **kw: propose_metier(plan, llm=FakeLLM(_BON_JSON)))

    pid = client.post("/api/projects", json=_PROJET_CONNECTE).json()["id"]
    mid = client.post(f"/api/projects/{pid}/modules", json={"name": "M"}).json()["id"]

    job = client.post(f"/api/modules/{mid}/cases",
                      json={"spec_content": "La spec", "title": "T"}).json()

    state = client.get(f"/api/modules/jobs/{job['job_id']}").json()
    assert state["status"] == "awaiting_metier"
    assert state["metier"]["title"] == "Réception et délivrance d'une commande"
    assert state["metier"]["steps"] == ["Ouvrir le formulaire", "Saisir la raison",
                                        "Envoyer la demande"]
    assert state["case_id"] is None
    assert client.get(f"/api/cases?module_id={mid}").json()["items"] == [], "aucun cas avant validation"


def test_le_document_CORRIGE_par_l_humain_fait_foi(client, monkeypatch):
    """L'humain peut tout réécrire — c'est l'intérêt de la pause. Ce sont SES étapes qui partent
    à la génération, jamais celles que l'IA avait proposées."""
    from testpilot.analysis import spec_analyzer as sa
    monkeypatch.setattr(sa.SpecAnalyzer, "analyze_spec_content",
                        lambda self, slug, content: _plan(content))
    monkeypatch.setattr(metier_writer, "propose_metier",
                        lambda plan, **kw: propose_metier(plan, llm=FakeLLM(_BON_JSON)))
    recu = {}
    monkeypatch.setattr(generation_service, "resume_generation",
                        lambda job_id, **kw: recu.update(kw))

    pid = client.post("/api/projects", json=_PROJET_CONNECTE).json()["id"]
    mid = client.post(f"/api/projects/{pid}/modules", json={"name": "M"}).json()["id"]
    job_id = client.post(f"/api/modules/{mid}/cases",
                         json={"spec_content": "La spec", "title": "T"}).json()["job_id"]

    r = client.post(f"/api/modules/jobs/{job_id}/metier", json={
        "title": "MON titre à moi",
        "preconditions": "Mon contexte",
        "steps": ["Mon étape unique"],
        "expected_result": "Mon verdict",
    })

    assert r.status_code == 202
    assert recu["metier"]["title"] == "MON titre à moi"
    assert recu["metier"]["steps"] == ["Mon étape unique"]


def test_un_metier_incomplet_est_REFUSE(client, monkeypatch):
    from testpilot.analysis import spec_analyzer as sa
    monkeypatch.setattr(sa.SpecAnalyzer, "analyze_spec_content",
                        lambda self, slug, content: _plan(content))
    monkeypatch.setattr(metier_writer, "propose_metier",
                        lambda plan, **kw: propose_metier(plan, llm=FakeLLM(_BON_JSON)))

    pid = client.post("/api/projects", json=_PROJET_CONNECTE).json()["id"]
    mid = client.post(f"/api/projects/{pid}/modules", json={"name": "M"}).json()["id"]
    job_id = client.post(f"/api/modules/{mid}/cases",
                         json={"spec_content": "La spec", "title": "T"}).json()["job_id"]

    r = client.post(f"/api/modules/jobs/{job_id}/metier", json={
        "title": "Un titre", "steps": [], "expected_result": "Un verdict"})

    assert r.status_code == 422
    assert "obligatoires" in r.json()["detail"]


def test_valider_deux_fois_est_REFUSE(client, monkeypatch):
    """Le second appel relancerait une génération payante sur un job déjà reparti."""
    from testpilot.analysis import spec_analyzer as sa
    monkeypatch.setattr(sa.SpecAnalyzer, "analyze_spec_content",
                        lambda self, slug, content: _plan(content))
    monkeypatch.setattr(metier_writer, "propose_metier",
                        lambda plan, **kw: propose_metier(plan, llm=FakeLLM(_BON_JSON)))
    monkeypatch.setattr(generation_service, "resume_generation", lambda job_id, **kw: None)

    pid = client.post("/api/projects", json=_PROJET_CONNECTE).json()["id"]
    mid = client.post(f"/api/projects/{pid}/modules", json={"name": "M"}).json()["id"]
    job_id = client.post(f"/api/modules/{mid}/cases",
                         json={"spec_content": "La spec", "title": "T"}).json()["job_id"]
    body = {"title": "T", "steps": ["a"], "expected_result": "r"}
    client.post(f"/api/modules/jobs/{job_id}/metier", json=body)

    r = client.post(f"/api/modules/jobs/{job_id}/metier", json=body)

    assert r.status_code == 409


def test_un_document_incomplet_fait_ECHOUER_le_job_sans_creer_de_cas(client, monkeypatch):
    from testpilot.analysis import spec_analyzer as sa
    monkeypatch.setattr(sa.SpecAnalyzer, "analyze_spec_content",
                        lambda self, slug, content: _plan(content))
    monkeypatch.setattr(metier_writer, "propose_metier",
                        lambda plan, **kw: MetierDraft())

    pid = client.post("/api/projects", json=_PROJET_CONNECTE).json()["id"]
    mid = client.post(f"/api/projects/{pid}/modules", json={"name": "M"}).json()["id"]
    job_id = client.post(f"/api/modules/{mid}/cases",
                         json={"spec_content": "La spec", "title": "T"}).json()["job_id"]

    state = client.get(f"/api/modules/jobs/{job_id}").json()
    assert state["status"] == "failed"
    assert "incomplet" in state["error"]
    assert client.get(f"/api/cases?module_id={mid}").json()["items"] == []
