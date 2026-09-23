"""Réservation durable AVANT chaque appel Sonnet 4.6 d'une qualification.

Enveloppe interne 50 USD ; aucune conversion présentée comme une facture en euros.
Une erreur fournisseur de coût inconnu conserve la réservation entière.
Barème vérifié le 2026-09-23 : entrée cache 1 h 6 USD/M, sortie 15 USD/M.
Réservation conservatrice : tout le contexte maximal 1 M au tarif cache le plus élevé.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from testpilot.guardrails.cost_tracker import CostLimitExceeded
from testpilot.llm.adapter import LLMAdapter


class QualificationBudget:
    LIMIT_USD = 50.0
    RESERVATION_USD = 6.12  # 1M entrée + 8000 sortie, aucun retry fournisseur

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, timeout=30)
        self.conn.execute('CREATE TABLE IF NOT EXISTS calls ('
                          'id INTEGER PRIMARY KEY, trial TEXT NOT NULL, '
                          'charged REAL NOT NULL, reconciled INTEGER NOT NULL DEFAULT 0)')
        self.conn.commit()

    def reserve(self, trial: str) -> int:
        self.conn.execute('BEGIN IMMEDIATE')
        try:
            total = self.conn.execute('SELECT COALESCE(SUM(charged),0) FROM calls').fetchone()[0]
            if total + self.RESERVATION_USD > self.LIMIT_USD:
                raise CostLimitExceeded('Enveloppe de qualification insuffisante avant appel')
            row = self.conn.execute('INSERT INTO calls(trial,charged) VALUES (?,?)',
                                    (trial, self.RESERVATION_USD))
            self.conn.commit()
            return row.lastrowid
        except BaseException:
            self.conn.rollback()
            raise

    def reconcile(self, call_id: int, actual: float):
        if not 0 <= actual <= self.RESERVATION_USD:
            raise CostLimitExceeded('Coût inattendu : qualification arrêtée, réservation conservée')
        self.conn.execute('UPDATE calls SET charged=?, reconciled=1 WHERE id=? AND reconciled=0',
                          (actual, call_id))
        self.conn.commit()

    def summary(self):
        total, uncertain = self.conn.execute(
            'SELECT COALESCE(SUM(charged),0), COALESCE(SUM(1-reconciled),0) FROM calls').fetchone()
        return {'charged_or_reserved_usd': total, 'uncertain_calls': uncertain,
                'limit_usd': self.LIMIT_USD}


class QualificationLLM(LLMAdapter):
    def __init__(self, budget: QualificationBudget, trial: str, *, secrets=()):
        super().__init__()
        self.budget, self.trial = budget, trial
        self.secrets = tuple(s for s in secrets if s)

    def _redact(self, value):
        if hasattr(value, 'model_dump'):
            value = value.model_dump(exclude_none=True)
        if isinstance(value, str):
            for secret in self.secrets:
                value = value.replace(secret, '[secret]')
        elif isinstance(value, list):
            value = [self._redact(item) for item in value]
        elif isinstance(value, dict):
            value = {key: self._redact(item) for key, item in value.items()}
        return value

    def call_with_tools(self, **kwargs):
        from testpilot import config
        model = kwargs.get('model') or config.MODEL_GENERATION
        if model != 'claude-sonnet-4-6' or kwargs.get('max_tokens', 8000) > 8000:
            raise ValueError('Configuration non couverte par la réservation de qualification')
        tracker = kwargs.get('cost_tracker')
        if tracker is None:
            raise ValueError('Suivi de coût obligatoire')
        for key in ('system_prompt', 'messages', 'tools'):
            if key in kwargs:
                kwargs[key] = self._redact(kwargs[key])
        # Le SDK réessaie autrement les erreurs réseau sans réservation supplémentaire.
        self._client = self._client_().with_options(max_retries=0)
        before = len(tracker.calls)
        call_id = self.budget.reserve(self.trial)
        try:
            return super().call_with_tools(**kwargs)
        finally:
            if len(tracker.calls) > before:
                self.budget.reconcile(call_id, sum(c.cost_usd for c in tracker.calls[before:]))
