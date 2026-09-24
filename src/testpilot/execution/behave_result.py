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
    # Le TYPE du step en échec, tel que Behave l'écrit dans son JSON (`step_type` : given | when |
    # then ; `Et`/`Mais` héritent du type du step précédent — mesuré sur behave 1.3.3, 2026-09-24),
    # ou `hook` pour une fixture (`before_scenario`…) en échec avant tout step. C'est un SIGNAL de
    # structure produit par Behave, jamais le libellé écrit par l'agent (décision 0015).
    step_type: str = ""


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
    # Refus MESURÉS sur l'application pendant le run (§5bis n°1). Niveau RUN, même raison.
    # Ce sont des FAITS, pas un verdict : ils n'influencent aucun statut, ils alimentent
    # l'apprentissage pour que le résolveur ne reproduise plus la valeur refusée.
    refus_mesures: list[dict] = field(default_factory=list)
    # Le PALIER de `locate_field` qui a résolu chaque champ (plan de consolidation, §1.2) — un
    # fait par champ résolu, y compris le cas silencieux `name`. Alimente la mémoire de dérive du
    # projet, jamais le verdict : un changement de palier est un signal à surveiller, pas un échec.
    selector_tiers: list[dict] = field(default_factory=list)
    # Libellés de menu APPRIS par le repli adaptatif de `navigate_menu` (Lot 2, 2026-09-23) — un
    # fait par segment résolu adaptativement. Niveau RUN, même raison que `selector_tiers`.
    # Alimente `testpilot.generation.menu_appris`, jamais le verdict.
    menus_appris: list[dict] = field(default_factory=list)
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

# Behave imprime « HOOK-ERROR in before_scenario: RuntimeError: … » : le JSON ne dit RIEN d'un hook
# en échec (scénario `hook_error`, steps sans résultat, aucun message — mesuré le 2026-09-24). Ce
# texte est produit par le RUNTIME, pas par l'agent : on le garde pour dire POURQUOI le test est bloqué.
_HOOK_ERROR_RE = re.compile(r"HOOK-ERROR in (\w+):\s*(.+)")
_TYPES_DE_STEP = ("given", "when", "then")
STEP_TYPE_HOOK = "hook"

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

# Sidecar des refus MESURÉS pendant le run (§5bis n°1 — « la règle apprise à chaque refus »).
# Mêmes noms dupliqués côté ``_base_helpers``, pour la même raison, et le même test d'accord.
REGLES_REFUS_FILE_ENV = "TP_REGLES_REFUS_FILE"
REGLES_REFUS_FILENAME = "regles_refus.jsonl"

_MAX_REFUS = 20

# Sidecar du palier de résolution de CHAQUE champ (plan de consolidation, §1.2). Mêmes noms
# dupliqués côté ``_base_helpers``, pour la même raison, et le même test d'accord.
SELECTOR_TIER_FILE_ENV = "TP_SELECTOR_TIER_FILE"
SELECTOR_TIER_FILENAME = "selector_tiers.jsonl"

# Un run peut résoudre beaucoup plus de champs qu'il n'y a de refus (chaque `fill_field`/
# `select_field_value` en écrit un) — plafond plus généreux que `_MAX_REFUS` pour autant.
_MAX_SELECTOR_TIERS = 200

# Sidecar des libellés de menu APPRIS par le repli adaptatif de `navigate_menu` (Lot 2 du plan de
# fiabilisation, 2026-09-23). Mêmes noms dupliqués côté `_base_helpers`, pour la même raison, et le
# même test d'accord.
MENU_LEARNED_FILE_ENV = "TP_MENU_APPRIS_FILE"
MENU_LEARNED_FILENAME = "menus_appris.jsonl"

# Un segment de menu n'est résolu qu'une poignée de fois par run (une navigation par scénario) —
# plafond nettement plus bas que `_MAX_SELECTOR_TIERS`.
_MAX_MENUS_APPRIS = 100


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


def read_refus_mesures(path, limit: int = _MAX_REFUS) -> list[dict]:
    """Les refus MESURÉS pendant le run, relus depuis le sidecar (§5bis n°1).

    Chaque ligne est un objet JSON décrivant un fait constaté sur l'application : quelle route,
    quel champ, quel drapeau de validation, quelle valeur a été refusée. Ce sont ces faits qui
    deviendront des règles apprises, pour que le résolveur ne reproduise plus la valeur.

    ⚠️ **Même raison qu'un fichier plutôt que le log** : Behave ne recrache pas la sortie d'un
    scénario capturé, et un refus survient précisément dans des scénarios que Behave capture. Le
    fichier ne dépend d'aucun routage de journalisation.

    Tolérant : une ligne illisible est sautée, pas propagée. Fichier absent = aucun refus (le cas
    nominal d'un run qui s'est bien passé), jamais une erreur.
    """
    try:
        content = Path(path).read_text(encoding="utf-8")
    except (OSError, ValueError):
        return []
    mesures: list[dict] = []
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            objet = json.loads(line)
        except ValueError:
            continue
        if isinstance(objet, dict):
            mesures.append(objet)
            if len(mesures) >= limit:
                break
    return mesures


def read_selector_tiers(path, limit: int = _MAX_SELECTOR_TIERS) -> list[dict]:
    """Les paliers de résolution consignés pendant le run, relus depuis le sidecar (§1.2).

    Chaque ligne est un fait `{"ident": ..., "tier": ...}` — quel palier de `locate_field` a
    résolu ce champ, y compris le palier silencieux `name`. Ce sont ces faits qui alimentent la
    mémoire de dérive du projet (`testpilot.execution.selector_memory`).

    Même raison qu'un fichier plutôt que le log : Behave ne recrache pas la sortie d'un scénario
    capturé, et une résolution a lieu dans TOUS les scénarios, verts compris.

    Tolérant : une ligne illisible est sautée, pas propagée. Fichier absent = aucune résolution
    consignée (hors d'un run réel), jamais une erreur.
    """
    try:
        content = Path(path).read_text(encoding="utf-8")
    except (OSError, ValueError):
        return []
    resolutions: list[dict] = []
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            objet = json.loads(line)
        except ValueError:
            continue
        if isinstance(objet, dict):
            resolutions.append(objet)
            if len(resolutions) >= limit:
                break
    return resolutions


def read_menus_appris(path, limit: int = _MAX_MENUS_APPRIS) -> list[dict]:
    """Les libellés de menu APPRIS pendant le run, relus depuis le sidecar (Lot 2, 2026-09-23).

    Chaque ligne est un fait `{"segment_original": ..., "libelle_reel": ..., "menu_path": ...}` —
    quel segment de menu cherché par le Gherkin a réellement été atteint via QUEL libellé, quand
    `navigate_menu` a dû recourir au repli adaptatif (« Chantier F »). Ce sont ces faits qui
    alimentent la mémoire de menus du projet (`testpilot.generation.menu_appris`), que la
    génération relit pour ne plus reproposer un libellé déjà connu pour être faux.

    Même raison qu'un fichier plutôt que le log : Behave ne recrache pas la sortie d'un scénario
    capturé, et un repli adaptatif de navigation a justement lieu dans un scénario qui finit vert.

    Tolérant : une ligne illisible est sautée, pas propagée. Fichier absent = aucun repli de
    navigation nécessaire pendant ce run (le cas nominal), jamais une erreur.
    """
    try:
        content = Path(path).read_text(encoding="utf-8")
    except (OSError, ValueError):
        return []
    faits: list[dict] = []
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            objet = json.loads(line)
        except ValueError:
            continue
        if isinstance(objet, dict):
            faits.append(objet)
            if len(faits) >= limit:
                break
    return faits


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


def _type_du_step(step: dict, precedent: str) -> str:
    """`given | when | then` du step. Behave le fournit et fait hériter `Et`/`Mais` ; si le champ
    manquait (autre version), on reprend le type du step précédent plutôt que de deviner sur un
    libellé — `""` tant qu'aucun step n'a déclaré son type."""
    declare = str(step.get("step_type") or "").lower()
    return declare if declare in _TYPES_DE_STEP else precedent


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
    messages_de_hook = [f"{m[1].strip()}" for m in _HOOK_ERROR_RE.findall(combined_log or "")]
    for feature in data:
        for scenario in feature.get("elements", []):
            if scenario.get("type") == "background":
                continue
            name = scenario.get("name", "") or scenario.get("keyword", "")
            first_error = ""
            step_failed = 0
            duration = 0.0
            type_precedent = ""
            for step in scenario.get("steps", []):
                type_precedent = _type_du_step(step, type_precedent)
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
                        # ⚠️ `raw` = la QUEUE utile du traceback (`meaningful_error`), PAS sa tête
                        # (`err[:500]`). La tête ne contient que les frames de Behave/Playwright ;
                        # le NOM de la classe d'exception est en fin de traceback. `defect_taxonomy`
                        # lit `raw` pour reconnaître le type (`DonneeRefuseeError`,
                        # `InvalidOptionValueError`…) : avec la tête, il ne le voyait JAMAIS en run
                        # réel (le 4ᵉ verdict ne se déclenchait pas — trouvé au rejeu du 2026-07-23).
                        # Cohérent avec `first_error` ci-dessus, qui prend déjà la queue.
                        failure_type=ftype, traceback_summary=summary[:300],
                        raw=meaningful_error(err), step_type=type_precedent,
                    ))
                elif status == "undefined":
                    undefined.add(full_step)
                elif status == "ambiguous":
                    result.ambiguous_steps.append(
                        (error_text(res.get("error_message")) or full_step)[:200])

            sc_status = scenario.get("status", "")
            if sc_status == "hook_error" and not step_failed:
                # Fixture en échec AVANT tout step : le JSON ne porte ni step en échec ni message.
                # On matérialise l'échec (sinon `scenario_verdict` ne verrait « aucune cause ») et
                # on y joint le message que Behave a imprimé.
                message = messages_de_hook.pop(0) if messages_de_hook else ""
                first_error = message or "Échec d'une fixture Behave avant le premier step."
                result.failures.append(BehaveFailure(
                    scenario_name=name, step_text="", failure_type=STEP_TYPE_HOOK,
                    traceback_summary="Fixture en échec avant tout step"[:300], raw=message,
                    step_type=STEP_TYPE_HOOK))
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
