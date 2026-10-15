"""F26(b) à travers la porte humaine : les deux champs de dépendance inter-cas survivent à l'API.

Bug mesuré le 2026-10-15 en cartographiant la chaîne « spécification → cas métier » :
`propose_metier` produit `depend_dun_autre_cas_du_groupe` / `etat_a_creer_par_ce_cas`,
`run_generation` les range dans le job — mais `MetierDraftOut` (GET du job) et `CaseValidationIn`
(POST de validation) ne les déclaraient pas. Pydantic les écartait sans bruit
(`extra="ignore"`) : l'écran ne les recevait jamais, ne pouvait donc pas les renvoyer, et
`validate_metier` retombait TOUJOURS sur `False` / `""`. Résultat : la garde de
`write_feature_file` (`ctx.depend_dun_autre_cas_du_groupe`, tools/write.py) n'était jamais armée
sur le chemin réel de l'application — elle ne l'était que dans les tests qui appellent l'agent
directement.

Ces tests passent par les VRAIES routes (GET puis POST, comme l'écran) et par le VRAI
`resume_generation` jusqu'à `_persist` ; seuls l'analyse, le découpage, la passe métier (LLM),
le connecteur et la boucle ReAct sont neutralisés. Ils échouent sur le code d'avant : le GET
n'expose pas les clés, et la version persistée porte `0` / `""`.
"""

import json

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.analysis.plan import TestPlan
from testpilot.api import app as app_mod
from testpilot.generation import agent as agent_mod
from testpilot.generation import decoupage, metier_writer
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, GenerationJobRepo, VersionRepo

_PROJET_CONNECTE = {"name": "P", "connector_type": "odoo", "base_url": "http://recette:8069",
                    "database": "db", "username": "qa", "password": "p"}

# Une action de création PROPRE au cas, nettement distincte de la précondition : elle passe le
# contrôle déterministe `verifier_dependance_inter_cas` (sinon le job échouerait dès la passe 4a).
_ETAT = "Créer un équipement avec une référence unique avant de l'affecter."
_PRECONDITION = "Un équipement existe déjà, créé par le cas précédent du groupe."


def _plan(spec="La spec.") -> TestPlan:
    return TestPlan(module_name="m", models=[], scenarios=[], personas=["u"], portal_routes=[],
                    risks=[], connector_type="odoo", cost_usd=0.0, raw_spec=spec)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return TestClient(app_mod.app)


def _neutraliser(monkeypatch, *, depend: bool, etat: str):
    """Neutralise tout ce qui appelle un LLM ou une application — garde les routes,
    `validate_metier`, `resume_generation` et `_persist` réels."""
    from testpilot.analysis import spec_analyzer as sa

    monkeypatch.setattr(sa.SpecAnalyzer, "analyze_spec_content",
                        lambda self, slug, content: _plan(content))
    monkeypatch.setattr(decoupage, "propose_decoupage", lambda plan, **kw: [
        decoupage.StoryPlan(user_story="Affectation",
                            cases=[decoupage.CaseBrief(title="Affecter", brief="Affecter")])])
    monkeypatch.setattr(metier_writer, "propose_metier",
                        lambda plan, **kw: metier_writer.MetierDraft(
                            title="Affecter un équipement", preconditions=_PRECONDITION,
                            steps=["Ouvrir l'équipement", "L'affecter à un employé"],
                            expected_result="L'équipement est affecté.",
                            depend_dun_autre_cas_du_groupe=depend,
                            etat_a_creer_par_ce_cas=etat))

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
                                  cost_usd=0.0, feature_content="# f", steps_content="# s",
                                  spec_hash="h", awaiting_review=True)
        reel_persist(self, plan, result, case_id=case_id, title=title, author=author,
                     module_id=module_id, metier=metier, group_id=group_id, refs=refs)
        return result

    monkeypatch.setattr(agent_mod.GenerationAgent, "generate", faux_generate)


def _job_en_attente(client) -> tuple[int, str]:
    pid = client.post("/api/projects", json=_PROJET_CONNECTE).json()["id"]
    mid = client.post(f"/api/projects/{pid}/modules", json={"name": "M"}).json()["id"]
    job_id = client.post(f"/api/modules/{mid}/cases",
                         json={"spec_content": "La spec", "title": "T"}).json()["job_id"]
    return mid, job_id


def _version_persistee(mid: int) -> dict:
    conn = get_initialized_db(config.DB_PATH)
    try:
        (cas,) = CaseRepo(conn).list_all(module_id=mid)
        return VersionRepo(conn).get(cas["current_version_id"])
    finally:
        conn.close()


def test_les_champs_de_dependance_traversent_la_porte_humaine_jusqu_a_la_version(
        client, monkeypatch):
    """Aller-retour complet, comme l'écran : GET → renvoi tel quel (`{...c}`) → POST → version."""
    _neutraliser(monkeypatch, depend=True, etat=_ETAT)
    mid, job_id = _job_en_attente(client)

    # 1. Le GET expose les deux champs (avant : clés absentes, écartées par `MetierDraftOut`).
    etat_job = client.get(f"/api/modules/jobs/{job_id}").json()
    assert etat_job["status"] == "awaiting_metier"
    (propose,) = etat_job["cases"]
    assert propose["depend_dun_autre_cas_du_groupe"] is True
    assert propose["etat_a_creer_par_ce_cas"] == _ETAT

    # 2. Le POST de validation, avec ce que l'écran a reçu renvoyé tel quel.
    r = client.post(f"/api/modules/jobs/{job_id}/metier", json={"cases": [propose]})
    assert r.status_code == 202

    # 3. Le job garde ce que l'humain a validé — c'est ce contenu qui part à la reprise.
    conn = get_initialized_db(config.DB_PATH)
    try:
        (valide,) = GenerationJobRepo(conn).get(job_id)["cases"]
    finally:
        conn.close()
    assert valide["depend_dun_autre_cas_du_groupe"] is True
    assert valide["etat_a_creer_par_ce_cas"] == _ETAT

    # 4. La version persistée par la reprise réelle porte les deux champs (avant : 0 / "").
    version = _version_persistee(mid)
    assert bool(version["depend_dun_autre_cas_du_groupe"]) is True
    assert version["etat_a_creer_par_ce_cas"] == _ETAT


def test_un_cas_independant_reste_independant_apres_la_porte(client, monkeypatch):
    """Contre-essai : la porte ne FABRIQUE pas de dépendance. Un cas que l'IA a déclaré
    indépendant reste `False` / `""` de bout en bout — sinon la garde de `write_feature_file`
    s'armerait à tort et refuserait des références légitimes."""
    _neutraliser(monkeypatch, depend=False, etat="")
    mid, job_id = _job_en_attente(client)

    (propose,) = client.get(f"/api/modules/jobs/{job_id}").json()["cases"]
    assert propose["depend_dun_autre_cas_du_groupe"] is False
    assert propose["etat_a_creer_par_ce_cas"] == ""
    assert client.post(f"/api/modules/jobs/{job_id}/metier",
                       json={"cases": [propose]}).status_code == 202

    version = _version_persistee(mid)
    assert bool(version["depend_dun_autre_cas_du_groupe"]) is False
    assert version["etat_a_creer_par_ce_cas"] == ""


def test_un_client_qui_omet_les_champs_n_est_pas_refuse(client, monkeypatch):
    """Compatibilité : un appel direct à l'API (ou un écran plus ancien) qui n'envoie pas ces
    champs reste accepté — ils retombent sur `False` / `""`, comme avant la migration 58."""
    _neutraliser(monkeypatch, depend=False, etat="")
    mid, job_id = _job_en_attente(client)

    r = client.post(f"/api/modules/jobs/{job_id}/metier", json={"cases": [
        {"title": "T", "steps": ["a"], "expected_result": "r"}]})

    assert r.status_code == 202
    version = _version_persistee(mid)
    assert bool(version["depend_dun_autre_cas_du_groupe"]) is False
    assert version["etat_a_creer_par_ce_cas"] == ""
    assert json.loads(version["test_steps"]) == ["a"]
