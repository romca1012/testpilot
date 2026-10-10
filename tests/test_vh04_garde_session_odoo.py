"""Revue du lot VH-04 (bloquant B3) — la garde de session était INERTE sur Odoo : cookies de départ vides (le `storage_state`
ne sert qu'au connecteur web) et mot de passe tapé par la connexion Odoo compté comme celui du test. Après `playwright_login`,
la session de référence est relevée et la saisie du harnais oubliée."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "behave_runtime" / "steps_library"))
import _base_helpers as H  # noqa: E402


def test_falsifiable_la_connexion_odoo_releve_la_session_de_reference(monkeypatch):
    from testpilot.connectors import odoo_login

    cookies = [{"name": "session_id", "value": "abc"}]
    context = SimpleNamespace(_browser_context=SimpleNamespace(cookies=lambda: cookies), _tp_cookies_session=frozenset())

    def connexion_qui_tape_le_mot_de_passe(ctx):
        ctx._tp_mot_de_passe_saisi = True   # le binding du DOM a vu la saisie du HARNAIS

    monkeypatch.setattr(odoo_login, "playwright_login", connexion_qui_tape_le_mot_de_passe)

    H.playwright_login(context)

    assert context._tp_cookies_session == frozenset({("session_id", "abc")})
    assert context._tp_mot_de_passe_saisi is False
