"""Provenance du coût écrit dans ``cost_ledger.source`` (§6).

Le ledger distingue ce qui est MESURÉ de ce qui est ESTIMÉ — cette distinction ne doit
jamais mentir. Règle de traçabilité (validée) :

- ``EstimatedCost`` : coût = tokens × barème. Source = ``'estimated'``.
- ``AnthropicApiCost`` : tente le coût RÉEL via l'Admin API. Le label ``'anthropic_api'``
  n'est écrit QUE si un chiffre réel a effectivement été renvoyé. Sans clé admin (stub
  Inc. 0) ou en cas d'échec, on retombe sur l'estimation ET on marque ``'estimated'`` —
  jamais ``'anthropic_api'`` — pour ne pas faire passer une estimation pour une mesure.

Chaque appel renvoie donc le COUPLE (coût, source effective), pas un simple montant :
c'est la source effective, pas la classe sollicitée, qui fait foi dans le ledger.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from testpilot import config
from testpilot.guardrails.cost_tracker import CostTracker

logger = logging.getLogger(__name__)

SOURCE_ESTIMATED = "estimated"
SOURCE_ANTHROPIC_API = "anthropic_api"


@dataclass(frozen=True)
class CostResult:
    """Coût d'un appel + provenance EFFECTIVE (celle à écrire dans le ledger)."""
    cost_usd: float
    source: str


class EstimatedCost:
    """Coût estimé par le barème local (actif en Inc. 0)."""

    label = SOURCE_ESTIMATED

    def cost_for_call(self, *, model: str, input_tokens: int, output_tokens: int,
                      cache_write_tokens: int = 0, cache_read_tokens: int = 0) -> CostResult:
        cost = CostTracker.estimate(model, input_tokens, output_tokens,
                                    cache_write_tokens, cache_read_tokens)
        return CostResult(cost_usd=cost, source=SOURCE_ESTIMATED)


class AnthropicApiCost:
    """Coût réel via l'Admin API — stubé en Inc. 0, repli honnête sur l'estimation.

    N'exige PAS de clé admin pour être instanciée : sans clé (ou si l'appel réel échoue),
    ``cost_for_call`` délègue à l'estimation et renvoie ``source='estimated'``. Le passage
    à ``'anthropic_api'`` est réservé à un chiffre réellement mesuré (Inc. 1).
    """

    label = SOURCE_ANTHROPIC_API

    def __init__(self, admin_key: str | None = None):
        self.admin_key = config.ANTHROPIC_ADMIN_KEY if admin_key is None else admin_key
        self._estimator = EstimatedCost()

    def _fetch_real_cost(self, **_kwargs) -> float | None:
        """Point d'extension Inc. 1 : interroge l'Admin API. Stub → None (pas de mesure)."""
        return None

    def cost_for_call(self, *, model: str, input_tokens: int, output_tokens: int,
                      cache_write_tokens: int = 0, cache_read_tokens: int = 0) -> CostResult:
        if self.admin_key:
            real = self._fetch_real_cost(
                model=model, input_tokens=input_tokens, output_tokens=output_tokens,
                cache_write_tokens=cache_write_tokens, cache_read_tokens=cache_read_tokens)
            if real is not None:
                return CostResult(cost_usd=real, source=SOURCE_ANTHROPIC_API)
            logger.warning("[cost] Admin API sans chiffre réel — repli sur l'estimation (source=estimated)")
        else:
            logger.debug("[cost] pas de clé admin — coût estimé, source=estimated")
        # Repli : montant estimé, MAIS traçabilité honnête → 'estimated'.
        return self._estimator.cost_for_call(
            model=model, input_tokens=input_tokens, output_tokens=output_tokens,
            cache_write_tokens=cache_write_tokens, cache_read_tokens=cache_read_tokens)


def get_cost_source(source: str | None = None):
    """Sélectionne la source de coût selon la config (``COST_SOURCE``)."""
    choice = (source or config.COST_SOURCE or SOURCE_ESTIMATED).lower()
    if choice == SOURCE_ANTHROPIC_API:
        return AnthropicApiCost()
    return EstimatedCost()
