"""§6 — provenance du coût : la traçabilité du ledger ne doit jamais mentir.

Le point critique : ``AnthropicApiCost`` sollicitée SANS chiffre réel (stub / pas de clé
admin) retombe sur l'estimation ET écrit ``source='estimated'`` — surtout PAS
``'anthropic_api'``. Le label ne passe à ``'anthropic_api'`` que si un chiffre réel a
effectivement été renvoyé. C'est la source EFFECTIVE, pas la classe sollicitée, qui fait foi.
"""

from testpilot.guardrails import cost_source as cs
from testpilot.guardrails.cost_tracker import CostTracker


_CALL = dict(model="claude-sonnet-4-6", input_tokens=1000, output_tokens=500)


def test_estimated_source_renvoie_montant_et_label_estimated():
    res = cs.EstimatedCost().cost_for_call(**_CALL)
    assert res.source == cs.SOURCE_ESTIMATED
    assert res.cost_usd == CostTracker.estimate(**_CALL)
    assert res.cost_usd > 0


def test_anthropic_stub_sans_cle_admin_retombe_sur_estimated():
    # Pas de clé admin → aucun chiffre réel → repli honnête, label 'estimated'.
    src = cs.AnthropicApiCost(admin_key="")
    res = src.cost_for_call(**_CALL)
    assert res.source == cs.SOURCE_ESTIMATED
    assert res.cost_usd == CostTracker.estimate(**_CALL)


def test_anthropic_avec_cle_mais_stub_sans_chiffre_reel_reste_estimated():
    # Clé présente mais l'Admin API (stub) ne renvoie aucun chiffre → toujours 'estimated'.
    src = cs.AnthropicApiCost(admin_key="sk-admin-xxx")
    res = src.cost_for_call(**_CALL)
    assert res.source == cs.SOURCE_ESTIMATED


def test_label_anthropic_api_seulement_si_chiffre_reel_mesure():
    # Simule Inc. 1 : l'Admin API renvoie un vrai chiffre → là, et seulement là, 'anthropic_api'.
    src = cs.AnthropicApiCost(admin_key="sk-admin-xxx")
    src._fetch_real_cost = lambda **_: 0.123456
    res = src.cost_for_call(**_CALL)
    assert res.source == cs.SOURCE_ANTHROPIC_API
    assert res.cost_usd == 0.123456


def test_get_cost_source_selon_config():
    assert isinstance(cs.get_cost_source("estimated"), cs.EstimatedCost)
    assert isinstance(cs.get_cost_source("anthropic_api"), cs.AnthropicApiCost)
    # Valeur inconnue → repli sûr sur l'estimation.
    assert isinstance(cs.get_cost_source("n_importe_quoi"), cs.EstimatedCost)


def test_classe_label_declare_vs_source_effective_sont_distincts():
    # La classe annonce sa vocation (label), mais le résultat porte la source réellement écrite.
    src = cs.AnthropicApiCost(admin_key="")
    assert src.label == cs.SOURCE_ANTHROPIC_API          # vocation de la classe
    assert src.cost_for_call(**_CALL).source == cs.SOURCE_ESTIMATED  # ce qui va au ledger
