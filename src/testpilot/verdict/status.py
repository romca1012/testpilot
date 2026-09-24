"""Les DEUX axes de statut du verdict (§5), calculés depuis un ExecutionOutcome brut.

- StatutExécution : le test a-t-il pu tourner techniquement (pas de crash/timeout/env) ?
- StatutFonctionnel : l'application s'est-elle comportée conformément au besoin ?

Les deux sont indépendants et jamais confondus. Règle de dérivation validée (section C) :
un échec d'assertion métier ⇒ exécution=success, fonctionnel=non_conforme (le test a bien
tourné mais l'app répond faux) ; un échec technique ⇒ exécution=technical_error,
fonctionnel=indetermine. L'agrégation par-cas ne masque jamais un non_conforme.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from testpilot.execution.executor import ExecutionOutcome
from testpilot.verdict import defect_taxonomy as dt

# Axe exécution
EXEC_SUCCESS = "success"
EXEC_TECHNICAL_ERROR = "technical_error"
EXEC_NOT_EXECUTED = "not_executed"
# Lot 02 (D1) : le test n'a PAS pu être joué parce qu'un PRÉREQUIS d'environnement n'est pas rempli
# (module non installé, session RPC absente, fixture/connexion en échec). Ni une panne de notre code
# (`technical_error` → à revérifier), ni un constat sur l'application. Nouvelle VALEUR de l'axe
# exécution, jamais un 3ᵉ axe : l'invariant « les deux axes ne fusionnent jamais » tient. Produite
# AUTOMATIQUEMENT par la cause `precondition_non_remplie`, jamais réparée automatiquement.
EXEC_BLOCKED = "blocked"
# Axe fonctionnel
FUNC_CONFORME = "conforme"
FUNC_NON_CONFORME = "non_conforme"
FUNC_INDETERMINE = "indetermine"
FUNC_NOT_EVALUATED = "not_evaluated"
# 4ᵉ verdict (§2bis) : le test a TOURNÉ (exécution=success) mais sa DONNÉE a été refusée —
# l'application n'est pas en cause, c'est le test à corriger. Nouvelle VALEUR de l'axe
# fonctionnel, jamais un 3ᵉ axe : l'invariant « les deux axes ne fusionnent jamais » tient.
FUNC_DONNEE_INVALIDE = "donnee_invalide"

# ── Confiance du verdict selon le CONNECTEUR (étape 2.2 du plan de consolidation, 2026-09-15 —
# audit « Le pari Mabl/Testim ») ─────────────────────────────────────────────────────────────
#
# Un cas Odoo peut être recoupé contre une vérité de référence INTERROGEABLE (RPC : get_schema/
# search/read) ; un cas sur le connecteur générique ne le peut PAS — `GenericWebConnector` lève
# `NotImplementedError` sur ces 5 méthodes (aucun modèle de données, cf. sa docstring). Le verdict
# d'un cas générique ne peut donc constater QUE ce que l'UI affiche, jamais une vérité côté base
# de données comme un cas Odoo. Ce champ n'AJOUTE aucune capacité : il étiquette honnêtement une
# différence de fiabilité déjà réelle aujourd'hui, plutôt que de présenter un verdict d'apparence
# identique quel que soit le connecteur.
GROUND_TRUTH_BACKEND_VERIFIED = "backend_verified"
GROUND_TRUTH_UI_ONLY = "ui_only"


def _ground_truth_pour(connector_type: str | None) -> str:
    """`None` (appelant qui ne résout pas encore le connecteur, ex. `cli.py`, `repair_service.py`)
    retombe sur `odoo` — comportement HISTORIQUE inchangé pour tout appelant qui ne fournit pas
    ce paramètre, exactement le même repli que `connectors/factory.py::build_connector`."""
    return (GROUND_TRUTH_BACKEND_VERIFIED if (connector_type or "odoo").lower() == "odoo"
            else GROUND_TRUTH_UI_ONLY)


@dataclass
class ScenarioVerdict:
    name: str
    execution_status: str
    functional_status: str
    failure_type: str = ""
    cause_category: str = ""
    error: str = ""
    # Le step en échec — TRACE, jamais critère. Il est écrit par l'agent : le lire pour classer
    # revenait à juger l'agent sur son propre texte (décision 0015, `defect_taxonomy`). Il est
    # transporté puis persisté pour qu'on puisse AUDITER `cause_category` a posteriori — sans
    # lui, aucune classification passée n'est vérifiable.
    step_text: str = ""


@dataclass
class CaseVerdict:
    execution_status: str
    functional_status: str
    scenarios: list[ScenarioVerdict] = field(default_factory=list)
    scenarios_passed: int = 0
    scenarios_failed: int = 0
    # Confiance du verdict selon le connecteur (étape 2.2) — défaut `backend_verified` : préserve
    # le comportement de tout appelant qui ne connaît pas encore le connecteur (ex. code existant
    # qui construit un `CaseVerdict` directement, `report_service._verdict_from_db`).
    ground_truth: str = GROUND_TRUTH_BACKEND_VERIFIED


def _failures_by_scenario(failures) -> dict[str, list]:
    grouped: dict[str, list] = {}
    for f in failures or []:
        grouped.setdefault(f.scenario_name, []).append(f)
    return grouped


def scenario_verdict(scenario, failures: list) -> ScenarioVerdict:
    """Projette un scénario behave + ses échecs sur les deux axes."""
    if scenario.status == "passed":
        if getattr(scenario, "constats_reussis", None) == 0:
            # Lot 03 (D3) : le scénario est allé au bout, mais AUCUN constat réussi n'a été consigné
            # sous un `Alors` (assertion dans une branche non prise, `Alors` qui ne fait qu'attendre…).
            # Un vert sans preuve n'est pas `conforme` — `indetermine`, à revérifier. `None` (mécanisme
            # absent : dry-run, résultat hors runner) laisse le comportement historique.
            return ScenarioVerdict(scenario.name, EXEC_SUCCESS, FUNC_INDETERMINE,
                                   "", dt.AUCUN_CONSTAT, "Aucune vérification exécutée")
        return ScenarioVerdict(scenario.name, EXEC_SUCCESS, FUNC_CONFORME)

    if scenario.status == "failed":
        cause = dt.dominant_category(failures) or dt.UNKNOWN
        failure_type = failures[0].failure_type if failures else ""
        step_text = failures[0].step_text if failures else ""
        if cause == dt.REFUS_NON_EXPLIQUE:
            # A tourné jusqu'au bout, mais rien n'explique le refus : ni constat sur l'application ni
            # panne du test. Manque d'observabilité → `indetermine` (jamais `non_conforme`).
            return ScenarioVerdict(scenario.name, EXEC_SUCCESS, FUNC_INDETERMINE,
                                   failure_type, cause, scenario.error, step_text)
        if cause in (dt.ASSERTION_MISMATCH, dt.ERREUR_SERVEUR_5XX):
            # A tourné techniquement, mais le comportement métier est faux → constat produit.
            return ScenarioVerdict(scenario.name, EXEC_SUCCESS, FUNC_NON_CONFORME,
                                   failure_type, cause, scenario.error, step_text)
        if cause == dt.DONNEE_REFUSEE:
            # A tourné techniquement ; c'est la DONNÉE du test qui a été refusée (4ᵉ verdict) —
            # l'application n'est PAS en cause. On n'accuse plus : on nomme un test à corriger.
            return ScenarioVerdict(scenario.name, EXEC_SUCCESS, FUNC_DONNEE_INVALIDE,
                                   failure_type, cause, scenario.error, step_text)
        if cause == dt.PRECONDITION_NON_REMPLIE:
            # Le test n'a jamais pu commencer à juger : un prérequis d'ENVIRONNEMENT manque (lot 02,
            # D1). `indetermine` côté fonctionnel — on n'a rien constaté sur l'application.
            return ScenarioVerdict(scenario.name, EXEC_BLOCKED, FUNC_INDETERMINE,
                                   failure_type, cause, scenario.error, step_text)
        # Cause technique (ou indéterminée) → le test n'a pas pu juger le fonctionnel.
        return ScenarioVerdict(scenario.name, EXEC_TECHNICAL_ERROR, FUNC_INDETERMINE,
                               failure_type, cause, scenario.error, step_text)

    # skipped / autre : n'a pas tourné en entier → interruption technique.
    return ScenarioVerdict(scenario.name, EXEC_TECHNICAL_ERROR, FUNC_INDETERMINE,
                           "", "", scenario.error)


def derive_verdict(outcome: ExecutionOutcome, *, connector_type: str | None = None) -> CaseVerdict:
    """Calcule le verdict à deux axes d'un cas depuis son ExecutionOutcome brut.

    `connector_type` (étape 2.2) : `None` par défaut — comportement HISTORIQUE inchangé pour tout
    appelant qui ne le fournit pas encore (`cli.py`, `repair_service.py`). Seul `run_service.py`,
    qui connaît déjà le projet du cas, le transmet réellement.
    """
    gt = _ground_truth_pour(connector_type)
    if not outcome.dry_run_passed:
        # Non résolvable (parsing/steps) → n'a jamais pu tourner techniquement.
        return CaseVerdict(EXEC_TECHNICAL_ERROR, FUNC_INDETERMINE, ground_truth=gt)

    real = outcome.real_run
    if real is None or real.returncode < 0:
        # Crash / timeout du sous-processus → interruption technique.
        return CaseVerdict(EXEC_TECHNICAL_ERROR, FUNC_INDETERMINE, ground_truth=gt)
    if real.returncode != 0 and not real.scenarios:
        # Le process a planté avec un code de retour POSITIF ordinaire (ex. exception Python non
        # rattrapée dans notre formatter JSON maison) — AVANT qu'aucun scénario n'ait pu être
        # rapporté. À distinguer d'un échec fonctionnel normal (`returncode` non nul MAIS au
        # moins un scénario réellement rapporté, lui, en échec). Sans cette garde, `aggregate([])`
        # ci-dessous rendait `not_executed` : « le test n'a jamais tourné », alors qu'il a
        # réellement tourné et planté — le même piège que « l'absence de signal prise pour un
        # signal positif » déjà traqué ailleurs (`_finalize_error`, §4.6). Audit 2026-08-07 (B4).
        return CaseVerdict(EXEC_TECHNICAL_ERROR, FUNC_INDETERMINE, ground_truth=gt)

    grouped = _failures_by_scenario(real.failures)
    verdicts = [scenario_verdict(s, grouped.get(s.name, [])) for s in real.scenarios]
    return aggregate(verdicts, connector_type=connector_type)


def aggregate(verdicts: list[ScenarioVerdict], *, connector_type: str | None = None) -> CaseVerdict:
    """Agrège les verdicts par-scénario au niveau du cas — sans jamais masquer un échec."""
    passed = sum(1 for v in verdicts
                 if v.execution_status == EXEC_SUCCESS and v.functional_status == FUNC_CONFORME)

    if not verdicts:
        execution_status = EXEC_NOT_EXECUTED
    elif any(v.execution_status == EXEC_TECHNICAL_ERROR for v in verdicts):
        execution_status = EXEC_TECHNICAL_ERROR
    elif any(v.execution_status == EXEC_BLOCKED for v in verdicts):
        # Priorité `technical_error` > `blocked` > `success` : une panne de notre code reste visible
        # (à revérifier) ; un prérequis manquant prime sur un succès partiel, jamais sur un constat
        # (un `non_conforme` surface toujours, ci-dessous, quelle que soit l'exécution).
        execution_status = EXEC_BLOCKED
    else:
        execution_status = EXEC_SUCCESS

    if any(v.functional_status == FUNC_NON_CONFORME for v in verdicts):
        functional_status = FUNC_NON_CONFORME  # un vrai constat (défaut applicatif) surface toujours
    elif any(v.functional_status == FUNC_DONNEE_INVALIDE for v in verdicts):
        # Sous le non_conforme, au-DESSUS du conforme : un scénario dont la donnée a été refusée
        # n'a rien pu prouver — il ne doit pas être masqué par les scénarios verts (§2bis).
        functional_status = FUNC_DONNEE_INVALIDE
    elif not verdicts:
        functional_status = FUNC_NOT_EVALUATED
    elif execution_status == EXEC_SUCCESS and all(v.functional_status == FUNC_CONFORME for v in verdicts):
        functional_status = FUNC_CONFORME
    else:
        functional_status = FUNC_INDETERMINE

    return CaseVerdict(
        execution_status=execution_status,
        functional_status=functional_status,
        scenarios=verdicts,
        scenarios_passed=passed,
        scenarios_failed=len(verdicts) - passed,
        ground_truth=_ground_truth_pour(connector_type),
    )


# ── Le statut de LECTURE d'un cas (déplacé depuis le frontend le 2026-07-24) ──────────────────
# Les deux axes du §5 sont la vérité ; ce statut est leur PROJECTION en une étiquette unique, pour
# les listes et les tableaux de bord. Il ne remplace jamais les deux axes : il les résume.
#
# ⚠️ **Cette règle vivait UNIQUEMENT en TypeScript.** Filtrer une liste par statut côté serveur
# aurait donc exigé de la réécrire en SQL — deux implémentations de la même règle, qui divergent
# le jour où l'une évolue, et dont l'écart est invisible (les deux « marchent »). On l'a déplacée
# ici : un seul endroit décide, et le frontend lit ce que le serveur a calculé.

STATUT_PASSED = "passed"
STATUT_FAILED = "failed"
STATUT_RETEST = "retest"
STATUT_BLOCKED = "blocked"
STATUT_UNTESTED = "untested"

# Ordre canonique (légende des graphiques, colonnes de filtre).
STATUTS = (STATUT_PASSED, STATUT_BLOCKED, STATUT_RETEST, STATUT_FAILED, STATUT_UNTESTED)

# ── Le MODE d'exécution : qui a joué le test ─────────────────────────────────
# Vocabulaire arrêté le 2026-08-04 (il remplace « provenance : exécuté / déclaré »). « Déclaré »
# sous-entendait une affirmation sans preuve ; **« manuelle » dit la vérité** : un humain a
# réellement joué le test, à la main, en suivant ses étapes. Ce n'est pas une case cochée, c'est
# une autre façon d'exécuter — et c'est bien ce qui doit rester lisible.
MODE_MANUELLE = "manuelle"
MODE_AUTOMATIQUE = "automatique"
MODES_EXECUTION = (MODE_MANUELLE, MODE_AUTOMATIQUE)

# Les statuts qu'un HUMAIN peut saisir en exécution MANUELLE.
# ⚠️ `untested` en est ABSENT, délibérément : le saisir serait indiscernable de « pas encore de
# résultat », et fabriquerait une ligne qui n'affirme rien. L'absence de résultat le dit déjà —
# mieux, et gratuitement.
STATUTS_MANUELS = (STATUT_PASSED, STATUT_FAILED, STATUT_RETEST, STATUT_BLOCKED)


def statut_de_test(execution: str | None, functional: str | None,
                   manuel: str | None = None) -> str:
    """Projette un résultat en une étiquette de lecture.

    ⚠️ **Un statut saisi en exécution MANUELLE n'est pas dérivé : il est constaté par un humain.**
    Il court-circuite donc la dérivation au lieu de s'y mélanger. C'est la seule façon d'intégrer
    un constat humain sans inventer des mesures qu'on n'a pas faites : saisir « passed » ne doit
    JAMAIS écrire `execution=success, functional=conforme`, qui prétendrait qu'une **machine** a
    constaté quelque chose. Les deux axes restent vides sur un résultat manuel, et l'écran
    l'affiche ainsi.

    Un `manuel` hors de `STATUTS_MANUELS` (vide, None, `untested`, valeur inconnue) est ignoré et
    la dérivation reprend : une valeur douteuse ne devient jamais une étiquette.

    Sans `manuel`, le comportement est celui d'avant l'exécution manuelle, à l'octet près.

    L'ordre des tests n'est pas décoratif — le fonctionnel prime sur l'exécution :

    - `conforme` → **passed** ;
    - `non_conforme` → **failed** ;
    - `donnee_invalide` → **retest** (4ᵉ verdict) : le test est à corriger. **Jamais `failed`**,
      qui accuserait l'application, ni `passed`, alors que rien n'a été prouvé ;
    - exécution `blocked` (lot 02, D1) → **blocked**, AVANT la règle `indetermine → retest` : un
      prérequis d'environnement manquant n'est ni un test à revérifier ni un défaut de l'application ;
    - `indetermine` → **retest** s'il a tourné, **untested** s'il n'a jamais été lancé ;
    - sans verdict fonctionnel, c'est le déroulement qui parle : `technical_error` → **blocked**,
      `success` → **passed** ;
    - à défaut → **untested**.
    """
    if manuel in STATUTS_MANUELS:
        return manuel
    if functional == FUNC_CONFORME:
        return STATUT_PASSED
    if functional == FUNC_NON_CONFORME:
        return STATUT_FAILED
    if functional == FUNC_DONNEE_INVALIDE:
        return STATUT_RETEST
    if execution == EXEC_BLOCKED:
        return STATUT_BLOCKED
    if functional == FUNC_INDETERMINE:
        return STATUT_UNTESTED if execution == EXEC_NOT_EXECUTED else STATUT_RETEST
    if execution == EXEC_TECHNICAL_ERROR:
        return STATUT_BLOCKED
    if execution == EXEC_SUCCESS:
        return STATUT_PASSED
    return STATUT_UNTESTED


# Expression SQL équivalente, pour FILTRER et TRIER sans charger la table entière.
# ⚠️ Elle est dérivée de la fonction ci-dessus, et un test compare les deux sur TOUTES les
# combinaisons possibles : sans cette comparaison, la version SQL divergerait un jour en silence.
def _case_derive(execution: str, functional: str) -> str:
    """La DÉRIVATION seule, depuis les deux axes — le corps historique de `sql_statut`."""
    return (
        f"CASE"
        f" WHEN {functional} = '{FUNC_CONFORME}' THEN '{STATUT_PASSED}'"
        f" WHEN {functional} = '{FUNC_NON_CONFORME}' THEN '{STATUT_FAILED}'"
        f" WHEN {functional} = '{FUNC_DONNEE_INVALIDE}' THEN '{STATUT_RETEST}'"
        f" WHEN {execution} = '{EXEC_BLOCKED}' THEN '{STATUT_BLOCKED}'"
        f" WHEN {functional} = '{FUNC_INDETERMINE}' THEN"
        f"   (CASE WHEN {execution} = '{EXEC_NOT_EXECUTED}' THEN '{STATUT_UNTESTED}'"
        f"         ELSE '{STATUT_RETEST}' END)"
        f" WHEN {execution} = '{EXEC_TECHNICAL_ERROR}' THEN '{STATUT_BLOCKED}'"
        f" WHEN {execution} = '{EXEC_SUCCESS}' THEN '{STATUT_PASSED}'"
        f" ELSE '{STATUT_UNTESTED}' END"
    )


def sql_statut(execution: str, functional: str, manuel: str | None = None) -> str:
    """Rend un CASE SQL calculant le statut depuis des colonnes nommées.

    `manuel` (colonne du statut saisi en exécution manuelle) court-circuite la dérivation,
    exactement comme dans `statut_de_test`. Sans lui, l'expression est IDENTIQUE à celle d'avant
    l'exécution manuelle : les appelants qui n'en connaissent pas la notion ne changent pas.

    ⚠️ La liste du `IN` est **générée depuis `STATUTS_MANUELS`**, jamais retapée — c'est ce qui
    empêche cette troisième forme de la règle de dériver. Et c'est un `IN` explicite plutôt qu'un
    `<> ''` : une valeur parasite en base ne doit pas pouvoir ressortir comme étiquette brute à
    l'écran (invariant `test_toute_combinaison_rend_un_statut_CONNU`).
    """
    derive = _case_derive(execution, functional)
    if manuel is None:
        return derive
    manuels = ", ".join(f"'{s}'" for s in STATUTS_MANUELS)
    return (f"CASE WHEN {manuel} IN ({manuels}) THEN {manuel}"
            f" ELSE ({derive}) END")
