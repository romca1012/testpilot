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


class ProjectRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, *, name: str, description: str = "", connector_type: str = "odoo",
               base_url: str = "", database: str = "", username: str = "",
               password: str = "") -> int:
        cur = self.conn.execute(
            "INSERT INTO project (name, description, connector_type, base_url, database,"
            " username, password, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (name, description, connector_type, base_url, database, username, password, now_iso()))
        self.conn.commit()
        return int(cur.lastrowid)

    def get(self, project_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM project WHERE id=?", (project_id,)).fetchone()
        return dict(row) if row else None

    def list_all(self) -> list[dict]:
        """Projets + compteurs de modules et de cas (pour l'accueil / le sélecteur)."""
        return _rows(self.conn.execute(
            "SELECT p.*,"
            " (SELECT COUNT(*) FROM module m WHERE m.project_id=p.id) AS module_count,"
            " (SELECT COUNT(*) FROM test_case tc JOIN module m ON tc.module_id=m.id"
            "  WHERE m.project_id=p.id) AS case_count"
            " FROM project p ORDER BY p.id"))

    def find_by_name(self, name: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM project WHERE name=?", (name,)).fetchone()
        return dict(row) if row else None

    def first(self) -> dict | None:
        """Projet par défaut (le plus ancien). Source unique de la règle « projet courant »
        hors interface : rattachement automatique ET connexion du runtime en CLI."""
        row = self.conn.execute("SELECT * FROM project ORDER BY id LIMIT 1").fetchone()
        return dict(row) if row else None

    def rename(self, project_id: int, *, name: str, description: str | None = None) -> None:
        if description is None:
            self.conn.execute("UPDATE project SET name=? WHERE id=?", (name, project_id))
        else:
            self.conn.execute("UPDATE project SET name=?, description=? WHERE id=?",
                              (name, description, project_id))
        self.conn.commit()

    def delete(self, project_id: int) -> None:
        """Supprime un projet ET toute sa descendance (modules, cas, versions, relectures,
        exécutions, résultats, réparations, coûts) — dans l'ordre des FK, en une transaction."""
        mod_sub = "SELECT id FROM module WHERE project_id=?"
        case_sub = f"SELECT id FROM test_case WHERE module_id IN ({mod_sub})"
        exec_sub = f"SELECT id FROM execution WHERE test_case_id IN ({case_sub})"
        cur = self.conn
        try:
            cur.execute(f"DELETE FROM scenario_result WHERE execution_id IN ({exec_sub})", (project_id,))
            cur.execute(f"DELETE FROM repair_attempt  WHERE execution_id IN ({exec_sub})", (project_id,))
            cur.execute(f"DELETE FROM cost_ledger      WHERE execution_id IN ({exec_sub})", (project_id,))
            cur.execute(f"DELETE FROM execution        WHERE test_case_id IN ({case_sub})", (project_id,))
            cur.execute(f"DELETE FROM review_decision  WHERE test_case_id IN ({case_sub})", (project_id,))
            cur.execute(f"DELETE FROM test_case_version WHERE test_case_id IN ({case_sub})", (project_id,))
            cur.execute(f"DELETE FROM test_case        WHERE module_id IN ({mod_sub})", (project_id,))
            cur.execute("DELETE FROM module  WHERE project_id=?", (project_id,))
            cur.execute("DELETE FROM project WHERE id=?", (project_id,))
            cur.commit()
        except Exception:
            cur.rollback()
            raise


class ModuleRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, *, project_id: int, name: str, description: str = "") -> int:
        cur = self.conn.execute(
            "INSERT INTO module (project_id, name, description, created_at) VALUES (?,?,?,?)",
            (project_id, name, description, now_iso()))
        self.conn.commit()
        return int(cur.lastrowid)

    def get(self, module_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT m.*, p.name AS project_name FROM module m JOIN project p ON m.project_id=p.id"
            " WHERE m.id=?", (module_id,)).fetchone()
        return dict(row) if row else None

    def list_for_project(self, project_id: int) -> list[dict]:
        return _rows(self.conn.execute(
            "SELECT m.*,"
            " (SELECT COUNT(*) FROM test_case tc WHERE tc.module_id=m.id) AS case_count"
            " FROM module m WHERE m.project_id=? ORDER BY m.id", (project_id,)))

    def find_by_name(self, project_id: int, name: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM module WHERE project_id=? AND name=?", (project_id, name)).fetchone()
        return dict(row) if row else None


def ensure_default_module(conn: sqlite3.Connection, feature_slug: str) -> int:
    """Trouve-ou-crée le module métier par défaut pour un slug technique.

    Rattache au PREMIER projet existant (le connecteur vit sur le projet — décision 0005) ;
    si aucun projet n'existe, en crée un depuis la config (connexion env). Module nommé d'après
    le slug (``demande_materiel`` → ``Demande materiel``). Sert à la génération/CLI sans
    imposer de saisie projet/module. Ne recrée jamais un projet nommé « Odoo » (un connecteur).
    """
    from testpilot import config as _cfg

    modules = ModuleRepo(conn)
    existing = ProjectRepo(conn).first()
    project_id = existing["id"] if existing else ProjectRepo(conn).create(
        name="Portail Sapian", connector_type="odoo", base_url=_cfg.ODOO_URL,
        database=_cfg.ODOO_DB, username=_cfg.ODOO_USER, password=_cfg.ODOO_PASSWORD)
    name = _prettify_slug(feature_slug)
    module = modules.find_by_name(project_id, name)
    return module["id"] if module else modules.create(project_id=project_id, name=name)


def _prettify_slug(slug: str) -> str:
    s = (slug or "").replace("_", " ").replace("-", " ").strip()
    return s[:1].upper() + s[1:] if s else "Sans module"


# Colonnes cas + jointure métier (module/projet) réutilisées par get/list.
_CASE_SELECT = (
    "SELECT tc.*, m.name AS module_name, m.project_id AS project_id, p.name AS project_name"
    " FROM test_case tc"
    " LEFT JOIN module m ON tc.module_id = m.id"
    " LEFT JOIN project p ON m.project_id = p.id"
)


class CaseRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, *, title: str, module_id: int | None = None, feature_slug: str = "",
               author: str = "", description: str = "", origin: str = "ia_generated",
               priority: str = "medium") -> int:
        ts = now_iso()
        cur = self.conn.execute(
            "INSERT INTO test_case (title, module_id, feature_slug, description,"
            " origin, validation_status, priority, author, created_at, updated_at)"
            " VALUES (?,?,?,?,?, 'never_executed', ?,?,?,?)",
            (title, module_id, feature_slug, description, origin, priority, author, ts, ts),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def set_priority(self, case_id: int, priority: str) -> None:
        self.conn.execute("UPDATE test_case SET priority=?, updated_at=? WHERE id=?",
                          (priority, now_iso(), case_id))
        self.conn.commit()

    def get(self, case_id: int) -> dict | None:
        row = self.conn.execute(_CASE_SELECT + " WHERE tc.id=?", (case_id,)).fetchone()
        return dict(row) if row else None

    def list_all(self, *, project_id: int | None = None, module_id: int | None = None) -> list[dict]:
        """Cas, triés par PRIORITÉ de lecture (high→low) puis titre.

        Tri de lecture uniquement : il ne préjuge pas de l'ordre d'exécution (décision 0006).
        """
        clauses, params = [], []
        if project_id is not None:
            clauses.append("m.project_id = ?"); params.append(project_id)
        if module_id is not None:
            clauses.append("tc.module_id = ?"); params.append(module_id)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        order = (" ORDER BY CASE tc.priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1"
                 " ELSE 2 END, tc.title COLLATE NOCASE, tc.id")
        return _rows(self.conn.execute(_CASE_SELECT + where + order, params))

    def feature_slug_taken(self, slug: str) -> bool:
        """Un slug = un fichier .feature sur disque : il doit être unique GLOBALEMENT."""
        row = self.conn.execute("SELECT 1 FROM test_case WHERE feature_slug=? LIMIT 1",
                                (slug,)).fetchone()
        return row is not None

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
                 report_json_path: str = "", report_html_path: str = "",
                 field_fallbacks: str = "") -> None:
        self.conn.execute(
            "UPDATE execution SET execution_status=?, functional_status=?, scenarios_total=?,"
            " scenarios_passed=?, scenarios_failed=?, cost_usd=?, iterations=?,"
            " duration_seconds=?, report_json_path=?, report_html_path=?, field_fallbacks=?"
            " WHERE id=?",
            (execution_status, functional_status, scenarios_total, scenarios_passed,
             scenarios_failed, cost_usd, iterations, duration_seconds, report_json_path,
             report_html_path, field_fallbacks, execution_id),
        )
        self.conn.commit()

    def get(self, execution_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM execution WHERE id=?", (execution_id,)).fetchone()
        return dict(row) if row else None

    def list_for_case(self, test_case_id: int) -> list[dict]:
        return _rows(self.conn.execute(
            "SELECT * FROM execution WHERE test_case_id=? ORDER BY id", (test_case_id,)))

    def list_recent(self, limit: int = 50, *, project_id: int | None = None) -> list[dict]:
        """Exécutions récentes (onglet Exécution), plus récentes d'abord, avec le contexte de
        ce qui a tourné (titre du cas + module).

        Filtrées sur un projet si ``project_id`` est fourni — jamais de mélange inter-projets.
        """
        select = (
            "SELECT e.*, tc.title AS case_title, m.name AS module_name"
            " FROM execution e"
            " LEFT JOIN test_case tc ON e.test_case_id = tc.id"
            " LEFT JOIN module m ON tc.module_id = m.id"
        )
        if project_id is not None:
            return _rows(self.conn.execute(
                select + " WHERE m.project_id = ? ORDER BY e.id DESC LIMIT ?",
                (project_id, max(1, limit))))
        return _rows(self.conn.execute(select + " ORDER BY e.id DESC LIMIT ?", (max(1, limit),)))

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
