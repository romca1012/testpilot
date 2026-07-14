"""Suivi des tokens et coûts d'un run + plafond par-run (§6).

Barème estimé (USD / million de tokens) par modèle Anthropic. Le plafond mensuel
cumulé et la réconciliation « coûts réels » sont ajoutés séparément (monthly_budget.py,
cost_source.py) pour garder ce tracker focalisé sur un run.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from testpilot import config

logger = logging.getLogger(__name__)

# USD par million de tokens.
PRICING: dict[str, dict[str, float]] = {
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0, "cache_write": 3.75, "cache_read": 0.30},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.0, "cache_write": 1.0, "cache_read": 0.08},
    "claude-opus-4-8": {"input": 15.0, "output": 75.0, "cache_write": 18.75, "cache_read": 1.50},
}
_PRICING_FALLBACK = "claude-sonnet-4-6"


class CostLimitExceeded(RuntimeError):
    """Levée quand le coût cumulé d'un run dépasse le plafond par-run."""


@dataclass
class CallRecord:
    model: str
    input_tokens: int
    output_tokens: int
    cache_write_tokens: int
    cache_read_tokens: int
    cost_usd: float
    label: str = ""
    at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CostTracker:
    """Accumule le coût estimé des appels d'un run et coupe au plafond par-run."""

    def __init__(self, limit_usd: float | None = None):
        self.limit_usd = config.COST_LIMIT_PER_RUN_USD if limit_usd is None else limit_usd
        self.total_cost: float = 0.0
        self.calls: list[CallRecord] = []

    @staticmethod
    def estimate(model: str, input_tokens: int, output_tokens: int,
                 cache_write_tokens: int = 0, cache_read_tokens: int = 0) -> float:
        pricing = PRICING.get(model, PRICING[_PRICING_FALLBACK])
        return (
            input_tokens * pricing["input"]
            + output_tokens * pricing["output"]
            + cache_write_tokens * pricing["cache_write"]
            + cache_read_tokens * pricing["cache_read"]
        ) / 1_000_000

    def track_call(self, *, model: str, input_tokens: int, output_tokens: int,
                   cache_write_tokens: int = 0, cache_read_tokens: int = 0,
                   label: str = "") -> float:
        """Enregistre un appel, accumule son coût, lève si le plafond par-run est franchi."""
        if model not in PRICING:
            logger.warning("[cost] modèle '%s' absent du barème — tarif Sonnet appliqué", model)
        cost = self.estimate(model, input_tokens, output_tokens, cache_write_tokens, cache_read_tokens)
        self.total_cost += cost
        self.calls.append(CallRecord(
            model=model, input_tokens=input_tokens, output_tokens=output_tokens,
            cache_write_tokens=cache_write_tokens, cache_read_tokens=cache_read_tokens,
            cost_usd=cost, label=label,
        ))
        if self.total_cost > self.limit_usd:
            raise CostLimitExceeded(
                f"Budget par-run dépassé : ${self.total_cost:.3f} > ${self.limit_usd:.2f}."
            )
        return cost

    def summary(self) -> dict:
        by_model: dict[str, dict] = {}
        for c in self.calls:
            entry = by_model.setdefault(c.model, {"calls": 0, "cost_usd": 0.0})
            entry["calls"] += 1
            entry["cost_usd"] = round(entry["cost_usd"] + c.cost_usd, 6)
        return {"total_cost_usd": round(self.total_cost, 6), "calls": len(self.calls), "by_model": by_model}
