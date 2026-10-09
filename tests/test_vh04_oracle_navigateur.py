"""Lot VH-04, étape 1 — oracle et navigateur, d'après la mesure base-4 (2026-10-09) et l'audit (V6, point 3 du lot 4).

- Un oracle qui répond en ERREUR HTTP n'a rien observé : `indetermine` (cause `oracle_en_erreur`), jamais `wrong_navigation`
  (un test « à réparer ») ni `non_conforme`.
- « l'oracle … renvoie N résultat(s) » sur une réponse OBJET : le test est mal posé (erreur technique), plus jamais un
  `non_conforme` sur une application saine (faux rouge mesuré : base-2 9 essais sur 30, base-4 1).
- « le champ … vaut … » compare des valeurs TYPÉES : `12.0` vaut « 12 », `true` vaut « true » — sans élargir (« 12 € » ≠ 12).
- Une adresse relative ouverte par un test (`page.goto("/__etat")`) se résout contre l'application du projet (base-4 : 2 essais
  en erreur technique « Cannot navigate to invalid URL »).
"""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

from testpilot.verdict import defect_origin as do
from testpilot.verdict import defect_taxonomy as dt
from testpilot.verdict import status as st

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "behave_runtime" / "steps_library"))
import _base_helpers as H  # noqa: E402


class _Oracle(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, code, objet):
        corps = json.dumps(objet).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)

    def do_GET(self):
        chemin = self.path.split("?")[0]
        if chemin == "/etat":
            return self._json(200, {"commandes": [], "total": 12.0, "payee": True, "remise": None, "code": "12"})
        if chemin == "/panne":
            return self._json(503, {"erreur": "indisponible"})
        if chemin in ("/", "/accueil"):
            corps = b"<html><body><h1>Accueil</h1></body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(corps)))
            self.end_headers()
            return self.wfile.write(corps)
        self._json(404, {"erreur": "absent"})


@pytest.fixture
def serveur():
    httpd = HTTPServer(("127.0.0.1", 0), _Oracle)
    fil = threading.Thread(target=httpd.serve_forever, daemon=True)
    fil.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()


def _contexte(serveur):
    requetes = [{"name": "etat", "method": "GET", "path": "/etat"}, {"name": "panne", "method": "GET", "path": "/panne"}]
    oracle, erreur = H.construire_oracle(
        {H._oracle_config.ENV_ORACLE: json.dumps({"base_url": serveur, "auth": {}, "queries": requetes})})
    return SimpleNamespace(oracle=oracle, oracle_erreur=erreur)


# ── Oracle en erreur ──────────────────────────────────────────────────────────────────────────────────────


def test_falsifiable_un_oracle_en_erreur_n_est_ni_un_test_a_reparer_ni_une_accusation(serveur):
    with pytest.raises(H.OracleEnErreurError) as erreur:
        H.oracle_champ_vaut(_contexte(serveur), "total", "panne", "12")

    assert isinstance(erreur.value, urllib.error.HTTPError), "reste une erreur HTTP, jamais un prérequis manquant"
    assert "503" in str(erreur.value)
    echec = SimpleNamespace(raw=f"_base_helpers.OracleEnErreurError: {erreur.value}", traceback_summary="",
                            failure_type="error", step_type="then")
    cause = dt.classify_failure(echec)
    assert cause == dt.ORACLE_EN_ERREUR
    assert do.classify_defect_origin(cause) == do.INDETERMINE
    scenario = SimpleNamespace(name="s", status="failed", error="", constats_echoues=0)
    verdict = st.scenario_verdict(scenario, [SimpleNamespace(**vars(echec), scenario_name="s", step_text="")])
    assert (verdict.execution_status, verdict.functional_status) == (st.EXEC_SUCCESS, st.FUNC_INDETERMINE)


def test_la_nouvelle_cause_a_un_libelle_francais_partout():
    assert dt.ORACLE_EN_ERREUR in dt.CATEGORIES and dt.ORACLE_EN_ERREUR in dt.LABELS
    assert "oracle_en_erreur:" in (RACINE / "frontend" / "src" / "lib" / "status.ts").read_text(encoding="utf-8")


# ── Un objet ne se compte pas ─────────────────────────────────────────────────────────────────────────────


def test_falsifiable_compter_un_objet_est_un_test_mal_pose_jamais_une_accusation(serveur):
    with pytest.raises(H.ReponseOracleNonComptableError):
        H.oracle_renvoie_n_resultats(_contexte(serveur), "etat", 0)

    echec = SimpleNamespace(raw="_base_helpers.ReponseOracleNonComptableError: …", traceback_summary="",
                            failure_type="error", step_type="then")
    assert dt.classify_failure(echec) == dt.BROKEN_TEST_CODE


# ── Comparaisons typées ───────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("obtenu, attendu, egal", [
    (12.0, "12", True), (12.0, "12,0", True), (12, "12.00", True),
    (12.0, "13", False), (12.0, "12 €", False),
    (True, "true", True), (True, "True", True), (True, "vrai", False), (False, "true", False),
    (None, "null", True), (None, "", False),
    ("12", "12", True), ("Payée", "payée", False),
])
def test_comparaison_typee_sans_elargir(obtenu, attendu, egal):
    assert H._valeurs_egales(obtenu, attendu) is egal


def test_falsifiable_une_liste_ou_un_objet_ne_vaut_jamais_un_texte(serveur, tmp_path, monkeypatch):
    monkeypatch.setenv(H.CONSTATS_FILE_ENV, str(tmp_path / "c.jsonl"))
    with pytest.raises(AssertionError, match="pas une valeur simple"):
        H.oracle_champ_vaut(_contexte(serveur), "commandes", "etat", "[]")


# ── Bout en bout : vrai Behave, vrai Chromium ─────────────────────────────────────────────────────────────


class _Application(_Oracle):
    def do_GET(self):
        if self.path.split("?")[0] == "/__etat":
            return self._json(200, {"clients": [{"nom": "Dupont"}]})
        return super().do_GET()


@pytest.fixture
def application():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Application)
    fil = threading.Thread(target=httpd.serve_forever, daemon=True)
    fil.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


_STEPS_RELATIFS = '''from behave import then
from _base_helpers import constater


@then('l\\'état relu à une adresse relative compte {n:d} client')
def step_impl(context, n):
    context.page.goto("/__etat")
    constater(len(__import__("json").loads(context.page.locator("body").inner_text())["clients"]) == n, "clients")
'''


@pytest.mark.conformance
def test_une_adresse_relative_ouverte_par_un_test_vise_l_application(application):
    from testpilot.execution.behave_runner import BehaveRunner
    from testpilot.execution.executor import Executor

    dossier = Path(tempfile.mkdtemp(prefix="vh04_"))
    (dossier / "rel.feature").write_text(
        "Fonctionnalité: Adresse relative\n\n  Scénario: relu\n    Soit j'accède à la page d'accueil de l'application\n"
        "    Alors l'état relu à une adresse relative compte 1 client\n", encoding="utf-8")
    (dossier / "rel_steps.py").write_text(_STEPS_RELATIFS, encoding="utf-8")
    runner = BehaveRunner(connection={"WEB_URL": application, "WEB_USER": "", "WEB_PASSWORD": ""},
                          connector_type="web", generated_dir=dossier)

    verdict = st.derive_verdict(Executor(runner, max_retries=0).execute("rel"), connector_type="web")

    v = verdict.scenarios[0]
    assert (v.execution_status, v.functional_status) == (st.EXEC_SUCCESS, st.FUNC_CONFORME), v.error[:400]
