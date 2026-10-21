"""Étape 4, morceau 7, partie A (A85-A88, porteur 2026-10-21) : l'IA écrit le test avec les écrans du compte du cas.

Ce que ces tests gardent :
1. interrupteur `TESTPILOT_GENERATION_PAR_COMPTE` éteint, ou cas joué avec le principal : RIEN ne change — même modèle (l'annexe
   des comptes n'est même pas lue), même message à l'IA, même empreinte de cible ;
2. allumé : l'IA reçoit les écrans du compte (ce qu'il voit, pas ce que voit le principal), le message nomme le compte (jamais
   son identifiant), l'essai et l'observation se font avec lui ; un compte en « connexion impossible » est refusé AVANT tout
   appel à l'IA ; un compte pas encore exploré : écrit avec le principal, et la fiche le dit (A85) ;
3. un test écrit pour un compte puis joué avec un autre est bloqué, interrupteur éteint compris (A86-A88) ; une version
   d'avant le morceau 7 est réputée écrite pour le principal (A87) ;
4. la relecture (points de vigilance, correction, réparation) se fait avec les écrans de l'ÉCRITURE.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from testpilot import config
from testpilot.analysis.plan import TestPlan
from testpilot.api.services import exploration_service as es
from testpilot.api.services import modele_du_cas as mdc
from testpilot.generation import domain_model, interrupteurs
from testpilot.generation import prompt as prompt_mod
from testpilot.generation.provenance import target_fingerprint


@pytest.fixture(autouse=True)
def isole(tmp_path, monkeypatch):
    d = tmp_path / "domain"
    d.mkdir()
    monkeypatch.setattr(domain_model, "DOMAIN_DIR", d)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "par_compte.db")
    monkeypatch.delenv(interrupteurs.ENV_GENERATION_PAR_COMPTE, raising=False)
    domain_model._charger.cache_clear()
    es._JOBS.clear()
    from testpilot.guardrails import bac_a_sable
    bac_a_sable.reinitialiser_pour_les_tests()
    yield
    domain_model._charger.cache_clear()


@pytest.fixture
def conn():
    from testpilot.store.db import get_initialized_db
    c = get_initialized_db()
    yield c
    c.close()


def _page(*champs):
    return {"champs": [{"name": n, "identifie_par": "name", "tag": "input", "type": "text", "visible": True, "label": n}
                       for n in champs], "actions": [], "liens": [], "formulaires": [], "titre": "", "url_exemple": ""}


def _projet_explore(conn, monkeypatch, *, refuses=()):
    """Un projet Odoo exploré : le principal voit /commandes et /comptabilite, Lecteur ne voit que /commandes."""
    from testpilot.connectors.runtime_env import comptes_pour_l_exploration
    from testpilot.store.repositories import ProjectAccountRepo, ProjectRepo

    ecrans = {"admin": {"/commandes": _page("client", "remise"), "/comptabilite": _page("journal")},
              "lecteur": {"/commandes": _page("client")}, "manager": {"/commandes": _page("client", "remise")}}

    def crawl(connexion, max_pages):
        if connexion["username"] in refuses:
            raise es.ConnexionDuCompteImpossible("connexion impossible : l'écran de connexion est resté affiché")
        return {"pages": dict(ecrans[connexion["username"]]), "transitions": {}, "onglets_internes": {},
                "modeles_backoffice": [], "familles": {}, "_session_fin": True, "_arretee": False, "_interrompue": False}

    monkeypatch.setattr(es, "_crawl", crawl)
    pid = ProjectRepo(conn).create(name="P", connector_type="odoo", base_url="http://odoo.local:8069")
    lecteur = ProjectAccountRepo(conn).create(pid, label="Lecteur", username="lecteur", password="pw-lecteur",
                                              business_role="Consultation")
    manager = ProjectAccountRepo(conn).create(pid, label="Manager", username="manager", password="pw-manager")
    es._JOBS["J"] = es._nouveau_job(pid)
    es.run_exploration("J", project_id=pid, comptes=comptes_pour_l_exploration(conn, pid), connexion={
        "base_url": "http://odoo.local:8069", "connector_type": "odoo", "nom": "P", "username": "admin",
        "password": "pw-admin"})
    domain_model._charger.cache_clear()
    return ProjectRepo(conn).get(pid), lecteur, manager


# ── 1. Éteint ou principal : rien ne change ──────────────────────────────────────────────────────────────────────────────

def test_falsifiable_eteint_le_modele_est_celui_d_avant_et_l_annexe_n_est_pas_lue(conn, monkeypatch):
    projet, lecteur, _ = _projet_explore(conn, monkeypatch)
    monkeypatch.setattr(es, "charger_carte", lambda *a: pytest.fail("la carte ne doit pas être lue, interrupteur éteint"))
    monkeypatch.setattr(domain_model, "charger_annexe_des_comptes", lambda *a: pytest.fail("l'annexe non plus"))
    cible = mdc.pour_la_generation(conn, projet, lecteur)
    assert cible.modele == domain_model.charger_modele(projet) and cible.vue == "principal" and not cible.avis
    assert cible.ecrit_pour["compte_id"] == lecteur, "pour qui il est écrit : noté quel que soit l'interrupteur (A88)"


def test_allume_avec_le_principal_rien_ne_change(conn, monkeypatch):
    projet, _, _ = _projet_explore(conn, monkeypatch)
    monkeypatch.setenv(interrupteurs.ENV_GENERATION_PAR_COMPTE, "1")
    cible = mdc.pour_la_generation(conn, projet, None)
    assert cible.modele == domain_model.charger_modele(projet) and cible.compte is None


def test_le_message_a_l_ia_et_l_empreinte_sont_ceux_d_avant_sans_compte_du_test():
    plan = TestPlan(module_name="m", models=[], scenarios=[], personas=["u"], portal_routes=[], risks=[],
                    connector_type="odoo", cost_usd=0.0, raw_spec="x")
    assert prompt_mod.build_initial_message(plan, None) == prompt_mod.build_initial_message(plan, None, compte_du_test=None)
    projet = {"id": 1, "base_url": "http://a", "username": "admin"}
    assert target_fingerprint(projet) == target_fingerprint(projet, compte=None)
    assert target_fingerprint(projet) != target_fingerprint(projet, compte="abc"), "une preuve du principal ≠ celle de Lecteur"


# ── 2. Allumé : les écrans du compte ─────────────────────────────────────────────────────────────────────────────────────

def test_falsifiable_allume_l_ia_recoit_les_ecrans_du_compte_et_jamais_son_identifiant(conn, monkeypatch):
    projet, lecteur, _ = _projet_explore(conn, monkeypatch)
    monkeypatch.setenv(interrupteurs.ENV_GENERATION_PAR_COMPTE, "1")
    cible = mdc.pour_la_generation(conn, projet, lecteur)
    assert cible.vue == "compte" and set(cible.modele["pages"]) == {"/commandes"}, "Lecteur ne voit pas /comptabilite"
    assert cible.modele["base_url"] == "http://odoo.local:8069" and cible.modele["mesure_le"], "métadonnées du principal"
    assert [c["name"] for c in cible.modele["pages"]["/commandes"]["champs"]] == ["client"]
    plan = TestPlan(module_name="m", models=[], scenarios=[], personas=["u"], portal_routes=["/commandes"], risks=[],
                    connector_type="odoo", cost_usd=0.0, raw_spec="x")
    message = prompt_mod.build_initial_message(plan, cible.modele, compte_du_test={**cible.compte, "vue": cible.vue})
    assert "joué en tant que « Lecteur » (rôle : Consultation)" in message
    assert "/comptabilite" not in message
    assert "lecteur" not in message.replace("Lecteur", "") and "pw-lecteur" not in message, "jamais l'identifiant (A74, D8)"


def test_falsifiable_a85_pas_encore_explore_ecrit_avec_le_principal_et_le_dit(conn, monkeypatch):
    from testpilot.store.repositories import ProjectAccountRepo

    projet, _, _ = _projet_explore(conn, monkeypatch)
    nouveau = ProjectAccountRepo(conn).create(projet["id"], label="Stagiaire", username="stagiaire", password="pw")
    monkeypatch.setenv(interrupteurs.ENV_GENERATION_PAR_COMPTE, "1")
    cible = mdc.pour_la_generation(conn, projet, nouveau)
    assert cible.modele == domain_model.charger_modele(projet) and cible.vue == "principal_faute_d_exploration"
    assert cible.avis == "Écrit sans les écrans de Stagiaire (pas encore exploré) — actualisez l'exploration puis régénérez"
    assert not cible.refus


def test_falsifiable_a85_connexion_impossible_refuse_avant_tout_appel_a_l_ia(conn, monkeypatch):
    projet, lecteur, _ = _projet_explore(conn, monkeypatch, refuses=("lecteur",))
    monkeypatch.setenv(interrupteurs.ENV_GENERATION_PAR_COMPTE, "1")
    cible = mdc.pour_la_generation(conn, projet, lecteur)
    assert cible.refus.startswith("Lecteur : connexion impossible") and "actualisez l'exploration" in cible.refus


# ── 3. Écrit pour un autre compte : bloqué (A86-A88) ─────────────────────────────────────────────────────────────────────

_NUMERO = iter(range(1, 10_000))


def _cas(conn, projet, *, compte_id=None, ecrit_pour=None, feature="# language: fr\nScénario: s\n  Quand j'agis\n"):
    from testpilot.store.repositories import CaseRepo, ModuleRepo, VersionRepo

    mid = ModuleRepo(conn).create(project_id=projet["id"], name=f"m{next(_NUMERO)}")
    cid = CaseRepo(conn).create(title="Devis", module_id=mid, feature_slug=f"devis_{mid}")
    provenance = json.dumps({"ecrit_pour": ecrit_pour}) if ecrit_pour else ""
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="", feature_content=feature,
                                   steps_content="", compte_id=compte_id, generation_provenance=provenance)
    CaseRepo(conn).set_current_version(cid, vid)
    return CaseRepo(conn).get(cid), vid


def test_falsifiable_a86_ecrit_pour_manager_joue_en_lecteur_est_bloque(conn, monkeypatch):
    from testpilot.api.services import run_service
    from testpilot.store.repositories import CaseRepo

    projet, lecteur, manager = _projet_explore(conn, monkeypatch)
    cas, vid = _cas(conn, projet, compte_id=manager, ecrit_pour={"compte_id": manager, "libelle": "Manager", "vue": "compte"})
    assert run_service.ecarts_cas_test(conn, cas, vid) == []
    v2 = CaseRepo(conn).update_metier(cas["id"], compte_id=lecteur)
    ecarts = run_service.ecarts_cas_test(conn, cas, v2)
    assert ecarts == ["écrit pour « Manager », joué en tant que « Lecteur » (régénérez le test, ou remettez « Joué en "
                      "tant que : Manager »)"]
    assert run_service.gate_du_cas(conn, cas, v2).allowed is False, "bloqué, même approuvé (mécanisme d'A42)"
    v3 = CaseRepo(conn).update_metier(cas["id"], compte_id=manager)
    assert run_service.ecarts_cas_test(conn, cas, v3) == [], "remis sur Manager : plus d'écart"


def test_falsifiable_a87_une_version_d_avant_est_reputee_ecrite_pour_le_principal(conn, monkeypatch):
    from testpilot.api.services import run_service

    projet, lecteur, _ = _projet_explore(conn, monkeypatch)
    cas, vid = _cas(conn, projet, compte_id=lecteur)   # aucune provenance « écrit pour »
    assert run_service.ecarts_cas_test(conn, cas, vid) == [
        "écrit pour « principal », joué en tant que « Lecteur » (régénérez le test, ou remettez « Joué en tant que : "
        "principal »)"]
    sans_test, vid2 = _cas(conn, projet, compte_id=lecteur, feature="")
    assert run_service.ecarts_cas_test(conn, sans_test, vid2) == [], "pas encore de test : rien à comparer"


def test_l_ecrit_pour_survit_a_une_correction(conn, monkeypatch):
    from testpilot.generation.provenance import revision_metadata
    from testpilot.store.repositories import VersionRepo

    projet, lecteur, manager = _projet_explore(conn, monkeypatch)
    cas, vid = _cas(conn, projet, compte_id=manager, ecrit_pour={"compte_id": manager, "libelle": "Manager", "vue": "compte"})
    origine = VersionRepo(conn).get(vid)
    corrigee = VersionRepo(conn).create(test_case_id=cas["id"], spec_content="", spec_hash="",
                                        feature_content=origine["feature_content"] + "  Alors c'est fait\n",
                                        steps_content="", **revision_metadata(origine))
    lignes = VersionRepo(conn).list_for_case(cas["id"])
    assert mdc.ecrit_pour_de_la_version(lignes, VersionRepo(conn).get(corrigee))["libelle"] == "Manager"


# ── 4. Relecture avec les écrans de l'écriture ───────────────────────────────────────────────────────────────────────────

def test_falsifiable_la_relecture_reprend_les_ecrans_et_la_cible_de_l_ecriture(conn, monkeypatch):
    from testpilot.store.repositories import VersionRepo

    projet, lecteur, _ = _projet_explore(conn, monkeypatch)
    from testpilot.connectors.runtime_env import empreinte_du_compte
    from testpilot.store.repositories import ProjectAccountRepo
    empreinte = empreinte_du_compte(ProjectAccountRepo(conn).lire(projet["id"], lecteur))
    cas, vid = _cas(conn, projet, compte_id=lecteur,
                    ecrit_pour={"compte_id": lecteur, "libelle": "Lecteur", "empreinte": empreinte, "vue": "compte"})
    lignes = VersionRepo(conn).list_for_case(cas["id"])
    modele, cible = mdc.pour_la_relecture(conn, projet, lignes, VersionRepo(conn).get(vid))
    assert set(modele["pages"]) == {"/commandes"} and cible == target_fingerprint(projet, compte=empreinte)
    principal, vid2 = _cas(conn, projet, ecrit_pour={"compte_id": None, "libelle": "principal", "vue": "principal"})
    modele2, cible2 = mdc.pour_la_relecture(conn, projet, VersionRepo(conn).list_for_case(principal["id"]),
                                            VersionRepo(conn).get(vid2))
    assert modele2 == domain_model.charger_modele(projet) and cible2 == target_fingerprint(projet), "calcul d'avant"


# ── 5. L'automatisation : essai et observation avec le compte, refus sans appel à l'IA ───────────────────────────────────

def _automatiser(conn, monkeypatch, cas_id):
    from testpilot.analysis import spec_analyzer as sa
    from testpilot.api.services import generation_service
    from testpilot.generation import agent as agent_mod

    vus = {}
    monkeypatch.setattr(sa.SpecAnalyzer, "analyze_spec_content", lambda self, slug, content: TestPlan(
        module_name=slug, models=[], scenarios=[], personas=["u"], portal_routes=[], risks=[], connector_type="odoo",
        cost_usd=0.0, raw_spec=content))

    def faux_generate(self, plan, **kw):
        vus["generate"] = kw
        vus["runner"] = dict(self.dry_runner.connection)
        from testpilot.generation.state import GenerationResult
        return GenerationResult(success=False, module_name=plan.module_name, stopped_reason="arrêt du test",
                                dry_run_passed=False, iterations=0, cost_usd=0.0)

    class _Runner:
        def __init__(self, **kw):
            self.connection = dict(kw.get("connection") or {})

    monkeypatch.setattr(agent_mod.GenerationAgent, "generate", faux_generate)
    monkeypatch.setattr("testpilot.connectors.odoo.OdooConnector.from_project",
                        lambda project, **kw: vus.setdefault("connecteur", kw) and None or type(
                            "C", (), {"connect": lambda s: None, "disconnect": lambda s: None})())
    monkeypatch.setattr("testpilot.execution.behave_runner.BehaveRunner", _Runner)
    from testpilot.store.repositories import CaseRepo, GenerationJobRepo
    module_id = CaseRepo(conn).get(cas_id)["module_id"]
    job = f"job-{next(_NUMERO)}"
    GenerationJobRepo(conn).creer(job, module_id=module_id)
    conn.commit()
    generation_service.run_automation(job, case_id=cas_id, module_id=module_id, slug=f"auto_{cas_id}", spec_content="x",
                                      metier={"title": "Devis"})
    vus["job"] = generation_service.get_job(conn, job)
    return vus


def test_falsifiable_allume_l_essai_et_l_observation_se_font_avec_le_compte(conn, monkeypatch):
    from testpilot.connectors.runtime_env import ENV_COMPTE_DU_TEST

    projet, lecteur, _ = _projet_explore(conn, monkeypatch)
    cas, _ = _cas(conn, projet, compte_id=lecteur)
    eteint = _automatiser(conn, monkeypatch, cas["id"])
    assert ENV_COMPTE_DU_TEST not in eteint["runner"] and eteint["connecteur"] == {}, "éteint : comme avant"
    assert eteint["generate"]["modele_du_cas"] is None and eteint["generate"]["ecrit_pour"]["libelle"] == "Lecteur"

    monkeypatch.setenv(interrupteurs.ENV_GENERATION_PAR_COMPTE, "1")
    allume = _automatiser(conn, monkeypatch, cas["id"])
    assert allume["runner"][ENV_COMPTE_DU_TEST] == "Lecteur"
    assert allume["connecteur"] == {"ui_user": "lecteur", "ui_password": "pw-lecteur"}, "le navigateur, pas le RPC (A73)"
    assert allume["generate"]["modele_du_cas"].vue == "compte"


def test_falsifiable_allume_un_compte_en_connexion_impossible_n_appelle_jamais_l_ia(conn, monkeypatch):
    projet, lecteur, _ = _projet_explore(conn, monkeypatch, refuses=("lecteur",))
    cas, _ = _cas(conn, projet, compte_id=lecteur)
    monkeypatch.setenv(interrupteurs.ENV_GENERATION_PAR_COMPTE, "1")
    vus = _automatiser(conn, monkeypatch, cas["id"])
    assert "generate" not in vus and "connecteur" not in vus, "ni IA ni navigateur"
    assert vus["job"]["status"] == "failed" and vus["job"]["error"].startswith("Lecteur : connexion impossible"), \
        "l'écran dit pourquoi et quoi faire"


# ── A89 : une vérification lue par le principal, pour un cas joué avec un autre compte ──────────────────────────────────────

_LU_PAR_LE_SERVEUR = '''
from behave import then


@then("le lecteur voit la facture")
def step_voit(context):
    constater(context.odoo.env["account.move"].search_count([]) == 1, "facture")


@then("la facture est affichée")
def step_affichee(context):
    constater(context.page.locator("text=F-001").count() == 1, "affichée")
'''


def test_falsifiable_a89_une_verification_lue_par_le_principal_est_signalee_pour_un_autre_compte():
    from testpilot.generation.assertion_lint import LU_PAR_LE_PRINCIPAL
    from testpilot.generation.avis_du_test import avis_du_test

    commun = dict(feature="", steps=_LU_PAR_LE_SERVEUR, observations=None, target_sha256="", base_url="",
                  reference_time=None, variables_des_lignes=(), connecteur_web=False, intention="", modele=None,
                  verified_fields=None)
    avis = [a for a in avis_du_test(**commun, joue_avec_un_autre_compte=True) if a["kind"] == LU_PAR_LE_PRINCIPAL]
    assert [a["step"] for a in avis] == ["le lecteur voit la facture"], "l'écran, lui, prouve ce que voit le compte"
    assert not [a for a in avis_du_test(**commun) if a["kind"] == LU_PAR_LE_PRINCIPAL], "le principal : rien à dire"


def test_a89_l_avis_a_une_raison_en_francais():
    from testpilot.verdict.review_gate import RAISONS_DES_AVIS

    assert RAISONS_DES_AVIS["verification_lue_par_le_principal"].startswith("Une vérification lit le serveur")


_TAUTOLOGIE = """
@then("truc")
def s(context):
    assert True
"""


@pytest.mark.parametrize("avec_tautologie", [False, True])
def test_falsifiable_a89_l_avis_n_est_jamais_envoye_a_la_correction(conn, monkeypatch, avec_tautologie):
    """Revue : prouvé par le comportement — avec l'avis A89 seul, la correction n'est pas appelée ; avec un autre point en
    plus, elle reçoit cet autre point SEUL (l'avis A89 est à juger par une personne)."""
    from testpilot.api.services import generation_service
    from testpilot.generation import correction_agent

    projet, lecteur, _ = _projet_explore(conn, monkeypatch)
    steps = "from behave import then\n" + _LU_PAR_LE_SERVEUR + (_TAUTOLOGIE if avec_tautologie else "")
    cas, vid = _cas(conn, projet, compte_id=lecteur, ecrit_pour={"compte_id": lecteur, "libelle": "Lecteur", "vue": "principal"})
    conn.execute("UPDATE test_case_version SET steps_content=? WHERE id=?", (steps, vid))
    conn.commit()
    recus = []

    def fausse_correction(**kw):
        recus.append(sorted({w["kind"] for w in kw["lint_warnings"]}))
        return correction_agent.CorrectionProposal(changed=False, feature_content="", steps_content="", summary="",
                                                   cost_usd=0.0, stopped_reason="done")
    monkeypatch.setattr(correction_agent, "propose_correction", fausse_correction)
    generation_service._finaliser_version_generee(conn, cas["id"], vid, module_name="m", connector=None,
                                                  dry_runner=object())
    assert recus == ([["always_true_constant"]] if avec_tautologie else []), "jamais l'avis A89 à la correction"


def test_falsifiable_a86_un_identifiant_change_depuis_l_ecriture_bloque(conn, monkeypatch):
    """Revue (bloquant) : même compte, identifiant de connexion changé (« manager » → « stagiaire ») — une autre personne."""
    from testpilot.api.services import run_service
    from testpilot.connectors.runtime_env import empreinte_du_compte
    from testpilot.store.repositories import ProjectAccountRepo

    projet, _, manager = _projet_explore(conn, monkeypatch)
    empreinte = empreinte_du_compte(ProjectAccountRepo(conn).lire(projet["id"], manager))
    cas, vid = _cas(conn, projet, compte_id=manager,
                    ecrit_pour={"compte_id": manager, "libelle": "Manager", "empreinte": empreinte, "vue": "compte"})
    assert run_service.ecarts_cas_test(conn, cas, vid) == []
    ProjectAccountRepo(conn).modifier(projet["id"], manager, username="stagiaire")
    assert run_service.ecarts_cas_test(conn, cas, vid) == [
        "le compte « Manager » a changé d'identifiant depuis l'écriture du test (régénérez le test)"]
    ProjectAccountRepo(conn).modifier(projet["id"], manager, password="autre")   # le mot de passe, lui, ne change rien
    ProjectAccountRepo(conn).modifier(projet["id"], manager, username="manager")
    assert run_service.ecarts_cas_test(conn, cas, vid) == []


def test_une_regeneration_identique_pour_un_autre_compte_n_est_plus_bloquee(conn, monkeypatch):
    """Revue : v1 écrite pour le principal, v2 passée en Lecteur (bloquée), v3 régénérée pour Lecteur au contenu identique —
    elle ne reste pas « écrite pour le principal » (sinon « régénérez » tournait en boucle)."""
    from testpilot.api.services import run_service
    from testpilot.store.repositories import CaseRepo, VersionRepo

    projet, lecteur, _ = _projet_explore(conn, monkeypatch)
    cas, v1 = _cas(conn, projet, ecrit_pour={"compte_id": None, "libelle": "principal", "vue": "principal"})
    v2 = CaseRepo(conn).update_metier(cas["id"], compte_id=lecteur)
    assert run_service.ecarts_cas_test(conn, cas, v2), "passé en Lecteur sans régénération : bloqué"
    origine = VersionRepo(conn).get(v2)
    v3 = VersionRepo(conn).create(test_case_id=cas["id"], spec_content="", spec_hash="",
                                  feature_content=origine["feature_content"], steps_content=origine["steps_content"],
                                  generation_provenance=json.dumps({"ecrit_pour": {"compte_id": lecteur, "libelle": "Lecteur",
                                                                                   "vue": "principal"}}))
    CaseRepo(conn).set_current_version(cas["id"], v3)
    assert run_service.ecarts_cas_test(conn, cas, v3) == []


def test_falsifiable_un_compte_sans_identifiants_echoue_jamais_un_repli_sur_le_principal(conn, monkeypatch):
    from testpilot.connectors import runtime_env

    projet, lecteur, _ = _projet_explore(conn, monkeypatch)
    cas, _ = _cas(conn, projet, compte_id=lecteur)
    monkeypatch.setenv(interrupteurs.ENV_GENERATION_PAR_COMPTE, "1")
    monkeypatch.setattr(runtime_env, "identifiants_du_compte", lambda *a: None)
    vus = _automatiser(conn, monkeypatch, cas["id"])
    assert "generate" not in vus and "connecteur" not in vus
    assert vus["job"]["error"].startswith("Lecteur : compte supprimé ou sans mot de passe")



# ── Revue, seconde passe : l'identité du compte d'observation web ────────────────────────────────────────────────────────

class _PageObs:
    def __init__(self, url_apres, mot_de_passe_visible):
        self.url, self._apres, self._mdp = "http://app.local/login", url_apres, mot_de_passe_visible

    def query_selector_all(self, _sel):
        return [type("C", (), {"is_visible": lambda s: True})()] if self._mdp else []


def _connecteur_web(monkeypatch, *, verifier, page):
    from testpilot.connectors import generic_web

    c = generic_web.GenericWebConnector("http://app.local", "lecteur", "pw", verifier_identite=verifier)
    fermes = []

    class _Nav:
        def new_context(self, **kw):
            return type("Ctx", (), {"new_page": lambda s: page})()

        def close(self):
            fermes.append(True)

    class _PW:
        chromium = type("Ch", (), {"launch": lambda s, **kw: _Nav()})()

        def stop(self):
            pass

    monkeypatch.setattr("playwright.sync_api.sync_playwright", lambda: type("S", (), {"start": lambda s: _PW()})())
    page.set_default_timeout = lambda t: None
    page.goto = lambda u: None
    page.wait_for_load_state = lambda s: None

    def _soumettre(pg):
        pg.url = pg._apres
        c._tentative_connexion_faite = True
    monkeypatch.setattr(c, "_tenter_connexion_generique", lambda pg: (setattr(c, "_url_avant_connexion", pg.url),
                                                                      _soumettre(pg)))
    return c, fermes


def test_falsifiable_observation_web_avec_un_compte_refuse_echoue_une_fois_et_ferme_le_navigateur(monkeypatch):
    c, fermes = _connecteur_web(monkeypatch, verifier=True, page=_PageObs("http://app.local/login?error", True))
    with pytest.raises(RuntimeError, match="observation avec le compte du cas impossible"):
        c._ensure_page()
    assert fermes == [True]
    with pytest.raises(RuntimeError, match="observation avec le compte du cas impossible"):
        c._ensure_page()   # mémorisé : aucune nouvelle tentative de connexion
    assert fermes == [True]


def test_observation_web_sans_verification_ou_compte_connecte_comme_avant(monkeypatch):
    c, _ = _connecteur_web(monkeypatch, verifier=False, page=_PageObs("http://app.local/login?error", True))
    assert c._ensure_page() is not None, "sans vérification : le comportement d'avant"
    c, _ = _connecteur_web(monkeypatch, verifier=True, page=_PageObs("http://app.local/accueil", False))
    assert c._ensure_page() is not None


def test_falsifiable_allume_projet_web_l_identite_est_prouvee_avant_tout_appel_a_l_ia(conn, monkeypatch):
    from testpilot.analysis import spec_analyzer as sa
    from testpilot.api.services import generation_service
    from testpilot.generation import agent as agent_mod
    from testpilot.store.repositories import CaseRepo, GenerationJobRepo, ProjectAccountRepo, ProjectRepo

    pid = ProjectRepo(conn).create(name="Web", connector_type="web", base_url="http://app.local")
    lecteur = ProjectAccountRepo(conn).create(pid, label="Lecteur", username="lecteur", password="pw")
    cas, _ = _cas(conn, ProjectRepo(conn).get(pid), compte_id=lecteur)
    monkeypatch.setenv(interrupteurs.ENV_GENERATION_PAR_COMPTE, "1")
    vus = {}

    class _Connecteur:
        def connect(self):
            pass

        def disconnect(self):
            pass

        def _ensure_page(self):
            raise RuntimeError("observation avec le compte du cas impossible : l'écran de connexion est resté affiché")

        def _run_in_browser(self, fn):
            return fn()
    monkeypatch.setattr("testpilot.connectors.generic_web.GenericWebConnector.from_project",
                        lambda project, **kw: vus.setdefault("kw", kw) and _Connecteur())
    monkeypatch.setattr("testpilot.execution.behave_runner.BehaveRunner", lambda **kw: SimpleNamespace(connection={}))
    monkeypatch.setattr(sa.SpecAnalyzer, "analyze_spec_content", lambda *a: pytest.fail("aucune analyse payée"))
    monkeypatch.setattr(agent_mod.GenerationAgent, "generate", lambda *a, **k: pytest.fail("aucun appel à l'IA"))
    module_id = CaseRepo(conn).get(cas["id"])["module_id"]
    GenerationJobRepo(conn).creer("job-web", module_id=module_id)
    conn.commit()
    generation_service.run_automation("job-web", case_id=cas["id"], module_id=module_id, slug="w", spec_content="x",
                                      metier={"title": "Devis"})
    assert vus["kw"]["verifier_identite"] is True and vus["kw"]["user"] == "lecteur"
    assert generation_service.get_job(conn, "job-web")["error"].startswith("Lecteur : observation avec le compte du cas")
