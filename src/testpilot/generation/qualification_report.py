"""Critères du plan approuvé : 30 cas, 3 essais, aucun essai manquant exclu."""
from __future__ import annotations

from collections import Counter
import math


def evaluate_campaign(corpus: list[dict], trials: list[dict]) -> dict:
    """Évalue des verdicts référencés indépendamment ; ne fabrique jamais cet oracle.

    `reference` identifie la référence métier indépendante de la sortie générée.
    `oracle_passed` et `fidelity_passed` sont fournis par son évaluateur, pas par le LLM testé.
    Des essais manquants sont des échecs au dénominateur et empêchent la qualification.
    """
    ids = [c['id'] for c in corpus]
    if len(ids) != 30 or len(set(ids)) != 30:
        raise ValueError('Corpus attendu : 30 cas distincts')
    if Counter(c['connector'] for c in corpus) != {'odoo': 20, 'web': 10}:
        raise ValueError('Répartition attendue : 20 Odoo et 10 web')
    if Counter(c['split'] for c in corpus) != {'development': 20, 'holdout': 10}:
        raise ValueError('Répartition attendue : 20 développement et 10 réserve')
    if not any(c.get('critical') is True for c in corpus):
        raise ValueError('Cas critiques non définis')
    if any(not c.get('reference') or c.get('expected_verdict') not in ('conforme', 'non_conforme') for c in corpus):
        raise ValueError('Référence indépendante et verdict attendu obligatoires')
    cases = {c['id']: c for c in corpus}
    indexed = {}
    total_cost = 0.0
    for trial in trials:
        key = (trial['case_id'], trial['iteration'])
        if key[0] not in cases or type(key[1]) is not int or key[1] not in (1, 2, 3) or key in indexed:
            raise ValueError('Essai inconnu, dupliqué ou itération invalide')
        cost = trial.get('cost_usd')
        if type(cost) not in (float, int) or not math.isfinite(cost) or cost < 0:
            raise ValueError('Coût de chaque essai, même échoué, obligatoire')
        total_cost += cost
        indexed[key] = trial

    def passed(case, trial):
        return (trial.get('generation_passed') is True
                and trial.get('technical_passed') is True
                and trial.get('fidelity_passed') is True
                and trial.get('oracle_passed') is True
                and trial.get('observed_verdict') == case['expected_verdict']
                and type(trial.get('physical_attempts')) is int and trial['physical_attempts'] == 1
                and trial.get('repair_used') is False
                and trial.get('adaptive_used') is False
                and trial.get('calibration_used') is False)

    successes = stable = holdout = critical_total = critical_passed = false_greens = 0
    for case in corpus:
        results = []
        for iteration in (1, 2, 3):
            trial = indexed.get((case['id'], iteration), {})
            ok = passed(case, trial)
            results.append(ok)
            successes += ok
            holdout += ok and case['split'] == 'holdout'
            critical_total += case.get('critical') is True
            critical_passed += ok and case.get('critical') is True
            false_greens += (trial.get('observed_verdict') == 'conforme'
                             and (case['expected_verdict'] != 'conforme'
                                  or trial.get('oracle_passed') is False
                                  or trial.get('fidelity_passed') is False))
        stable += all(results)
    complete = len(indexed) == 90
    return {'qualified': complete and successes >= 86 and stable >= 27 and holdout >= 29
            and critical_passed == critical_total and false_greens == 0,
            'complete': complete, 'expected_trials': 90, 'recorded_trials': len(indexed),
            'missing_trials': 90 - len(indexed), 'successful_trials': successes,
            'success_rate': successes / 90, 'stable_cases': stable,
            'holdout_successes': holdout, 'holdout_total': 30,
            'critical_successes': critical_passed, 'critical_total': critical_total,
            'known_false_greens': false_greens, 'recorded_cost_usd': total_cost}
