"""Amendement §4.3-bis (2026-09-15) — la validation métier ne vaut relecture QUE si le cas sort
« propre » de la génération (aucun point de vigilance).

⚠️ **Le bug réel qui motive ce resserrement.** §4.3 approuvait TOUJOURS une version produite
depuis un métier validé — même avec de vrais points de vigilance (0008/0017/0021) — au motif que
la validation métier valait relecture. Mais AUCUN écran ne montre les cas restés `needs_review` :
un cas approuvé à tort ne posait pas de problème visible, mais un cas resté à relire sans qu'aucun
écran ne le signale reste bloqué **à vie** (cas 82, 2026-09-15) dès qu'il n'est jamais retouché
manuellement (ce qui aurait ré-approuvé via `PATCH .../metier`). Puisqu'approuver systématiquement
ne protégeait de toute façon personne (les signaux n'étaient jamais lus), le critère devient : un
cas SANS aucun point de vigilance est digne de confiance sans relecture ; un cas AVEC un point de
vigilance reste bloqué, mais pour de vrai — un humain doit encore pouvoir le trouver (chantier
séparé, une liste dédiée), ce que ce fichier ne couvre pas.
"""

import json

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import app as app_mod
from testpilot.api.services import generation_service
from testpilot.generation import domain_model
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import (
    CaseRepo,
    ModuleRepo,
    ProjectRepo,
    ReviewRepo,
    VersionRepo,
    ensure_default_module,
)
from testpilot.verdict import review_gate

_STEPS_PROPRES = 'from behave import when\n\n\n@when("j\'agis")\ndef step(context):\n    pass\n'
# Motif exact de la décision 0008 (`test_assertion_lint.py`) : une assertion infalsifiable.
_STEPS_TAUTOLOGIQUES = (
    'from behave import then\n\n\n@then("truc")\ndef s(context):\n    assert True\n')


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    c = get_initialized_db(tmp_path / "a.db")
    yield c
    c.close()


def _cas_avec_version(conn, *, steps_content: str, feature_content: str = "# f") -> tuple[int, int]:
    mid = ensure_default_module(conn, "m")
    cid = CaseRepo(conn).create(title="C", module_id=mid, feature_slug="c")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="h",
                                   feature_content=feature_content, steps_content=steps_content)
    CaseRepo(conn).set_current_version(cid, vid)
    return cid, vid


# ── `lint_warnings_for_version` — le point de calcul partagé (route ET auto-approbation) ────────

def test_lint_warnings_for_version_vide_quand_rien_a_signaler(conn):
    cid, vid = _cas_avec_version(conn, steps_content=_STEPS_PROPRES)
    case = CaseRepo(conn).get(cid)

    warnings = generation_service.lint_warnings_for_version(
        conn, case, VersionRepo(conn).list_for_case(cid), vid)

    assert warnings == []


def test_lint_warnings_for_version_remonte_une_assertion_infalsifiable(conn):
    """0008 : le MÊME contrôle que celui affiché sur la fiche du cas (`test_assertion_lint.py`)."""
    cid, vid = _cas_avec_version(conn, steps_content=_STEPS_TAUTOLOGIQUES)
    case = CaseRepo(conn).get(cid)

    warnings = generation_service.lint_warnings_for_version(
        conn, case, VersionRepo(conn).list_for_case(cid), vid)

    assert any(w["kind"] == "always_true_constant" for w in warnings)


def test_lint_warnings_for_version_rend_vide_sans_version_courante(conn):
    """Un cas sans version (`version_id=None` jamais atteint ici, mais version introuvable dans
    `version_rows`) ne doit rien fabriquer — silence, pas erreur."""
    mid = ensure_default_module(conn, "m")
    cid = CaseRepo(conn).create(title="C", module_id=mid, feature_slug="c")
    case = CaseRepo(conn).get(cid)

    warnings = generation_service.lint_warnings_for_version(conn, case, [], 999)

    assert warnings == []


# ── `_auto_approuver_si_propre` — le nouveau critère d'approbation automatique ──────────────────

def test_auto_approuver_si_propre_approuve_un_cas_sans_avertissement(conn):
    cid, vid = _cas_avec_version(conn, steps_content=_STEPS_PROPRES)
    assert review_gate.evaluate_gate(ReviewRepo(conn), vid).allowed is False

    generation_service._auto_approuver_si_propre(conn, cid, vid)

    decision = review_gate.evaluate_gate(ReviewRepo(conn), vid)
    assert decision.allowed is True
    assert ReviewRepo(conn).latest_for_version(vid)["reviewer"] == "validation-metier"


def test_auto_approuver_si_propre_laisse_a_relire_un_cas_avec_point_de_vigilance(conn):
    """🔴 Le test du resserrement : AVANT §4.3-bis, ce cas aurait été approuvé quand même — c'est
    exactement le bug (un cas jamais retouché reste ensuite bloqué à vie, sans qu'aucun écran ne
    le montre). APRÈS, il reste `needs_review`, et surtout, on peut désormais TOMBER dessus depuis
    la fiche du cas (mêmes lint_warnings que la route)."""
    cid, vid = _cas_avec_version(conn, steps_content=_STEPS_TAUTOLOGIQUES)

    generation_service._auto_approuver_si_propre(conn, cid, vid)

    decision = review_gate.evaluate_gate(ReviewRepo(conn), vid)
    assert decision.allowed is False
    assert decision.needs_review is True
    assert ReviewRepo(conn).latest_for_version(vid) is None, "aucune approbation n'a été tracée"


def test_auto_approuver_si_propre_ignore_un_cas_sans_version(conn):
    """`version_id=None` (génération arrêtée avant persistance) : rien à approuver, rien ne
    plante."""
    generation_service._auto_approuver_si_propre(conn, case_id=999, version_id=None)


# ── Bout en bout via `run_automation` — la même politique s'applique au cas manuel automatisé ──

def _cas_manuel(conn):
    mid = ensure_default_module(conn, "m")
    cid = CaseRepo(conn).create_manual(
        module_id=mid, title="Connexion valide", preconditions="Un compte existe.",
        test_steps=json.dumps(["Ouvrir la page", "Valider"]),
        expected_result="Accès au tableau de bord.")
    return cid


def _neutraliser_generation(monkeypatch, *, feature_content: str, steps_content: str):
    """Même neutralisation que `test_automatisation_cas_manuel.py` : pas de LLM, pas de vrai
    navigateur — seul le contenu produit (feature/steps) varie d'un test à l'autre ici."""
    from testpilot.analysis import spec_analyzer as sa
    from testpilot.analysis.plan import TestPlan
    from testpilot.generation import agent as agent_mod
    from testpilot.generation.state import GenerationResult
    from testpilot.store.repositories import VersionRepo as VR

    monkeypatch.setattr(sa.SpecAnalyzer, "analyze_spec_content",
                        lambda self, slug, content: TestPlan(
                            module_name=slug, models=[], scenarios=[], personas=["u"],
                            portal_routes=[], risks=[], connector_type="odoo", cost_usd=0.0,
                            raw_spec=content))

    def faux_generate(self, plan, *, case_id=None, metier=None, author="", projet=None, **kw):
        vid = VR(self.case_repo.conn).create(
            test_case_id=case_id, spec_content="", spec_hash="h",
            feature_content=feature_content, steps_content=steps_content,
            change_summary="Automatisation", title=metier["title"],
            preconditions=metier["preconditions"],
            test_steps=json.dumps(metier["steps"]), expected_result=metier["expected_result"])
        self.case_repo.set_current_version(case_id, vid)
        r = GenerationResult(success=True, module_name=plan.module_name, stopped_reason="done",
                             dry_run_passed=True, iterations=1, cost_usd=0.05,
                             feature_content=feature_content, steps_content=steps_content,
                             spec_hash="h", awaiting_review=True)
        r.case_id = case_id
        r.version_id = vid
        return r
    monkeypatch.setattr(agent_mod.GenerationAgent, "generate", faux_generate)
    monkeypatch.setattr("testpilot.connectors.odoo.OdooConnector.from_project",
                        lambda project: type("C", (), {"connect": lambda s: None,
                                                       "disconnect": lambda s: None})())
    monkeypatch.setattr("testpilot.execution.behave_runner.BehaveRunner",
                        lambda **kw: object())


def test_run_automation_approuve_un_cas_propre(conn, monkeypatch):
    cid = _cas_manuel(conn)
    _neutraliser_generation(monkeypatch, feature_content="# f", steps_content=_STEPS_PROPRES)
    monkeypatch.setattr(config, "DB_PATH", conn.execute("PRAGMA database_list").fetchone()[2])

    job_id, params = generation_service.start_automation(conn, cid)
    generation_service.run_automation(job_id, **params)

    conn2 = get_initialized_db(config.DB_PATH)
    vid = CaseRepo(conn2).get(cid)["current_version_id"]
    assert review_gate.evaluate_gate(ReviewRepo(conn2), vid).allowed is True
    conn2.close()


def test_run_automation_n_approuve_plus_un_cas_avec_point_de_vigilance(conn, monkeypatch):
    """Régression du resserrement §4.3-bis sur le chemin RÉEL (cas manuel automatisé) : avant ce
    correctif, ce cas aurait été approuvé malgré son assertion infalsifiable."""
    cid = _cas_manuel(conn)
    _neutraliser_generation(monkeypatch, feature_content="# f",
                            steps_content=_STEPS_TAUTOLOGIQUES)
    monkeypatch.setattr(config, "DB_PATH", conn.execute("PRAGMA database_list").fetchone()[2])

    job_id, params = generation_service.start_automation(conn, cid)
    generation_service.run_automation(job_id, **params)

    conn2 = get_initialized_db(config.DB_PATH)
    vid = CaseRepo(conn2).get(cid)["current_version_id"]
    decision = review_gate.evaluate_gate(ReviewRepo(conn2), vid)
    assert decision.allowed is False
    assert decision.needs_review is True
    conn2.close()


# ── Le smoke-check (0021) compte aussi comme point de vigilance à la génération ─────────────────

_MODELE = {
    "connector_type": "odoo",
    "mesure_le": "2026-09-15",
    "pages": {"/formulaire/{id}": {"champs": [
        {"name": "types_demandes", "tag": "select", "options": [
            ["nouvel_entrant", "Demande de nouvel entrant"]]},
    ]}},
}
_FEATURE_VALEUR_INVENTEE = (
    'Fonctionnalité: Demande\n'
    '  Scénario: [NOMINAL] Demande\n'
    '    Et le champ demande "types_demandes" est rempli avec "new"\n')


@pytest.fixture
def modele_en_place(tmp_path, monkeypatch):
    dossier = tmp_path / "domain"
    dossier.mkdir()
    (dossier / "odoo.json").write_text(json.dumps(_MODELE, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(domain_model, "DOMAIN_DIR", dossier)
    domain_model._charger.cache_clear()
    yield dossier
    domain_model._charger.cache_clear()


def test_auto_approuver_si_propre_laisse_a_relire_une_valeur_inventee(conn, modele_en_place):
    """0021 : un champ/valeur qui n'existe pas dans le domaine mesuré bloque aussi l'approbation
    automatique — pas seulement une assertion infalsifiable (0008)."""
    pid = ProjectRepo(conn).create(name="P", connector_type="odoo")
    mid = ModuleRepo(conn).create(project_id=pid, name="Demande", description="")
    cid = CaseRepo(conn).create(title="C", module_id=mid, feature_slug="c")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="h",
                                   feature_content=_FEATURE_VALEUR_INVENTEE,
                                   steps_content=_STEPS_PROPRES)
    CaseRepo(conn).set_current_version(cid, vid)

    generation_service._auto_approuver_si_propre(conn, cid, vid)

    assert review_gate.evaluate_gate(ReviewRepo(conn), vid).allowed is False


# ── `GET /api/cases/needing-review` — la liste qui rend un cas bloqué TROUVABLE ──────────────────
#
# ⚠️ C'est la seconde moitié explicitement demandée avec le resserrement : « il faudrait alors un
# vrai écran/liste pour les retrouver ». Sans elle, resserrer l'approbation automatique aurait
# juste déplacé le bug (un cas bloqué invisible) plutôt que de le corriger.

@pytest.fixture
def client(tmp_path, monkeypatch):
    from testpilot.api.deps import get_conn

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    c = get_initialized_db(config.DB_PATH)
    app_mod.app.dependency_overrides[get_conn] = lambda: c
    yield TestClient(app_mod.app)
    app_mod.app.dependency_overrides.clear()
    c.close()


def test_needing_review_liste_un_cas_avec_point_de_vigilance(client):
    from testpilot.api.deps import get_conn
    conn = app_mod.app.dependency_overrides[get_conn]()

    pid = ProjectRepo(conn).create(name="P")
    mid = ModuleRepo(conn).create(project_id=pid, name="M", description="")
    cid = CaseRepo(conn).create(title="À relire", module_id=mid, feature_slug="a-relire")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="h",
                                   feature_content="# f", steps_content=_STEPS_TAUTOLOGIQUES)
    CaseRepo(conn).set_current_version(cid, vid)

    r = client.get(f"/api/cases/needing-review?project_id={pid}")

    assert r.status_code == 200
    corps = r.json()
    assert any(c["case_id"] == cid for c in corps)
    ligne = next(c for c in corps if c["case_id"] == cid)
    assert ligne["version_id"] == vid
    assert ligne["lint_warnings_count"] >= 1
    assert ligne["reason"]


def test_needing_review_omet_un_cas_approuve(client):
    from testpilot.api.deps import get_conn
    conn = app_mod.app.dependency_overrides[get_conn]()

    pid = ProjectRepo(conn).create(name="P")
    mid = ModuleRepo(conn).create(project_id=pid, name="M", description="")
    cid = CaseRepo(conn).create(title="Propre", module_id=mid, feature_slug="propre")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="h",
                                   feature_content="# f", steps_content=_STEPS_PROPRES)
    CaseRepo(conn).set_current_version(cid, vid)
    generation_service._auto_approuver_si_propre(conn, cid, vid)

    corps = client.get(f"/api/cases/needing-review?project_id={pid}").json()

    assert all(c["case_id"] != cid for c in corps)


def test_needing_review_omet_un_cas_manuel_jamais_automatise(client):
    """Un cas manuel sans `current_version_id` n'a jamais été soumis au gate — il n'a rien à
    approuver, il n'appartient donc pas à cette liste (sinon TOUT cas manuel y apparaîtrait)."""
    from testpilot.api.deps import get_conn
    conn = app_mod.app.dependency_overrides[get_conn]()

    pid = ProjectRepo(conn).create(name="P")
    mid = ModuleRepo(conn).create(project_id=pid, name="M", description="")
    CaseRepo(conn).create_manual(module_id=mid, title="Manuel", preconditions="",
                                test_steps=json.dumps(["a"]), expected_result="r")

    corps = client.get(f"/api/cases/needing-review?project_id={pid}").json()

    assert corps == []


def test_needing_review_projet_inconnu_404(client):
    assert client.get("/api/cases/needing-review?project_id=999").status_code == 404
