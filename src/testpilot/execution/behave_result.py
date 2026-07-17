"""Résultat structuré d'un run Behave + parsing de la sortie JSON.

Le format ``--format json`` de Behave est la source fiable (zéro regex sur le happy
path). Le ``failure_type`` produit reste au niveau SYMPTÔME (ui_timeout, assertion,
permission, http_error, odoorpc, odoo_data, unknown) — sa projection en cause racine est
faite par ``verdict/defect_taxonomy``.

Deux particularités de Behave ≥ 1.3 sont gérées ici :
- ``Status.error`` (exception) est distinct de ``Status.failed`` (assertion) : son message
  n'est écrit dans le JSON que grâce au formatter maison (``behave_runtime/tp_json_formatter``) ;
- ``error_message`` peut être une LISTE de lignes (message multi-ligne) → ``error_text``.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

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
    # Replis « libellé → nom technique » tracés par les helpers UI (décision 0007, phase B+).
    # Niveau RUN : on ne les rattache pas au scénario (corréler l'ordre des logs aux scénarios
    # serait fragile pour un bénéfice marginal).
    field_fallbacks: list[str] = field(default_factory=list)
    dry_run: bool = False
    raw_stdout: str = ""
    raw_stderr: str = ""

    @property
    def has_undefined(self) -> bool:
        return bool(self.undefined_steps)

    @property
    def has_ambiguous(self) -> bool:
        return bool(self.ambiguous_steps)


# Statuts d'échec de Behave ≥1.3 : 'failed' = assertion, 'error' = exception inattendue,
# 'hook_error'/'cleanup_error' = fixture (before/after) en échec.
_FAILING_STEP_STATUSES = frozenset({"failed", "error", "hook_error", "cleanup_error"})
_FAILING_SCENARIO_STATUSES = frozenset({"failed", "error", "hook_error", "cleanup_error"})

_TIMEOUT_RE = re.compile(r"TimeoutError.*?:(.+?)(?:\n|$)", re.DOTALL)
# ⚠️ « AssertionError: » n'apparaît PAS dans la sortie de Behave : `model.py:1888` (behave 1.3.3)
# remplace le nom de la classe par son propre préfixe « ASSERT FAILED: ». Cette regex ne voyait
# donc JAMAIS une assertion en run réel — les 5 assertions de la base sont toutes tombées en
# `failure_type='unknown'`, et la taxonomie devait les rattraper aux mots-clés (décision 0015).
# Les deux formes sont acceptées : « ASSERT FAILED » (Behave) et « AssertionError » (appel direct
# / mode verbose, où Behave joint le traceback).
_ASSERT_RE = re.compile(r"(?:AssertionError|ASSERT FAILED):\s*(.+?)(?:\n|$)")
_ODOORPC_RE = re.compile(r"(odoorpc|OdooRPC|xmlrpc)\w*Error.*?:(.+?)(?:\n|$)", re.IGNORECASE)
_ACCESS_RE = re.compile(r"(AccessError|403|Permission denied)", re.IGNORECASE)
# Erreur HTTP sur une ROUTE (404/405/5xx, HTTPError requests…) : le test a visé un endpoint
# qui n'existe pas ou refuse la méthode — un problème de PARCOURS, pas de sélecteur.
# Placé après _ACCESS_RE : un 403 reste un problème de droit, pas de navigation.
_HTTP_RE = re.compile(r"HTTPError|\b[45]\d\d\s+(?:client|server)\s+error|Method Not Allowed",
                      re.IGNORECASE)


def error_text(raw) -> str:
    """Normalise le ``error_message`` de Behave en chaîne.

    Le formatter JSON écrit une LISTE de lignes dès que le message est multi-ligne
    (``split_text_into_lines`` est vrai par défaut) — typiquement une erreur Playwright
    (« Call log: … ») ou une assertion détaillée. Sans cette normalisation, la suite du
    parsing reçoit une liste et lève un TypeError : le run serait alors clos en « erreur
    technique », masquant un éventuel vrai bug (faux-négatif §5 inacceptable).
    """
    if raw is None:
        return ""
    if isinstance(raw, (list, tuple)):
        return "\n".join(str(line) for line in raw)
    return str(raw)


# Ligne d'exception d'un traceback Python : ``module.qualifié.XxxError: message`` (ou
# Exception / Timeout). Ancrée en début de ligne pour ne pas matcher un ``: Error`` au fil
# du texte. On garde la DERNIÈRE (une chaîne d'exceptions finit sur celle réellement levée).
_EXCEPTION_LINE_RE = re.compile(r"^[\w.]+(?:Error|Exception|Timeout)\b.*", re.MULTILINE)


def meaningful_error(raw, limit: int = 600) -> str:
    """Partie EXPLOITABLE d'un traceback pour un lecteur humain (message + « Call log »).

    Un traceback Python porte l'information utile à la FIN : la ligne d'exception et son
    message, suivis — pour Playwright — d'un bloc ``Call log:`` qui contient le sélecteur
    réellement attendu. Tronquer par la TÊTE (``raw[:N]``) ne garde que les frames internes
    de Behave/Playwright et jette le message ; c'est ce qui rendait le sélecteur fautif
    invisible en base et à l'écran (§6.1, écart 3). On repart donc de la dernière ligne
    d'exception jusqu'à la fin. À défaut de ligne identifiable, la queue reste plus parlante
    que la tête.
    """
    text = error_text(raw).strip()
    if not text:
        return ""
    matches = list(_EXCEPTION_LINE_RE.finditer(text))
    tail = text[matches[-1].start():].strip() if matches else text[-limit:].strip()
    return tail[:limit]


# Nom du fichier sidecar où les helpers UI consignent leurs replis « libellé → nom technique »
# (décision 0007, phase B+), et de la variable d'env qui le désigne. Nom DUPLIQUÉ avec
# ``_base_helpers`` (l'importer tirerait Playwright dans la couche API) : l'accord des deux
# valeurs est tenu par test (test_field_resolution).
FIELD_FALLBACK_FILE_ENV = "TP_FIELD_FALLBACK_FILE"
FIELD_FALLBACK_FILENAME = "field_fallbacks.txt"

_MAX_FIELD_FALLBACKS = 20


def read_field_fallbacks(path, limit: int = _MAX_FIELD_FALLBACKS) -> list[str]:
    """Replis « libellé → nom technique » consignés pendant le run (décision 0007, phase B+).

    ⚠️ **Pourquoi un fichier et non la sortie de Behave.** Le premier jet de B+ lisait le marqueur
    dans ``combined_log`` : il était **aveugle en run réel**. Mesuré (behave 1.3.3) — Behave capture
    stdout/stderr/logging et ne les recrache PAS pour un scénario VERT **dès qu'un environment.py
    est présent**, ce que ``BehaveRunner._assemble`` fait TOUJOURS. Le signal se perdait donc
    exactement sur le cas qu'il doit couvrir (champ renommé → repli → run vert). Le fichier ne
    dépend d'aucun routage de Behave : c'est la seule propriété qui compte ici.

    Dédupliqué (le même repli se répète à chaque scénario) et plafonné : la liste est persistée.
    Fichier absent = aucun repli (cas nominal), jamais une erreur.
    """
    try:
        content = Path(path).read_text(encoding="utf-8")
    except (OSError, ValueError):
        return []
    found: list[str] = []
    for line in content.splitlines():
        message = line.strip()
        if message and message not in found:
            found.append(message)
            if len(found) >= limit:
                break
    return found


def classify_failure(snippet: str) -> tuple[str, str]:
    """Classe un message d'erreur par SYMPTÔME technique.

    L'assertion est reconnue EN PREMIER : « ASSERT FAILED: » est écrit par Behave lui-même, donc
    le fait qu'il s'agisse d'une assertion est ACQUIS. Tout ce qui suit est le message rédigé par
    l'agent — le tester d'abord laisserait un « permission denied » écrit dans une assertion
    devenir un problème de droits (`permission`), c'est-à-dire un défaut d'environnement à
    réparer, alors que l'application vient peut-être de répondre faux (§4.4, décision 0015).
    """
    snippet = error_text(snippet)
    if _ASSERT_RE.search(snippet):
        m = _ASSERT_RE.search(snippet)
        return "assertion", f"Assertion en échec : {m.group(1)[:150] if m else ''}"
    if _TIMEOUT_RE.search(snippet):
        m = _TIMEOUT_RE.search(snippet)
        return "ui_timeout", f"TimeoutError : {m.group(1)[:150] if m else ''}"
    if _ACCESS_RE.search(snippet):
        return "permission", "AccessError / 403 — profil ou droit manquant"
    if _HTTP_RE.search(snippet):
        m = _HTTP_RE.search(snippet)
        return "http_error", f"Erreur HTTP sur une route : {m.group(0)[:150] if m else ''}"
    if _ODOORPC_RE.search(snippet):
        m = _ODOORPC_RE.search(snippet)
        return "odoorpc", f"OdooRPC error : {m.group(2)[:150] if m else ''}"
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
                if status in _FAILING_STEP_STATUSES:
                    step_failed += 1
                    err = error_text(res.get("error_message"))
                    if not first_error:
                        # Message EXPLOITABLE (exception + « Call log » avec le sélecteur),
                        # pas la tête du traceback : cf. meaningful_error (§6.1, écart 3).
                        first_error = meaningful_error(err)
                    ftype, summary = classify_failure(err)
                    result.failures.append(BehaveFailure(
                        scenario_name=name, step_text=full_step,
                        failure_type=ftype, traceback_summary=summary[:300], raw=err[:500],
                    ))
                elif status == "undefined":
                    undefined.add(full_step)
                elif status == "ambiguous":
                    result.ambiguous_steps.append(
                        (error_text(res.get("error_message")) or full_step)[:200])

            sc_status = scenario.get("status", "")
            # Behave ≥1.3 distingue 'failed' (assertion) de 'error'/'hook_error' (exception,
            # échec de fixture). Tous sont des scénarios en échec côté verdict : on les
            # ramène explicitement à 'failed' plutôt que de compter dessus par accident.
            if sc_status in _FAILING_SCENARIO_STATUSES:
                sc_status = "failed"
            elif sc_status not in ("passed", "failed", "skipped"):
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
