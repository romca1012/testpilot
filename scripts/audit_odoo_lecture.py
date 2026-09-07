"""Sonde Odoo locale en lecture : RPC et formulaire portail, sans création métier."""

import json
from urllib.parse import urlparse

from testpilot import config
from testpilot.connectors.odoo import OdooConnector


def main():
    if urlparse(config.ODOO_URL).hostname not in {"localhost", "127.0.0.1", "host.docker.internal"}:
        raise RuntimeError("Cette sonde est réservée à la recette Docker locale")
    connector = OdooConnector.from_config()
    checks = {}
    try:
        connector.connect()
        checks["rpc_login"] = "ok"
        checks["rpc_schema_res_users"] = bool(connector.get_schema("res.users"))

        def portail():
            page = connector._ensure_page()
            page.goto(config.ODOO_URL.rstrip("/") + "/myservices")
            page.wait_for_load_state("networkidle")
            assert "/web/login" not in page.url, "Portail redirigé vers la connexion"
            assert page.locator("input[name='password']").count() == 0, "Connexion non acquise"
            assert page.locator("body").inner_text().strip(), "Page vide"
            return {"path": urlparse(page.url).path, "forms": page.locator("form").count(),
                    "links": page.locator("a[href]").count()}

        checks["portal_authenticated"] = connector._run_in_browser(portail)
        print(json.dumps({"status": "ok", "checks": checks}, ensure_ascii=False))
        return 0
    except Exception as exc:
        # Les messages réseau peuvent contenir des URL ou informations de connexion.
        print(json.dumps({"status": "failed", "checks": checks,
                          "error_type": type(exc).__name__}, ensure_ascii=False))
        return 1
    finally:
        connector.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
