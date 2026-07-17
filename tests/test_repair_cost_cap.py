"""Le plafond de coût borne le CAS, plus l'appel — et le §9 du brief redevient tenable.

LE BUG. `propose_fix` faisait `cost_tracker = cost_tracker or CostTracker()` et personne ne lui
en passait : **un tracker NEUF à chaque tentative**, donc au plafond entier, donc **remis à zéro**.
`COST_LIMIT_PER_RUN_USD = $2` ne bornait pas un run, il bornait un APPEL. Le coût réel d'un cas
pouvait donc atteindre :

    génération ($2) + REPAIR_BUDGET_DEFAULT × $2  =  jusqu'à $6

contre la cible du **§9 du brief : moins de 1 €/cas** (= $1,08 à `EUR_USD_RATE`). Le garde-fou
« budget » que le §6 exige existait, était testé, et ne gardait rien : chaque tentative rachetait
un plafond neuf. C'est le motif du projet une fois de plus — **un garde-fou décoratif**, comme le
`position` de `0006` ou le stall du circuit — mais appliqué à l'argent.

LE CORRECTIF. `repair_service` construit **un seul** `CostTracker` pour toute la boucle
(`REPAIR_COST_LIMIT_PER_CASE_USD`) et le passe à chaque tentative. Deux conséquences testées ici :

1. le plafond **cumule** entre tentatives et coupe le cas (escalade humaine, §6 du brief) ;
2. `RepairProposal.cost_usd` rend le **delta** de la tentative, jamais le total du tracker —
   sinon partager le tracker ferait **double-compter** la tentative 1 dans la 2, et le ledger
   comme `session.cost_usd` mentiraient **à la hausse**. Un correctif de comptage qui fausse le
   comptage aurait été une belle ironie.
"""

from dataclasses import dataclass, field

import pytest

from testpilot import config
from testpilot.api.services import repair_service
from testpilot.generation import repair_agent
from testpilot.guardrails.cost_tracker import CostTracker
from testpilot.llm.adapter import LLMResponse, ToolUseBlock
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, CostRepo, ExecutionRepo, ReviewRepo, VersionRepo

_STEPS = "from behave import when\n\n\n@when(\"je fais l'action\")\ndef step_impl(context):\n    pass\n"


class FakeLLM:
    """Chaque appel coûte `cost_par_appel` — on pilote la dépense pour tester le plafond."""

    def __init__(self, script, cost_par_appel=0.30):
        self.script = list(script)
        self.cost_par_appel = cost_par_appel
        self.calls = 0

    def call_with_tools(self, *, system_prompt, messages, tools, cost_tracker=None, **_):
        self.calls += 1
        if cost_tracker is not None:
            # `track_call` estime depuis les tokens ; on court-circuite pour un coût exact et
            # déterministe, tout en passant par le CHEMIN RÉEL qui lève `CostLimitExceeded`.
            cost_tracker.total_cost += self.cost_par_appel
            if cost_tracker.total_cost > cost_tracker.limit_usd:
                from testpilot.guardrails.cost_tracker import CostLimitExceeded
                raise CostLimitExceeded(
                    f"Budget dépassé : ${cost_tracker.total_cost:.3f} > "
                    f"${cost_tracker.limit_usd:.2f}.")
        return self.script[min(self.calls - 1, len(self.script) - 1)], None


class DR:
    def __init__(self, success=True):
        self.success = success
        self.undefined_steps = []
        self.ambiguous_steps = []


class FakeDryRunner:
    def dry_run(self, module_name):
        return DR(success=True)


def _ecrit():
    return LLMResponse(stop_reason="tool_use", tool_calls=[
        ToolUseBlock(id="s", name="write_steps_file", input={"content": _STEPS}),
    ])


@dataclass
class _Failure:
    scenario_name: str = "[Nominal]"
    step_text: str = "Quand je fais l'action"
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
    failures: list = field(default_factory=lambda: [_Failure()])
    scenarios: list = field(default_factory=lambda: [_Scenario()])
    returncode: int = 1


@dataclass
class _Outcome:
    real_run: _RealRun | None
    execution_id: int | None = None
    dry_run_passed: bool = True
    module_name: str = "cas"


@pytest.fixture(autouse=True)
def _isolate_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "GENERATED_DIR", tmp_path / "gen")
    monkeypatch.setattr(config, "STEPS_LIBRARY_DIR", tmp_path / "steps_lib")
    (tmp_path / "gen").mkdir()
    (tmp_path / "steps_lib").mkdir()


@pytest.fixture
def conn(tmp_path):
    c = get_initialized_db(tmp_path / "r.db")
    yield c
    c.close()


def _cas(conn, *, budget=2):
    cid = CaseRepo(conn).create(title="Cas", feature_slug="cas")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="spec", spec_hash="h",
                                   feature_content="# feature v1", steps_content=_STEPS)
    CaseRepo(conn).set_current_version(cid, vid)
    ReviewRepo(conn).create(test_case_id=cid, version_id=vid, decision="approved",
                            reviewer="qa", repair_budget=budget)
    eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid)
    return cid, vid, eid


# ── Le delta, pas le total ────────────────────────────────────────────────────

def test_une_tentative_ne_rend_que_son_propre_cout(monkeypatch):
    """Le tracker est partagé : rendre `total_cost` ferait double-compter la tentative d'avant.

    Échoue sur le code d'avant (`cost_usd=round(cost_tracker.total_cost, 6)`) : le tracker arrive
    déjà chargé de $0,50, l'appel coûte $0,30, et l'ancien code rendait **$0,80** au lieu de
    $0,30 — soit la tentative précédente recomptée.
    """
    tracker = CostTracker(limit_usd=5.0)
    tracker.total_cost = 0.50          # une tentative précédente a déjà dépensé

    proposal = repair_agent.propose_fix(
        module_name="cas", scenarios=[_Scenario()], failures=[_Failure()], steps_content=_STEPS,
        llm=FakeLLM([_ecrit()], cost_par_appel=0.30), dry_runner=FakeDryRunner(),
        cost_tracker=tracker)

    assert proposal.cost_usd == pytest.approx(0.30), "la tentative précédente est recomptée"
    assert tracker.total_cost == pytest.approx(0.80), "le tracker doit, LUI, cumuler"


# ── Le plafond borne le cas ───────────────────────────────────────────────────

def test_le_plafond_cumule_entre_tentatives_et_coupe_le_cas(conn, monkeypatch):
    """LE test du bug : sur le code d'avant, chaque tentative rachetait un plafond neuf.

    Plafond du cas : $0,50. Chaque appel LLM coûte $0,30.
      - tentative 1 : $0,30 cumulé — passe.
      - tentative 2 : $0,60 cumulé > $0,50 — **coupée**.
    Avant le correctif, la tentative 2 repartait de $0 et passait tranquillement : le cas
    dépensait $0,60 sous un plafond de $0,50, sans que rien ne bronche.
    """
    monkeypatch.setattr(config, "REPAIR_COST_LIMIT_PER_CASE_USD", 0.50)
    cid, vid, eid = _cas(conn, budget=3)
    depart = _Outcome(real_run=_RealRun(), execution_id=eid)

    llm = FakeLLM([_ecrit()], cost_par_appel=0.30)
    monkeypatch.setattr(repair_agent, "LLMAdapter", lambda: llm)

    def run_once(new_version_id):
        eid2 = ExecutionRepo(conn).create(test_case_id=cid, version_id=new_version_id,
                                          trigger="rerun")
        out = _Outcome(real_run=_RealRun(), execution_id=eid2)
        return out

    session = repair_service.run_repair_loop(
        conn, case_id=cid, version_id=vid, module_name="cas", outcome=depart,
        run_once=run_once, dry_runner=FakeDryRunner())

    assert session.outcome == repair_service.COST_EXCEEDED
    assert "plafond de coût" in session.reason
    # Le cas s'arrête à 1 tentative RETENUE, la 2ᵉ ayant été coupée par le plafond.
    assert session.attempts == 1
    assert session.cost_usd == pytest.approx(0.60), "le coût réellement dépensé doit être dit"


def test_le_cout_coupe_le_cas_quand_le_circuit_ne_coupe_pas(conn, monkeypatch):
    """Le §9 quand le budget de TENTATIVES ne suffit pas à protéger : c'est le coût qui borne.

    ⚠️ **Mise en scène délicate, apprise en écrivant ce test.** Avec des échecs IDENTIQUES, le
    circuit coupe sur le **stall** (3 signatures répétées) avant que le coût ne morde : l'issue
    est `stalled`, pas `cost_exceeded`. C'est **correct** — le brief §6 dit « le premier seuil
    atteint » — mais ça ne teste alors pas le plafond de coût.

    On fait donc **varier le type d'exception à chaque run** : chaque tentative a une signature
    distincte (c'est un vrai progrès, cf. `0015`/`failure_signature`), donc le stall ne se
    déclenche jamais, et le budget de 5 tentatives ne coupe pas non plus. **Seul le coût reste**
    — et c'est lui qu'on mesure ici.

    ⚠️ **Les types doivent rester dans `BROKEN_TEST_CODE`** (`0015`) : un `ValueError` ou un
    `OSError` ne sont pas au barème → `unknown` → `indetermine` → le circuit s'arrête en
    `needs_confirmation` (§4.4), et là encore le coût ne mordrait pas. Ces types-ci sont ceux
    que la taxonomie déclare réparables — le seul cas où la boucle a le droit de continuer.

    Budget 5 × $0,10 = $0,50 possible ; plafond $0,35 → coupé à la 4ᵉ ($0,40).
    """
    monkeypatch.setattr(config, "REPAIR_COST_LIMIT_PER_CASE_USD", 0.35)
    cid, vid, eid = _cas(conn, budget=5)
    depart = _Outcome(real_run=_RealRun(), execution_id=eid)

    llm = FakeLLM([_ecrit()], cost_par_appel=0.10)
    monkeypatch.setattr(repair_agent, "LLMAdapter", lambda: llm)

    # Tous dans BROKEN_TEST_CODE (0015) → réparables, donc le circuit continue ; mais types
    # DISTINCTS → signatures distinctes, donc aucun stall.
    types = iter(["TypeError: a", "AttributeError: b", "KeyError: c", "IndexError: d",
                  "NameError: e"])

    def run_once(new_version_id):
        eid2 = ExecutionRepo(conn).create(test_case_id=cid, version_id=new_version_id,
                                          trigger="rerun")
        # Une exception différente à chaque tour → signature différente → aucun stall.
        echec = _Failure(raw=next(types, "RuntimeError: z"))
        return _Outcome(real_run=_RealRun(failures=[echec]), execution_id=eid2)

    session = repair_service.run_repair_loop(
        conn, case_id=cid, version_id=vid, module_name="cas", outcome=depart,
        run_once=run_once, dry_runner=FakeDryRunner())

    assert session.outcome == repair_service.COST_EXCEEDED, (
        f"ni le stall ni le budget ne devaient couper ici — issue obtenue : {session.outcome}")
    # Le dépassement se constate à l'appel qui le franchit : on tolère UN appel de débord (c'est
    # le mécanisme même du tracker : il facture puis lève), jamais `budget × plafond` ($0,50).
    assert session.cost_usd <= 0.35 + 0.10, "le plafond du CAS n'a pas borné le cas"


def test_le_ledger_ne_double_compte_pas_les_tentatives(conn, monkeypatch):
    """Le total du ledger d'un cas doit être la SOMME des tentatives, pas leur cumul recompté.

    C'est `CostRepo.total_for_case_usd` — la mesure du §9. Si `propose_fix` rendait le total du
    tracker partagé, chaque tentative écrirait au ledger le cumul depuis le début : 2 tentatives
    à $0,10 donneraient $0,10 + $0,20 = $0,30 au lieu de $0,20.
    """
    monkeypatch.setattr(config, "REPAIR_COST_LIMIT_PER_CASE_USD", 5.0)
    cid, vid, eid = _cas(conn, budget=2)
    depart = _Outcome(real_run=_RealRun(), execution_id=eid)

    llm = FakeLLM([_ecrit()], cost_par_appel=0.10)
    monkeypatch.setattr(repair_agent, "LLMAdapter", lambda: llm)

    def run_once(new_version_id):
        eid2 = ExecutionRepo(conn).create(test_case_id=cid, version_id=new_version_id,
                                          trigger="rerun")
        return _Outcome(real_run=_RealRun(), execution_id=eid2)

    session = repair_service.run_repair_loop(
        conn, case_id=cid, version_id=vid, module_name="cas", outcome=depart,
        run_once=run_once, dry_runner=FakeDryRunner())

    # 2 tentatives × 1 appel × $0,10 (le dry-run vert clôt chaque session en un tour).
    assert session.attempts == 2
    assert session.cost_usd == pytest.approx(0.20)
    assert CostRepo(conn).total_for_case_usd(cid) == pytest.approx(0.20)


# ── Le calibrage, lié au brief ────────────────────────────────────────────────

# Mesures RÉELLES du 2026-07-17 — lues au ledger, pas estimées.
# `scripts/mesure_cout_cas.py` et `scripts/mesure_generation_chemin_ecran.py` les reproduisent.
GENERATION_ECRAN = 0.1050    # chemin écran, spec `demande_materiel` — le chemin des utilisateurs
ANALYSE_ECRAN = 0.0157       # jamais mesurée avant ce jour (SpecAnalyzer sans tracker)
GENERATION_PIRE = 0.4529     # CLI, 2026-07-15 — AVANT les garde-fous : régime révolu
REPARATION = 0.2895          # une tentative — périmé à la baisse (mesuré sans dry-run)


def test_le_plafond_par_defaut_tient_le_9_avec_le_budget_par_defaut():
    """Le calcul de calibration du 2026-07-17, verrouillé — sinon il dérive en silence.

    Le plafond de réparation est calibré sur le PIRE observé — c'est ainsi qu'on borne :
    §9 ($1,08) − génération pire cas ($0,4529) = $0,6271 → $0,62.
    Vérification : REPAIR_BUDGET_DEFAULT (2) × $0,2895 = $0,5790 ≤ $0,62. Ça tient, donc le
    budget par défaut RESTE à 2 — la mesure ne demande pas de le descendre à 1.

    Si quelqu'un remonte le budget par défaut sans toucher au plafond, ce test le dit.
    """
    marge = config.BUDGET_PER_CASE_USD - GENERATION_PIRE
    assert config.REPAIR_COST_LIMIT_PER_CASE_USD <= marge, (
        "le plafond de réparation dépasse ce que le §9 laisse après la pire génération mesurée")

    cout_attendu = config.REPAIR_BUDGET_DEFAULT * REPARATION
    assert cout_attendu <= config.REPAIR_COST_LIMIT_PER_CASE_USD, (
        f"{config.REPAIR_BUDGET_DEFAULT} tentatives à ${REPARATION} = ${cout_attendu:.4f} "
        f"> plafond ${config.REPAIR_COST_LIMIT_PER_CASE_USD} : baisser le budget par défaut "
        f"plutôt que dépasser la cible du §9")

    # Même au pire cas historique, le cas complet reste sous le §9.
    assert GENERATION_PIRE + cout_attendu <= config.BUDGET_PER_CASE_USD


def test_le_plafond_de_generation_ne_fait_echouer_aucune_generation_connue():
    """`COST_LIMIT_PER_RUN_USD` : recalibré de $2,00 à $0,50 sur la mesure du chemin ÉCRAN.

    Un plafond doit couper un emballement, **jamais** une création légitime : on vérifie donc
    qu'il reste au-dessus de TOUT ce qui a été réellement mesuré — y compris le pire, issu d'un
    régime (d'avant les garde-fous) où l'agent produisait 7,8× plus de code.
    """
    assert config.COST_LIMIT_PER_RUN_USD > GENERATION_PIRE, (
        "le plafond couperait la pire génération jamais mesurée : il ferait échouer une création")
    assert config.COST_LIMIT_PER_RUN_USD > GENERATION_ECRAN * 4, (
        "moins de 4x la marge sur le coût réel : le premier cas un peu plus gros échouerait")
    # Et il reste très en dessous de l'ancienne valeur absurde ($2,00 = 16,6x le réel).
    assert config.COST_LIMIT_PER_RUN_USD <= 1.0


def test_le_cout_reel_mesure_d_un_cas_tient_le_9():
    """Le §9 sur les chiffres du chemin réel — la seule mesure qui compte pour le produit."""
    creation = ANALYSE_ECRAN + GENERATION_ECRAN
    complet = creation + config.REPAIR_BUDGET_DEFAULT * REPARATION

    assert creation <= config.BUDGET_PER_CASE_USD * 0.15, (
        f"création mesurée ${creation:.4f} — attendu ~11 % du §9")
    assert complet <= config.BUDGET_PER_CASE_USD, (
        f"cas complet mesuré ${complet:.4f} > §9 ${config.BUDGET_PER_CASE_USD:.4f}")
