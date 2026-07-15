"""§5 — les échecs techniques ne doivent plus être opaques (décision 0002).

Trois défauts corrigés ensemble, tous vérifiés ici :
- B : ``error_message`` peut être une LISTE (message multi-ligne) → le parser crashait, et le
      run était clos en « erreur technique », masquant un vrai bug (faux-négatif §5) ;
- A : Behave ≥1.3 n'écrit pas le message des steps ``error`` → formatter maison ;
- C : une erreur HTTP sur une route est un problème de PARCOURS, pas de sélecteur.
"""

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from testpilot.execution.behave_result import (
    BehaveFailure,
    classify_failure,
    error_text,
    parse_behave_json,
)
from testpilot.execution.behave_runner import BehaveRunner
from testpilot.verdict import defect_origin as do
from testpilot.verdict import defect_taxonomy as dt


def _json_with(step_status: str, error_message, scenario_status: str = "failed") -> str:
    return json.dumps([{"elements": [{
        "type": "scenario", "name": "S", "status": scenario_status,
        "steps": [{"keyword": "Alors", "name": "le total est bon",
                   "result": {"status": step_status, "duration": 0.1,
                              "error_message": error_message}}],
    }]}])


# ── B : normalisation du message (le correctif le plus critique) ───────────────
def test_error_text_normalise_liste_chaine_et_none():
    assert error_text(["ligne 1", "ligne 2"]) == "ligne 1\nligne 2"
    assert error_text("déjà une chaîne") == "déjà une chaîne"
    assert error_text(None) == ""


def test_message_en_liste_ne_crashe_plus_et_reste_un_vrai_bug():
    """Une assertion multi-ligne arrive en LISTE : elle doit rester détectée comme vrai bug.

    Avant : TypeError → run clos en « erreur technique » → le vrai bug était masqué.
    """
    out = _json_with("failed", ["Traceback (most recent call last):",
                                "AssertionError: attendu 0, obtenu 5"])
    result = parse_behave_json(out, 1)

    failure = result.failures[0]
    assert failure.failure_type == "assertion"
    assert "attendu 0" in failure.raw
    # La chaîne complète : le verdict doit conclure « vrai bug », jamais « erreur technique ».
    cause = dt.classify_failure(failure)
    assert cause == dt.ASSERTION_MISMATCH
    assert do.classify_defect_origin(cause) == do.VRAI_BUG


# ── A : message des steps « errored » ─────────────────────────────────────────
def test_step_errored_avec_message_est_exploitable():
    out = _json_with("error", "ERROR: HTTPError: 404 Client Error: NOT FOUND for url: <url>")
    result = parse_behave_json(out, 1)

    assert len(result.failures) == 1
    assert result.failures[0].failure_type != "unknown"   # plus opaque
    assert result.scenarios[0].status == "failed"


def test_step_errored_sans_message_reste_tolere():
    # Formatter natif (repli) : pas de message → on ne crashe pas, la cause reste inconnue.
    out = _json_with("error", None)
    result = parse_behave_json(out, 1)
    assert result.failures[0].failure_type == "unknown"


def test_hook_error_compte_comme_scenario_en_echec():
    """Fixture en échec (ex. Odoo injoignable) → échec honnête, jamais 'passed'."""
    out = _json_with("hook_error", "ERROR: ConnectionRefusedError", scenario_status="hook_error")
    result = parse_behave_json(out, 1)
    assert result.scenarios[0].status == "failed"
    assert result.failed == 1
    assert result.passed == 0


# ── C : une erreur HTTP est un problème de parcours ───────────────────────────
def test_404_est_une_navigation_erronee_pas_un_selecteur():
    msg = ("requests.exceptions.HTTPError: 404 Client Error: NOT FOUND for url: "
           "http://localhost:10017/web/dataset/call_kw")
    ftype, _ = classify_failure(msg)
    assert ftype == "http_error"

    failure = BehaveFailure("S", "Et le compteur est enregistre", *classify_failure(msg))
    cause = dt.classify_failure(failure)
    assert cause == dt.WRONG_NAVIGATION          # et non WRONG_FIELD_NAME (« not found »)
    assert dt.LABELS[cause] == "Navigation erronée"


def test_405_method_not_allowed_est_une_navigation():
    ftype, _ = classify_failure("HTTPError: 405 Client Error: Method Not Allowed")
    assert ftype == "http_error"


def test_403_reste_un_probleme_de_droit_pas_de_navigation():
    """Non-régression : l'ajout des motifs HTTP ne doit pas avaler les erreurs de permission."""
    ftype, _ = classify_failure("odoorpc.error.RPCError: AccessError: 403 Forbidden")
    assert ftype == "permission"
    failure = BehaveFailure("S", "étape", ftype, "AccessError / 403")
    assert dt.classify_failure(failure) == dt.MISSING_ROLE


def test_timeout_playwright_reste_un_selecteur():
    """Non-régression : un timeout UI ne doit pas basculer en navigation."""
    ftype, _ = classify_failure('TimeoutError: Page.fill: Timeout 15000ms exceeded.\n'
                                'Call log:\n  - waiting for locator("input[name=x]")')
    assert ftype == "ui_timeout"


def test_repli_de_symptome_http_error_vers_navigation():
    # Sans mot-clé exploitable dans le texte, le symptôme seul doit suffire.
    assert dt.classify_failure(BehaveFailure("S", "", "http_error", "")) == dt.WRONG_NAVIGATION


# ── A (intégration) : vrai run behave, formatter maison ───────────────────────
_PROBE_FEATURE = "# language: fr\nFonctionnalité: sonde\n  Scénario: erreur non-assertion\n    Quand une erreur http survient\n"
_PROBE_STEPS = '''
from behave import when

@when(u'une erreur http survient')
def step_impl(context):
    raise RuntimeError("404 Client Error: NOT FOUND for url: http://localhost:10017/web/dataset/call_kw")
'''


@pytest.fixture
def probe_dirs():
    tmp = Path(tempfile.mkdtemp())
    runtime, gen, lib = tmp / "runtime", tmp / "gen", tmp / "lib"
    for d in (runtime, gen, lib):
        d.mkdir()
    # runtime SANS environment.py (aucun Odoo requis) mais AVEC le formatter maison.
    shutil.copy2(Path("behave_runtime/tp_json_formatter.py"), runtime / "tp_json_formatter.py")
    (gen / "probe.feature").write_text(_PROBE_FEATURE, encoding="utf-8")
    (gen / "probe_steps.py").write_text(_PROBE_STEPS, encoding="utf-8")
    yield runtime, gen, lib
    shutil.rmtree(tmp, ignore_errors=True)


def test_run_reel_le_formatter_recupere_le_message_dun_step_errored(probe_dirs):
    """Preuve de bout en bout : une exception (non-assertion) remonte avec son message.

    Sans le formatter maison, Behave n'écrit rien pour un ``Status.error`` → cause 'unknown'.
    """
    runtime, gen, lib = probe_dirs
    result = BehaveRunner(runtime_dir=runtime, generated_dir=gen, steps_library_dir=lib).real_run("probe")

    assert result.scenarios[0].status == "failed"
    assert len(result.failures) == 1
    failure = result.failures[0]
    assert failure.raw, "le message d'erreur doit être récupéré (était vide avant le formatter)"
    assert "404" in failure.raw or "NOT FOUND" in failure.raw.upper()
