"""Repositories — accès au référentiel TestPilot.

Chaque classe encapsule une table (ou un agrégat proche). Entrées/sorties = dict
simples pour garder le socle léger et portable vers PostgreSQL. Les valeurs d'enum
font autorité dans ``verdict/status.py`` ; la base les reflète via des CHECK (schema.sql).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


def now_iso() -> str:
    """Horodatage ISO-8601 UTC (format TEXT portable)."""
    return datetime.now(timezone.utc).isoformat()


def period_of(ts: str | None = None) -> str:
    """Clé de période mensuelle 'YYYY-MM' pour l'agrégation budgétaire."""
    dt = datetime.fromisoformat(ts) if ts else datetime.now(timezone.utc)
    return dt.strftime("%Y-%m")


def _rows(cursor: sqlite3.Cursor) -> list[dict]:
    return [dict(r) for r in cursor.fetchall()]


class CaseRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, *, title: str, module: str, author: str = "", description: str = "",
               origin: str = "ia_generated", connector_type: str = "odoo") -> int:
        ts = now_iso()
        cur = self.conn.execute(
            "INSERT INTO test_case (title, module, connector_type, description, origin,"
            " validation_status, author, created_at, updated_at)"
            " VALUES (?,?,?,?,?, 'never_executed', ?,?,?)",
            (title, module, connector_type, description, origin, author, ts, ts),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def get(self, case_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM test_case WHERE id=?", (case_id,)).fetchone()
        return dict(row) if row else None

    def list_all(self) -> list[dict]:
        return _rows(self.conn.execute("SELECT * FROM test_case ORDER BY id"))

    def set_current_version(self, case_id: int, version_id: int) -> None:
        self.conn.execute(
            "UPDATE test_case SET current_version_id=?, updated_at=? WHERE id=?",
            (version_id, now_iso(), case_id),
        )
        self.conn.commit()

    def set_validation_status(self, case_id: int, status: str) -> None:
        self.conn.execute(
            "UPDATE test_case SET validation_status=?, updated_at=? WHERE id=?",
            (status, now_iso(), case_id),
        )
        self.conn.commit()

    def update_last_outcome(self, case_id: int, *, execution_status: str,
                            functional_status: str, executed_at: str) -> None:
        self.conn.execute(
            "UPDATE test_case SET last_execution_status=?, last_functional_status=?,"
            " last_executed_at=?, updated_at=? WHERE id=?",
            (execution_status, functional_status, executed_at, now_iso(), case_id),
        )
        self.conn.commit()


class VersionRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, *, test_case_id: int, spec_content: str, spec_hash: str,
               feature_content: str, steps_content: str, feature_path: str = "",
               steps_path: str = "", change_summary: str = "", created_by: str = "") -> int:
        number = self.conn.execute(
            "SELECT COALESCE(MAX(version_number), 0) + 1 AS n"
            " FROM test_case_version WHERE test_case_id=?",
            (test_case_id,),
        ).fetchone()["n"]
        cur = self.conn.execute(
            "INSERT INTO test_case_version (test_case_id, version_number, spec_content,"
            " spec_hash, feature_content, steps_content, feature_path, steps_path,"
            " change_summary, created_at, created_by) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (test_case_id, number, spec_content, spec_hash, feature_content, steps_content,
             feature_path, steps_path, change_summary, now_iso(), created_by),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def get(self, version_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM test_case_version WHERE id=?", (version_id,)).fetchone()
        return dict(row) if row else None

    def latest_for_case(self, test_case_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM test_case_version WHERE test_case_id=?"
            " ORDER BY version_number DESC LIMIT 1",
            (test_case_id,),
        ).fetchone()
        return dict(row) if row else None

    def list_for_case(self, test_case_id: int) -> list[dict]:
        return _rows(self.conn.execute(
            "SELECT * FROM test_case_version WHERE test_case_id=? ORDER BY version_number",
            (test_case_id,)))


class ReviewRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, *, test_case_id: int, version_id: int, decision: str,
               reviewer: str = "", comment: str = "") -> int:
        cur = self.conn.execute(
            "INSERT INTO review_decision (test_case_id, version_id, decision, reviewer,"
            " comment, decided_at) VALUES (?,?,?,?,?,?)",
            (test_case_id, version_id, decision, reviewer, comment, now_iso()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def latest_for_version(self, version_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM review_decision WHERE version_id=? ORDER BY id DESC LIMIT 1",
            (version_id,)).fetchone()
        return dict(row) if row else None

    def is_version_approved(self, version_id: int) -> bool:
        latest = self.latest_for_version(version_id)
        return bool(latest and latest["decision"] == "approved")

    def list_for_case(self, test_case_id: int) -> list[dict]:
        """Historique des décisions de relecture d'un cas (toutes versions), anté-chronologique."""
        return _rows(self.conn.execute(
            "SELECT * FROM review_decision WHERE test_case_id=? ORDER BY id DESC",
            (test_case_id,)))


class ExecutionRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, *, test_case_id: int, version_id: int, trigger: str = "first_run") -> int:
        cur = self.conn.execute(
            "INSERT INTO execution (test_case_id, version_id, trigger, started_at)"
            " VALUES (?,?,?,?)",
            (test_case_id, version_id, trigger, now_iso()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def finalize(self, execution_id: int, *, execution_status: str, functional_status: str,
                 scenarios_total: int, scenarios_passed: int, scenarios_failed: int,
                 cost_usd: float, iterations: int, duration_seconds: float,
                 report_json_path: str = "", report_html_path: str = "") -> None:
        self.conn.execute(
            "UPDATE execution SET execution_status=?, functional_status=?, scenarios_total=?,"
            " scenarios_passed=?, scenarios_failed=?, cost_usd=?, iterations=?,"
            " duration_seconds=?, report_json_path=?, report_html_path=? WHERE id=?",
            (execution_status, functional_status, scenarios_total, scenarios_passed,
             scenarios_failed, cost_usd, iterations, duration_seconds, report_json_path,
             report_html_path, execution_id),
        )
        self.conn.commit()

    def get(self, execution_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM execution WHERE id=?", (execution_id,)).fetchone()
        return dict(row) if row else None

    def list_for_case(self, test_case_id: int) -> list[dict]:
        return _rows(self.conn.execute(
            "SELECT * FROM execution WHERE test_case_id=? ORDER BY id", (test_case_id,)))

    def list_recent(self, limit: int = 50) -> list[dict]:
        """Exécutions récentes tous cas confondus (onglet Exécution), plus récentes d'abord."""
        return _rows(self.conn.execute(
            "SELECT * FROM execution ORDER BY id DESC LIMIT ?", (max(1, limit),)))

    def add_scenario_result(self, *, execution_id: int, scenario_name: str,
                            execution_status: str, functional_status: str,
                            failure_type: str = "", cause_category: str = "",
                            error_summary: str = "") -> int:
        cur = self.conn.execute(
            "INSERT INTO scenario_result (execution_id, scenario_name, execution_status,"
            " functional_status, failure_type, cause_category, error_summary)"
            " VALUES (?,?,?,?,?,?,?)",
            (execution_id, scenario_name, execution_status, functional_status,
             failure_type, cause_category, error_summary),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def list_scenario_results(self, execution_id: int) -> list[dict]:
        return _rows(self.conn.execute(
            "SELECT * FROM scenario_result WHERE execution_id=? ORDER BY id", (execution_id,)))


class RepairRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, *, execution_id: int, attempt_number: int, failure_signature: str,
               cause_category: str, defect_origin: str, confirmation_status: str,
               what_was_tried: str = "") -> int:
        cur = self.conn.execute(
            "INSERT INTO repair_attempt (execution_id, attempt_number, failure_signature,"
            " cause_category, defect_origin, confirmation_status, what_was_tried, created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (execution_id, attempt_number, failure_signature, cause_category, defect_origin,
             confirmation_status, what_was_tried, now_iso()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def confirm(self, attempt_id: int, *, confirmation_status: str, confirmed_by: str) -> None:
        self.conn.execute(
            "UPDATE repair_attempt SET confirmation_status=?, confirmed_by=?, confirmed_at=?"
            " WHERE id=?",
            (confirmation_status, confirmed_by, now_iso(), attempt_id),
        )
        self.conn.commit()

    def list_for_execution(self, execution_id: int) -> list[dict]:
        return _rows(self.conn.execute(
            "SELECT * FROM repair_attempt WHERE execution_id=? ORDER BY attempt_number",
            (execution_id,)))

    def list_pending(self) -> list[dict]:
        return _rows(self.conn.execute(
            "SELECT * FROM repair_attempt WHERE confirmation_status='pending_human' ORDER BY id"))


class CostRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def add_entry(self, *, phase: str, model: str, cost_usd: float, source: str,
                  execution_id: int | None = None, at: str | None = None) -> int:
        ts = at or now_iso()
        cur = self.conn.execute(
            "INSERT INTO cost_ledger (period_month, execution_id, phase, model, cost_usd,"
            " source, created_at) VALUES (?,?,?,?,?,?,?)",
            (period_of(ts), execution_id, phase, model, cost_usd, source, ts),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def monthly_total_usd(self, month: str | None = None) -> float:
        target = month or period_of()
        row = self.conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) AS total FROM cost_ledger WHERE period_month=?",
            (target,)).fetchone()
        return float(row["total"])
