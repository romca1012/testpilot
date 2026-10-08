import pytest
from testpilot.generation.qualification_budget import QualificationBudget
from testpilot.guardrails.cost_tracker import CostLimitExceeded


def test_identifiants_connus_ne_partent_pas_dans_les_prompts(tmp_path):
    from testpilot.generation.qualification_budget import QualificationLLM
    budget = QualificationBudget(tmp_path / 'budget.db')
    llm = QualificationLLM(budget, 'test', secrets=('mot-secret', 'api-secret'))
    payload = [{'role': 'user', 'content': [{'type': 'text', 'text': 'mot-secret api-secret'}]}]
    assert llm._redact(payload)[0]['content'][0]['text'] == '[secret] [secret]'
    assert payload[0]['content'][0]['text'] == 'mot-secret api-secret'
    budget.conn.close()


def test_reservation_survit_au_crash_et_borne_les_appels(tmp_path):
    path = tmp_path / 'budget.db'
    budget = QualificationBudget(path)
    first = budget.reserve('one')
    budget.conn.close()
    restarted = QualificationBudget(path)
    assert restarted.summary()['uncertain_calls'] == 1
    restarted.reconcile(first, .12)
    for _ in range(8):
        restarted.reserve('unknown')
    with pytest.raises(CostLimitExceeded):
        restarted.reserve('too-much')
    assert restarted.summary()['charged_or_reserved_usd'] < restarted.LIMIT_USD
    restarted.conn.close()


def test_la_reparation_haiku_est_couverte_un_modele_plus_cher_reste_refuse(tmp_path):
    """Falsifiable : la réservation est calculée au tarif de Sonnet 4.6 -- Haiku (moins cher) passe, Opus (plus cher) non."""
    from testpilot.generation.qualification_budget import QualificationLLM
    budget = QualificationBudget(tmp_path / 'budget.db')
    llm = QualificationLLM(budget, 'test')
    for modele in ('claude-haiku-4-5', 'claude-sonnet-4-6'):
        with pytest.raises(ValueError, match='Suivi de coût obligatoire'):  # a franchi le premier garde
            llm.call_with_tools(model=modele)
    for modele in ('claude-opus-4-8', 'modele-inconnu'):
        with pytest.raises(ValueError, match='non couverte'):
            llm.call_with_tools(model=modele, cost_tracker=object())
    with pytest.raises(ValueError, match='non couverte'):
        llm.call_with_tools(model='claude-haiku-4-5', max_tokens=9000, cost_tracker=object())
    budget.conn.close()


def test_le_tarif_de_haiku_sans_date_n_est_plus_celui_de_sonnet():
    from testpilot.guardrails.cost_tracker import CostTracker
    assert CostTracker.estimate('claude-haiku-4-5', 1_000_000, 0) == 0.80
    assert CostTracker.estimate('claude-haiku-4-5', 1_000_000, 0) == CostTracker.estimate('claude-haiku-4-5-20251001', 1_000_000, 0)

