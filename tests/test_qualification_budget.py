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
