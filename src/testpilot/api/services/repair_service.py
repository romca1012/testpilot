"""Boucle de réparation — L'ORCHESTRATEUR PILOTE (décision 0014, étape 3).

    run vN → échec → circuit.evaluate() → l'agent propose → vN+1 → run vN+1 → …

⚠️ **Le circuit décide, jamais l'agent.** `repair_circuit.evaluate()` a été écrit pour ça : il
rend `should_continue`. L'agent, lui, ne fait que proposer une correction — il n'a aucun outil
pour exécuter (design (b) arbitré). Lui donner ce pouvoir remettrait le garde-fou dans les mains
du composant qu'il encadre, alors que `0012` a montré que le circuit lit un texte que l'agent
écrit lui-même.

**Modèle B** : une exécution = **un run réel d'une version**. Chaque ligne d'exécution reste
donc vraie (une version, un verdict, un run) et §4.2 tient littéralement, ligne par ligne. Le
prix est un historique plus fourni ; c'est la trace honnête.

**Le gate reste souverain** (§4.3) : le budget vient de la relecture (`0014` étape 2), et une
version réparée **n'est jamais approuvée d'office** — elle repasse « à relire » pour ratification
avant tout run futur. Fabriquer une `review_decision` signée par l'IA serait l'auto-approbation
qu'on a écartée.

**Le critère d'adoption, en un coup d'œil** (`0016` + `0018`) — l'ordre est le contrat :

    on ADOPTE si   (le test tourne ENTIÈREMENT   [0016, est_executable]
                    OU il tourne MIEUX qu'avant  [0018, progresse])
      ET PAS de régression      [principe 5     — un scénario vert devenu rouge]
      ET PAS de couverture perdue [0018          — un scénario DISPARU]

Les deux refus priment sur les deux voies d'adoption, et ce n'est pas un détail : « moins d'échecs
techniques » s'obtient trivialement **en supprimant les scénarios qui échouent**. Le principe 5 ne
l'attrape pas (il ne surveille que les scénarios *verts*) — c'est `couverture_perdue` qui ferme
cette porte, et sans elle `progresse` serait une invitation au masquage d'échec (§5 du brief).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from testpilot import config
from testpilot.generation import memoire_reparation, repair_agent
from testpilot.guardrails.cost_tracker import CostTracker
from testpilot.guardrails.repair_circuit import CircuitState, evaluate, failure_signature
from testpilot.store.repositories import (
    CaseRepo,
    CostRepo,
    ExecutionRepo,
    RepairRepo,
    ReviewRepo,
    VersionRepo,
)
from testpilot.verdict.status import EXEC_SUCCESS, FUNC_CONFORME, derive_verdict

logger = logging.getLogger(__name__)

# Issue propre à cette boucle : le test n'a pas tourné du tout (le circuit, lui, ne connaît que
# des ÉCHECS — il n'a aucun moyen de distinguer « aucun échec » de « aucun run »).
RUN_FAILED = "run_failed"
# Le test tourne, mais la réparation a cassé des scénarios qui passaient (principe 5). Distinct de
# `run_failed` : ici le test s'exécute — c'est la COUVERTURE qui a reculé.
REGRESSION = "regression"
# La réparation a SUPPRIMÉ des scénarios (garde de couverture, 0018). Distinct de `regression` :
# là un scénario vert est devenu rouge (il existe encore, il échoue) ; ici il a DISPARU. Le second
# est pire — il ne laisse aucune trace, et il améliore les chiffres. Ligne rouge du §5 du brief.
COVERAGE_LOST = "coverage_lost"
# Le §9 du brief est atteint : les réparations CUMULÉES du cas ont épuisé leur marge. Le brief §6
# veut que « le premier seuil atteint déclenche une escalade vers un humain avec un rapport de ce
# qui a été essayé » — les deux seuils sont donc tentatives (le circuit) ET budget (celui-ci).
# Distinct d'`agent_no_fix` : là l'agent n'avait rien à proposer, ici on l'a coupé.
COST_EXCEEDED = "cost_exceeded"


@dataclass
class RepairSession:
    """Ce que la boucle a fait — assez pour l'expliquer à un humain."""

    attempts: int = 0
    outcome: str = ""              # issue du circuit (resolved | real_bug | stalled | …)
    reason: str = ""
    resolved: bool = False         # run entièrement VERT (axe fonctionnel compris)
    # Le test TOURNE ENTIÈREMENT (axe exécution seul) — voie d'adoption de 0016. Distinct de
    # `resolved` : un test qui tourne et révèle un vrai bug est réparé, pas raté.
    executable: bool = False
    # Le test tourne MIEUX qu'au départ (moins d'échecs techniques) — seconde voie d'adoption,
    # décision 0018. Sans elle, un test à moitié réparé est jeté et le rejeu suivant rachète le
    # même travail.
    progresse: bool = False
    # Scénarios qui passaient AVANT et ne passent plus APRÈS (principe 5). Non vide ⇒ pas
    # d'adoption, quoi que disent `executable`/`progresse`.
    regressions: list[str] = field(default_factory=list)
    # COMBIEN de scénarios ont DISPARU (garde de couverture, 0018). > 0 ⇒ pas d'adoption, jamais :
    # c'est la contrepartie obligatoire de `progresse` — supprimer un scénario en échec ferait
    # sinon « progresser » le compteur. Ligne rouge du §5 du brief.
    # Un COMPTE, pas des noms : un nom de scénario est écrit par l'agent (principe 1).
    couverture_perdue: int = 0
    final_version_id: int | None = None
    executions: list[int] = field(default_factory=list)
    cost_usd: float = 0.0


def a_tourne(outcome) -> bool:
    """Le test s'est-il RÉELLEMENT exécuté ?

    ⚠️ **Distinction vitale, trouvée en run réel (étape 6).** Quand le dry-run échoue, Behave ne
    joue rien et `Executor` rend `real_run=None` → `_failures_of` donnait alors une liste vide,
    **exactement comme un test qui passe**. Le circuit concluait « plus aucun échec — réparation
    terminée » alors que **le test n'avait jamais tourné** : il adoptait une version cassée en
    proclamant sa victoire.

    C'est le **faux négatif** que §4.4 déclare inacceptable, et le motif déjà traqué en `0010`,
    `0011` et `0013` : **l'absence de signal prise pour un signal positif**. Mesuré : l'exécution
    13 (v7) avait 0 scénario et la réparation s'est déclarée réussie.
    """
    return outcome is not None and getattr(outcome, "real_run", None) is not None


def _record_cost(conn, execution_id: int | None, cost_usd: float) -> None:
    """Écrit le coût d'un appel de réparation au ledger ET sur l'exécution qui l'a provoqué.

    ⚠️ **Le §9 du brief — « moins de 1 € pour la génération + exécution d'un module » — n'était
    pas mesurable sur ce chemin.** `cost_ledger` n'était alimenté que par la CLI ; tout ce qui
    passe par l'API (donc par l'écran, donc par cette boucle) dépensait sans laisser de trace, et
    `run_service._persist` écrit `cost_usd=0.0` en dur. Cinq appels à l'agent le 2026-07-17
    (v7→v11) n'ont produit **aucune ligne** de ledger.

    On rattache le coût à l'exécution qui a **provoqué** la proposition (l'échec à réparer) : elle
    existe toujours, alors que la version proposée peut n'être jamais exécutée. Le total par cas
    se lit ensuite par `CostRepo.total_for_case_usd`.

    Best-effort : une écriture de comptabilité ne doit jamais faire échouer une réparation qui,
    elle, a réussi — mais elle ne doit pas non plus disparaître en silence (§4.6).
    """
    if not cost_usd:
        return
    try:
        CostRepo(conn).add_entry(phase="repair", model=config.MODEL_REPAIR,
                                 cost_usd=cost_usd, source=config.COST_SOURCE,
                                 execution_id=execution_id)
        if execution_id is not None:
            ExecutionRepo(conn).add_cost(execution_id, cost_usd)
    except Exception:
        logger.exception("[repair] coût de %s USD NON enregistré (exécution %s) — le budget §9 "
                         "sera sous-évalué d'autant", cost_usd, execution_id)


def _scenarios_verts(outcome) -> set[str]:
    """Noms des scénarios `success/conforme` d'un run. Vide si le test n'a pas tourné."""
    if not a_tourne(outcome):
        return set()
    return {v.name for v in derive_verdict(outcome).scenarios
            if v.execution_status == EXEC_SUCCESS and v.functional_status == FUNC_CONFORME}


def regressions(avant, apres) -> list[str]:
    """Scénarios qui passaient AVANT la réparation et ne passent plus APRÈS (principe 5).

    ⚠️ **Coût marginal NUL** : la boucle exécute déjà le test avant et après — les deux runs sont
    faits et payés. Comparer est une lecture, pas une exécution de plus. C'est ce qui rend cette
    garde inconditionnelle : elle n'a aucun prix.

    Elle attrape ce qu'AUCUNE analyse statique ne peut voir : un scénario **supprimé**. Un step
    n'est `undefined` (donc rattrapé par le dry-run) que si le `.feature` le réclame ENCORE. Si
    l'agent réécrit les DEUX fichiers et retire un scénario avec son step, le dry-run est
    satisfait — et le run paraît **meilleur** : moins de scénarios, donc moins d'échecs. C'est
    « l'absence de signal prise pour un signal positif » sous sa forme la plus dangereuse, puisque
    supprimer la couverture **améliore** les chiffres.

    Un scénario disparu compte donc comme une régression : il passait, il ne passe plus — ne plus
    exister n'est pas une réussite.
    """
    return sorted(_scenarios_verts(avant) - _scenarios_verts(apres))


def _nb_scenarios(outcome) -> int:
    """COMBIEN de scénarios ont été joués. -1 si le test n'a pas tourné (≠ « zéro scénario »)."""
    if not a_tourne(outcome):
        return -1
    return len(outcome.real_run.scenarios)


def couverture_perdue(avant, apres) -> int:
    """Combien de scénarios ont DISPARU entre les deux runs — la garde de couverture (`0018`).

    ⚠️ **Indissociable de `progresse()`. Jamais l'une sans l'autre.** Adopter sur le progrès de
    l'axe exécution (« moins d'échecs techniques qu'avant ») ouvre une porte béante : **le moyen
    le plus simple de réduire les échecs est de SUPPRIMER les scénarios qui échouent.** Mesuré
    avant d'écrire ce code, contre le vrai `regressions()` :

        supprimer un scénario qui PASSAIT    → regressions() rend ['A']  → refusé ✅
        supprimer un scénario EN ÉCHEC       → regressions() rend []     → ACCEPTÉ ❌

    Le principe 5 ne surveille que les scénarios **verts** : il ne voit pas partir un scénario qui
    échouait. Sans cette garde, « supprimer la couverture » deviendrait la **stratégie gagnante**
    de la boucle — et le run suivant paraîtrait parfait. C'est la **ligne rouge du §5 du brief**
    (« jamais de masquage d'un échec ») et le motif que `PRINCIPES.md` nomme le plus dangereux :
    *« l'absence de signal prise pour un signal positif, sous sa forme la plus dangereuse, puisque
    supprimer la couverture améliore les chiffres »*.

    ⚠️ **ON COMPTE, ON NE COMPARE PAS LES NOMS — et c'est le PRINCIPE 1.** Mon premier jet
    diffait les `scenario_name` : `sorted(noms_avant - noms_apres)`. Les tests de `0016` l'ont
    immédiatement attrapé, et ils avaient raison — **un nom de scénario est du texte écrit par
    l'agent**. Il lui suffisait de **renommer** un scénario pour que la garde croie à une
    suppression et **refuse une réparation légitime**. C'est exactement la faute que
    `failure_signature` avait déjà payée (`PRINCIPES.md`, principe 1 : *« renommer un scénario
    suffisait à changer la signature »*) — je l'ai rejouée à l'identique, dans la garde censée
    protéger la couverture.

    Le **nombre** de scénarios est un fait structurel du run, insensible aux libellés.

    **Limite assumée, à ne pas taire** : un agent qui supprimerait 2 scénarios en échec et en
    ajouterait 2 triviaux garderait le compte constant et passerait. Un diff par nom l'attraperait
    — au prix d'un faux positif à chaque renommage, qui bloquerait la convergence que `0018`
    existe pour obtenir. **Arbitrage assumé : le faux négatif exotique plutôt que le faux positif
    systématique.** La version est de toute façon relue (`to_review`, §4.3), et le lint `0008`
    passe au gate sur les assertions triviales.

    **Coût nul** : les deux runs sont déjà faits et payés (comme le principe 5).
    """
    n_avant, n_apres = _nb_scenarios(avant), _nb_scenarios(apres)
    if n_avant < 0 or n_apres < 0:
        return 0        # pas de run d'un côté : rien à comparer (`a_tourne` tranche ailleurs)
    return max(0, n_avant - n_apres)


def _echecs_techniques(outcome) -> int:
    """Nombre de scénarios en échec TECHNIQUE (axe exécution). -1 si le test n'a pas tourné.

    `-1` et non `0` : « pas de run » n'est pas « aucun échec ». C'est le piège de `a_tourne()`,
    et le rendre comparable par erreur ferait passer une version injouable pour un progrès.
    """
    if not a_tourne(outcome):
        return -1
    return sum(1 for v in derive_verdict(outcome).scenarios
               if v.execution_status != EXEC_SUCCESS)


def progresse(avant, apres) -> bool:
    """L'axe EXÉCUTION a-t-il progressé ? — le critère d'adoption de `0018`.

    ⚠️ **`0016` avait corrigé « réparée = passe au vert » en « réparée = TOURNE ». Mais « tourne »
    est resté du TOUT-OU-RIEN** : `est_executable` exige que TOUS les scénarios tournent, donc une
    version où 1 scénario sur 3 tourne proprement valait exactement une version où 0 sur 3
    tournent. Le tout-ou-rien est plus tenace que l'axe qu'il habite.

    Mesuré (cas 1, rejeu du 2026-07-17, exécutions 25 → 27) : `v7` délègue l'authentification, ne
    réinvente aucun transport et fait passer **1 scénario sur 3** là où `v1` en passe **0**. Elle a
    été **jetée**, le disque rembobiné sur `v1` — et le rejeu suivant a redépensé son budget à
    re-corriger le `404` et l'auth **déjà corrigés**. **$0,41 de travail racheté par rejeu.** La
    boucle ne pouvait pas converger : il lui faut ~4 tentatives, elle en a 2, et elle ne gardait
    rien entre deux sessions.

    Progresser = **strictement moins de scénarios en échec technique qu'au départ**. Un test qui
    passe de 3 échecs à 2 a avancé : on le garde, et la session suivante repart de là.

    ⚠️ **Ne dit RIEN de l'axe fonctionnel** (§4.1) : un test qui tourne et révèle un vrai bug
    progresse — c'est même le but de l'outil.
    """
    n_avant, n_apres = _echecs_techniques(avant), _echecs_techniques(apres)
    if n_apres < 0:
        return False        # le test ne tourne plus du tout : jamais un progrès
    if n_avant < 0:
        return True         # il ne tournait pas, il tourne : c'est le progrès maximal
    return n_apres < n_avant


def est_executable(outcome) -> bool:
    """Le test TOURNE-t-il ENTIÈREMENT ? — le critère d'adoption de `0016`.

    ⚠️ **Depuis `0018`, ce n'est plus la seule voie d'adoption** : `progresse()` en ouvre une
    seconde, pour le progrès PARTIEL. Cette fonction reste la définition de « le test tourne »,
    utilisée pour `session.executable` et le rapport — elle n'est simplement plus le seul juge.

    ⚠️ « Tourne » (axe EXÉCUTION) et « passe » (axe FONCTIONNEL) sont deux choses, et §4.1 exige
    qu'elles ne fusionnent jamais. La boucle adoptait une réparation seulement si le run était
    **entièrement vert** — elle fusionnait donc les deux axes, dans la direction la plus coûteuse :
    **un test réparé qui détecte un vrai bug ne pouvait JAMAIS être adopté**. Plus l'application
    était défectueuse, moins l'outil savait garder ses propres réparations.

    Mesuré (cas 1, exécutions 16 → 17) : `v1` mourait en `HTTPError 404` (0/3, l'outil ne juge
    rien) ; la réparation `v9` faisait TOURNER le test (`success/non_conforme`, 1/3, deux
    assertions en échec — un constat sur l'application). `v9` a été jetée, le disque rembobiné,
    et le run suivant refaisait le 404 — indéfiniment, en rebrûlant le budget à chaque fois.

    On délègue à `derive_verdict` plutôt que de relire les échecs ici : les deux axes doivent se
    calculer à UN SEUL endroit, sinon ils dérivent — et la dérive serait à diagnostiquer plus tard.

    C'est la règle du §5, celle des deux axes : *« un test qui tourne et détecte un vrai bug est
    un SUCCÈS technique »*. Elle était aussi portée par `review_gate.validation_status_after_run`,
    supprimée avec la migration 25 — la règle, elle, n'a pas bougé d'un pouce.
    """
    if not a_tourne(outcome):
        return False
    return derive_verdict(outcome).execution_status == EXEC_SUCCESS


def _failures_of(outcome) -> list:
    """Échecs du run. ⚠️ Vide ne veut RIEN dire sans `a_tourne()` : voir sa docstring."""
    return list(outcome.real_run.failures) if a_tourne(outcome) else []


def _scenarios_of(outcome) -> list:
    return list(outcome.real_run.scenarios) if outcome and outcome.real_run else []


def _routes_du_cas(outcome) -> list[str]:
    """Les routes que ce run a réellement touchées, pour ne montrer que les règles pertinentes.

    Lues sur les refus MESURÉS du run (`route` y est déjà normalisée), jamais devinées dans le
    texte des scénarios — qui est écrit par l'agent. Vide → la mémoire montre tout ce que le
    projet a appris : mieux vaut un peu de bruit qu'une règle utile passée sous silence.
    """
    run = getattr(outcome, "real_run", None)
    return sorted({str(m.get("route")) for m in (getattr(run, "refus_mesures", None) or [])
                   if isinstance(m, dict) and m.get("route")})


def run_repair_loop(conn, *, case_id: int, version_id: int, module_name: str,
                    outcome, run_once, connector=None, dry_runner=None) -> RepairSession:
    """Répare tant que le circuit l'autorise. `run_once(version_id) -> outcome` est injecté.

    `outcome` est le résultat du run initial (déjà persisté par l'appelant) : la boucle part de
    son échec. `run_once` crée une exécution et la persiste — la boucle ne sait pas comment,
    c'est ce qui la rend testable sans Behave ni Odoo.

    ⚠️ `dry_runner` n'est PAS optionnel en production, malgré son défaut. `repair_agent` promet
    dans sa docstring que « le dry-run valide le correctif, et seulement ensuite l'orchestrateur
    le rejoue pour de vrai ». Cette boucle ne le passait pas : la promesse était fausse, et le
    correctif n'était validé par RIEN avant un run réel de ~300 s. Le défaut à `None` existe pour
    les tests qui injectent l'agent (ils n'ont ni Behave ni disque) ; `run_service` passe le vrai
    runner, et un test le garde (`test_repair_dry_run.py`).
    """
    session = RepairSession()
    budget = ReviewRepo(conn).repair_budget_for_version(version_id)

    # Le budget EST le plafond du circuit : budget=0 → `evaluate` coupe au premier tour
    # (0 >= 0) sans aucun cas particulier. Le garde-fou existant fait le travail.
    circuit = CircuitState(max_iterations=budget, stall_limit=config.REPAIR_STALL_LIMIT)

    # ⚠️ PLAFOND CUMULÉ PAR CAS = génération + TOUTES les réparations, borné au §9 (BUDGET_PER_CASE
    # — l'unique cible de coût du produit, « réparations cumulées comprises »).
    #
    # Deux trous comblés ici, au-delà du « un seul tracker par session » déjà en place :
    #  1. le tracker repartait de $0 à CHAQUE appel de la boucle (nouveau `CostTracker`), donc les
    #     réparations d'une session ignoraient celles des sessions précédentes du même cas ;
    #  2. il ne comptait QUE les réparations : la GÉNÉRATION n'entrait jamais dans le plafond.
    # Résultat : deux sous-plafonds indépendants ($0,50 génération + $0,62 réparations) pouvaient
    # s'additionner AU-DESSUS du §9 ($1,12 = 104 %) alors que chaque poste restait sous son seuil.
    #
    # On SEEDE donc le tracker avec ce que le cas a DÉJÀ dépensé (génération + réparations
    # antérieures, lues au ledger) et on plafonne au §9 : le cumul vivant ne peut plus franchir le
    # plafond global, quelle que soit la répartition entre postes. `REPAIR_COST_LIMIT_PER_CASE_USD`
    # (sous-plafond réparations-seules) est SUPERSÉDÉ par cette enveloppe unique.
    #
    # ⚠️ Cela lit `total_for_case_usd` — que le §9-KPI ne doit PAS lire (arbitrage porteur : le KPI
    # se compare à la CRÉATION, cf. `creation_cost_usd`). Ici ce n'est pas le KPI, c'est le
    # GARDE-FOU de dépense : borner le cumul au §9 est une enveloppe de sécurité, pas une mesure.
    deja_depense = CostRepo(conn).total_for_case_usd(case_id)
    cost_tracker = CostTracker(limit_usd=config.BUDGET_PER_CASE_USD, initial_cost=deja_depense)

    versions = VersionRepo(conn)
    cases = CaseRepo(conn)
    # Le projet du cas : il désigne l'annuaire ET les règles apprises (`0005` — un annuaire par
    # instance). Absent → la mémoire se taira, la réparation se lancera quand même.
    project_id = (cases.get(case_id) or {}).get("project_id")
    current_version_id = version_id
    failures = _failures_of(outcome)
    # État de départ, figé AVANT toute réparation : c'est la référence de non-régression
    # (principe 5). Gratuit — ce run est déjà fait et déjà payé.
    outcome_depart = outcome

    while True:
        # ⚠️ AVANT toute évaluation : un test qui n'a pas tourné n'a pas « zéro échec », il n'a
        # pas de résultat. Laisser `evaluate` voir une liste vide lui ferait conclure
        # « résolu » — et la boucle adopterait une version cassée (bug trouvé en run réel).
        if not a_tourne(outcome):
            session.outcome = RUN_FAILED
            session.reason = (
                "le test n'a pas pu s'exécuter (dry-run en échec) — il ne parse plus. "
                "La réparation l'a cassé, ou la version de départ était déjà injouable."
            )
            logger.warning("[repair] cas %s : le test ne tourne plus après %s tentative(s) — "
                           "aucune adoption", case_id, session.attempts)
            break

        decision = evaluate(circuit, failures)
        session.outcome, session.reason = decision.outcome, decision.reason
        if not decision.should_continue:
            break

        version = versions.get(current_version_id)
        if version is None:
            session.outcome, session.reason = "error", "version courante introuvable"
            break

        # Ce que ce cas a DÉJÀ appris — recalculé à CHAQUE tentative (une requête SQL et un
        # fichier, gratuit). C'est ce qui permet à la tentative 2 de savoir ce que le run de la
        # tentative 1 vient de prouver, au lieu de le redécouvrir en le repayant.
        regles, faits = memoire_reparation.collecter(
            conn, case_id=case_id, project_id=project_id, routes=_routes_du_cas(outcome))

        # 1. L'agent propose — il ne décide de rien.
        proposal = repair_agent.propose_fix(
            module_name=module_name,
            scenarios=_scenarios_of(outcome),
            failures=failures,
            memoire=memoire_reparation.as_prompt_section(regles, faits),
            # Le fichier ACTUEL : `write_steps_file` le REMPLACE, l'agent doit donc partir de
            # son contenu et le rendre entier — sans lui, il réécrit de mémoire et tronque.
            steps_content=version["steps_content"] or "",
            connector=connector,
            # Le dry-run rattrape DANS la session ce qui, sinon, coûte un run réel pour rien :
            # un correctif qui ne parse plus, ou un step supprimé que le `.feature` réclame
            # encore. Mesuré au rejeu du 2026-07-17 (v12) : l'agent a retiré son step d'auth sans
            # toucher au `.feature` → `undefined` → RUN_FAILED. Sans dry-run ici, l'agent n'a
            # jamais su qu'il avait cassé le test ; avec, il reçoit la liste des steps undefined
            # et corrige dans le MÊME appel.
            dry_runner=dry_runner,
            # Partagé entre les tentatives : c'est LUI qui fait du plafond un plafond de CAS.
            cost_tracker=cost_tracker,
        )
        session.cost_usd = round(session.cost_usd + proposal.cost_usd, 6)
        # Le coût est enregistré ICI, avant tout `break` : un agent qui ne propose RIEN a quand
        # même coûté. Le compter seulement quand ça marche donnerait un budget flatteur — soit
        # « affiché ≠ réel » (§4.6) appliqué à l'argent.
        _record_cost(conn, getattr(outcome, "execution_id", None), proposal.cost_usd)

        if proposal.stopped_reason == "cost_exceeded" and not proposal.changed:
            # Le plafond a coupé avant que l'agent n'écrive quoi que ce soit : insister
            # rebrûlerait sans rien produire. Escalade humaine (§6 du brief), avec le chiffre.
            session.outcome = COST_EXCEEDED
            session.reason = (
                f"plafond de coût des réparations atteint "
                f"(${cost_tracker.total_cost:.4f} / ${cost_tracker.limit_usd:.2f}) après "
                f"{session.attempts} tentative(s) — le §9 du brief (moins de 1 €/cas) borne le "
                f"cas entier. À reprendre par un humain."
            )
            logger.warning("[repair] cas %s : budget épuisé (%.4f/%.2f USD) après %s tentative(s)",
                           case_id, cost_tracker.total_cost, cost_tracker.limit_usd,
                           session.attempts)
            break

        if not proposal.changed:
            # Aveu utile : l'agent n'a rien réécrit (il ne sait pas, ou il conclut à un bug de
            # l'application). Insister brûlerait le budget pour rien.
            session.outcome = "agent_no_fix"
            session.reason = proposal.summary or "l'agent n'a proposé aucune correction"
            break

        # 2. Une tentative = une VERSION (trace honnête de ce qui a été tenté).
        new_version_id = versions.create(
            test_case_id=case_id,
            spec_content=version["spec_content"], spec_hash=version["spec_hash"],
            feature_content=proposal.feature_content or version["feature_content"],
            steps_content=proposal.steps_content or version["steps_content"],
            change_summary=proposal.summary[:500] or "Réparation automatique",
            created_by="repair-agent",
        )
        session.attempts += 1
        circuit.record(failure_signature(failures))

        # 3. On rejoue — nouvelle EXÉCUTION (modèle B).
        _record_attempt(conn, outcome, failures, session.attempts, proposal.summary)
        outcome = run_once(new_version_id)
        session.executions.append(getattr(outcome, "execution_id", None))
        failures = _failures_of(outcome)
        current_version_id = new_version_id

    session.resolved = (session.outcome == "resolved")
    # Décision 0016 : on adopte dès que le test TOURNE — jamais « dès qu'il passe ». `resolved`
    # (run entièrement vert) reste distinct et informatif, mais il ne commande plus rien.
    session.executable = est_executable(outcome)
    # Décision 0018 : le progrès PARTIEL de l'axe exécution suffit — sinon la boucle jette un test
    # à moitié réparé et rachète le même travail au rejeu suivant.
    session.progresse = progresse(outcome_depart, outcome)
    # Principe 5 : n'avoir rien cassé de ce qui PASSAIT.
    session.regressions = regressions(outcome_depart, outcome)
    # Garde de couverture (0018) : n'avoir rien SUPPRIMÉ, même en échec. Indissociable du critère
    # de progrès — sans elle, supprimer les scénarios qui échouent serait la stratégie gagnante.
    session.couverture_perdue = couverture_perdue(outcome_depart, outcome)
    session.final_version_id = current_version_id

    a_tente = current_version_id != version_id
    # ⚠️ L'ORDRE DES GARDES EST LE CONTRAT. Les deux refus passent AVANT toute adoption : une
    # version qui a perdu de la couverture n'est jamais adoptée, quel que soit son « progrès » —
    # c'est la ligne rouge du §5 du brief (« jamais de masquage d'un échec »).
    adopte = ((session.executable or session.progresse)
              and not session.regressions and not session.couverture_perdue
              and a_tente)

    if session.couverture_perdue and a_tente:
        # LE refus qui rend `progresse()` recevable. « Moins d'échecs techniques » s'obtient en
        # supprimant les scénarios qui échouent : le principe 5 ne le voit pas (il ne surveille
        # que les scénarios VERTS). Mesuré avant d'écrire ce code, cf. `couverture_perdue`.
        session.outcome = COVERAGE_LOST
        session.reason = (
            f"la réparation SUPPRIME {session.couverture_perdue} scénario(s) "
            f"({_nb_scenarios(outcome_depart)} → {_nb_scenarios(outcome)}). Moins d'échecs parce "
            f"que moins de tests — c'est un masquage d'échec (§5 du brief). Non adoptée."
        )
        logger.warning("[repair] cas %s : réparation REFUSÉE — %s scénario(s) SUPPRIMÉ(S) "
                       "(%s → %s)", case_id, session.couverture_perdue,
                       _nb_scenarios(outcome_depart), _nb_scenarios(outcome))
    elif session.regressions and (session.executable or session.progresse) and a_tente:
        # Le test tourne, mais il a perdu des scénarios qui passaient : adopter serait troquer une
        # erreur technique visible contre une perte de couverture SILENCIEUSE — le pire échange.
        session.outcome = REGRESSION
        session.reason = (
            "la réparation fait tourner le test mais casse "
            f"{len(session.regressions)} scénario(s) qui passaient : "
            f"{', '.join(session.regressions)}. Non adoptée."
        )
        logger.warning("[repair] cas %s : réparation REFUSÉE — régression sur %s",
                       case_id, session.regressions)
    _sync_disque(versions, adopte, version_id, current_version_id, module_name)

    if adopte:
        # La version réparée devient la référence — mais elle n'est PAS approuvée : personne ne
        # l'a relue, et le gate le verra (il porte sur la VERSION). C'est le prix de l'option C :
        # la réparation est invisible PENDANT la session, jamais après.
        cases.set_current_version(case_id, current_version_id)
        if session.executable:
            logger.info("[repair] cas %s : test rendu exécutable en %s tentative(s) → v%s "
                        "(issue : %s), à ratifier",
                        case_id, session.attempts, current_version_id, session.outcome)
        else:
            # Adoption sur PROGRÈS (0018) : le test ne tourne pas encore entièrement, mais il
            # tourne MIEUX. On garde, sinon le prochain rejeu rachète ce travail.
            logger.info("[repair] cas %s : PROGRÈS partiel gardé → v%s (%s → %s échecs "
                        "techniques) en %s tentative(s), à ratifier — le test ne tourne pas "
                        "encore entièrement (issue : %s)",
                        case_id, current_version_id, _echecs_techniques(outcome_depart),
                        _echecs_techniques(outcome), session.attempts, session.outcome)
    elif a_tente:
        # Le test ne tourne toujours pas : la référence reste la version qu'un HUMAIN a
        # approuvée. Les versions tentées demeurent en historique — la trace de ce qui a été
        # essayé.
        session.final_version_id = version_id
        logger.info("[repair] cas %s non réparé (%s) — v%s reste la référence",
                    case_id, session.outcome, version_id)
    return session


def _sync_disque(versions, adopte: bool, version_id: int,
                 current_version_id: int, module_name: str) -> None:
    """Le DISQUE doit toujours refléter la version qui fait référence.

    ⚠️ Le runner lit les fichiers **sur disque** (`BehaveRunner._assemble` les recopie), pas la
    base. Or `write_steps_file` a écrit la tentative de l'agent sur ce disque. Si la réparation
    n'est PAS adoptée, la base dit « v1 » et le disque contient « v3 » : **le prochain run
    exécuterait v3 en prétendant v1** — un « affiché ≠ réel » (§4.6), et le pire genre : le
    verdict porterait sur un code que personne n'a approuvé.

    On réécrit donc systématiquement la version de référence après la boucle.

    `adopte` (et non plus `session.resolved`) : c'est le critère d'ADOPTION qui dit quelle version
    fait référence — depuis `0016`, « le test tourne », pas « le test passe ».
    """
    if current_version_id == version_id:
        return   # aucune tentative retenue : l'agent n'a rien écrit sur le disque
    reference = current_version_id if adopte else version_id
    version = versions.get(reference)
    if version is None:
        logger.error("[repair] version de référence %s introuvable — disque non resynchronisé",
                     reference)
        return
    try:
        config.GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        (config.GENERATED_DIR / f"{module_name}.feature").write_text(
            version["feature_content"] or "", encoding="utf-8")
        (config.GENERATED_DIR / f"{module_name}_steps.py").write_text(
            version["steps_content"] or "", encoding="utf-8")
        logger.info("[repair] disque resynchronisé sur la version de référence v%s", reference)
    except OSError:
        # Laisser un disque divergent serait pire que bruyant : un run futur mentirait.
        logger.exception("[repair] ÉCHEC de la resynchronisation du disque sur v%s — le prochain "
                         "run pourrait exécuter un code qui n'est pas celui de la version "
                         "courante", reference)


def _record_attempt(conn, outcome, failures, attempt_number: int, what_was_tried: str) -> None:
    """Renseigne `what_was_tried` sur le diagnostic de l'exécution qui a échoué.

    La colonne existait et était **vide partout** : elle est faite pour dire ce que l'agent a
    tenté. « J'ai corrigé » n'apprendrait rien — on stocke ce qu'il DIT avoir changé, tel quel,
    et un humain le lira.
    """
    execution_id = getattr(outcome, "execution_id", None)
    if execution_id is None:
        return
    repairs = RepairRepo(conn)
    existing = repairs.list_for_execution(execution_id)
    if existing:
        conn.execute("UPDATE repair_attempt SET what_was_tried=?, attempt_number=? WHERE id=?",
                     (what_was_tried[:1000], attempt_number, existing[0]["id"]))
        conn.commit()
    elif failures:
        repairs.create(
            execution_id=execution_id, attempt_number=attempt_number,
            failure_signature=failure_signature(failures),
            cause_category="", defect_origin="test_a_reparer",
            confirmation_status="pending_human", what_was_tried=what_was_tried[:1000])
