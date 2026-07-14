"""Résultat structuré d'un run Behave + parsing de la sortie JSON.

Le format ``--format json`` de Behave est la source fiable (zéro regex sur le happy
path). Le ``failure_type`` produit reste au niveau SYMPTÔME (ui_timeout, assertion,
permission, odoorpc, odoo_data, unknown) — sa projection en cause racine est faite par
``verdict/defect_taxonomy``.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class BehaveFailure:
    scenario_name: str
    step_text: str
    failure_type: str
    traceback_summary: str
    raw: str = ""


@dataclass
class BehaveScenario:
    name: str
    status: str  # passed | failed | skipped
    duration: float = 0.0
    error: str = ""


@dataclass
class BehaveResult:
    success: bool
    returncode: int
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    undefined_steps: list[str] = field(default_factory=list)
    ambiguous_steps: list[str] = field(default_factory=list)
    failures: list[BehaveFailure] = field(default_factory=list)
    scenarios: list[BehaveScenario] = field(default_factory=list)
    dry_run: bool = False
    raw_stdout: str = ""
    raw_stderr: str = ""

    @property
    def has_undefined(self) -> bool:
        return bool(self.undefined_steps)

    @property
    def has_ambiguous(self) -> bool:
        return bool(self.ambiguous_steps)


_TIMEOUT_RE = re.compile(r"TimeoutError.*?:(.+?)(?:\n|$)", re.DOTALL)
_ASSERT_RE = re.compile(r"AssertionError:\s*(.+?)(?:\n|$)")
_ODOORPC_RE = re.compile(r"(odoorpc|OdooRPC|xmlrpc)\w*Error.*?:(.+?)(?:\n|$)", re.IGNORECASE)
_ACCESS_RE = re.compile(r"(AccessError|403|Permission denied)", re.IGNORECASE)


def classify_failure(snippet: str) -> tuple[str, str]:
    """Classe un message d'erreur par SYMPTÔME technique."""
    if _TIMEOUT_RE.search(snippet):
        m = _TIMEOUT_RE.search(snippet)
        return "ui_timeout", f"TimeoutError : {m.group(1)[:150] if m else ''}"
    if _ACCESS_RE.search(snippet):
        return "permission", "AccessError / 403 — profil ou droit manquant"
    if _ODOORPC_RE.search(snippet):
        m = _ODOORPC_RE.search(snippet)
        return "odoorpc", f"OdooRPC error : {m.group(2)[:150] if m else ''}"
    if _ASSERT_RE.search(snippet):
        m = _ASSERT_RE.search(snippet)
        return "assertion", f"AssertionError : {m.group(1)[:150] if m else ''}"
    if "not found" in snippet.lower() or "does not exist" in snippet.lower():
        return "odoo_data", "Enregistrement attendu introuvable"
    return "unknown", snippet[:150]


def parse_behave_json(json_output: str, returncode: int, dry_run: bool = False,
                      combined_log: str = "") -> BehaveResult:
    """Parse la sortie JSON de Behave. Fallback minimal si le JSON est absent/illisible."""
    result = BehaveResult(success=(returncode == 0), returncode=returncode, dry_run=dry_run,
                          raw_stdout=combined_log[-3000:])
    if not (json_output and json_output.strip()):
        return result

    try:
        data = json.loads(json_output)
    except json.JSONDecodeError as exc:
        logger.debug("[behave] JSON illisible, résultat minimal : %s", exc)
        return result
    if not isinstance(data, list):
        data = [data]

    undefined: set[str] = set()
    for feature in data:
        for scenario in feature.get("elements", []):
            if scenario.get("type") == "background":
                continue
            name = scenario.get("name", "") or scenario.get("keyword", "")
            first_error = ""
            step_failed = 0
            duration = 0.0
            for step in scenario.get("steps", []):
                res = step.get("result", {})
                status = res.get("status", "skipped")
                duration += res.get("duration", 0.0) or 0.0
                full_step = f"{step.get('keyword', '').strip()} {step.get('name', '')}".strip()
                if status in ("failed", "error"):
                    step_failed += 1
                    err = res.get("error_message", "") or ""
                    if not first_error:
                        first_error = err[:300]
                    ftype, summary = classify_failure(err)
                    result.failures.append(BehaveFailure(
                        scenario_name=name, step_text=full_step,
                        failure_type=ftype, traceback_summary=summary[:300], raw=err[:500],
                    ))
                elif status == "undefined":
                    undefined.add(full_step)
                elif status == "ambiguous":
                    result.ambiguous_steps.append((res.get("error_message", "") or full_step)[:200])

            sc_status = scenario.get("status", "")
            if sc_status not in ("passed", "failed", "skipped"):
                sc_status = "failed" if step_failed else "passed"
            if sc_status == "passed":
                result.passed += 1
            elif sc_status == "failed":
                result.failed += 1
            else:
                result.skipped += 1
            result.scenarios.append(BehaveScenario(
                name=name, status=sc_status, duration=round(duration, 3), error=first_error,
            ))

    result.undefined_steps = sorted(undefined)
    return result
