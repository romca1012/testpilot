"""Décision 0014, étape 3 — L'ORCHESTRATEUR pilote la boucle, jamais l'agent.

Le design (b), arbitré : `repair_circuit.evaluate()` décide de continuer ou d'arrêter ; l'agent
ne fait que **proposer** une correction. Lui donner ce pouvoir remettrait le garde-fou dans les
mains du composant qu'il encadre — et `0012` a montré que le circuit lit un texte que l'agent
écrit lui-même.

Tests déterministes : ni Behave, ni Odoo, ni LLM. `run_once` et l'agent sont injectés.
"""

from dataclasses import dataclass, field

import pytest

from testpilot import config
from testpilot.api.services import repair_service
from testpilot.generation.repair_agent import RepairProposal
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import (
    CaseRepo,
    ExecutionRepo,
    RepairRepo,
    ReviewRepo,
    VersionRepo,
)


# ── Doublures ─────────────────────────────────────────────────────────────────

@dataclass
class _Failure:
    """Fidèle à l'échec RÉEL du cas 2 (exécutions 4 à 7) — le témoin de `0014`.

    ⚠️ Ce commentaire disait exactement l'inverse jusqu'à `0015` : « la cause vient du mot
    `team_id` dans le **step_text**, pas de l'erreur ; un `TypeError` nu tomberait en
    `unknown` ». C'était vrai, et c'était le défaut — le classement dépendait d'un libellé
    **écrit par l'agent**. Depuis `0015`, la cause vient du TYPE d'exception (`raw`) :
    `TypeError` → `broken_test_code` → réparable, quel que soit le nom du step.

    `step_text` reste ici parce que c'est le vrai libellé du cas 2 (et qu'il est désormais
    persisté pour l'audit), mais il n'a plus AUCUN effet sur le classement — c'est précisément
    ce que garde `tests/test_taxonomy_signal.py`.
    """

    scenario_name: str = "[Nominal] — Raison de demande renseignée"
    step_text: str = 'Alors le dernier ticket créé a le champ "team_id" pointant vers "Matériel"'
    failure_type: str = "unknown"
    traceback_summary: str = ""
    raw: str = "TypeError: 'int' object is not subscriptable"


@dataclass
class _Scenario:
    name: str = "[Nominal]"
    status: str = "failed"
    error: str = ""


@dataclass
class _RealRun:
    failures: list = field(default_factory=list)
    scenarios: list = field(default_factory=lambda: [_Scenario()])
    returncode: int = 1


@dataclass
class _Outcome:
    """Miroir d'`ExecutionOutcome` — `derive_verdict` le lit pour l'axe EXÉCUTION (0016).

    `dry_run_passed` et `returncode` ne sont pas décoratifs : le critère d'adoption délègue à
    `derive_verdict`, qui les lit. Une doublure qui les omettrait testerait un objet que la
    production ne produit jamais.
    """

    # `real_run=None` = le test n'a PAS tourné (dry-run en échec) — le cas du bug trouvé en réel.
    real_run: _RealRun | None
    execution_id: int | None = None
    dry_run_passed: bool = True
    module_name: str = "cas"


# Un SECOND échec, réellement différent mais toujours porteur d'un signal — ce que produit un
# vrai run. Les doublures passaient auparavant un texte nu (« encore », « autre erreur ») : sans
# type d'exception, il n'y a rien à classer, et depuis `0015` un échec inclassable s'arrête pour
# confirmation humaine (`unknown` → `indetermine`) au lieu d'être réparé sur la foi d'un mot du
# libellé. Le comportement testé — deux tentatives puis succès — reste le même.
AUTRE_ERREUR = "AttributeError: 'NoneType' object has no attribute 'id'"


def _echec(raw="TypeError: 'int' object is not subscriptable"):
    return _Outcome(real_run=_RealRun(failures=[_Failure(raw=raw)]))


def _succes():
    return _Outcome(real_run=_RealRun(failures=[], scenarios=[_Scenario(status="passed")]))


def _tourne_mais_bug_applicatif():
    """Le test TOURNE et révèle un vrai bug — la forme exacte du cas 1 réparé (`v9`, exec 17).

    Un scénario passe, un autre échoue sur une ASSERTION : `derive_verdict` rend donc
    `success/non_conforme` — l'axe exécution dit « ça tourne », l'axe fonctionnel dit
    « l'application ne se conforme pas ». C'est un **constat**, ce pour quoi l'outil existe.

    ⚠️ Les noms doivent coïncider entre scénario et échec : `status._failures_by_scenario`
    regroupe par `scenario_name`.
    """
    echec = _Failure(scenario_name="[ERREUR] Produit invalide",
                     step_text="Alors une erreur est affichée",
                     failure_type="assertion",
                     raw="ASSERT FAILED: l'application a accepté un produit invalide")
    return _Outcome(real_run=_RealRun(
        failures=[echec],
        scenarios=[_Scenario(name="[NOMINAL] Demande complète", status="passed"),
                   _Scenario(name="[ERREUR] Produit invalide", status="failed")]))


@pytest.fixture
def conn(tmp_path):
    c = get_initialized_db(tmp_path / "r.db")
    yield c
    c.close()


def _cas(conn, *, budget=2, module_id=None):
    cid = CaseRepo(conn).create(title="Cas", feature_slug="cas", module_id=module_id)
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="spec", spec_hash="h",
                                   feature_content="# feature v1", steps_content="# steps v1")
    CaseRepo(conn).set_current_version(cid, vid)
    ReviewRepo(conn).create(test_case_id=cid, version_id=vid, decision="approved",
                            reviewer="qa", repair_budget=budget)
    eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid)
    return cid, vid, eid


def _agent(monkeypatch, *suites):
    """L'agent rend successivement les propositions données. Compte ses invocations."""
    appels = {"n": 0}
    sequence = list(suites)

    def faux_propose(**kwargs):
        appels["n"] += 1
        return sequence.pop(0) if sequence else RepairProposal(changed=False)

    monkeypatch.setattr(repair_service.repair_agent, "propose_fix", faux_propose)
    return appels


def _runner(conn, cid, resultats):
    """`run_once` injecté : crée une exécution et rend le résultat prévu."""
    suite = list(resultats)

    def run_once(version_id):
        eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=version_id, trigger="rerun")
        out = suite.pop(0) if suite else _echec()
        out.execution_id = eid
        return out

    return run_once


# ── Le chemin « répare » ──────────────────────────────────────────────────────

def test_une_reparation_qui_reussit_adopte_la_nouvelle_version(conn, monkeypatch):
    cid, vid, eid = _cas(conn, budget=2)
    _agent(monkeypatch, RepairProposal(changed=True, steps_content="# steps v2 corrigé",
                                       summary="search() rend des ids : browse() ajouté."))
    depart = _echec(); depart.execution_id = eid

    session = repair_service.run_repair_loop(
        conn, case_id=cid, version_id=vid, module_name="cas",
        outcome=depart, run_once=_runner(conn, cid, [_succes()]))

    assert session.attempts == 1
    assert session.outcome == "resolved" and session.resolved

    # Une tentative = une VERSION (trace honnête de ce qui a été tenté).
    versions = VersionRepo(conn).list_for_case(cid)
    assert len(versions) == 2
    v2 = [v for v in versions if v["id"] != vid][0]
    assert v2["steps_content"] == "# steps v2 corrigé"
    assert "browse()" in v2["change_summary"]      # ce que l'agent DIT avoir fait

    # La version réparée devient la référence…
    assert CaseRepo(conn).get(cid)["current_version_id"] == v2["id"]


def test_la_version_reparee_n_est_JAMAIS_approuvee_d_office(conn, monkeypatch):
    """LE test de l'option (i). Fabriquer une `review_decision` signée par l'IA serait
    l'auto-approbation écartée : une version que personne n'a relue n'est jamais approuvée,
    quelle que soit la justification."""
    cid, vid, eid = _cas(conn, budget=2)
    _agent(monkeypatch, RepairProposal(changed=True, steps_content="# v2", summary="corrigé"))
    depart = _echec(); depart.execution_id = eid

    repair_service.run_repair_loop(conn, case_id=cid, version_id=vid, module_name="cas",
                                   outcome=depart, run_once=_runner(conn, cid, [_succes()]))

    v2 = CaseRepo(conn).get(cid)["current_version_id"]
    # Aucune décision de relecture sur v2 — donc le gate la refuse pour tout run FUTUR.
    assert ReviewRepo(conn).latest_for_version(v2) is None
    assert ReviewRepo(conn).is_version_approved(v2) is False
    # …et la ratification attendue se lit sur la VERSION, seul endroit où elle s'inscrit : le
    # statut recopié sur le cas est parti avec la migration 25 (il redisait ceci, en moins fidèle).
    assert CaseRepo(conn).get(cid)["etat"] == "new"


def test_deux_tentatives_avant_de_reussir(conn, monkeypatch):
    cid, vid, eid = _cas(conn, budget=2)
    appels = _agent(monkeypatch,
                    RepairProposal(changed=True, steps_content="# v2", summary="essai 1"),
                    RepairProposal(changed=True, steps_content="# v3", summary="essai 2"))
    depart = _echec(); depart.execution_id = eid

    session = repair_service.run_repair_loop(
        conn, case_id=cid, version_id=vid, module_name="cas",
        outcome=depart, run_once=_runner(conn, cid, [_echec(AUTRE_ERREUR), _succes()]))

    assert appels["n"] == 2 and session.attempts == 2
    assert session.resolved
    assert len(VersionRepo(conn).list_for_case(cid)) == 3      # v1 + 2 tentatives


# ── Le chemin « arrête » — le circuit décide ─────────────────────────────────

def test_budget_zero_n_appelle_meme_pas_l_agent(conn, monkeypatch):
    """budget=0 → `evaluate` coupe au premier tour (0 >= 0), sans cas particulier : le
    garde-fou existant fait le travail. Aucun appel LLM n'est engagé."""
    cid, vid, eid = _cas(conn, budget=0)
    appels = _agent(monkeypatch, RepairProposal(changed=True, steps_content="# v2"))
    depart = _echec(); depart.execution_id = eid

    session = repair_service.run_repair_loop(
        conn, case_id=cid, version_id=vid, module_name="cas",
        outcome=depart, run_once=_runner(conn, cid, [_succes()]))

    assert appels["n"] == 0
    assert session.attempts == 0
    assert session.outcome == "max_iterations"
    assert len(VersionRepo(conn).list_for_case(cid)) == 1     # aucune version créée


def test_version_non_relue_aucune_reparation(conn, monkeypatch):
    """§4.3 : pas de gate, pas d'exécution — donc pas de réparation."""
    cid = CaseRepo(conn).create(title="Cas", feature_slug="cas")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="",
                                   feature_content="", steps_content="")
    CaseRepo(conn).set_current_version(cid, vid)
    eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid)
    appels = _agent(monkeypatch, RepairProposal(changed=True, steps_content="# v2"))
    depart = _echec(); depart.execution_id = eid

    session = repair_service.run_repair_loop(
        conn, case_id=cid, version_id=vid, module_name="cas",
        outcome=depart, run_once=_runner(conn, cid, [_succes()]))
    assert appels["n"] == 0 and session.attempts == 0


def test_un_vrai_bug_arrete_la_boucle_immediatement(conn, monkeypatch):
    """Le signal métier prime : réparer un vrai bug n'a pas de sens, l'app répond faux.
    Arbitrage du porteur : on sur-arrête à tort plutôt que de laisser la réparation courir sur
    une vraie régression (§4.4). Le faux positif est infirmable depuis `0013`."""
    cid, vid, eid = _cas(conn, budget=2)
    appels = _agent(monkeypatch, RepairProposal(changed=True, steps_content="# v2"))
    # ⚠️ step_text SANS mot-clé : sinon `team_id` gagnerait — les catégories sont testées par
    # priorité, et le NOM DU STEP peut donc l'emporter sur l'erreur réelle (angle mort connu,
    # consigné au backlog). Ici « attendu » → ASSERTION_MISMATCH → vrai_bug.
    depart = _Outcome(real_run=_RealRun(failures=[_Failure(
        step_text="Alors le ticket est conforme",
        raw="AssertionError: attendu 26206, obtenu 26205")]))
    depart.execution_id = eid

    session = repair_service.run_repair_loop(
        conn, case_id=cid, version_id=vid, module_name="cas",
        outcome=depart, run_once=_runner(conn, cid, [_succes()]))

    assert appels["n"] == 0
    assert session.outcome == "real_bug"
    assert not session.resolved


def test_un_agent_qui_ne_sait_pas_reparer_arrete_la_boucle(conn, monkeypatch):
    """Un aveu utile vaut mieux qu'une tentative au hasard : insister brûlerait le budget."""
    cid, vid, eid = _cas(conn, budget=2)
    _agent(monkeypatch, RepairProposal(changed=False, summary="Le formulaire refuse un champ "
                                                              "requis que la spec ne cite pas."))
    depart = _echec(); depart.execution_id = eid

    session = repair_service.run_repair_loop(
        conn, case_id=cid, version_id=vid, module_name="cas",
        outcome=depart, run_once=_runner(conn, cid, [_succes()]))

    assert session.attempts == 0
    assert session.outcome == "agent_no_fix"
    assert "champ requis" in session.reason          # son aveu est conservé
    assert len(VersionRepo(conn).list_for_case(cid)) == 1


def test_une_reparation_ratee_ne_change_PAS_la_reference(conn, monkeypatch):
    """La référence reste la version qu'un HUMAIN a approuvée. Les versions tentées demeurent
    en historique — c'est la trace de ce qui a été essayé, pas une promotion."""
    cid, vid, eid = _cas(conn, budget=1)
    _agent(monkeypatch, RepairProposal(changed=True, steps_content="# v2 raté", summary="essai"))
    depart = _echec(); depart.execution_id = eid

    session = repair_service.run_repair_loop(
        conn, case_id=cid, version_id=vid, module_name="cas",
        outcome=depart, run_once=_runner(conn, cid, [_echec()]))

    assert session.attempts == 1 and not session.resolved
    assert CaseRepo(conn).get(cid)["current_version_id"] == vid     # v1 reste la référence
    assert len(VersionRepo(conn).list_for_case(cid)) == 2           # v2 existe en historique
    assert session.final_version_id == vid


# ── Le test qui manquait : « pas de run » ≠ « aucun échec » ──────────────────

def test_un_run_qui_n_a_pas_tourne_n_est_JAMAIS_resolved(conn, monkeypatch):
    """LE bug trouvé en run réel (étape 6), que mes 10 tests avaient laissé passer.

    Quand le dry-run échoue, Behave ne joue rien et `real_run` vaut None → la liste d'échecs
    est vide, **exactement comme un test qui passe**. Le circuit concluait « plus aucun échec —
    réparation terminée » alors que le test n'avait jamais tourné, et la boucle **adoptait une
    version cassée en proclamant sa victoire**. Faux négatif (§4.4) — le motif même de `0010`,
    `0011` et `0013` : l'absence de signal prise pour un signal positif.

    Mesuré en réel : l'exécution 13 (v7) avait **0 scénario** et la réparation s'est déclarée
    réussie. Ce test échoue sur le code d'avant le correctif.
    """
    cid, vid, eid = _cas(conn, budget=2)
    _agent(monkeypatch, RepairProposal(changed=True, steps_content="# v2 qui ne parse plus",
                                       summary="correction qui casse le fichier"))
    depart = _echec(); depart.execution_id = eid

    # Le run de la version « réparée » ne tourne pas : Behave n'a rien joué.
    session = repair_service.run_repair_loop(
        conn, case_id=cid, version_id=vid, module_name="cas",
        outcome=depart, run_once=_runner(conn, cid, [_Outcome(real_run=None)]))

    assert not session.resolved, "un test qui n'a pas tourné n'est PAS une réparation réussie"
    assert session.outcome == repair_service.RUN_FAILED
    assert "ne parse plus" in session.reason
    # …et surtout : la version cassée n'est PAS adoptée.
    assert CaseRepo(conn).get(cid)["current_version_id"] == vid
    assert session.final_version_id == vid


def test_une_version_de_depart_injouable_n_est_pas_reparee(conn, monkeypatch):
    """Même garde à l'entrée : si le run initial n'a pas tourné, il n'y a rien à réparer depuis
    un échec qu'on n'a pas observé — et surtout rien à déclarer résolu."""
    cid, vid, eid = _cas(conn, budget=2)
    appels = _agent(monkeypatch, RepairProposal(changed=True, steps_content="# v2"))
    depart = _Outcome(real_run=None); depart.execution_id = eid

    session = repair_service.run_repair_loop(
        conn, case_id=cid, version_id=vid, module_name="cas",
        outcome=depart, run_once=_runner(conn, cid, [_succes()]))

    assert appels["n"] == 0 and session.attempts == 0
    assert not session.resolved and session.outcome == repair_service.RUN_FAILED


# ── Modèle B : une exécution = un run ────────────────────────────────────────

def test_chaque_tentative_rejouee_cree_sa_propre_execution(conn, monkeypatch):
    """Modèle B : chaque ligne d'exécution reste vraie — une version, un verdict, un run.
    §4.2 tient littéralement, ligne par ligne."""
    cid, vid, eid = _cas(conn, budget=2)
    _agent(monkeypatch,
           RepairProposal(changed=True, steps_content="# v2", summary="a"),
           RepairProposal(changed=True, steps_content="# v3", summary="b"))
    depart = _echec(); depart.execution_id = eid

    repair_service.run_repair_loop(
        conn, case_id=cid, version_id=vid, module_name="cas",
        outcome=depart, run_once=_runner(conn, cid, [_echec(AUTRE_ERREUR), _succes()]))

    execs = ExecutionRepo(conn).list_for_case(cid)
    assert len(execs) == 3                                  # run initial + 2 rejeux
    versions_jouees = {e["version_id"] for e in execs}
    assert len(versions_jouees) == 3                        # chacune sur SA version


# ── what_was_tried : la colonne qui était vide partout ───────────────────────

def test_what_was_tried_est_renseigne(conn, monkeypatch):
    """La colonne existait et était vide partout : elle dit ce que l'agent a tenté.
    « J'ai corrigé » n'apprendrait rien — on stocke ce qu'il DIT avoir changé."""
    cid, vid, eid = _cas(conn, budget=1)
    RepairRepo(conn).create(execution_id=eid, attempt_number=1, failure_signature="sig",
                            cause_category="missing_server_context",
                            defect_origin="test_a_reparer", confirmation_status="pending_human")
    _agent(monkeypatch, RepairProposal(
        changed=True, steps_content="# v2",
        summary="search() rend des ids, pas des dicts : browse() ajouté avant .id"))
    depart = _echec(); depart.execution_id = eid

    repair_service.run_repair_loop(conn, case_id=cid, version_id=vid, module_name="cas",
                                   outcome=depart, run_once=_runner(conn, cid, [_succes()]))

    tente = RepairRepo(conn).list_for_execution(eid)[0]
    assert "browse()" in tente["what_was_tried"]
    assert tente["defect_origin"] == "test_a_reparer"   # le diagnostic machine reste intact


# ── Bug 2 : l'agent doit RENDRE LE FICHIER ENTIER ────────────────────────────

def test_le_contenu_actuel_du_fichier_est_donne_a_l_agent(conn, monkeypatch):
    """Trouvé en run réel (0014 étape 6) : l'agent a rendu le SEUL step qu'il corrigeait.

    `write_steps_file` REMPLACE le fichier → les 3 autres steps ont disparu, le dry-run a
    échoué, le test ne tournait plus. Deux causes : le contrat du tool n'était écrit nulle part
    (« Écrit le fichier… »), et l'agent n'avait pas le contenu actuel — il réécrivait de mémoire.
    Ce test fige le second : le fichier courant DOIT lui parvenir.
    """
    recu = {}

    def faux_propose(**kwargs):
        recu.update(kwargs)
        return RepairProposal(changed=True, steps_content="# v2 entier", summary="ok")

    monkeypatch.setattr(repair_service.repair_agent, "propose_fix", faux_propose)
    cid, vid, eid = _cas(conn, budget=1)
    depart = _echec(); depart.execution_id = eid

    repair_service.run_repair_loop(conn, case_id=cid, version_id=vid, module_name="cas",
                                   outcome=depart, run_once=_runner(conn, cid, [_succes()]))

    assert recu.get("steps_content") == "# steps v1", (
        "l'agent doit recevoir le contenu ACTUEL du fichier : sans lui il réécrit de mémoire "
        "et rend un extrait, ce qui efface les steps qu'il ne cite pas")


def test_le_contrat_des_tools_d_ecriture_dit_qu_ils_REMPLACENT():
    """Le contrat doit être dans la description que l'agent lit à CHAQUE appel, pas seulement
    dans un prompt — c'est le manque qui a produit le fichier tronqué."""
    from testpilot.generation.tools import TOOLS_DEFINITIONS

    for nom in ("write_steps_file", "write_feature_file"):
        outil = next(t for t in TOOLS_DEFINITIONS if t["name"] == nom)
        description = outil["description"]
        assert "REMPLACE" in description, f"{nom} ne dit pas qu'il remplace le fichier"
        assert "ENTIER" in description, f"{nom} n'exige pas le contenu entier"


# ── Bug 3 : le DISQUE doit refléter la version de référence ──────────────────

def test_une_reparation_ratee_resynchronise_le_disque(conn, monkeypatch, tmp_path):
    """Le runner lit le DISQUE, pas la base. `write_steps_file` y a écrit la tentative.

    Si la réparation n'est pas adoptée, la base dit « v1 » mais le disque contient « v2 » :
    le prochain run exécuterait v2 en prétendant v1 — « affiché ≠ réel » (§4.6), et le verdict
    porterait sur un code que personne n'a approuvé. Constaté en réel : le disque gardait v7
    (1 step) quand la base était revenue à v2 (4 steps).
    """
    monkeypatch.setattr(config, "GENERATED_DIR", tmp_path)
    (tmp_path / "cas_steps.py").write_text("# écrit par l'agent, tentative ratée", encoding="utf-8")

    cid, vid, eid = _cas(conn, budget=1)
    _agent(monkeypatch, RepairProposal(changed=True, steps_content="# v2 raté", summary="essai"))
    depart = _echec(); depart.execution_id = eid

    session = repair_service.run_repair_loop(
        conn, case_id=cid, version_id=vid, module_name="cas",
        outcome=depart, run_once=_runner(conn, cid, [_echec()]))

    assert not session.resolved
    # Le disque porte de nouveau la version de RÉFÉRENCE (v1), pas la tentative.
    assert (tmp_path / "cas_steps.py").read_text(encoding="utf-8") == "# steps v1"


def test_une_reparation_reussie_laisse_la_version_adoptee_sur_disque(conn, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "GENERATED_DIR", tmp_path)
    cid, vid, eid = _cas(conn, budget=1)
    _agent(monkeypatch, RepairProposal(changed=True, steps_content="# v2 corrigé", summary="ok"))
    depart = _echec(); depart.execution_id = eid

    session = repair_service.run_repair_loop(
        conn, case_id=cid, version_id=vid, module_name="cas",
        outcome=depart, run_once=_runner(conn, cid, [_succes()]))

    assert session.resolved
    assert (tmp_path / "cas_steps.py").read_text(encoding="utf-8") == "# v2 corrigé"


# ── Décision 0016 : « réparée » = « le test TOURNE », jamais « le test passe » ──
# Le critère d'adoption fusionnait les deux axes (§4.1) : un test réparé qui détecte un vrai bug
# ne pouvait JAMAIS être adopté. Mesuré sur le cas 1 (exec 16 → 17) : la réparation `v9` faisait
# tourner le test et révélait deux vrais échecs d'assertion — elle a été jetée, le disque
# rembobiné sur la version cassée, et le run suivant refaisait le `HTTPError 404`.

def test_un_test_qui_TOURNE_et_revele_un_vrai_bug_est_ADOPTE(conn, monkeypatch):
    """LE test de 0016 — il échoue sur le code d'avant (`resolved` exigeait zéro échec).

    C'est le cas d'usage central : un test existant survit à un changement de contrat technique
    et révèle un vrai problème fonctionnel derrière. La réparation doit être GARDÉE.
    """
    cid, vid, eid = _cas(conn, budget=2)
    _agent(monkeypatch, RepairProposal(changed=True, steps_content="# v2 odoorpc", summary="fix"))
    depart = _echec(); depart.execution_id = eid

    session = repair_service.run_repair_loop(
        conn, case_id=cid, version_id=vid, module_name="cas",
        outcome=depart, run_once=_runner(conn, cid, [_tourne_mais_bug_applicatif()]))

    assert session.executable            # le test tourne : axe EXÉCUTION
    assert not session.resolved          # mais il n'est PAS vert : axe FONCTIONNEL
    assert session.outcome == "real_bug"  # le circuit s'est arrêté sur un vrai bug — et c'est bien

    v2 = CaseRepo(conn).get(cid)["current_version_id"]
    assert v2 != vid, "la réparation qui a révélé le bug doit être ADOPTÉE, pas jetée"
    assert VersionRepo(conn).get(v2)["steps_content"] == "# v2 odoorpc"
    # …et elle n'est jamais approuvée d'office : le gate reste souverain (0014, option (i)).
    assert ReviewRepo(conn).is_version_approved(v2) is False


def test_le_disque_porte_la_version_adoptee_meme_si_elle_n_est_pas_verte(conn, monkeypatch, tmp_path):
    """Le rembobinage du disque suit le critère d'ADOPTION, pas la verdeur du run.

    Sinon la base dirait « v2 » et le disque contiendrait « v1 » — l'inverse exact du défaut que
    `_sync_disque` corrige.
    """
    monkeypatch.setattr(config, "GENERATED_DIR", tmp_path)
    cid, vid, eid = _cas(conn, budget=1)
    _agent(monkeypatch, RepairProposal(changed=True, steps_content="# v2 odoorpc", summary="fix"))
    depart = _echec(); depart.execution_id = eid

    repair_service.run_repair_loop(
        conn, case_id=cid, version_id=vid, module_name="cas",
        outcome=depart, run_once=_runner(conn, cid, [_tourne_mais_bug_applicatif()]))

    assert (tmp_path / "cas_steps.py").read_text(encoding="utf-8") == "# v2 odoorpc"


def test_un_test_qui_ne_tourne_toujours_pas_n_est_PAS_adopte(conn, monkeypatch):
    """La contrepartie : `A` n'adopte pas n'importe quoi. Le critère reste l'axe EXÉCUTION."""
    cid, vid, eid = _cas(conn, budget=1)
    _agent(monkeypatch, RepairProposal(changed=True, steps_content="# v2 rate", summary="essai"))
    depart = _echec(); depart.execution_id = eid

    session = repair_service.run_repair_loop(
        conn, case_id=cid, version_id=vid, module_name="cas",
        outcome=depart, run_once=_runner(conn, cid, [_echec()]))

    assert not session.executable
    assert CaseRepo(conn).get(cid)["current_version_id"] == vid   # v1 reste la référence


def test_une_reparation_qui_casse_le_parsing_n_est_PAS_adoptee(conn, monkeypatch):
    """`real_run=None` (dry-run en échec) : le test ne tourne pas → jamais adopté.

    Garde le bug 1 de `0014` fermé : l'absence d'échecs ne vaut pas succès.
    """
    cid, vid, eid = _cas(conn, budget=1)
    _agent(monkeypatch, RepairProposal(changed=True, steps_content="# v2 cassé", summary="essai"))
    depart = _echec(); depart.execution_id = eid

    session = repair_service.run_repair_loop(
        conn, case_id=cid, version_id=vid, module_name="cas",
        outcome=depart, run_once=_runner(conn, cid, [_Outcome(real_run=None)]))

    assert not session.executable
    assert session.outcome == repair_service.RUN_FAILED
    assert CaseRepo(conn).get(cid)["current_version_id"] == vid


# ── Décision 0016, option (iii) : la divergence est VISIBLE, jamais corrigée en silence ──

def test_la_version_d_origine_du_verdict_est_exposee(conn, monkeypatch):
    """Les `last_*` d'un cas peuvent décrire une version rembobinée : on le DIT.

    On ne recalcule pas le verdict depuis la version courante (option (ii), écartée) : ce serait
    masquer un run réel. On surface — ligne du projet depuis 0007 B+, 0008, 0013.
    """
    from testpilot.api import schemas

    cid, vid, eid = _cas(conn, budget=1)
    _agent(monkeypatch, RepairProposal(changed=True, steps_content="# v2 rate", summary="essai"))
    depart = _echec(); depart.execution_id = eid

    # Réparation qui ne rend PAS le test exécutable → v1 reste la référence, mais le dernier run
    # (celui de la tentative) a écrit les `last_*` du cas.
    repair_service.run_repair_loop(
        conn, case_id=cid, version_id=vid, module_name="cas",
        outcome=depart, run_once=_runner(conn, cid, [_echec()]))

    row = CaseRepo(conn).get(cid)
    assert row["current_version_id"] == vid
    out = schemas.case_summary(row)
    assert out.last_verdict_version_id != vid       # le verdict vient de la tentative…
    assert out.verdict_from_other_version is True   # …et on le signale


def test_aucune_divergence_signalee_quand_il_n_y_en_a_pas(conn, monkeypatch):
    """Une alerte inventée serait aussi nuisible qu'une alerte tue."""
    from testpilot.api import schemas

    cid, vid, eid = _cas(conn, budget=1)
    _agent(monkeypatch, RepairProposal(changed=True, steps_content="# v2 ok", summary="fix"))
    depart = _echec(); depart.execution_id = eid

    repair_service.run_repair_loop(
        conn, case_id=cid, version_id=vid, module_name="cas",
        outcome=depart, run_once=_runner(conn, cid, [_succes()]))

    out = schemas.case_summary(CaseRepo(conn).get(cid))
    assert out.verdict_from_other_version is False   # la version adoptée EST celle qui a tourné


def test_un_cas_jamais_execute_ne_diverge_de_rien(conn):
    from testpilot.api import schemas

    cid = CaseRepo(conn).create(title="Neuf", feature_slug="neuf")
    out = schemas.case_summary(CaseRepo(conn).get(cid))
    assert out.last_verdict_version_id is None
    assert out.verdict_from_other_version is False


# ── Mesure du budget §9 : « moins de 1 € pour la génération + exécution d'un module » ──
# Seule contrainte de coût CHIFFRÉE du brief, et elle n'était mesurable nulle part : `cost_ledger`
# n'était alimenté que par la CLI, et `run_service._persist` écrit `cost_usd=0.0` en dur. Les 5
# appels à l'agent du 2026-07-17 (v7→v11) n'ont laissé AUCUNE trace.

def test_le_cout_d_une_reparation_est_enregistre(conn, monkeypatch):
    from testpilot.store.repositories import CostRepo

    cid, vid, eid = _cas(conn, budget=1)
    _agent(monkeypatch, RepairProposal(changed=True, steps_content="# v2", summary="fix",
                                       cost_usd=0.0231))
    depart = _echec(); depart.execution_id = eid

    session = repair_service.run_repair_loop(
        conn, case_id=cid, version_id=vid, module_name="cas",
        outcome=depart, run_once=_runner(conn, cid, [_succes()]))

    assert session.cost_usd == pytest.approx(0.0231)
    assert CostRepo(conn).total_for_case_usd(cid) == pytest.approx(0.0231)
    # …et le détail explique le total plutôt que de l'asséner.
    detail = CostRepo(conn).breakdown_for_case(cid)
    assert detail and detail[0]["phase"] == "repair"
    assert detail[0]["calls"] == 1


def test_un_agent_qui_ne_propose_RIEN_a_quand_meme_coute(conn, monkeypatch):
    """Ne compter que les réparations réussies donnerait un budget flatteur — §4.6 sur l'argent."""
    from testpilot.store.repositories import CostRepo

    cid, vid, eid = _cas(conn, budget=2)
    _agent(monkeypatch, RepairProposal(changed=False, summary="je ne sais pas", cost_usd=0.0198))
    depart = _echec(); depart.execution_id = eid

    session = repair_service.run_repair_loop(
        conn, case_id=cid, version_id=vid, module_name="cas",
        outcome=depart, run_once=_runner(conn, cid, [_succes()]))

    assert session.outcome == "agent_no_fix"
    assert CostRepo(conn).total_for_case_usd(cid) == pytest.approx(0.0198)


def test_chaque_tentative_ajoute_au_cout_du_cas(conn, monkeypatch):
    """Le coût s'ACCUMULE : `finalize` écrit une fois, la réparation dépense après — écraser
    perdrait l'un ou l'autre."""
    from testpilot.store.repositories import CostRepo

    cid, vid, eid = _cas(conn, budget=2)
    _agent(monkeypatch,
           RepairProposal(changed=True, steps_content="# v2", summary="a", cost_usd=0.02),
           RepairProposal(changed=True, steps_content="# v3", summary="b", cost_usd=0.03))
    depart = _echec(); depart.execution_id = eid

    repair_service.run_repair_loop(
        conn, case_id=cid, version_id=vid, module_name="cas",
        outcome=depart, run_once=_runner(conn, cid, [_echec(AUTRE_ERREUR), _succes()]))

    assert CostRepo(conn).total_for_case_usd(cid) == pytest.approx(0.05)


def test_le_budget_du_paragraphe_9_est_nomme_dans_la_config():
    """Le §9 n'existait dans AUCUNE constante : impossible de mesurer contre lui.

    ⚠️ **Ce test gardait la contradiction inverse — elle est RÉSOLUE le 2026-07-17.**
    Il exigeait `COST_LIMIT_PER_RUN_USD > BUDGET_PER_CASE_USD`, pour que le constat gênant « le
    plafond par run n'applique pas le §9 » ne se perde pas. Il a fait son travail : il a échoué
    à la seconde où le plafond est passé de $2,00 à $0,50, en renvoyant vers la doc à corriger.

    Le sens s'inverse donc : le plafond de génération est maintenant **sous** le §9, ce qui est
    l'état voulu. Assertion retournée plutôt que supprimée — un garde qui a servi ne se jette
    pas, il se met à jour.
    """
    assert config.BUDGET_PER_CASE_EUR == 1.00
    assert config.BUDGET_PER_CASE_USD == pytest.approx(1.00 * config.EUR_USD_RATE)
    assert config.COST_LIMIT_PER_RUN_USD < config.BUDGET_PER_CASE_USD, (
        "COST_LIMIT_PER_RUN_USD est repassé AU-DESSUS du §9 : le plafond de génération ne "
        "l'applique plus. Recalibrer sur une mesure réelle "
        "(scripts/mesure_generation_chemin_ecran.py), pas à vue.")


# ── Principe 5 : aucune adoption si un scénario qui passait ne passe plus ──────
# Coût marginal NUL : les deux runs (avant/après) sont déjà faits et déjà payés par la boucle.

def _run(verts=(), rouges=(), techniques=()):
    """Un run réel. `verts` passent ; `rouges` échouent sur une ASSERTION ; `techniques` sur un
    `TypeError`.

    ⚠️ La distinction n'est pas cosmétique : une assertion → `vrai_bug` → le circuit s'arrête à
    **0 tentative** (§4.4) et aucune réparation n'a lieu. Pour exercer la boucle, le run de DÉPART
    doit porter un échec **technique** — c'est ce qui la déclenche. Ma première version de ces
    tests l'ignorait et ne réparait jamais rien.
    """
    scenarios = [_Scenario(name=n, status="passed") for n in verts]
    scenarios += [_Scenario(name=n, status="failed") for n in list(rouges) + list(techniques)]
    failures = [_Failure(scenario_name=n, failure_type="assertion",
                         raw="ASSERT FAILED: l'application répond faux") for n in rouges]
    failures += [_Failure(scenario_name=n, failure_type="unknown",
                          raw="TypeError: 'int' object is not subscriptable") for n in techniques]
    return _Outcome(real_run=_RealRun(failures=failures, scenarios=scenarios))


def test_une_reparation_qui_SUPPRIME_un_scenario_vert_est_refusee(conn, monkeypatch):
    """LE test du principe 5 — et le seul filet possible contre ce cas.

    Un step n'est `undefined` (donc rattrapé par le dry-run) que si le `.feature` le réclame
    ENCORE. Si l'agent réécrit les DEUX fichiers et retire un scénario, le dry-run est satisfait
    et le run paraît MEILLEUR : moins de scénarios, moins d'échecs. Seule la comparaison
    avant/après le voit.

    ⚠️ **Le VERDICT a changé le 2026-07-17 (`0018`), pas le comportement.** Ce scénario n'est pas
    seulement *cassé* : il a **DISPARU** (2 scénarios → 1). La garde de couverture de `0018` est
    plus précise que le principe 5 sur ce cas, donc c'est elle qui nomme le refus —
    `COVERAGE_LOST` plutôt que `REGRESSION`. Les deux labels partitionnent proprement :

        scénario SUPPRIMÉ                 → COVERAGE_LOST  (il n'en reste aucune trace)
        scénario PRÉSENT mais devenu rouge → REGRESSION     (il tourne encore, il échoue)

    « Ne passe plus » suggère qu'il tourne encore : c'est **moins vrai et moins alarmant** que
    « a disparu ». `session.regressions` continue de le nommer — aucune information n'est perdue.
    L'essentiel du test est intact : **cette version n'est JAMAIS adoptée**.
    """
    cid, vid, eid = _cas(conn, budget=1)
    _agent(monkeypatch, RepairProposal(changed=True, steps_content="# v2 ampute", summary="fix"))
    depart = _run(verts=["[NOMINAL] Demande complète"], techniques=["[ERREUR] Produit invalide"])
    depart.execution_id = eid

    # Après : le scénario en échec est « corrigé »… en supprimant le scénario NOMINAL qui passait.
    session = repair_service.run_repair_loop(
        conn, case_id=cid, version_id=vid, module_name="cas",
        outcome=depart, run_once=_runner(conn, cid, [_run(verts=["[ERREUR] Produit invalide"])]))

    assert session.executable                       # le test tourne, et il est même tout vert…
    assert session.resolved                         # …au sens « aucun échec » !
    assert session.regressions == ["[NOMINAL] Demande complète"]   # le principe 5 le nomme toujours
    assert session.couverture_perdue == 1           # …mais il a DISPARU, et c'est plus grave
    assert session.outcome == repair_service.COVERAGE_LOST
    assert CaseRepo(conn).get(cid)["current_version_id"] == vid, (
        "une réparation qui perd un scénario vert ne doit JAMAIS être adoptée, même verte")


def test_une_reparation_qui_CASSE_un_scenario_vert_est_refusee(conn, monkeypatch):
    """Variante : le scénario existe toujours mais ne passe plus."""
    cid, vid, eid = _cas(conn, budget=1)
    _agent(monkeypatch, RepairProposal(changed=True, steps_content="# v2", summary="fix"))
    depart = _run(verts=["A"], techniques=["B"]); depart.execution_id = eid

    # Après : B est réparé, mais A échoue désormais sur une assertion — le test TOURNE toujours
    # (success/non_conforme), donc `executable` est vrai : seule la non-régression le rattrape.
    session = repair_service.run_repair_loop(
        conn, case_id=cid, version_id=vid, module_name="cas",
        outcome=depart, run_once=_runner(conn, cid, [_run(verts=["B"], rouges=["A"])]))

    assert session.executable                       # le test tourne…
    assert session.regressions == ["A"]             # …mais A ne passe plus
    assert session.outcome == repair_service.REGRESSION
    assert CaseRepo(conn).get(cid)["current_version_id"] == vid


def test_le_disque_revient_a_la_reference_quand_la_reparation_regresse(conn, monkeypatch, tmp_path):
    """Refuser l'adoption sans rembobiner le disque ferait exécuter v2 en prétendant v1 (§4.6)."""
    monkeypatch.setattr(config, "GENERATED_DIR", tmp_path)
    cid, vid, eid = _cas(conn, budget=1)
    _agent(monkeypatch, RepairProposal(changed=True, steps_content="# v2 ampute", summary="fix"))
    depart = _run(verts=["A"], techniques=["B"]); depart.execution_id = eid

    repair_service.run_repair_loop(
        conn, case_id=cid, version_id=vid, module_name="cas",
        outcome=depart, run_once=_runner(conn, cid, [_run(verts=["B"])]))

    assert (tmp_path / "cas_steps.py").read_text(encoding="utf-8") == "# steps v1"


def test_aucune_regression_signalee_quand_la_reparation_ne_perd_rien(conn, monkeypatch):
    """Le cas 1 réel : 0 scénario vert avant → rien à protéger → l'adoption reste possible.

    Une garde qui refuserait ici bloquerait la réparation la plus utile du projet.
    """
    cid, vid, eid = _cas(conn, budget=1)
    _agent(monkeypatch, RepairProposal(changed=True, steps_content="# v2 odoorpc", summary="fix"))
    depart = _echec(); depart.execution_id = eid      # 0 scénario vert (technical_error)

    session = repair_service.run_repair_loop(
        conn, case_id=cid, version_id=vid, module_name="cas",
        outcome=depart, run_once=_runner(conn, cid, [_tourne_mais_bug_applicatif()]))

    assert session.regressions == []
    assert session.executable
    assert CaseRepo(conn).get(cid)["current_version_id"] != vid   # adoptée : rien n'a régressé


def test_regressions_est_une_fonction_pure_et_gratuite():
    """Aucun run, aucun LLM : deux `outcome` déjà en main suffisent."""
    avant = _run(verts=["A", "B"], techniques=["C"])
    apres = _run(verts=["A"], techniques=["C"])
    assert repair_service.regressions(avant, apres) == ["B"]
    assert repair_service.regressions(avant, avant) == []
    # Un run qui n'a pas tourné n'a aucun scénario vert : rien à comparer, aucune régression.
    assert repair_service.regressions(_Outcome(real_run=None), apres) == []


# ── La MÉMOIRE : ce qu'une session a appris, la suivante le sait (§5bis n°1 + 0018) ──

def test_GARDE_une_regle_apprise_a_la_session_1_est_CONNUE_a_la_session_2(
        conn, monkeypatch, tmp_path):
    """Le cœur du chantier : la connaissance traverse les sessions de rejeu.

    ⚠️ Échoue sur le code d'avant. `propose_fix` ne recevait que le fichier de steps courant :
    chaque session repartait aveugle et redécouvrait — en la REPAYANT — une contrainte que
    l'application avait déjà refusée. C'est le volet de `0018` que l'adoption sur progrès
    (`progresse`/`couverture_perdue`) ne pouvait pas fermer : elle garde une version, pas un
    savoir.
    """
    from testpilot.generation import regles_apprises as ra
    from testpilot.store.repositories import ModuleRepo, ProjectRepo

    monkeypatch.setattr(ra, "REGLES_DIR", tmp_path / "regles-apprises")
    ra._lire.cache_clear()

    # Rattaché à un PROJET : les règles apprises sont propres à une instance (`0005`), et sans
    # projet il n'y a rien à retrouver. C'est aussi la forme réelle d'un cas en production.
    projet = ProjectRepo(conn).create(name="Portail", description="")
    module = ModuleRepo(conn).create(project_id=projet, name="Fournisseurs", description="")
    cid, vid, eid = _cas(conn, budget=1, module_id=module)

    # Session 1 : l'application refuse notre donnée. Le fait est appris.
    ra.enregistrer(projet, [{"route": "/fournisseur/creation",
                             "champ": "tva_intracommunautaire",
                             "type_contrainte": "customError", "valeur_contrainte": "",
                             "valeur_refusee": "TestPilot", "origine": "navigateur",
                             "preuve": "uniquement des chiffres"}])

    vus = {}

    def faux_propose(**kwargs):
        vus.update(kwargs)
        return RepairProposal(changed=False)

    monkeypatch.setattr(repair_service.repair_agent, "propose_fix", faux_propose)
    depart = _echec(); depart.execution_id = eid

    # Session 2 : une NOUVELLE boucle, qui n'a rien vu de la première.
    repair_service.run_repair_loop(
        conn, case_id=cid, version_id=vid, module_name="cas",
        outcome=depart, run_once=_runner(conn, cid, [_echec()]))

    memoire = vus.get("memoire") or ""
    assert "tva_intracommunautaire" in memoire, (
        "la règle apprise à la session précédente doit parvenir à l'agent — sinon il la "
        "redécouvre et la repaye à chaque rejeu")
    assert "TestPilot" in memoire


def test_sans_rien_d_appris_la_memoire_reste_VIDE(conn, monkeypatch, tmp_path):
    """Anti-faux-positif : pas de section, donc aucun coût de prompt ajouté."""
    from testpilot.generation import regles_apprises as ra

    monkeypatch.setattr(ra, "REGLES_DIR", tmp_path / "vide")
    ra._lire.cache_clear()

    cid, vid, eid = _cas(conn, budget=1)
    vus = {}

    def faux_propose(**kwargs):
        vus.update(kwargs)
        return RepairProposal(changed=False)

    monkeypatch.setattr(repair_service.repair_agent, "propose_fix", faux_propose)
    depart = _echec(); depart.execution_id = eid

    repair_service.run_repair_loop(
        conn, case_id=cid, version_id=vid, module_name="cas",
        outcome=depart, run_once=_runner(conn, cid, [_echec()]))

    assert vus.get("memoire") == ""
