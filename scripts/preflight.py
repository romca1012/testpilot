"""Contrôles locaux sans effet de bord avant de démarrer TestPilot en production."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from testpilot import config
from testpilot.store.db import get_initialized_db


def verifier(*, navigateur: bool = False) -> dict:
    config.validate_production()
    controles = {}

    conn = get_initialized_db()
    try:
        conn.execute("SELECT 1").fetchone()
        controles["database"] = "ok"
    finally:
        conn.close()

    data_dir = Path(config.DATA_DIR)
    data_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=".preflight-", dir=data_dir, delete=True):
        controles["data_directory"] = "ok"

    if navigateur:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            browser.close()
        controles["chromium"] = "ok"
    else:
        controles["chromium"] = "non vérifié (ajouter --browser)"

    controles["production_configuration"] = "ok"
    return controles


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", action="store_true", help="lance réellement Chromium")
    args = parser.parse_args(argv)
    try:
        resultat = verifier(navigateur=args.browser)
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": "ok", "checks": resultat}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
