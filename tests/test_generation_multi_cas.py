"""Génération multi-cas (§9, 2026-08-05), mise à PLAT à l'étape 3 (2026-08-07) : une spécification
produit une liste plate de cas — plus aucune Section auto-créée par user story. L'utilisateur
choisit lui-même, sur l'écran de validation, la Section de chaque cas (existante ou nouvelle,
créée par le MÊME endpoint que partout ailleurs dans l'app) — ou aucune, auquel cas le cas repart
sur l'enveloppe automatique 1:1 déjà en place (`CaseRepo.create`).

Ces tests portent sur l'ORCHESTRATION de `generation_service.resume_generation` (répétition du
pipeline mono-cas déjà testé) — pas sur la génération Gherkin elle-même (connecteur, dry-run, agent
technique), neutralisée ici via `GenerationAgent.generate` pour n'exercer que `_persist` (déjà
couvert en détail par `test_generation_deux_passes.py`).

Ce que ces tests figent :
- `resume_generation` NE CRÉE PLUS AUCUNE Section — elle range chaque cas dans le `group_id` reçu,
  tel quel ;
- un cas SANS `group_id` repart sur l'enveloppe automatique (une par cas, jamais partagée) ;
- un `group_id` invalide (Section disparue, ou d'un AUTRE module) replie sur l'enveloppe
  automatique SANS faire échouer le cas — juste signalé dans `error` ;
- plusieurs cas peuvent partager la MÊME Section (choisie par l'utilisateur), sans qu'aucun nombre
  ne soit imposé ;
- `refs` de chaque cas porte le nom de sa user story d'origine — un simple repère de provenance,
  jamais une Section ;
- le découpage ET chaque passe métier sont comptés au ledger (orphelins, avant tout cas créé) ;
- la reprise fonctionne avec une liste de cas RÉDUITE par rapport à la proposition initiale —
  aucune trace des cas retirés n'apparaît.
"""

import json
from datetime import datetime, timedelta, timezone

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
    GenerationJobRepo,
    ModuleRepo,
    ProjectRepo,
)

_PROJET_CONNECTE = {"name": "P", "connector_type": "odoo", "base_url": "http://recette:8069",
                    "database": "db", "username": "qa", "password": "p"}


@pytest.fixture
def conn(tmp_path, monkeypatch):
    path = tmp_path / "multi.db"
    monkeypatch.setattr(config, "DB_PATH", path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
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
    code), pour exercer la persistance réelle (Section, refs, coût)."""
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


_PROJET_WEB = {"name": "P-web", "connector_type": "web", "base_url": "https://www.saucedemo.com",
              "username": "standard_user", "password": "secret_sauce"}


def _module_web(conn) -> int:
    pid = ProjectRepo(conn).create(**_PROJET_WEB)
    return ModuleRepo(conn).create(project_id=pid, name="M-web")


def _cas(titre: str, *, user_story: str = "") -> dict:
    return {"title": titre, "preconditions": "", "steps": [f"Étape de {titre}"],
           "expected_result": f"Verdict de {titre}", "user_story": user_story}


def _resume(conn, job_id: str, *, module_id: int, **kw):
    """Appelle `resume_generation` comme le fait la route : le job existe TOUJOURS déjà à ce
    stade (créé par `start_generation`, mis à jour par `validate_metier`) — jamais appelé à
    froid en production. On reproduit cette précondition ici plutôt que de l'assouplir dans le
    code de production pour un usage que la vraie route ne fait jamais."""
    if GenerationJobRepo(conn).get(job_id) is None:
        GenerationJobRepo(conn).creer(job_id, module_id=module_id)
    generation_service.resume_generation(job_id, module_id=module_id, **kw)


# ── Choix du connecteur selon `connector_type` (bug SauceDemo, 2026-09-11) ────────────────────

def test_resume_generation_sur_un_projet_web_N_APPELLE_JAMAIS_odoo(conn, monkeypatch):
    """⚠️ Le vrai bug qui a atteint `/dev` : `resume_generation` construisait TOUJOURS un
    `OdooConnector`, même pour un projet `web` — `odoorpc` tentait alors du JSON-RPC contre un
    site qui n'en a évidemment aucun (SauceDemo), et la génération technique plantait en
    `HTTP Error 405: Method Not Allowed` avant d'écrire le moindre test, alors que l'exploration,
    elle, avait parfaitement réussi sur ce même projet. Garde qu'AUCUN appel à
    `OdooConnector.from_project` ne se produit pour un projet `web`, et que
    `GenericWebConnector.from_project` est bien celui utilisé à sa place."""
    from testpilot.analysis import spec_analyzer as sa
    from testpilot.connectors import generic_web as gw_mod
    from testpilot.connectors import odoo as odoo_mod

    mid = _module_web(conn)
    monkeypatch.setattr(sa.SpecAnalyzer, "analyze_spec_content",
                        lambda self, slug, content: _plan(content))
    monkeypatch.setattr("testpilot.execution.behave_runner.BehaveRunner", lambda **kw: object())

    appels_odoo: list[int] = []
    appels_web: list[int] = []

    def _faux_connecteur(*_a, **_kw):
        return type("C", (), {"connect": lambda s: None, "disconnect": lambda s: None})()

    monkeypatch.setattr(odoo_mod.OdooConnector, "from_project",
                        classmethod(lambda cls, *a, **kw: (appels_odoo.append(1),
                                                           _faux_connecteur())[1]))
    monkeypatch.setattr(gw_mod.GenericWebConnector, "from_project",
                        classmethod(lambda cls, *a, **kw: (appels_web.append(1),
                                                           _faux_connecteur())[1]))

    reel_persist = agent_mod.GenerationAgent._persist

    def faux_generate(self, plan, *, case_id=None, title="", author="", module_id=None,
                      metier=None, group_id=None, projet=None, refs=""):
        from testpilot.generation.state import GenerationResult
        result = GenerationResult(success=True, module_name=plan.module_name,
                                  stopped_reason="done", dry_run_passed=True, iterations=1,
                                  cost_usd=0.02, feature_content="# f", steps_content="# s",
                                  spec_hash="h", awaiting_review=True)
        reel_persist(self, plan, result, case_id=case_id, title=title, author=author,
                    module_id=module_id, metier=metier, group_id=group_id, refs=refs)
        return result

    monkeypatch.setattr(agent_mod.GenerationAgent, "generate", faux_generate)

    _resume(conn, "job1", module_id=mid, title="Spec", spec_content="LE TEXTE", author="qa",
           cases=[_cas("Connexion réussie")])

    assert appels_odoo == [], "OdooConnector ne doit JAMAIS être construit pour un projet web"
    assert appels_web == [1]


def test_le_pouls_rafraichit_updated_at_apres_chaque_cas_pas_seulement_a_la_fin(conn, monkeypatch):
    """⚠️ Le vrai bug qui a atteint `/dev` (2026-09-13) : `GenerationJobRepo.get()` réputait un
    job "running" MORT (« le serveur a peut-être redémarré ») après SEUIL_BLOQUE_SECONDES
    (15 min) SANS LA MOINDRE écriture — or `resume_generation` n'écrivait rien avant sa toute
    fin. Une spec à 15 cas contre un site neuf dépassait légitimement ce délai : l'écran
    abandonnait un job qui continuait pourtant réellement en fond, et finissait « done » quelques
    minutes plus tard sans que personne ne le voie. Vieillit le job AVANT de lancer la boucle
    (simule une passe métier déjà longue) : si le pouls fonctionne, `get()` ne doit JAMAIS
    réputer le job mort pendant le traitement du deuxième cas, malgré ce vieillissement initial.

    ⚠️ Les cas sont désormais traités EN PARALLÈLE (2026-09-14, correctif de lenteur) : `conn`
    (la connexion du TEST) ne doit JAMAIS être touchée depuis `faux_generate`, qui s'exécute dans
    un thread ouvrier — sqlite refuse une connexion utilisée hors de son thread d'origine
    (`sqlite3.InterfaceError`). On ouvre donc une connexion FRAÎCHE (même fichier, via
    `config.DB_PATH` déjà pointé par la fixture) à chaque besoin, exactement comme le fait
    `_traiter_un_cas` en production. La concurrence est bornée à 1 ici pour garder un ordre de
    traitement déterministe (cas A puis cas B) — le pouls lui-même ne dépend pas de cet ordre."""
    from testpilot.generation import agent as agent_mod2
    from testpilot.generation.state import GenerationResult
    from testpilot.store.repositories import GenerationJobRepo

    mid = _module(conn)
    from testpilot.analysis import spec_analyzer as sa
    monkeypatch.setattr(sa.SpecAnalyzer, "analyze_spec_content",
                        lambda self, slug, content: _plan(content))
    monkeypatch.setattr("testpilot.connectors.odoo.OdooConnector.from_project",
                        lambda project: type("C", (), {"connect": lambda s: None,
                                                       "disconnect": lambda s: None})())
    monkeypatch.setattr("testpilot.execution.behave_runner.BehaveRunner", lambda **kw: object())
    monkeypatch.setattr(config, "MAX_CONCURRENT_JOBS", 1)

    job_id = "job-pouls"
    GenerationJobRepo(conn).creer(job_id, module_id=mid)

    statut_vu_au_2e_cas = {}
    reel_persist = agent_mod2.GenerationAgent._persist
    appels = {"n": 0}

    def faux_generate(self, plan, *, case_id=None, title="", author="", module_id=None,
                      metier=None, group_id=None, projet=None, refs=""):
        appels["n"] += 1
        if appels["n"] == 1:
            # Simule le TEMPS RÉELLEMENT ÉCOULÉ pendant la génération technique du premier cas
            # (ex. 16 minutes sur un site neuf, sans bibliothèque de steps à réutiliser) — APRÈS
            # le démarrage de la boucle, pas avant : c'est bien le scénario réel (un job qui
            # avance légitimement lentement), pas un job mort avant même d'avoir commencé.
            passe = (datetime.now(timezone.utc)
                    - timedelta(seconds=GenerationJobRepo.SEUIL_BLOQUE_SECONDES + 60)).isoformat()
            conn_frais = get_initialized_db(config.DB_PATH)
            conn_frais.execute("UPDATE generation_job SET updated_at=? WHERE id=?",
                               (passe, job_id))
            conn_frais.commit()
            conn_frais.close()
        if appels["n"] == 2:
            # Le pouls du PREMIER cas (déclenché par `resume_generation` juste après ce
            # vieillissement simulé) doit déjà avoir rafraîchi updated_at — get() ne doit donc
            # PAS réputer le job mort ici.
            conn_frais = get_initialized_db(config.DB_PATH)
            try:
                statut_vu_au_2e_cas["status"] = GenerationJobRepo(conn_frais).get(job_id)["status"]
            finally:
                conn_frais.close()
        result = GenerationResult(success=True, module_name=plan.module_name,
                                  stopped_reason="done", dry_run_passed=True, iterations=1,
                                  cost_usd=0.01, feature_content="# f", steps_content="# s",
                                  spec_hash="h", awaiting_review=True)
        reel_persist(self, plan, result, case_id=case_id, title=title, author=author,
                    module_id=module_id, metier=metier, group_id=group_id, refs=refs)
        return result

    monkeypatch.setattr(agent_mod2.GenerationAgent, "generate", faux_generate)

    _resume(conn, job_id, module_id=mid, title="Spec", spec_content="LE TEXTE", author="qa",
           cases=[_cas("Cas A"), _cas("Cas B")])

    assert statut_vu_au_2e_cas["status"] == "running", (
        "le job a été déclaré mort en cours de route alors qu'il avançait réellement")
    assert GenerationJobRepo(conn).get(job_id)["status"] == "done"


# ── group_id choisi par l'utilisateur : aucune Section auto-créée ─────────────

def test_resume_generation_NE_CREE_AUCUNE_section(conn, monkeypatch):
    """Le cœur de l'étape 3 : avant, une Section naissait par user story. Plus maintenant — le
    nombre de Sections dans le module ne bouge PAS après la génération."""
    mid = _module(conn)
    _neutraliser_pipeline_technique(monkeypatch)
    avant = len(CaseGroupRepo(conn).list_for_module(mid))

    _resume(conn, "job1", module_id=mid, title="Spec", spec_content="LE TEXTE", author="qa",
           cases=[_cas("Connexion réussie")])

    apres = len(CaseGroupRepo(conn).list_for_module(mid))
    # Le cas SANS `group_id` retombe sur son enveloppe auto 1:1 (`CaseRepo.create`) — CETTE
    # Section-là existe, mais ce n'est pas `resume_generation` qui l'a fabriquée : c'est le même
    # mécanisme qu'un cas manuel créé sans section, inchangé depuis toujours.
    assert apres == avant + 1


def test_un_cas_avec_group_id_atterrit_DANS_cette_section(conn, monkeypatch):
    mid = _module(conn)
    _neutraliser_pipeline_technique(monkeypatch)
    cible = CaseGroupRepo(conn).create(module_id=mid, title="Ma section à moi")

    _resume(conn, "job1", module_id=mid, title="Spec", spec_content="LE TEXTE", author="qa",
           group_id=cible, cases=[_cas("Connexion réussie")])

    cas = CaseRepo(conn).list_all(module_id=mid)
    assert len(cas) == 1
    assert cas[0]["group_id"] == cible


def test_plusieurs_cas_PARTAGENT_la_meme_section_choisie_UNE_FOIS_pour_le_lot(conn, monkeypatch):
    """La Section est choisie une fois, avant la génération (étape 3bis) — tous les cas du lot
    y atterrissent, quelle que soit leur user story d'origine."""
    mid = _module(conn)
    _neutraliser_pipeline_technique(monkeypatch)
    section = CaseGroupRepo(conn).create(module_id=mid, title="Connexion")

    _resume(conn, "job1", module_id=mid, title="Spec", spec_content="LE TEXTE", author="qa",
           group_id=section,
           cases=[_cas("Connexion réussie"), _cas("Connexion refusée")])

    cas = CaseRepo(conn).list_all(module_id=mid)
    assert {c["group_id"] for c in cas} == {section}
    assert len(cas) == 2


def test_un_cas_SANS_group_id_repart_sur_SA_PROPRE_enveloppe(conn, monkeypatch):
    """Deux cas sans section choisie : chacun la sienne, jamais partagée entre eux."""
    mid = _module(conn)
    _neutraliser_pipeline_technique(monkeypatch)

    _resume(conn, "job1", module_id=mid, title="Spec", spec_content="LE TEXTE", author="qa",
           cases=[_cas("Cas A"), _cas("Cas B")])

    cas = CaseRepo(conn).list_all(module_id=mid)
    assert len(cas) == 2
    assert cas[0]["group_id"] != cas[1]["group_id"]


def test_un_group_id_INTROUVABLE_replie_TOUT_LE_LOT_sur_l_enveloppe_auto(conn, monkeypatch):
    """Section supprimée entre le lancement et la génération (rare, mais possible) : les cas
    doivent quand même être créés — juste pas où prévu — et le repli doit être VISIBLE, pas
    silencieux. Validé UNE SEULE FOIS pour tout le lot, pas cas par cas (étape 3bis)."""
    mid = _module(conn)
    _neutraliser_pipeline_technique(monkeypatch)

    _resume(conn, "job1", module_id=mid, title="Spec", spec_content="LE TEXTE", author="qa",
           group_id=999999, cases=[_cas("Connexion réussie"), _cas("Connexion refusée")])

    cas = CaseRepo(conn).list_all(module_id=mid)
    assert len(cas) == 2
    assert all(c["group_id"] != 999999 for c in cas)   # replié sur une enveloppe réelle
    assert cas[0]["group_id"] != cas[1]["group_id"]     # chacune la sienne, jamais partagée

    job = generation_service.get_job(conn, "job1")
    assert job["status"] == "done"
    assert "n'existe plus" in job["error"]


def test_un_group_id_d_un_AUTRE_module_replie_aussi_sur_l_enveloppe_auto(conn, monkeypatch):
    mid = _module(conn)
    autre_mid = ModuleRepo(conn).create(
        project_id=ProjectRepo(conn).create(**{**_PROJET_CONNECTE, "name": "Autre"}), name="Autre module")
    section_ailleurs = CaseGroupRepo(conn).create(module_id=autre_mid, title="Pas ici")
    _neutraliser_pipeline_technique(monkeypatch)

    _resume(conn, "job1", module_id=mid, title="Spec", spec_content="LE TEXTE", author="qa",
           group_id=section_ailleurs, cases=[_cas("Connexion réussie")])

    cas = CaseRepo(conn).list_all(module_id=mid)
    assert len(cas) == 1
    assert cas[0]["group_id"] != section_ailleurs
    assert CaseGroupRepo(conn).get(cas[0]["group_id"])["module_id"] == mid


def test_un_cas_en_ECHEC_TECHNIQUE_ne_fait_PAS_echouer_les_cas_DEJA_persistes(conn, monkeypatch):
    """⚠️ Bug réel, mesuré le 2026-08-05 sur une vraie génération (spec « mutation payeur ») :
    un chemin Windows trop long (`[Errno 2] No such file or directory`) sur UN cas faisait
    échouer TOUT le job — alors que les cas précédents de la même boucle étaient déjà persistés
    en base. Le job doit rester `done` si d'autres cas de la boucle ont réussi, avec l'échec du
    cas fautif SEULEMENT rapporté dans `error`."""
    mid = _module(conn)
    _neutraliser_pipeline_technique(monkeypatch)

    reel_generate = agent_mod.GenerationAgent.generate

    def generate_avec_un_echec_technique(self, plan, **kw):
        if "PLANTE" in (kw.get("metier") or {}).get("title", ""):
            raise OSError(2, "No such file or directory", "chemin trop long")
        return reel_generate(self, plan, **kw)

    monkeypatch.setattr(agent_mod.GenerationAgent, "generate", generate_avec_un_echec_technique)

    _resume(conn, "job1", module_id=mid, title="Spec", spec_content="LE TEXTE", author="qa",
           cases=[_cas("Connexion réussie"), _cas("PLANTE ici")])

    cas = CaseRepo(conn).list_all(module_id=mid)
    assert {c["title"] for c in cas} == {"Connexion réussie"}, (
        "le cas qui a réussi AVANT le crash doit rester persisté")

    job = generation_service.get_job(conn, "job1")
    assert job["status"] == "done", "un autre cas de la boucle a réussi — le job ne doit pas échouer"
    assert "PLANTE ici" in job["error"], "l'échec technique doit être rapporté, pas avalé"


# ── refs = nom de la story d'origine (simple provenance, jamais une Section) ──

def test_refs_de_chaque_cas_est_le_nom_de_sa_story_d_origine(conn, monkeypatch):
    mid = _module(conn)
    _neutraliser_pipeline_technique(monkeypatch)

    _resume(conn, "job3", module_id=mid, title="Spec", spec_content="LE TEXTE", author="qa",
           cases=[_cas("Connexion réussie", user_story="Connexion"),
                 _cas("Lien valide", user_story="Réinitialisation"),
                 _cas("Lien expiré", user_story="Réinitialisation")])

    cas = CaseRepo(conn).list_all(module_id=mid)
    refs_par_titre = {c["title"]: c["refs"] for c in cas}
    assert refs_par_titre == {
        "Connexion réussie": "Connexion",
        "Lien valide": "Réinitialisation",
        "Lien expiré": "Réinitialisation",
    }


# ── Le coût : découpage + N passes métier + N générations ────────────────────

def test_le_cout_de_chaque_cas_genere_est_enregistre_au_ledger(conn, monkeypatch):
    mid = _module(conn)
    _neutraliser_pipeline_technique(monkeypatch, cout_par_cas=0.05)

    _resume(conn, "job5", module_id=mid, title="Spec", spec_content="LE TEXTE", author="qa",
           cases=[_cas("Connexion réussie"), _cas("Lien valide"), _cas("Lien expiré")])

    # 3 cas générés à 0,05 $ + l'analyse partagée (neutralisée à $0, donc aucune ligne orpheline
    # supplémentaire — `_record_generation_cost` n'écrit jamais une ligne à $0).
    assert CostRepo(conn).monthly_total_usd() == pytest.approx(0.15)
    for c in CaseRepo(conn).list_all(module_id=mid):
        phases = {r["phase"] for r in CostRepo(conn).breakdown_for_case(c["id"])}
        assert "generation" in phases


def test_le_decoupage_et_les_N_passes_metier_sont_comptes_AU_LEDGER_avant_tout_cas(conn, monkeypatch):
    """`run_generation` (la passe 4a) enregistre le coût du découpage ET de chaque passe métier —
    en lignes ORPHELINES, puisqu'aucun cas n'existe encore à ce stade (ils naissent tous ensemble
    à la validation, §9b). Le découpage par story reste un OUTIL INTERNE de l'IA (§9a) : son coût
    existe toujours, même si son résultat ne crée plus de Section."""
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

    job = generation_service.get_job(conn, job_id)
    assert job["status"] == "awaiting_metier"
    # La liste est PLATE : deux cas, chacun avec sa provenance (`user_story`), pas de Section.
    assert len(job["cases"]) == 2
    assert {c["user_story"] for c in job["cases"]} == {"Connexion"}
    phases = {r["phase"] for r in conn.execute(
        "SELECT DISTINCT phase FROM cost_ledger WHERE test_case_id IS NULL")}
    assert "decoupage" in phases
    assert "metier" in phases
    # Deux passes métier (une par cas planifié) à 0,02 $ + le découpage à 0,01 $.
    assert CostRepo(conn).monthly_total_usd() == pytest.approx(0.05)


# ── La reprise avec une liste RÉDUITE ─────────────────────────────────────────

def test_la_reprise_avec_une_liste_REDUITE_ne_laisse_AUCUNE_TRACE_des_cas_retires(conn, monkeypatch):
    """L'utilisateur a supprimé un cas à la validation : SEULE la liste réduite arrive à
    `resume_generation` (jamais la proposition complète) — rien ne doit trahir l'existence du cas
    écarté."""
    mid = _module(conn)
    _neutraliser_pipeline_technique(monkeypatch)
    # La proposition initiale portait 2 cas ; l'humain n'a retenu que le premier. C'est CETTE
    # liste réduite, et RIEN d'autre, qui est passée ici.
    _resume(conn, "job6", module_id=mid, title="Spec", spec_content="LE TEXTE", author="qa",
           cases=[_cas("Connexion réussie", user_story="Connexion")])

    cas = CaseRepo(conn).list_all(module_id=mid)
    assert [c["title"] for c in cas] == ["Connexion réussie"]
    assert "abandonné" not in json.dumps(cas, ensure_ascii=False)


def test_bout_en_bout_valide_PUIS_reprise_AVEC_une_liste_reduite(conn, monkeypatch):
    """De bout en bout : le job propose 2 cas pour une Section déjà choisie AVANT la génération
    (étape 3bis), l'humain n'en valide qu'UN via `validate_metier` — c'est cette liste réduite,
    et RIEN d'autre, que `resume_generation` reçoit et persiste, toujours dans la même Section."""
    mid = _module(conn)
    _neutraliser_pipeline_technique(monkeypatch)
    section = CaseGroupRepo(conn).create(module_id=mid, title="Connexion")
    job_id = "job7"
    GenerationJobRepo(conn).creer(job_id, module_id=mid, payload={
        "title": "Spec", "author": "qa", "spec_content": "LE TEXTE", "group_id": section,
    })
    GenerationJobRepo(conn).maj(
        job_id, status="awaiting_metier",
        cases=[_cas("Connexion réussie", user_story="Connexion"),
              _cas("Connexion via SSO", user_story="Connexion")])

    # L'écran de validation envoie la liste ÉDITÉE : un seul cas retenu. La Section, elle, était
    # déjà fixée avant la génération — `validate_metier` n'y touche pas.
    params = generation_service.validate_metier(
        conn, job_id, [_cas("Connexion réussie", user_story="Connexion")])
    generation_service.resume_generation(job_id, **params)

    cas = CaseRepo(conn).list_all(module_id=mid)
    assert [c["title"] for c in cas] == ["Connexion réussie"]
    assert cas[0]["group_id"] == section
    job = generation_service.get_job(conn, job_id)
    assert job["status"] == "done"
    assert len(job["case_ids"]) == 1


def test_validate_metier_REFUSE_si_PLUS_AUCUN_cas_n_est_retenu(conn):
    """Tous les cas supprimés à la validation : rien à générer, on le dit plutôt que de démarrer
    un job vide."""
    job_id = "jobY"
    GenerationJobRepo(conn).creer(job_id, module_id=1, payload={
        "title": "T", "author": "qa", "spec_content": "s",
    })
    GenerationJobRepo(conn).maj(job_id, status="awaiting_metier", cases=[_cas("Connexion réussie")])

    with pytest.raises(generation_service.GenerationError) as exc:
        generation_service.validate_metier(conn, job_id, [])
    assert exc.value.code == "invalid_metier"


def test_validate_metier_TRANSPORTE_le_group_id_du_job_SANS_le_toucher(conn):
    """La Section (`group_id`) vit dans le job, fixée AVANT la génération — `validate_metier`
    ne la lit ni ne l'écrit, elle voyage telle quelle jusqu'à `resume_generation` (étape 3bis)."""
    job_id = "jobZ"
    GenerationJobRepo(conn).creer(job_id, module_id=1, payload={
        "title": "T", "author": "qa", "spec_content": "s", "group_id": 42,
    })
    GenerationJobRepo(conn).maj(job_id, status="awaiting_metier", cases=[_cas("Connexion réussie")])

    params = generation_service.validate_metier(
        conn, job_id, [_cas("Connexion réussie"), _cas("Connexion via SSO")])

    assert params["group_id"] == 42
    assert "group_id" not in params["cases"][0]   # plus de group_id PAR CAS (revenu en arrière)
