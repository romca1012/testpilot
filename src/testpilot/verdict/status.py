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

from testpilot.execution.behave_result import PALIER_ADAPTATIF
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


# ── Confiance du verdict (lot 05, D5) ───────────────────────────────────────────────────────────────────
#
# Un vert n'a pas toujours la même valeur : obtenu par la cascade déterministe c'est une preuve NOMINALE ; obtenu parce
# qu'un LLM a retrouvé un élément renommé (`auto_resolue`) ou au second essai après un timeout (`apres_retry`), c'est
# exactement une régression d'interface ou une instabilité qu'une campagne doit signaler. Ce n'est PAS un troisième axe
# ni un nouveau statut : `statut_de_test` reste `passed`, la confiance le QUALIFIE (« Réussi — à confirmer »).
# Distincte de `ground_truth` (ci-dessus), qui dit ce que le CONNECTEUR permet de recouper, pas comment CE run a abouti.
# Calcul PUR depuis deux signaux du runtime — le sidecar des paliers et le fait d'avoir rejoué — jamais depuis le texte
# de l'agent (décision 0015).
CONFIANCE_NOMINALE = "nominale"
CONFIANCE_AUTO_RESOLUE = "auto_resolue"
CONFIANCE_APRES_RETRY = "apres_retry"
# Lot VH-03 (D28) : résultat d'une version RÉPARÉE par l'agent et pas encore relue — jamais le résultat du cas.
CONFIANCE_APRES_REPARATION = "apres_reparation"
CONFIANCES = (CONFIANCE_NOMINALE, CONFIANCE_AUTO_RESOLUE, CONFIANCE_APRES_RETRY, CONFIANCE_APRES_REPARATION)
# Libellés français (CONTINUITE §4.7 : aucune valeur d'enum brute à l'écran). DUPLIQUÉS dans `frontend/src/lib/status.ts`
# (`CONFIANCE_LABEL`), même test d'accord que les causes (`tests/test_confiance_libelles.py`).
LIBELLES_CONFIANCE = {
    CONFIANCE_NOMINALE: "Nominale",
    CONFIANCE_AUTO_RESOLUE: "Résolue automatiquement",
    CONFIANCE_APRES_RETRY: "Obtenue au second essai",
    CONFIANCE_APRES_REPARATION: "Après réparation, non relue",
}
LIBELLE_A_CONFIRMER = "Réussi — à confirmer"
# Du moins au plus préoccupant : le cas prend la confiance du scénario le moins sûr.
_RANG_CONFIANCE = {CONFIANCE_NOMINALE: 0, CONFIANCE_AUTO_RESOLUE: 1, CONFIANCE_APRES_RETRY: 2,
                   CONFIANCE_APRES_REPARATION: 3}


def a_confirmer(statut: str | None, confiance: str | None) -> bool:
    """« Réussi — à confirmer » : un `passed` dont la confiance n'est pas nominale. PUR, calculé par le SERVEUR (comme
    `statut_de_test`) : l'écran lit ce booléen, il ne redérive jamais la règle. Une confiance absente (résultat manuel,
    exécution ancienne) ou inconnue n'ajoute aucune réserve — elle n'a pas été mesurée."""
    return statut == "passed" and confiance in (CONFIANCE_AUTO_RESOLUE, CONFIANCE_APRES_RETRY, CONFIANCE_APRES_REPARATION)


def _ground_truth_pour(connector_type: str | None, oracle_utilise: bool = False) -> str:
    """`None` (appelant qui ne résout pas encore le connecteur, ex. `cli.py`, `repair_service.py`)
    retombe sur `odoo` — comportement HISTORIQUE inchangé pour tout appelant qui ne fournit pas
    ce paramètre, exactement le même repli que `connectors/factory.py::build_connector`.

    `oracle_utilise` (lot 07e, D7) : TOUS les scénarios du cas ont interrogé l'oracle backend du
    projet sous un `Alors` — un connecteur qui ne peut sinon recouper que l'UI (`ui_only`) obtient
    alors la même garantie qu'Odoo. N'AJOUTE rien pour Odoo, déjà `backend_verified` par son RPC.

    ⚠️ **Unanimité, pas majorité** (revue du 2026-09-28) : un SEUL scénario recoupé ne peut pas
    prêter `backend_verified` à tout le cas — un cas à plusieurs scénarios dont un seul interroge
    l'oracle laisserait croire que les AUTRES l'ont été aussi, alors qu'ils ne prouvent que l'UI.
    Même convention que `functional_status = conforme` (`aggregate`, ci-dessous), qui exige que
    TOUS les scénarios soient conformes — jamais qu'un seul le soit. `confiance`, à l'inverse, prend
    le scénario le MOINS sûr : les deux vont dans le même sens prudent, seul le sens de comparaison
    change selon que la valeur qualifiée est « bonne » (ground_truth, conforme) ou « mauvaise »
    (confiance, functional_status non_conforme).
    """
    # Lot VH-04 (point 4, audit V6) : plus de « vérifié côté serveur » d'office pour Odoo. Avant, tout cas Odoo l'était —
    # même un cas qui n'avait constaté QUE l'écran. Désormais, quel que soit le connecteur : chaque scénario a recoupé le
    # serveur sous un `Alors` (oracle, ou lecture RPC observée pendant le step du constat), sinon `ui_only`.
    return GROUND_TRUTH_BACKEND_VERIFIED if oracle_utilise else GROUND_TRUTH_UI_ONLY


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
    # Lot 05 (D5) : comment CE scénario a abouti. `nominale` par défaut = tout appelant qui ne calcule pas la confiance
    # (rapports relus depuis la base, historique) garde le comportement d'avant.
    confiance: str = CONFIANCE_NOMINALE
    # Les éléments (champ, menu) qu'un repli adaptatif a dû retrouver dans CE scénario — de quoi expliquer « à confirmer ».
    resolutions_adaptatives: list[str] = field(default_factory=list)
    # Lot 07e (D7) : ce scénario a interrogé l'oracle backend sous un `Alors` (réussi ou échoué).
    oracle_verifie: bool = False
    serveur_verifie: bool = False  # lot VH-04 (point 4) : oracle OU lecture RPC observée sous un `Alors`
    # A52 : la ligne du scénario dans le fichier joué (`BehaveScenario.ligne`) et les rangs des itérations qu'il couvre (vide =
    # toutes), que `run_service._persist` déduit de la ligne. Aucune règle de verdict ne les lit : ils ne servent qu'à montrer
    # le résultat de chaque itération (`statuts_par_iteration`).
    ligne: int = 0
    iterations: tuple[int, ...] = ()


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
    # Lot 05 (D5) : la moins sûre des confiances de ses scénarios (voir `_RANG_CONFIANCE`).
    confiance: str = CONFIANCE_NOMINALE


def qualifier_confiance(verdicts: list[ScenarioVerdict], *, rejoue: bool,
                        paliers: list[dict] | None) -> None:
    """Pose `confiance` (et `resolutions_adaptatives`) sur chaque scénario — calcul PUR, modifie en place.

    Règle (D5) : `apres_retry` si l'outcome a été rejoué ; sinon `auto_resolue` si au moins une résolution ADAPTATIVE
    a eu lieu dans le scénario ; sinon `nominale`. Une résolution dont le scénario n'est pas identifié (hook absent,
    ligne ancienne) qualifie TOUS les scénarios : sans nom on ne peut pas prouver qu'un scénario n'est pas concerné, et se
    tromper vers « nominale » serait le faux vert que ce champ existe pour éviter. Même limite assumée que les constats :
    deux scénarios de même nom (« Plan du scénario ») partagent leurs résolutions.
    """
    adaptatives = [p for p in (paliers or []) if isinstance(p, dict) and p.get("tier") == PALIER_ADAPTATIF]
    for v in verdicts:
        concernees = [p for p in adaptatives if p.get("scenario") in ("", None, v.name)]
        idents: list[str] = []
        for p in concernees:
            ident = str(p.get("ident") or "").strip()
            if ident and ident not in idents:
                idents.append(ident)
        v.resolutions_adaptatives = idents
        adaptative = bool(concernees)
        if rejoue:
            v.confiance = CONFIANCE_APRES_RETRY
        elif adaptative:
            v.confiance = CONFIANCE_AUTO_RESOLUE
        else:
            v.confiance = CONFIANCE_NOMINALE


def _failures_by_scenario(failures) -> dict[str, list]:
    grouped: dict[str, list] = {}
    for f in failures or []:
        grouped.setdefault(f.scenario_name, []).append(f)
    return grouped


def scenario_verdict(scenario, failures: list) -> ScenarioVerdict:
    """Projette un scénario behave + ses échecs sur les deux axes."""
    verdict = _scenario_verdict_axes(scenario, failures)
    verdict.oracle_verifie = bool(getattr(scenario, "oracle_verifie", False))
    verdict.serveur_verifie = verdict.oracle_verifie or bool(getattr(scenario, "serveur_verifie", False))
    verdict.ligne = int(getattr(scenario, "ligne", 0) or 0)   # transportée pour l'affichage, jamais lue ici
    return verdict


def _scenario_verdict_axes(scenario, failures: list) -> ScenarioVerdict:
    if scenario.status == "passed":
        if (getattr(scenario, "constats_echoues", None) or 0) > 0:
            # Lot VH-02 (V10) : une vérification a ÉCHOUÉ pendant ce scénario, et pourtant il est allé au bout — l'échec a été
            # avalé (exception rattrapée dans le code du test). Un autre constat réussi ne rachète pas celui-là.
            return ScenarioVerdict(scenario.name, EXEC_SUCCESS, FUNC_INDETERMINE, "", dt.CONSTAT_ECHOUE_IGNORE,
                                   "Une vérification a échoué sans faire échouer le test")
        if getattr(scenario, "constats_reussis", None) == 0:
            # Lot 03 (D3) : le scénario est allé au bout, mais AUCUN constat réussi n'a été consigné
            # sous un `Alors` (assertion dans une branche non prise, `Alors` qui ne fait qu'attendre…).
            # Un vert sans preuve n'est pas `conforme` — `indetermine`, à revérifier. `None` (mécanisme
            # absent : dry-run, résultat hors runner) laisse le comportement historique.
            return ScenarioVerdict(scenario.name, EXEC_SUCCESS, FUNC_INDETERMINE,
                                   "", dt.AUCUN_CONSTAT, "Aucune vérification exécutée")
        alors_vides = getattr(scenario, "alors_sans_constat", None)
        if alors_vides:
            # Q1 (D16) : au moins un `Alors` ASSERTIF est passé sans rien constater. Un autre constat réussi ne le
            # couvre pas : ce qu'il annonçait n'a jamais été vérifié. `indetermine`, cause existante `aucun_constat`
            # (aucune nouvelle valeur d'enum) ; le step fautif est porté en TRACE (`step_text`), jamais en critère.
            return ScenarioVerdict(scenario.name, EXEC_SUCCESS, FUNC_INDETERMINE, "", dt.ALORS_SANS_CONSTAT,
                                   "Un « Alors » n'a rien vérifié", step_text=alors_vides[0])
        return ScenarioVerdict(scenario.name, EXEC_SUCCESS, FUNC_CONFORME)

    if scenario.status == "failed":
        cause = dt.dominant_category(failures) or dt.UNKNOWN
        failure_type = failures[0].failure_type if failures else ""
        step_text = failures[0].step_text if failures else ""
        if cause in (dt.REFUS_NON_EXPLIQUE, dt.ORACLE_EN_ERREUR, dt.ALORS_SANS_CONSTAT):
            # Lot VH-04 : un oracle qui répond en ERREUR n'a rien observé non plus — même règle, jamais `non_conforme`.
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
    # `getattr` : même tolérance que `constats_reussis` ci-dessus pour un résultat construit à la main (doublures de
    # test) — `ExecutionOutcome` et `BehaveResult` portent toujours ces deux champs en production.
    qualifier_confiance(verdicts, rejoue=bool(getattr(outcome, "retried", False)),
                        paliers=getattr(real, "selector_tiers", None))
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
        ground_truth=_ground_truth_pour(
            connector_type, bool(verdicts) and all(v.serveur_verifie or v.oracle_verifie for v in verdicts)),
        confiance=max((v.confiance for v in verdicts), key=lambda c: _RANG_CONFIANCE.get(c, 0),
                      default=CONFIANCE_NOMINALE),
    )


def statuts_par_iteration(scenarios: list[ScenarioVerdict], nombre: int, statut_du_cas: str) -> list[str]:
    """A52 : le statut de lecture de chaque itération (rang 1 à `nombre`), pour l'écran — jamais un verdict.

    Une itération est jugée sur ses scénarios — ceux qui la portent, et ceux qui les couvrent toutes (sans étiquette) — par la
    MÊME règle que le cas (`aggregate` puis `statut_de_test`) : sans scénario rapporté, « non testé », jamais « réussi ».
    Garde-fou : quand le cas n'est pas réussi alors que toutes ses itérations le paraissent (une garde au niveau du cas l'a
    déclassé), elles prennent le statut du cas — l'écran ne montre jamais tout en vert un cas qui ne l'est pas. De même quand
    aucune n'a de scénario rapporté (revue du 2026-10-18 : « Untested » partout sous un cas « Blocked »)."""
    statuts = []
    for rang in range(1, max(0, nombre) + 1):
        siens = [s for s in scenarios if not s.iterations or rang in s.iterations]
        verdict = aggregate(siens)
        statuts.append(statut_de_test(verdict.execution_status, verdict.functional_status))
    if statuts and statut_du_cas != STATUT_PASSED and all(s == STATUT_PASSED for s in statuts):
        return [statut_du_cas] * len(statuts)
    if statuts and statut_du_cas not in (STATUT_PASSED, STATUT_UNTESTED) and all(s == STATUT_UNTESTED for s in statuts):
        return [statut_du_cas] * len(statuts)   # aucun scénario rapporté (interruption) : l'écran dit ce que dit le cas
    return statuts


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
# Les libellés de l'écran (vocabulaire de TestRail), DUPLIQUÉS de `frontend/src/lib/status.ts::TEST_STATUS` pour le rapport
# imprimable — un test vérifie qu'ils sont d'accord (CONTINUITE §4.7 : aucune valeur brute à l'écran).
LIBELLES_STATUT = {STATUT_PASSED: "Passed", STATUT_FAILED: "Failed", STATUT_RETEST: "Retest", STATUT_BLOCKED: "Blocked",
                   STATUT_UNTESTED: "Untested"}

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


# ── D31 (validée par le porteur le 2026-10-09) : un « Réussi » obtenu contre une AUTRE attente métier ──────────────────
#
# Avant : éditer le résultat attendu ou les étapes d'un cas gardait l'ancien test, approuvé d'office (amendement §4.3), et le
# cas continuait d'afficher « Réussi » — obtenu contre l'ancienne attente. Exemple : « remise de 10 % » devient « 15 % », le
# test vérifie toujours 10 %, l'application applique 10 %, le cas reste vert ; le bug (pas de passage à 15 %) est invisible.
# Désormais, tant qu'aucun run n'a eu lieu sur une version portant la NOUVELLE attente, le cas affiche « Retest ».
# On ne recalcule PAS le résultat et on ne masque aucun run (décision 0016 (iii)) : seule l'étiquette de LECTURE du cas
# change, et seulement de `passed` vers `retest` — un échec reste un échec, le run garde son verdict dans l'historique.

def statut_du_cas(execution: str | None, functional: str | None, *, attente_changee: bool) -> str:
    """L'étiquette de lecture d'un CAS : `statut_de_test`, sauf un `passed` obtenu contre une autre attente métier."""
    statut = statut_de_test(execution, functional)
    return STATUT_RETEST if attente_changee and statut == STATUT_PASSED else statut


def sql_statut_du_cas(execution: str, functional: str, attente_changee: str) -> str:
    """Forme SQL de `statut_du_cas` — `attente_changee` est une expression SQL booléenne (comparée en test)."""
    derive = sql_statut(execution, functional)
    return (f"CASE WHEN ({attente_changee}) AND ({derive}) = '{STATUT_PASSED}' THEN '{STATUT_RETEST}'"
            f" ELSE ({derive}) END")
