"""Décision 0018 — on adopte le PROGRÈS de l'axe exécution, et supprimer un test n'est pas progresser.

LE DÉFAUT. `0016` avait corrigé « réparée = passe au vert » en « réparée = **tourne** ». Mais
« tourne » était resté du **tout-ou-rien** : `est_executable` exige que TOUS les scénarios tournent,
donc une version où 1 scénario sur 3 tourne proprement valait exactement une version où 0 sur 3
tournent. Mesuré (cas 1, rejeu du 2026-07-17, exécutions 25 → 27) : `v7` délègue l'auth, ne
réinvente aucun transport, fait passer **1/3** là où `v1` passe **0/3** — et elle a été **jetée**,
le disque rembobiné sur `v1`. Le rejeu suivant a redépensé son budget à re-corriger le `404` et
l'auth **déjà corrigés** : **$0,41 de travail racheté par rejeu**. La boucle ne pouvait pas
converger — il lui faut ~4 tentatives, elle en a 2, et elle ne gardait rien entre sessions.

LE PIÈGE, ET C'EST TOUT L'ENJEU DE CE FICHIER. Adopter sur « moins d'échecs techniques » ouvre une
porte béante : **le moyen le plus simple de réduire les échecs est de supprimer les scénarios qui
échouent.** Mesuré AVANT d'écrire le code, contre le vrai `regressions()` :

    supprimer un scénario qui PASSAIT   → regressions() rend ['A']  → refusé ✅
    supprimer un scénario EN ÉCHEC      → regressions() rend []     → ACCEPTÉ ❌

Le principe 5 ne surveille que les scénarios **verts**. Sans garde de couverture, « supprimer la
couverture » serait la **stratégie gagnante** de la boucle, et le run suivant paraîtrait parfait —
la **ligne rouge du §5 du brief** (« jamais de masquage d'un échec »).

`test_supprimer_un_scenario_en_echec_ne_fait_pas_gagner_le_verdict` est le test qui garde ce trou.

⚠️ **LA GARDE COMPTE, ELLE NE COMPARE PAS LES NOMS — et c'est le PRINCIPE 1.** Mon premier jet
diffait les `scenario_name` (`noms_avant - noms_apres`). **Les tests de `0016` l'ont attrapé
immédiatement**, et ils avaient raison : un nom de scénario est **du texte écrit par l'agent**, et
il lui suffisait d'en **renommer** un pour que la garde croie à une suppression et refuse une
réparation légitime. C'est la faute que `failure_signature` avait déjà payée (`PRINCIPES.md`,
principe 1 : *« renommer un scénario suffisait à changer la signature »*) — rejouée à l'identique
dans la garde censée protéger la couverture. Le **nombre** de scénarios est un fait structurel du
run ; le nom ne l'est pas.
"""

from dataclasses import dataclass, field

import pytest

from testpilot.api.services import repair_service
from testpilot.api.services.repair_service import (
    couverture_perdue,
    progresse,
    regressions,
)
from testpilot.generation.repair_agent import RepairProposal
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, ExecutionRepo, ReviewRepo, VersionRepo


# ── Doublures ─────────────────────────────────────────────────────────────────

@dataclass
class _Failure:
    scenario_name: str
    step_text: str = "Quand je fais l'action"
    failure_type: str = "ui_timeout"
    traceback_summary: str = ""
    raw: str = "TypeError: 'int' object is not subscriptable"


@dataclass
class _Scenario:
    name: str
    status: str = "failed"
    error: str = ""


@dataclass
class _RealRun:
    failures: list = field(default_factory=list)
    scenarios: list = field(default_factory=list)
    returncode: int = 1


@dataclass
class _Outcome:
    real_run: _RealRun | None
    execution_id: int | None = None
    dry_run_passed: bool = True
    module_name: str = "cas"


def _run(*specs):
    """`_run(('A', 'passed'), ('B', 'failed'))` — un outcome à N scénarios.

    Les noms DOIVENT coïncider entre scénario et échec : `status._failures_by_scenario`
    regroupe par `scenario_name`.
    """
    scenarios = [_Scenario(name=n, status=s) for n, s in specs]
    failures = [_Failure(scenario_name=n) for n, s in specs if s != "passed"]
    return _Outcome(real_run=_RealRun(failures=failures, scenarios=scenarios))


def _pas_de_run():
    """Le dry-run a échoué : Behave n'a rien joué. `real_run=None`."""
    return _Outcome(real_run=None)


# ── LE test : supprimer un scénario en échec ne fait pas gagner ───────────────

def test_supprimer_un_scenario_en_echec_ne_fait_pas_gagner_le_verdict():
    """🔴 LE trou de `progresse()`, gardé par un test et plus seulement par la doc.

    AVANT : A passe, B et C échouent  → 2 échecs techniques.
    APRÈS : B et C SUPPRIMÉS, A passe → 0 échec technique.

    `progresse()` dit « oui » — c'est arithmétiquement vrai et c'est précisément le danger.
    Le principe 5 ne bronche pas : A passait avant, A passe encore. **Seule la garde de
    couverture voit partir B et C**, et c'est elle qui doit refuser l'adoption.
    """
    avant = _run(("A", "passed"), ("B", "failed"), ("C", "failed"))
    apres = _run(("A", "passed"))          # B et C ont disparu

    assert progresse(avant, apres) is True, (
        "mise en scène : le compteur d'échecs DOIT baisser, c'est ce qui rend le piège crédible")
    assert regressions(avant, apres) == [], (
        "le principe 5 ne voit RIEN : il ne surveille que les scénarios verts")

    # La seule garde qui l'attrape.
    assert couverture_perdue(avant, apres) == 2, (
        "supprimer les scénarios qui échouent doit être détecté : sinon c'est la stratégie "
        "gagnante de la boucle, et c'est un masquage d'échec (§5 du brief)")


def test_supprimer_un_scenario_qui_passait_reste_attrape_par_les_deux_gardes():
    """Le cas que le principe 5 couvrait déjà — la nouvelle garde ne le remplace pas."""
    avant = _run(("A", "passed"), ("B", "failed"))
    apres = _run(("B", "failed"))          # A (vert) a disparu

    assert regressions(avant, apres) == ["A"]
    assert couverture_perdue(avant, apres) == 1


def test_renommer_un_scenario_n_est_PAS_une_perte_de_couverture():
    """🔴 PRINCIPE 1 : la garde ne décide pas sur du texte écrit par l'agent.

    Mon premier jet diffait les NOMS : renommer un scénario faisait croire à une suppression et
    **refusait une réparation légitime**. Les tests de `0016` l'ont attrapé — c'est la faute que
    `failure_signature` avait déjà payée, rejouée dans la garde censée protéger la couverture.
    """
    avant = _run(("[Nominal]", "failed"), ("[Limite]", "passed"))
    apres = _run(("[NOMINAL] Demande complète", "passed"), ("[LIMITE] 4 accessoires", "passed"))

    assert couverture_perdue(avant, apres) == 0, (
        "un simple renommage est pris pour une suppression : la garde décide sur le texte de "
        "l'agent (principe 1) et bloquerait la convergence que 0018 existe pour obtenir")


def test_la_couverture_intacte_ne_declenche_aucune_garde():
    """Anti-faux-positif : réparer sans rien supprimer ne doit pas être puni."""
    avant = _run(("A", "failed"), ("B", "failed"))
    apres = _run(("A", "passed"), ("B", "failed"))

    assert couverture_perdue(avant, apres) == 0
    assert regressions(avant, apres) == []
    assert progresse(avant, apres) is True


def test_ajouter_un_scenario_n_est_pas_une_perte_de_couverture():
    """Anti-faux-positif : l'agent a le droit d'ajouter (§6 — il explore)."""
    avant = _run(("A", "failed"))
    apres = _run(("A", "passed"), ("B", "passed"))

    assert couverture_perdue(avant, apres) == 0


# ── Le critère de progrès lui-même ────────────────────────────────────────────

def test_progresse_sur_le_cas_reel_v1_vers_v7():
    """Les chiffres RÉELS du rejeu : v1 = 0/3, v7 = 1/3. C'est ce que 0016 jetait."""
    v1 = _run(("NOMINAL", "failed"), ("ERREUR", "failed"), ("LIMITE", "failed"))
    v7 = _run(("NOMINAL", "failed"), ("ERREUR", "passed"), ("LIMITE", "failed"))

    assert repair_service.est_executable(v7) is False, (
        "v7 ne tourne pas ENTIÈREMENT — c'est pour ça que 0016 la jetait")
    assert progresse(v1, v7) is True, "3 échecs → 2 : c'est un progrès, il faut le garder"
    assert couverture_perdue(v1, v7) == 0


def test_un_test_qui_ne_tourne_plus_du_tout_n_est_jamais_un_progres():
    """`real_run=None` ⇒ « pas de run », jamais « aucun échec ». Le piège d'`a_tourne`."""
    avant = _run(("A", "failed"))
    assert progresse(avant, _pas_de_run()) is False


def test_un_test_qui_se_met_a_tourner_est_le_progres_maximal():
    """Le départ n'a pas tourné, l'arrivée oui : on garde, évidemment."""
    assert progresse(_pas_de_run(), _run(("A", "failed"))) is True


def test_stagner_n_est_pas_progresser():
    """Même nombre d'échecs : rien n'a avancé, on n'adopte pas."""
    avant = _run(("A", "failed"), ("B", "passed"))
    apres = _run(("A", "failed"), ("B", "passed"))
    assert progresse(avant, apres) is False


def test_regresser_n_est_pas_progresser():
    avant = _run(("A", "passed"), ("B", "passed"))
    apres = _run(("A", "failed"), ("B", "passed"))
    assert progresse(avant, apres) is False


# ── La boucle complète ────────────────────────────────────────────────────────

@pytest.fixture
def conn(tmp_path):
    c = get_initialized_db(tmp_path / "p.db")
    yield c
    c.close()


def _cas(conn, *, budget=2):
    cid = CaseRepo(conn).create(title="Cas", feature_slug="cas")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="spec", spec_hash="h",
                                   feature_content="# feature", steps_content="# steps")
    CaseRepo(conn).set_current_version(cid, vid)
    ReviewRepo(conn).create(test_case_id=cid, version_id=vid, decision="approved",
                            reviewer="qa", repair_budget=budget)
    eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid)
    return cid, vid, eid


def _agent(monkeypatch, *props):
    suite = list(props)

    def faux(**kwargs):
        return suite.pop(0) if suite else RepairProposal(changed=False)

    monkeypatch.setattr(repair_service.repair_agent, "propose_fix", faux)


def _runner(conn, cid, resultats):
    suite = list(resultats)

    def run_once(version_id):
        eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=version_id, trigger="rerun")
        out = suite.pop(0)
        out.execution_id = eid
        return out

    return run_once


def test_la_boucle_ADOPTE_un_progres_partiel(conn, monkeypatch):
    """Le cœur de `0018` : v7 (1/3) est GARDÉE contre v1 (0/3).

    Échoue sur le code d'avant : `adopte` valait `session.executable and …`, et `executable` est
    faux ici (2 scénarios sur 3 en échec technique) → la version était jetée, disque rembobiné.
    """
    cid, vid, eid = _cas(conn, budget=1)
    _agent(monkeypatch, RepairProposal(changed=True, steps_content="# v2", summary="auth déléguée"))
    depart = _run(("NOMINAL", "failed"), ("ERREUR", "failed"), ("LIMITE", "failed"))
    depart.execution_id = eid
    apres = _run(("NOMINAL", "failed"), ("ERREUR", "passed"), ("LIMITE", "failed"))

    session = repair_service.run_repair_loop(
        conn, case_id=cid, version_id=vid, module_name="cas",
        outcome=depart, run_once=_runner(conn, cid, [apres]))

    assert session.progresse is True
    assert session.executable is False, "le test ne tourne PAS entièrement — et on l'adopte quand même"
    assert session.final_version_id != vid, "le progrès a été JETÉ : la boucle rachètera ce travail"
    assert CaseRepo(conn).get(cid)["current_version_id"] == session.final_version_id
    # Jamais approuvée d'office : le gate reste souverain (§4.3).
    assert CaseRepo(conn).get(cid)["validation_status"] == "to_review"


def test_la_boucle_REFUSE_une_suppression_de_scenario_en_echec(conn, monkeypatch):
    """🔴 Le trou, gardé de bout en bout : l'agent supprime, le compteur baisse, on refuse.

    C'est le test que le porteur a exigé explicitement — le trou ne doit pas être gardé par la
    doc seule.
    """
    cid, vid, eid = _cas(conn, budget=1)
    _agent(monkeypatch, RepairProposal(changed=True, steps_content="# v2", summary="j'ai « corrigé »"))
    depart = _run(("A", "passed"), ("B", "failed"), ("C", "failed"))
    depart.execution_id = eid
    apres = _run(("A", "passed"))       # B et C supprimés → 0 échec technique

    session = repair_service.run_repair_loop(
        conn, case_id=cid, version_id=vid, module_name="cas",
        outcome=depart, run_once=_runner(conn, cid, [apres]))

    assert session.couverture_perdue == 2
    assert session.outcome == repair_service.COVERAGE_LOST
    assert "masquage" in session.reason
    # ⚠️ LA garde : malgré `executable=True` ET `progresse=True`, on N'ADOPTE PAS.
    assert session.executable is True, "mise en scène : le run paraît PARFAIT, c'est le piège"
    assert session.progresse is True
    assert session.final_version_id == vid, (
        "une version qui supprime des scénarios a été ADOPTÉE : c'est un masquage d'échec (§5)")
    assert CaseRepo(conn).get(cid)["current_version_id"] == vid


def test_la_couverture_prime_sur_la_regression_dans_le_verdict(conn, monkeypatch):
    """Quand les deux gardes mordent, on nomme la PIRE : un scénario disparu, pas juste cassé."""
    cid, vid, eid = _cas(conn, budget=1)
    _agent(monkeypatch, RepairProposal(changed=True, steps_content="# v2", summary="x"))
    depart = _run(("A", "passed"), ("B", "failed"))
    depart.execution_id = eid
    apres = _run(("B", "passed"))       # A (vert) supprimé

    session = repair_service.run_repair_loop(
        conn, case_id=cid, version_id=vid, module_name="cas",
        outcome=depart, run_once=_runner(conn, cid, [apres]))

    assert session.outcome == repair_service.COVERAGE_LOST
    assert session.final_version_id == vid


def test_une_stagnation_n_est_toujours_pas_adoptee(conn, monkeypatch):
    """Anti-régression de `0018` : on n'adopte pas pour le plaisir de garder quelque chose."""
    cid, vid, eid = _cas(conn, budget=1)
    _agent(monkeypatch, RepairProposal(changed=True, steps_content="# v2", summary="x"))
    depart = _run(("A", "failed"), ("B", "failed"))
    depart.execution_id = eid
    apres = _run(("A", "failed"), ("B", "failed"))

    session = repair_service.run_repair_loop(
        conn, case_id=cid, version_id=vid, module_name="cas",
        outcome=depart, run_once=_runner(conn, cid, [apres]))

    assert session.progresse is False
    assert session.final_version_id == vid
