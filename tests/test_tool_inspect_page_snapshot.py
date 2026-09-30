"""Tool `inspect_page_snapshot` (lot 09, C9) — connecteur factice, même motif que
`test_tool_inspect_odoo_view.py`. La preuve avec un vrai Chromium vit dans
`test_elements_interactifs_visibles.py` (la fonction partagée elle-même)."""

from __future__ import annotations

from types import SimpleNamespace

from testpilot.generation.tools import ToolContext, dispatch
from testpilot.generation.tools.inspect import inspect_page_snapshot

_SNAPSHOT = {
    "url": "https://exemple.test/compte",
    "elements": [
        {"role": "textbox", "nom": "E-mail", "type": "email"},
        {"role": "button", "nom": "Se connecter", "type": ""},
    ],
    "error": "",
}


def test_inspect_page_snapshot_decrit_chaque_element_observe():
    ctx = ToolContext("m", None, connector=SimpleNamespace(
        inspect_page_snapshot=lambda url: _SNAPSHOT))

    outcome = inspect_page_snapshot(ctx, "/compte")

    assert outcome.ok is True
    assert "E-mail" in outcome.observation
    assert "Se connecter" in outcome.observation
    assert "textbox" in outcome.observation


def test_inspect_page_snapshot_sans_element_le_dit_explicitement():
    ctx = ToolContext("m", None, connector=SimpleNamespace(
        inspect_page_snapshot=lambda url: {"url": url, "elements": [], "error": ""}))

    outcome = inspect_page_snapshot(ctx, "/vide")

    assert outcome.ok is True
    assert "aucun élément" in outcome.observation


def test_inspect_page_snapshot_sans_connecteur():
    ctx = ToolContext("m", None, connector=None)
    assert inspect_page_snapshot(ctx, "/compte").ok is False


def test_inspect_page_snapshot_sans_url():
    ctx = ToolContext("m", None, connector=SimpleNamespace(
        inspect_page_snapshot=lambda url: _SNAPSHOT))
    assert inspect_page_snapshot(ctx, "").ok is False


def test_inspect_page_snapshot_relaie_l_erreur_de_perception():
    ctx = ToolContext("m", None, connector=SimpleNamespace(
        inspect_page_snapshot=lambda url: {"url": "", "elements": [], "error": "page fermée"}))

    outcome = inspect_page_snapshot(ctx, "/compte")

    assert outcome.ok is False
    assert "page fermée" in outcome.observation


def test_inspect_page_snapshot_est_route_par_dispatch():
    ctx = ToolContext("m", None, connector=SimpleNamespace(
        inspect_page_snapshot=lambda url: _SNAPSHOT))

    outcome = dispatch("inspect_page_snapshot", {"page_url": "/compte"}, ctx)

    assert outcome.ok is True
    assert "Se connecter" in outcome.observation
