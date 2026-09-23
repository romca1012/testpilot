import pytest
from testpilot.generation.qualification_report import evaluate_campaign


def campaign():
    corpus = [{'id': i, 'connector': 'odoo' if i < 20 else 'web',
               'split': 'development' if i % 3 else 'holdout',
               'critical': i == 1, 'reference': f'requirement-{i}',
               'expected_verdict': 'conforme'} for i in range(30)]
    trials = [{'case_id': i, 'iteration': j, 'generation_passed': True,
               'technical_passed': True, 'fidelity_passed': True, 'oracle_passed': True,
               'observed_verdict': 'conforme', 'physical_attempts': 1, 'repair_used': False,
               'adaptive_used': False, 'calibration_used': False, 'cost_usd': .1}
              for i in range(30) for j in (1, 2, 3)]
    return corpus, trials


def test_campagne_complete_satisfait_le_contrat():
    corpus, trials = campaign()
    assert evaluate_campaign(corpus, trials)['qualified']


def test_manquant_reste_au_denominateur():
    corpus, trials = campaign()
    result = evaluate_campaign(corpus, trials[:-1])
    assert not result['qualified'] and result['missing_trials'] == 1
    assert result['success_rate'] == 89 / 90


@pytest.mark.parametrize('change', [{'physical_attempts': 2}, {'adaptive_used': True},
                                  {'fidelity_passed': False}, {'generation_passed': False}])
def test_echec_critique_ne_se_dilue_pas_dans_le_total(change):
    corpus, trials = campaign()
    trials[3].update(change)  # cas critique 1
    result = evaluate_campaign(corpus, trials)
    assert result['successful_trials'] == 89 and not result['qualified']


def test_doublon_refuse_et_faux_vert_bloquant():
    corpus, trials = campaign()
    with pytest.raises(ValueError, match='dupliqué'):
        evaluate_campaign(corpus, trials + [trials[0]])
    trials[0]['oracle_passed'] = False
    result = evaluate_campaign(corpus, trials)
    assert result['known_false_greens'] == 1 and not result['qualified']
