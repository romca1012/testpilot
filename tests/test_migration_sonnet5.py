"""Vague 2 — B1 : readiness de la migration Sonnet 5 (GATED sur le coût).

On rend le code Sonnet-5-prêt SANS casser le défaut (Sonnet 4.6) ni Haiku. Ces gardes fixent la
règle model-aware : Sonnet 5 rejette `temperature` (400) et veut la pensée adaptative + `effort` ;
Haiku 4.5 et Sonnet 4.6 gardent `temperature`. Le flip du modèle par défaut reste la décision du
porteur, hors de ce lot.
"""

from __future__ import annotations

from testpilot.llm.adapter import _params_echantillonnage
from testpilot.guardrails.cost_tracker import PRICING


# ── Le helper model-aware ─────────────────────────────────────────────────────

def test_sonnet5_pas_de_temperature_mais_thinking_et_effort():
    """⚠️ Le cœur de la migration : Sonnet 5 REJETTE `temperature` (400). On envoie la pensée
    adaptative + `effort` à la place."""
    p = _params_echantillonnage("claude-sonnet-5", temperature=0.2)
    assert "temperature" not in p, "temperature -> 400 sur Sonnet 5"
    assert p["thinking"] == {"type": "adaptive"}
    assert p["output_config"]["effort"] == "high"


def test_opus_4_8_est_aussi_adaptatif():
    p = _params_echantillonnage("claude-opus-4-8", temperature=0.1)
    assert "temperature" not in p and "thinking" in p


def test_haiku_garde_temperature():
    """Haiku 4.5 (analyse/réparation) accepte `temperature` — on ne le prive pas."""
    p = _params_echantillonnage("claude-haiku-4-5-20251001", temperature=0.1)
    assert p == {"temperature": 0.1}


def test_sonnet_4_6_garde_temperature_zero_regression():
    """GARDE NÉGATIVE : le défaut ACTUEL reste dans la branche `temperature`, à l'identique.
    Aucune régression tant que le porteur n'a pas basculé sur Sonnet 5."""
    p = _params_echantillonnage("claude-sonnet-4-6", temperature=0.2)
    assert p == {"temperature": 0.2}
    assert "thinking" not in p


def test_modele_inconnu_retombe_sur_temperature():
    """Prudence : un modèle non listé garde `temperature` (comportement historique)."""
    assert _params_echantillonnage("un-modele-quelconque", temperature=0.15) == {"temperature": 0.15}


# ── Le barème ─────────────────────────────────────────────────────────────────

def test_sonnet5_est_au_bareme():
    assert "claude-sonnet-5" in PRICING
    assert PRICING["claude-sonnet-5"]["input"] == 3.0
    assert PRICING["claude-sonnet-5"]["output"] == 15.0


def test_opus_4_8_corrige_a_5_25():
    """Erreur pré-existante corrigée : Opus 4.8 = 5/25 (pas 15/75, l'ancien tarif 4.0/4.1)."""
    assert PRICING["claude-opus-4-8"]["input"] == 5.0
    assert PRICING["claude-opus-4-8"]["output"] == 25.0
