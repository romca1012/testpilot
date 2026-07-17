"""Sonde : les OPTIONS reelles d'un <select> du formulaire. ZERO appel LLM (decision 0019).

    PYTHONUTF8=1 python scripts/probe_select_options.py

Reproduit le diagnostic MANUEL de 0019 : `select_option(value="new")` expire au bout de 30 s en
disant `waiting for locator("select[name='types_demandes']")` -- ce qui donne a croire que le
SELECT est introuvable. Il ne l'est pas : il est la, visible, active. Playwright attend en realite
l'OPTION `value="new"`, qui n'existe pas (les seules valeurs sont `nouvel_entrant` et
`remplacement_materiel`). Toute la chaine a cru le message : la taxonomie a classe
`wrong_field_name`, et l'agent a repare un selecteur qui n'avait aucun probleme.

Utilise le VRAI helper de la bibliotheque partagee plutot que de reinventer l'auth --
c'est exactement l'erreur de 0017, et mon premier jet de sonde l'a rejouee.
"""
import sys, types
from pathlib import Path
sys.path.insert(0, str(Path("src").resolve()))
sys.path.insert(0, str(Path("behave_runtime/steps_library").resolve()))
from playwright.sync_api import sync_playwright
from testpilot import config
import _base_helpers as H

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = types.SimpleNamespace(
        page=b.new_page(), odoo_url=config.ODOO_URL, odoo_db=config.ODOO_DB,
        odoo_user=config.ODOO_USER, odoo_password=config.ODOO_PASSWORD)
    H.playwright_login(ctx)
    print("apres login, url :", ctx.page.url)

    ctx.page.goto(f"{config.ODOO_URL}/formulaire/1")
    ctx.page.wait_for_load_state("networkidle")
    print("url formulaire   :", ctx.page.url)

    sel = ctx.page.locator("select[name='types_demandes']")
    print("select count     :", sel.count())
    if sel.count():
        print("visible          :", sel.first.is_visible())
        print("enabled          :", sel.first.is_enabled())
        opts = sel.first.evaluate(
            "el => Array.from(el.options).map(o => [o.value, o.text.trim()])")
        print("OPTIONS REELLES (value | texte) :")
        for v, t in opts:
            print(f"   {v!r:12} | {t!r}")
    b.close()
