"""Mesure en lecture seule la qualité du premier passage d'une base SQLite locale.

Usage : python scripts/audit_generation_quality.py --db data/testpilot.db
Ne charge pas la configuration, ne migre pas la base et ne contacte aucun service.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from contextlib import closing
from pathlib import Path


def audit(db_path: Path) -> dict:
    with closing(sqlite3.connect(db_path.resolve().as_uri() + '?mode=ro', uri=True)) as conn:
        rows = conn.execute(
            "SELECT execution_status, functional_status, substr(started_at, 1, 10) "
            "FROM execution WHERE trigger = 'first_run' "
            "AND NOT (execution_status = 'not_executed' AND duration_seconds = 0 "
            "AND scenarios_total = 0 AND error_message = '')"
        ).fetchall()
        has_attempts = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                                    "AND name='execution_attempt'").fetchone()
        physical = conn.execute(
            "SELECT a.execution_status, a.functional_status, a.finished_at FROM execution e "
            "LEFT JOIN execution_attempt a ON a.execution_id=e.id AND a.attempt_number=1 "
            "WHERE e.trigger='first_run'").fetchall() if has_attempts else []
        total_first_runs = conn.execute(
            "SELECT COUNT(*) FROM execution WHERE trigger='first_run'").fetchone()[0]
    measured = [r for r in physical if r[2]]
    first_success = sum(r[0] == 'success' for r in measured)
    statuses = Counter(row[0] for row in rows)
    functional = Counter(row[1] for row in rows if row[0] == 'success')
    attempted = statuses['success'] + statuses['technical_error']
    usable = functional['conforme'] + functional['non_conforme']
    by_day = {}
    for execution, _, day in rows:
        by_day.setdefault(day, Counter())[execution] += 1
    return {
        'scope': 'historical final outcomes of first_run executions; internal retries may be included',
        'first_attempt': {
            'measured': len(measured),
            'unmeasured': (sum(r[2] is None for r in physical) if has_attempts else total_first_runs),
            'pending': sum(r[2] == '' for r in physical),
            'technical_success': first_success,
            'technical_success_rate': first_success / len(measured) if measured else None,
        },
        'total': len(rows),
        'technical_success': statuses['success'],
        'technical_error': statuses['technical_error'],
        'not_executed': statuses['not_executed'],
        'technical_success_rate': statuses['success'] / attempted if attempted else None,
        'functional_outcomes_of_technical_success': dict(functional),
        'usable_functional_verdicts': usable,
        'usable_functional_verdict_rate': usable / attempted if attempted else None,
        'by_day': dict(sorted(by_day.items())),
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.db), ensure_ascii=False, indent=2))
