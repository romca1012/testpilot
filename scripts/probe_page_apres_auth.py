import sys, types
from pathlib import Path
sys.path.insert(0, str(Path("src").resolve()))
sys.path.insert(0, str(Path("behave_runtime/steps_library").resolve()))
from playwright.sync_api import sync_playwright
from testpilot import config
import _base_helpers as H

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = types.SimpleNamespace(page=b.new_page(), odoo_url=config.ODOO_URL,
        odoo_db=config.ODOO_DB, odoo_user=config.ODOO_USER, odoo_password=config.ODOO_PASSWORD)
    H.playwright_login(ctx)
    print("=== APRES playwright_login (ce que fait le step partage d'auth) ===")
    print("  url :", ctx.page.url)
    tab = ctx.page.get_by_role("tab", name="Ordinateurs")
    print("  onglet 'Ordinateurs' present ici ?", tab.count())
    print()
    print("=== APRES navigation explicite vers /myservices ===")
    ctx.page.goto(f"{config.ODOO_URL}/myservices"); ctx.page.wait_for_load_state("networkidle")
    print("  url :", ctx.page.url)
    print("  onglet 'Ordinateurs' present ici ?", ctx.page.get_by_role("tab", name="Ordinateurs").count())
    b.close()
