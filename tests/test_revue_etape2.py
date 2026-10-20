"""Revue de l'étape 2 du plan unique (2026-10-20), première passe — les points « à corriger » et leurs gardes.

C1 : l'âge des preuves se mesure à la version qui les a APPORTÉES (une régénération du même test avec de nouvelles preuves).
C2 : un cadre illisible n'efface pas les champs de la page.
C3 : l'IA sait qu'un champ est dans un cadre ; les options d'un cadre ne valent pas pour la page.
C5 : « Débloquer » n'est proposé que si une approbation peut débloquer (pas en cas d'écart A42).
Gravité : la liste « Cas bloqués » montre la raison la plus grave d'abord.
Règle : le Contexte de la fonctionnalité vaut aussi dans ses règles.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from testpilot.api.services import generation_service as service
from testpilot.connectors._web_helpers import PlaywrightError, extract_form
from testpilot.generation.evidence import contextual_warnings
from testpilot.verdict import review_gate
from testpilot.verdict.review_gate import GateDecision

MAINTENANT = datetime.now(timezone.utc)


def test_falsifiable_les_preuves_se_datent_a_la_version_qui_les_a_apportees():
    hier = {"id": 1, "created_at": (MAINTENANT - timedelta(days=3)).isoformat(), "observation_evidence": "[1]"}
    copie = {"id": 2, "created_at": (MAINTENANT - timedelta(days=1)).isoformat(), "observation_evidence": "[1]"}
    regeneree = {"id": 3, "created_at": MAINTENANT.isoformat(), "observation_evidence": "[2]"}
    assert service._apport_des_preuves([hier, copie], copie) is hier, "une copie recopie les preuves"
    assert service._apport_des_preuves([hier, copie, regeneree], regeneree) is regeneree, "nouvelles preuves : aujourd'hui"


def test_falsifiable_une_regeneration_du_meme_test_n_a_pas_de_fausse_alerte(tmp_path, monkeypatch):
    """Revue C1, reproduit : même Gherkin et mêmes steps que la veille, preuves relevées aujourd'hui."""
    from testpilot.generation.provenance import target_fingerprint

    projet = {"id": 3, "base_url": "http://127.0.0.1:8095", "connector_type": "web"}

    class _Projets:
        def __init__(self, conn):
            pass

        def get(self, _id):
            return projet

    monkeypatch.setattr("testpilot.store.repositories.ProjectRepo", _Projets)
    monkeypatch.setattr("testpilot.generation.domain_model.charger_modele", lambda p: None)
    feature = ('# language: fr\nFonctionnalité: F\n  Scénario: S\n    Soit j\'ouvre la page "/acces"\n'
               '    Quand je renseigne le champ "age" avec la valeur "17"\n')
    preuve = {"source": "ui", "resource": "http://127.0.0.1:8095/acces", "observed_at": MAINTENANT.isoformat(),
              "target_sha256": target_fingerprint(projet), "fields": [{"name": "age", "visible": True}]}
    commun = {"title": "Accès", "steps_content": "", "created_by": "ia", "feature_content": feature}
    veille = {**commun, "id": 1, "created_at": (MAINTENANT - timedelta(days=1)).isoformat(), "observation_evidence": "[]"}
    du_jour = {**commun, "id": 2, "created_at": MAINTENANT.isoformat(), "observation_evidence": json.dumps([preuve])}
    from testpilot import config
    from testpilot.store.db import get_initialized_db
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "c1.db")
    conn = get_initialized_db()
    avis = [w["kind"] for w in service.lint_warnings_for_version(conn, {"project_id": 3, "title": "Accès"},
                                                                  [veille, du_jour], 2)]
    conn.close()
    assert "champ_ui_non_verifie" not in avis


class _El:
    def __init__(self, **a):
        self.a = a

    def get_attribute(self, n):
        return self.a.get(n)


class _Doc:
    def __init__(self, noms):
        self.noms = noms

    def query_selector_all(self, _s):
        return [_El(name=n) for n in self.noms]

    def query_selector(self, _s):
        return None


class _CadreDetache(_Doc):
    def __init__(self, parent):
        super().__init__([])
        self.parent_frame = parent

    def frame_element(self):
        return _El(name="pub")

    def query_selector_all(self, _s):
        raise PlaywrightError("Frame was detached")


def test_falsifiable_un_cadre_detache_n_efface_pas_les_champs_de_la_page():
    page = _Doc(["email"])
    page.main_frame = object()
    page.frames = [page.main_frame, _CadreDetache(page.main_frame)]
    page.url = "http://h/p"
    assert [f["name"] for f in extract_form(page)["fields"]] == ["email"]


def test_l_ia_sait_qu_un_champ_est_dans_un_cadre_et_ses_options_ne_valent_pas_pour_la_page(tmp_path):
    from testpilot.generation.tools import ToolContext
    from testpilot.generation.tools.inspect import inspect_page_form

    class _Connecteur:
        def inspect_form(self, url):
            return {"url": url, "fields": [
                {"name": "pays", "tag": "select", "options": [["fr", "France"]], "required": True},
                {"name": "pays", "tag": "select", "options": [["xx", "Pub"]], "cadre": ["pub"], "required": True}],
                "sonde": {"selects": {"pays": {"independant": True}}}}

    ctx = ToolContext("m", tmp_path, connector=_Connecteur())
    sortie = inspect_page_form(ctx, "http://h/form")
    assert "pays (cadre « pub »)" in sortie.observation
    assert ctx.options_select["pays"] == {"fr", "France"}, "les options du cadre n'élargissent pas celles de la page"


def test_falsifiable_debloquer_n_est_propose_que_si_une_approbation_peut_debloquer(tmp_path, monkeypatch):
    from testpilot import config
    from testpilot.api.services import run_service
    from testpilot.store.db import get_initialized_db
    from testpilot.store.repositories import CaseRepo, ReviewRepo, VersionRepo, ensure_default_module

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "c5.db")
    conn = get_initialized_db()
    cid = CaseRepo(conn).create(title="A", module_id=ensure_default_module(conn, "a"), feature_slug="a")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="", title="A", steps_content="",
                                   feature_content="# language: fr\nFonctionnalité: F\n  Scénario: S\n    Alors x\n")
    CaseRepo(conn).set_current_version(cid, vid)
    cas = CaseRepo(conn).get(cid)
    assert run_service.blocage_du_cas(conn, cas, vid, avis=[])[2] is True, "non approuvée : une approbation débloque"
    ReviewRepo(conn).create(test_case_id=cid, version_id=vid, decision="approved", reviewer="porteur")
    monkeypatch.setattr(run_service, "ecarts_cas_test", lambda *a, **k: ["age"])
    decision, _, debloquable = run_service.blocage_du_cas(conn, cas, vid, avis=[])
    assert not decision.allowed and debloquable is False, "écart A42 : l'approbation serait refusée (409)"
    conn.close()


def test_la_raison_la_plus_grave_vient_d_abord():
    decision = GateDecision(allowed=False, needs_review=True, reason="r")
    raisons = review_gate.raisons_du_blocage(decision, approuvee=False, rejetee=False, ecarts=[], avis=[
        {"kind": "champ_ui_non_verifie"}, {"kind": "verification_changee_apres_defaut"}])
    assert raisons[0] == review_gate.RAISONS_DES_AVIS["verification_changee_apres_defaut"]


def test_falsifiable_le_contexte_de_la_fonctionnalite_vaut_dans_ses_regles():
    feature = ("# language: fr\nFonctionnalité: F\n  Contexte:\n    Soit j'ouvre la page \"/clients\"\n"
               "  Règle: R\n    Scénario: S\n      Quand je renseigne le champ \"age\" avec la valeur \"17\"\n")
    preuve = {"source": "ui", "resource": "http://127.0.0.1:8095/acces", "observed_at": MAINTENANT.isoformat(),
              "target_sha256": "c1", "fields": [{"name": "age", "visible": True}]}
    avis = contextual_warnings(feature, [preuve], target_sha256="c1", base_url="http://127.0.0.1:8095")
    assert [a["line"] for a in avis] == [7], "la page du Contexte (/clients) vaut dans la règle : champ vu ailleurs"
