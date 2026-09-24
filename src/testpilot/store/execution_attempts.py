"""Journal durable des tentatives physiques, distinct du verdict final d'exécution."""
from __future__ import annotations

from dataclasses import asdict
import json

from testpilot.execution.executor import ExecutionOutcome
from testpilot.store.repositories import now_iso
from testpilot.verdict.status import derive_verdict


class ExecutionAttemptRepo:
    def __init__(self, conn):
        self.conn = conn

    def start(self, execution_id: int, number: int, *, reason: str,
              artifacts_path: str = '', provenance: dict | None = None) -> int:
        cur = self.conn.execute(
            'INSERT INTO execution_attempt (execution_id, attempt_number, reason, '
            'started_at, artifacts_path, provenance) VALUES (?,?,?,?,?,?)',
            (execution_id, number, reason, now_iso(), artifacts_path,
             json.dumps(provenance or {}, ensure_ascii=False)))
        self.conn.commit()
        return int(cur.lastrowid)

    def finish(self, attempt_id: int, result, duration: float,
               *, connector_type: str | None = None) -> None:
        verdict = derive_verdict(ExecutionOutcome('attempt', True, real_run=result),
                                 connector_type=connector_type)
        self.conn.execute(
            'UPDATE execution_attempt SET finished_at=?, execution_status=?, '
            'functional_status=?, duration_seconds=?, result_json=? WHERE id=? '
            "AND finished_at=''",
            (now_iso(), verdict.execution_status, verdict.functional_status, duration,
             json.dumps(asdict(result), ensure_ascii=False), attempt_id))
        self.conn.commit()

    def list_for_execution(self, execution_id: int) -> list[dict]:
        return [dict(row) for row in self.conn.execute(
            'SELECT * FROM execution_attempt WHERE execution_id=? ORDER BY attempt_number',
            (execution_id,)).fetchall()]


def summarize_first_attempts(conn, *, project_id=None, allowed_project_ids=None) -> dict:
    if project_id is not None and allowed_project_ids is not None:
        raise ValueError('project_id et allowed_project_ids sont mutuellement exclusifs')
    where = " WHERE e.trigger='first_run'"
    params = []
    if project_id is not None:
        where += ' AND m.project_id=?'
        params.append(project_id)
    elif allowed_project_ids is not None:
        ids = list(dict.fromkeys(allowed_project_ids))
        where += ' AND m.project_id IN (' + ','.join('?' for _ in ids) + ')' if ids else ' AND 0=1'
        params.extend(ids)
    rows = conn.execute(
        'SELECT e.id, a.execution_status, a.functional_status, a.finished_at, '
        "CASE WHEN EXISTS (SELECT 1 FROM execution_attempt r WHERE r.execution_id=e.id "
        "AND r.attempt_number>1) THEN 1 ELSE 0 END AS retried "
        'FROM execution e JOIN test_case c ON c.id=e.test_case_id '
        'JOIN module m ON m.id=c.module_id LEFT JOIN execution_attempt a '
        'ON a.execution_id=e.id AND a.attempt_number=1' + where, tuple(params)).fetchall()
    measured = [r for r in rows if r['finished_at']]
    ran = sum(r['execution_status'] == 'success' for r in measured)
    useful = sum(r['execution_status'] == 'success' and
                 r['functional_status'] in ('conforme', 'non_conforme') for r in measured)
    return {'measured': len(measured), 'ran': ran, 'usable_verdicts': useful,
            'technical_error': sum(r['execution_status'] == 'technical_error' for r in measured),
            'blocked': sum(r['execution_status'] == 'blocked' for r in measured),
            'retried': sum(r['retried'] for r in rows),
            'unmeasured': sum(r['finished_at'] is None for r in rows),
            'pending': sum(r['finished_at'] == '' for r in rows),
            'ran_rate': ran / len(measured) if measured else None,
            'usable_verdict_rate': useful / len(measured) if measured else None}
