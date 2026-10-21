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


# ── A96 (remplace l'avis A89) : plus aucun cas « à relire » pour une vérification lue par le serveur ──────────────────────

_LU_PAR_LE_SERVEUR = """
from behave import then


@then("le lecteur voit la facture")
def step_voit(context):
    constater(context.odoo.env["account.move"].search_count([]) == 1, "facture")
"""


def test_a96_une_verification_lue_par_le_serveur_ne_met_plus_rien_a_relire():
    """A96 : les « Alors » d'un cas joué avec un compte lisent avec CE compte — l'avis A89 (« à relire ») disparaît."""
    from testpilot.generation.avis_du_test import avis_du_test
    from testpilot.verdict.review_gate import RAISONS_DES_AVIS

    avis = avis_du_test(feature="", steps=_LU_PAR_LE_SERVEUR, observations=None, target_sha256="", base_url="",
                        reference_time=None, variables_des_lignes=(), connecteur_web=False, intention="", modele=None,
                        verified_fields=None)
    assert avis == [] and "verification_lue_par_le_principal" not in RAISONS_DES_AVIS


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



# ── A96 : le harnais vérifie avec le compte du cas, recoupé avec le principal ────────────────────────────────────────────

@pytest.fixture
def H():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "behave_runtime" / "steps_library"))
    import _base_helpers
    return _base_helpers


class _SessionRPC:
    def __init__(self, reponses):
        self.reponses, self.appels = reponses, []

    def execute_kw(self, model, method, args=None, kwargs=None):
        self.appels.append((model, method))
        return self.reponses.get((model, method), 0)


def _ctx_a96(H, monkeypatch, *, principal, compte):
    principale, du_compte = _SessionRPC(principal), _SessionRPC(compte)
    monkeypatch.setattr(H, "_ouvrir_session_rpc", lambda ctx, u, p: du_compte)
    ctx = SimpleNamespace(odoo=principale, _odoo_principal=principale, compte_courant="Lecteur", odoo_user="lecteur",
                          odoo_password="pw", created={}, created_ordre=[])
    return ctx, principale, du_compte


def test_falsifiable_a96_un_alors_lit_avec_le_compte_et_les_autres_steps_avec_le_principal(H, monkeypatch):
    ctx, principale, _ = _ctx_a96(H, monkeypatch, principal={}, compte={})
    H.poser_la_session_des_verifications(ctx, "given")
    assert ctx.odoo is principale, "mise en place des données : le principal"
    H.poser_la_session_des_verifications(ctx, "then")
    assert isinstance(ctx.odoo, H.SessionDesVerifications)
    ctx.compte_courant = "principal"
    H.poser_la_session_des_verifications(ctx, "then")
    assert ctx.odoo is principale, "un cas joué avec le principal ne change pas"
    web = SimpleNamespace(odoo=None, compte_courant="Lecteur")
    H.poser_la_session_des_verifications(web, "then")
    assert web.odoo is None, "web : aucune session serveur"


def test_falsifiable_a96_le_compte_voit_la_meme_chose_que_le_principal_c_est_son_verdict(H, monkeypatch):
    ctx, _, _ = _ctx_a96(H, monkeypatch, principal={("account.move", "search"): [7]}, compte={("account.move", "search"): [7]})
    assert H.SessionDesVerifications(ctx, "Lecteur").execute_kw("account.move", "search", [[("name", "=", "F-001")]]) == [7]


@pytest.mark.parametrize("methode, compte, principal", [
    ("search", [30], [30, 29]),        # mesuré : un doublon dont le compte ne voit qu'un exemplaire — « pas de doublon »
    ("search_count", 1, 2),
    ("read", [{"id": 5, "sale_order_ids": [30]}], [{"id": 5, "sale_order_ids": [30, 29]}]),   # mesuré : liés filtrés
])
def test_falsifiable_a96_le_compte_qui_voit_une_partie_n_est_jamais_passe(H, monkeypatch, methode, compte, principal):
    """Revue d'A96 (bloquant, mesuré sur le banc) : pas seulement « rien » — un compte qui voit une PARTIE conclut sur ce qu'il
    a le droit de voir (« aucun doublon » vrai pour le compte, faux pour l'application)."""
    ctx, _, _ = _ctx_a96(H, monkeypatch, principal={("sale.order", methode): principal}, compte={("sale.order", methode): compte})
    with pytest.raises(H.ConstatNonConcluantError, match="« Lecteur » voit moins que le compte principal dans sale.order"):
        H.SessionDesVerifications(ctx, "Lecteur").execute_kw("sale.order", methode, [[]])


def test_falsifiable_a96_une_absence_contredite_par_le_principal_n_est_jamais_passe(H, monkeypatch):
    """« Aucune commande n'a été créée » vu par un compte qui ne voit aucune commande — le principal en voit une : on ne sait
    pas si l'application a fauté, « non concluant », jamais « Passé »."""
    ctx, _, _ = _ctx_a96(H, monkeypatch, principal={("sale.order", "search"): [42]}, compte={("sale.order", "search"): []})
    session = H.SessionDesVerifications(ctx, "Lecteur")
    with pytest.raises(H.ConstatNonConcluantError, match="« Lecteur » voit moins que le compte principal dans sale.order"):
        session.execute_kw("sale.order", "search", [[("id", ">", 10)]])


def test_a96_une_absence_confirmee_par_le_principal_est_une_vraie_absence(H, monkeypatch):
    ctx, _, _ = _ctx_a96(H, monkeypatch, principal={("sale.order", "search"): []}, compte={("sale.order", "search"): []})
    assert H.SessionDesVerifications(ctx, "Lecteur").execute_kw("sale.order", "search", [[]]) == []


def test_a96_une_creation_sous_un_alors_est_nettoyee_par_le_principal(H, monkeypatch):
    ctx, _, _ = _ctx_a96(H, monkeypatch, principal={}, compte={("res.partner", "create"): 77})
    H.SessionDesVerifications(ctx, "Lecteur").execute_kw("res.partner", "create", [{}])
    assert ctx.created == {"res.partner": [77]} and ctx.created_ordre == [("res.partner", 77)]


def test_a96_le_message_a_l_ia_ne_dit_plus_que_le_serveur_se_lit_avec_le_principal():
    plan = TestPlan(module_name="m", models=[], scenarios=[], personas=["u"], portal_routes=[], risks=[],
                    connector_type="odoo", cost_usd=0.0, raw_spec="x")
    message = prompt_mod.build_initial_message(plan, None, compte_du_test={"libelle": "Lecteur", "vue": "compte"})
    assert "lisent l'écran ET le serveur avec « Lecteur »" in message and "qui voit TOUT" not in message



def test_falsifiable_a96_une_connexion_refusee_du_compte_est_un_prerequis(H, monkeypatch):
    def _refus(*a):
        raise RuntimeError("Wrong login ID or password")
    monkeypatch.setattr(H, "_ouvrir_session_rpc", _refus)
    ctx = SimpleNamespace(odoo=None, _odoo_principal=_SessionRPC({}), compte_courant="Lecteur", odoo_user="lecteur",
                          odoo_password="mauvais")
    with pytest.raises(H.PreconditionNonRemplieError, match="connexion au serveur impossible avec le compte « Lecteur »"):
        H.SessionDesVerifications(ctx, "Lecteur").execute_kw("sale.order", "search", [[]])


def test_falsifiable_a96_une_lecture_du_compte_compte_comme_lecture_du_serveur(H, monkeypatch):
    vus = []
    monkeypatch.setattr(H, "noter_lecture_rpc", lambda: vus.append(True))
    ctx, _, _ = _ctx_a96(H, monkeypatch, principal={("sale.order", "search"): [1]}, compte={("sale.order", "search"): [1]})
    H.SessionDesVerifications(ctx, "Lecteur").execute_kw("sale.order", "search", [[]])
    assert vus == [True]


def test_falsifiable_a96_lire_un_champ_ne_lit_que_ce_champ(H):
    """Revue d'A96 (mesuré sur le banc) : `browse(id)` lisait tous les champs — un compte restreint était refusé sur un champ
    sans rapport. Un vrai modèle odoorpc (attribut `_odoo`) est lu par `read([id], [champ])`, rien d'autre."""
    appels = []

    class _Modele:
        _odoo = object()

        @classmethod
        def read(cls, ids, champs):
            appels.append((ids, champs))
            return [{"id": ids[0], champs[0]: "x@y"}]

        @classmethod
        def browse(cls, *a):
            raise AssertionError("browse lirait tous les champs")
    assert H.enregistrement(_Modele, 10).read(["email"]) == [{"id": 10, "email": "x@y"}] and appels == [([10], ["email"])]


def test_falsifiable_a96_les_crochets_posent_et_rendent_la_session_du_principal():
    """Revue d'A96 : sans le retour du principal en fin de step, le nettoyage tournerait avec le compte (suppressions
    refusées, résidus) ; sans la sauvegarde, il n'y aurait rien à rendre."""
    from pathlib import Path

    texte = (Path(__file__).resolve().parent.parent / "behave_runtime" / "environment.py").read_text(encoding="utf-8")
    debut = texte.index("def before_scenario(")
    scenario = texte[debut:texte.index("\ndef ", debut + 10)]
    assert "context._odoo_principal = context.odoo" in scenario
    etape = texte[texte.index("def before_step("):texte.index("def after_step(")]
    assert "poser_la_session_des_verifications(context" in etape
    fin = texte[texte.index("def after_step("):]
    assert "context.odoo = context._odoo_principal" in fin[:fin.index("\ndef ", 10)]


def test_falsifiable_a96_ne_pas_voir_verifie_l_existence_avec_le_principal(H, monkeypatch):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "behave_runtime" / "steps_library" / "odoo"))
    """Sous un « Alors », `context.odoo` est la session du compte : l'existence de l'enregistrement se vérifie avec le
    PRINCIPAL (sinon « cet utilisateur ne voit pas » serait non concluant à chaque fois)."""
    import types
    import _odoo_droits_steps as droits

    monkeypatch.setattr(droits, "session_rpc_du_compte_qui_agit",
                        lambda ctx: types.SimpleNamespace(env={"sale.order": types.SimpleNamespace(search_count=lambda d: 0)}))
    ctx = types.SimpleNamespace(
        last_record_model="sale.order", last_record_ids=[1], odoo=types.SimpleNamespace(env={}),
        _odoo_principal=types.SimpleNamespace(env={"sale.order": types.SimpleNamespace(search_count=lambda d: 1)}))
    droits.step_utilisateur_ne_voit_pas_enregistrement(ctx)



# ── Revue d'A96, seconde passe ───────────────────────────────────────────────────────────────────────────────────────────

def test_falsifiable_a96_le_refus_d_action_appelle_l_action_seule_jamais_browse(monkeypatch):
    """Mesuré sur le banc : `browse(id).write()` refusé (lecture d'un champ sans rapport) alors que le `write` direct du
    commercial est AUTORISÉ — le refus n'existait qu'à l'écran, et le cas sortait « Passé »."""
    import sys
    import types
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "behave_runtime" / "steps_library"))
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "behave_runtime" / "steps_library" / "odoo"))
    import _odoo_droits_steps as droits

    class AccessError(Exception):
        pass

    class _Modele:
        def search_count(self, domaine):
            return 1

        def browse(self, *a):
            raise AccessError("You are not allowed to access 'Bon de commande fournisseur' (purchase.order) records.")

    session = types.SimpleNamespace(env={"res.partner": _Modele()}, execute_kw=lambda *a: True)   # l'action réussit
    monkeypatch.setattr(droits, "session_rpc_du_compte_qui_agit", lambda ctx: session)
    monkeypatch.setattr(droits, "constater_visible", lambda loc, message="": None)
    page = types.SimpleNamespace(locator=lambda sel: object())
    ctx = types.SimpleNamespace(page=page, odoo_version=(17, 0), last_record_model="res.partner", last_record_ids=[10])
    with pytest.raises(AssertionError):
        droits.step_action_refusee(ctx, "write")


def test_falsifiable_a96_une_lecture_refusee_au_compte_est_non_concluante_pas_a_reparer(H, monkeypatch):
    class _Refus:
        def execute_kw(self, *a, **k):
            raise RuntimeError("You are not allowed to access 'Bon de commande fournisseur' (purchase.order) records.")
    monkeypatch.setattr(H, "_ouvrir_session_rpc", lambda ctx, u, p: _Refus())
    ctx = SimpleNamespace(_odoo_principal=_SessionRPC({}), compte_courant="Lecteur", odoo_user="l", odoo_password="p")
    with pytest.raises(H.ConstatNonConcluantError, match="« Lecteur » n'a pas le droit de lire purchase.order"):
        H.SessionDesVerifications(ctx, "Lecteur").execute_kw("purchase.order", "search_count", [[]])


def test_falsifiable_a96_l_autre_porte_d_odoorpc_est_recoupee_aussi(H, monkeypatch):
    ctx, _, compte = _ctx_a96(H, monkeypatch, principal={("sale.order", "search_count"): 2},
                              compte={("sale.order", "search_count"): 1})
    compte.execute = None
    session = H.SessionDesVerifications(ctx, "Lecteur")
    with pytest.raises(H.ConstatNonConcluantError):
        session.execute("sale.order", "search_count", [])


def test_falsifiable_a96_search_read_compare_aussi_les_lies(H, monkeypatch):
    ctx, _, _ = _ctx_a96(H, monkeypatch, principal={("res.partner", "search_read"): [{"id": 5, "sale_order_ids": [32, 31]}]},
                         compte={("res.partner", "search_read"): [{"id": 5, "sale_order_ids": [32]}]})
    with pytest.raises(H.ConstatNonConcluantError):
        H.SessionDesVerifications(ctx, "Lecteur").execute_kw("res.partner", "search_read", [[]])


def test_falsifiable_a96_la_garde_persiste_meme_si_le_step_avale_l_exception(H, monkeypatch):
    """Revue : un step généré `try: … except Exception: return 0` effaçait la garde — le repère reste sur le contexte, et
    `after_step` en fait un « Alors » sans constat (indéterminé)."""
    ctx, _, _ = _ctx_a96(H, monkeypatch, principal={("sale.order", "search_count"): 2}, compte={("sale.order", "search_count"): 1})
    try:
        H.SessionDesVerifications(ctx, "Lecteur").execute_kw("sale.order", "search_count", [[]])
    except Exception:
        pass   # ce que ferait un step qui avale
    assert ctx._tp_recoupement_contredit.startswith("« Lecteur » voit moins")
    from pathlib import Path
    texte = (Path(__file__).resolve().parent.parent / "behave_runtime" / "environment.py").read_text(encoding="utf-8")
    fin = texte[texte.index("def after_step("):]
    assert 'raison="recoupement_contredit"' in fin[:fin.index("\ndef ", 10)]



# ── Liens entre l'écriture par compte (partie A) et la colonne « Compte » des lignes (partie B) ─────────────────────────

def _lignes(conn, projet, cas_id, lignes):
    """`lignes` : [(nom, compte_id | "principal" | None)] — None = case vide (compte du cas)."""
    from testpilot.store.repositories import CaseDataRepo, TestDataRepo

    depot = TestDataRepo(conn)
    nom = f"resultat_{cas_id}"
    variable = next((v["id"] for v in depot.variables(projet["id"]) if v["nom"] == nom), None) or depot.creer_variable(
        projet["id"], nom=nom)
    CaseDataRepo(conn).remplacer(cas_id, projet["id"], [
        {"nom": nom, "valeurs": {variable: "x"}, "compte_choisi": compte is not None,
         "compte_id": None if compte in (None, "principal") else compte} for nom, compte in lignes])


def test_falsifiable_une_ligne_jouee_avec_un_compte_pour_lequel_le_test_n_a_pas_ete_ecrit_est_bloquee(conn, monkeypatch):
    from testpilot.api.services import run_service

    projet, lecteur, manager = _projet_explore(conn, monkeypatch)
    cas, vid = _cas(conn, projet, ecrit_pour={"compte_id": None, "libelle": "principal", "vue": "principal",
                                              "comptes_des_lignes": [0, lecteur]})
    _lignes(conn, projet, cas["id"], [("L1", "principal"), ("L2", lecteur)])
    assert [e for e in run_service.ecarts_cas_test(conn, cas, vid) if "est jouée en tant que" in e] == [], "écrit pour ces comptes : rien"
    _lignes(conn, projet, cas["id"], [("L1", "principal"), ("L2", manager)])
    assert [e for e in run_service.ecarts_cas_test(conn, cas, vid) if "est jouée en tant que" in e] == [
        "la ligne « L2 » est jouée en tant que « Manager », le test n'a pas été écrit pour ce compte (régénérez le test, ou "
        "remettez cette ligne sur le compte pour lequel il a été écrit)"]


def test_falsifiable_un_test_d_avant_les_comptes_des_lignes_est_repute_ecrit_pour_le_seul_compte_du_cas(conn, monkeypatch):
    from testpilot.api.services import run_service

    projet, lecteur, _ = _projet_explore(conn, monkeypatch)
    cas, vid = _cas(conn, projet, ecrit_pour={"compte_id": None, "libelle": "principal", "vue": "principal"})
    _lignes(conn, projet, cas["id"], [("L1", None), ("L2", lecteur)])
    assert any("la ligne « L2 » est jouée en tant que « Lecteur »" in e for e in run_service.ecarts_cas_test(conn, cas, vid))


def test_pour_la_generation_note_les_comptes_des_lignes_pour_lesquels_le_test_est_ecrit(conn, monkeypatch):
    projet, lecteur, _ = _projet_explore(conn, monkeypatch)
    cas, _ = _cas(conn, projet, compte_id=lecteur)
    _lignes(conn, projet, cas["id"], [("Vide", None), ("Principal", "principal")])
    cible = mdc.pour_la_generation(conn, projet, lecteur, cas["id"])
    assert [(l["nom"], l["libelle"]) for l in cible.comptes_des_lignes] == [("Vide", "Lecteur"), ("Principal", "principal")]
    assert cible.ecrit_pour["comptes_des_lignes"] == sorted({0, lecteur})


def test_la_consigne_des_lignes_n_apparait_qu_avec_des_lignes_a_compte():
    plan = TestPlan(module_name="m", models=[], scenarios=[], personas=["u"], portal_routes=[], risks=[],
                    connector_type="odoo", cost_usd=0.0, raw_spec="x")
    assert prompt_mod.build_initial_message(plan, None) == prompt_mod.build_initial_message(plan, None, comptes_des_lignes=None)
    message = prompt_mod.build_initial_message(plan, None, comptes_des_lignes=[
        {"nom": "L1", "libelle": "Lecteur"}, {"nom": "L2", "libelle": "Manager"}])
    assert "« L1 » en tant que « Lecteur », « L2 » en tant que « Manager »" in message and "n'écris AUCUNE connexion" in message


def test_falsifiable_allume_l_essai_se_joue_avec_le_compte_de_la_premiere_ligne(conn, monkeypatch):
    from testpilot.connectors.runtime_env import ENV_COMPTE_DU_TEST

    projet, lecteur, manager = _projet_explore(conn, monkeypatch)
    cas, _ = _cas(conn, projet)   # cas joué avec le principal, lignes à compte
    _lignes(conn, projet, cas["id"], [("L1", manager), ("L2", lecteur)])
    monkeypatch.setenv(interrupteurs.ENV_GENERATION_PAR_COMPTE, "1")
    vus = _automatiser(conn, monkeypatch, cas["id"])
    assert vus["runner"][ENV_COMPTE_DU_TEST] == "Manager"
    assert [l["libelle"] for l in vus["generate"]["modele_du_cas"].comptes_des_lignes] == ["Manager", "Lecteur"]
    monkeypatch.delenv(interrupteurs.ENV_GENERATION_PAR_COMPTE)
    eteint = _automatiser(conn, monkeypatch, cas["id"])
    assert ENV_COMPTE_DU_TEST not in eteint["runner"] and eteint["generate"]["modele_du_cas"] is None
    assert eteint["generate"]["ecrit_pour"]["comptes_des_lignes"] == sorted({manager, lecteur}), "noté même éteint"



# ── Revue finale du morceau 7 ─────────────────────────────────────────────────────────────────────────────────────────────

def test_falsifiable_l_ecrit_pour_se_verifie_sur_les_lignes_figees_que_le_run_joue(conn, monkeypatch):
    """Revue finale (bloquant) : campagne lancée avec L2 en Lecteur (figée), puis L2 remise au compte du cas dans la fiche —
    la porte ne voit plus d'écart, mais le run joue L2 FIGÉE en Lecteur. Le contrôle se refait sur les lignes figées."""
    from testpilot.api.services import donnees_de_test_service as service
    from testpilot.store.repositories import ExecutionRepo, RunRepo

    projet, lecteur, _ = _projet_explore(conn, monkeypatch)
    cas, vid = _cas(conn, projet, ecrit_pour={"compte_id": None, "libelle": "principal", "vue": "principal"},
                    feature="# language: fr\nFonctionnalité: F\n  Scénario: s\n    Alors la page affiche le texte \"{{resultat_%d}}\"\n"
                    % 0)
    conn.execute("UPDATE test_case_version SET feature_content=? WHERE id=?",
                 (f"# language: fr\nFonctionnalité: F\n  Scénario: s\n    Alors la page affiche le texte \"{{{{resultat_{cas['id']}}}}}\"\n",
                  vid))
    conn.commit()
    _lignes(conn, projet, cas["id"], [("L1", None), ("L2", lecteur)])
    run_id = RunRepo(conn).create(project_id=projet["id"], name="Nuit", case_ids=[cas["id"]])
    service.figer_pour_la_campagne(conn, RunRepo(conn).get(run_id))
    _lignes(conn, projet, cas["id"], [("L1", None), ("L2", None)])   # la fiche ne montre plus d'écart
    eid = ExecutionRepo(conn).create(test_case_id=cas["id"], version_id=vid)
    conn.execute("UPDATE execution SET run_id=? WHERE id=?", (run_id, eid))
    conn.commit()
    script = service.preparer_le_script(conn, eid, cas["id"], vid, "m")
    assert script.blocage.startswith("Données de test : la ligne « L2 » est jouée en tant que « Lecteur », le test n'a pas "
                                     "été écrit pour ce compte"), script.blocage
    assert script.blocage.endswith("corrigez la fiche, puis créez une nouvelle exécution."), "en campagne : la seule issue"


def test_une_ligne_au_compte_supprime_n_est_pas_un_ecart_a92_s_en_charge(conn, monkeypatch):
    from testpilot.api.services import run_service
    from testpilot.store.repositories import ProjectAccountRepo

    projet, lecteur, _ = _projet_explore(conn, monkeypatch)
    cas, vid = _cas(conn, projet, ecrit_pour={"compte_id": None, "libelle": "principal", "vue": "principal"})
    _lignes(conn, projet, cas["id"], [("L1", None), ("L2", lecteur)])
    ProjectAccountRepo(conn).supprimer(projet["id"], lecteur)
    assert not [e for e in run_service.ecarts_cas_test(conn, cas, vid) if "est jouée en tant que" in e]


def test_falsifiable_allume_une_ligne_au_compte_supprime_n_appelle_jamais_l_ia(conn, monkeypatch):
    from testpilot.store.repositories import ProjectAccountRepo

    projet, lecteur, _ = _projet_explore(conn, monkeypatch)
    cas, _ = _cas(conn, projet)
    _lignes(conn, projet, cas["id"], [("L1", None), ("L2", lecteur)])
    ProjectAccountRepo(conn).supprimer(projet["id"], lecteur)
    monkeypatch.setenv(interrupteurs.ENV_GENERATION_PAR_COMPTE, "1")
    vus = _automatiser(conn, monkeypatch, cas["id"])
    assert "generate" not in vus and "connecteur" not in vus
    assert vus["job"]["error"].startswith("Données de test : la ligne « L2 » est jouée avec un compte supprimé")


def test_une_seule_consigne_quand_les_lignes_ont_leur_compte_et_elle_dit_de_qui_sont_les_ecrans():
    plan = TestPlan(module_name="m", models=[], scenarios=[], personas=["u"], portal_routes=[], risks=[],
                    connector_type="odoo", cost_usd=0.0, raw_spec="x")
    message = prompt_mod.build_initial_message(plan, None, comptes_des_lignes=[{"nom": "L1", "libelle": "Lecteur"}],
                                               ecrans_de="principal")
    assert "Les écrans mesurés ci-dessus sont ceux de « principal »" in message
    assert "## Compte avec lequel ce test sera joué" not in message



def test_falsifiable_l_agent_n_envoie_qu_une_consigne_et_dit_de_qui_sont_les_ecrans(monkeypatch):
    """Revue (seconde passe) : prouvé en passant par `GenerationAgent.generate` — cas joué en Lecteur (écrans de Lecteur) avec
    des lignes à compte : la consigne des lignes seule, et « ceux de « Lecteur » »."""
    from testpilot.generation import agent as agent_mod

    vus = {}

    def _message(*a, **kw):
        vus.update(kw)
        raise RuntimeError("arrêt du test")
    monkeypatch.setattr(agent_mod.prompt_mod, "build_initial_message", _message)
    cible = mdc.ModeleDuCas(modele={"pages": {}}, compte={"id": 4, "libelle": "Lecteur", "empreinte": "e"}, vue="compte",
                            comptes_des_lignes=[{"nom": "L1", "libelle": "Manager", "compte_id": 7}])
    plan = TestPlan(module_name="m", models=[], scenarios=[], personas=["u"], portal_routes=[], risks=[],
                    connector_type="odoo", cost_usd=0.0, raw_spec="x")
    agent = agent_mod.GenerationAgent.__new__(agent_mod.GenerationAgent)
    with pytest.raises(RuntimeError, match="arrêt du test"):
        agent.generate(plan, projet={"id": 1}, modele_du_cas=cible)
    assert "compte_du_test" not in vus and vus["ecrans_de"] == "Lecteur"
    assert vus["comptes_des_lignes"] == cible.comptes_des_lignes


def test_falsifiable_allume_une_premiere_ligne_sans_mot_de_passe_n_appelle_jamais_l_ia(conn, monkeypatch):
    from testpilot.store.repositories import ProjectAccountRepo

    projet, lecteur, manager = _projet_explore(conn, monkeypatch)
    ProjectAccountRepo(conn).modifier(projet["id"], manager, password="")
    cas, _ = _cas(conn, projet)
    _lignes(conn, projet, cas["id"], [("L1", manager), ("L2", lecteur)])
    monkeypatch.setenv(interrupteurs.ENV_GENERATION_PAR_COMPTE, "1")
    vus = _automatiser(conn, monkeypatch, cas["id"])
    assert "generate" not in vus and vus["job"]["error"].startswith("Manager : compte sans mot de passe")
