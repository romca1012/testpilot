"""Confinement des navigateurs de la campagne du banc d'agents : bouclage seulement (2026-10-07).

Un test GÉNÉRÉ par un modèle s'exécute dans un vrai navigateur pendant une campagne payante : il ne doit pouvoir joindre que
l'application locale du banc. `TP_LOOPBACK_ONLY=1` lance Chromium avec un proxy inexistant ; Chromium contourne le proxy pour
`localhost`/`127.0.0.1`/`[::1]` et refuse tout le reste. On le prouve avec un vrai Chromium (la règle implicite de Chromium est
exactement ce dont tout dépend) : l'application locale répond, un nom de domaine et une IP littérale externes sont refusés.
Les tests purs vérifient que le réglage est sans effet hors campagne et que les deux copies du helper s'accordent.
"""

from __future__ import annotations

import importlib.util
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from testpilot import config
from testpilot.connectors import contexte_navigateur as cn

_ENV_PATH = config.BEHAVE_RUNTIME_DIR / "environment.py"


def _environment():
    spec = importlib.util.spec_from_file_location("environment_confinement", _ENV_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ── Purs ─────────────────────────────────────────────────────────────────────────────────────────

def test_hors_campagne_aucun_argument_n_est_ajoute(monkeypatch):
    monkeypatch.delenv("TP_LOOPBACK_ONLY", raising=False)

    assert cn.arguments_de_confinement() == []
    assert _environment()._arguments_de_confinement() == []


def test_en_campagne_un_proxy_inexistant_est_pose(monkeypatch):
    monkeypatch.setenv("TP_LOOPBACK_ONLY", "1")

    assert cn.arguments_de_confinement() == ["--proxy-server=http://127.0.0.1:9"]


def test_seule_la_valeur_un_active_le_confinement(monkeypatch):
    for valeur in ("0", "", "true", "oui"):
        monkeypatch.setenv("TP_LOOPBACK_ONLY", valeur)
        assert cn.arguments_de_confinement() == [], valeur


def test_les_deux_copies_du_helper_s_accordent(monkeypatch):
    """`environment.py` tourne dans le sous-processus Behave sans dépendre du paquet : même valeur, par test d'accord."""
    for valeur in ("1", "0"):
        monkeypatch.setenv("TP_LOOPBACK_ONLY", valeur)
        assert _environment()._arguments_de_confinement() == cn.arguments_de_confinement()
    assert cn.ENV_CONFINEMENT_BOUCLAGE == "TP_LOOPBACK_ONLY"


def test_la_campagne_active_le_confinement_pour_tout_le_processus_relance(monkeypatch):
    import sys
    racine = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location("banc_agents_conf", racine / "scripts" / "banc_agents.py")
    ba = importlib.util.module_from_spec(spec)
    sys.modules["banc_agents_conf"] = ba
    spec.loader.exec_module(ba)
    vus = []
    monkeypatch.setattr(ba.subprocess, "call", lambda cmd, env: vus.append(env) or 0)
    monkeypatch.delenv("BANC_AGENTS_ISOLE", raising=False)

    ba.relancer_isole(["--reel"])

    assert vus[0]["TP_LOOPBACK_ONLY"] == "1"


# ── Vrai Chromium ────────────────────────────────────────────────────────────────────────────────

class _Local(BaseHTTPRequestHandler):
    def log_message(self, *_a):
        pass

    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ok")


@contextmanager
def _application():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Local)
    fil = threading.Thread(target=srv.serve_forever, daemon=True)
    fil.start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}"
    finally:
        srv.shutdown()
        srv.server_close()
        fil.join(timeout=5)


def _joignable(page, url: str) -> bool:
    return bool(page.evaluate(
        "async (u) => { try { const r = await fetch(u, {mode: 'no-cors'}); return true; } catch (e) { return false; } }", url))


@pytest.mark.conformance
def test_chromium_confine_joint_le_local_et_refuse_l_exterieur(monkeypatch):
    from playwright.sync_api import sync_playwright

    monkeypatch.setenv("TP_LOOPBACK_ONLY", "1")
    with _application() as base, sync_playwright() as pw:
        navigateur = pw.chromium.launch(headless=True, args=cn.arguments_de_confinement())
        try:
            page = navigateur.new_page()
            page.goto(f"{base}/")

            assert _joignable(page, f"{base}/") is True, "l'application locale doit rester joignable"
            assert _joignable(page, "http://example.com/") is False, "un nom de domaine externe doit être refusé"
            assert _joignable(page, "http://203.0.113.9/") is False, "une IP littérale externe doit être refusée aussi"
        finally:
            navigateur.close()


@pytest.mark.conformance
def test_sans_confinement_le_navigateur_n_a_pas_de_proxy(monkeypatch):
    """Sens inverse : hors campagne, aucun argument — l'application locale reste joignable comme avant."""
    from playwright.sync_api import sync_playwright

    monkeypatch.delenv("TP_LOOPBACK_ONLY", raising=False)
    with _application() as base, sync_playwright() as pw:
        navigateur = pw.chromium.launch(headless=True, args=cn.arguments_de_confinement())
        try:
            page = navigateur.new_page()
            page.goto(f"{base}/")

            assert _joignable(page, f"{base}/") is True
        finally:
            navigateur.close()
