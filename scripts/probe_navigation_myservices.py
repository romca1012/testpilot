"""Repérage ciblé (lecture seule, aucun LLM) : la route /myservices atterrit-elle où on l'attend,
et « Ordinateurs » y est-il cliquable ?

Objectif : CONFIRMER ou INFIRMER l'hypothèse « /myservices n'atterrit pas où on croit » — pas réparer.
- piste 1 : après goto, l'URL n'est PAS /myservices (redirection) → mauvais atterrissage.
- piste 2 : l'URL EST /myservices mais aucun sélecteur d'onglet ne trouve « Ordinateurs » → bonne
            page, mauvais sélecteur (l'onglet n'est pas un role=tab).

Rejouable : PYTHONUTF8=1 python scripts/probe_navigation_myservices.py
"""
import sys, types, json
from pathlib import Path
sys.path.insert(0, str(Path("src").resolve()))
sys.path.insert(0, str(Path("behave_runtime/steps_library").resolve()))
from playwright.sync_api import sync_playwright
from testpilot import config
import _base_helpers as H  # le VRAI helper de login des tests (fidélité au harnais réel)

CIBLE = "Ordinateurs"

# Les sélecteurs que le step généré essaie, DANS L'ORDRE (cf. steps_content v10 : step_click_tab_portail).
SELECTEURS_CSS = [
    ".nav-link:has-text('{t}')",
    ".nav-item a:has-text('{t}')",
    "[role='tab']:has-text('{t}')",
    "li a:has-text('{t}')",
    "a:has-text('{t}')",
    "button:has-text('{t}')",
]


def etat(page):
    print("  url          :", page.url)
    print("  title        :", page.title())
    print(f"  [role=tab] '{CIBLE}' :", page.get_by_role("tab", name=CIBLE).count(), "(le sélecteur qui a TIMEOUT en exec 30)")
    for sel in SELECTEURS_CSS:
        s = sel.format(t=CIBLE)
        try:
            print(f"  {s:38} :", page.locator(s).count())
        except Exception as e:
            print(f"  {s:38} : erreur {e}")
    try:
        print(f"  get_by_text('{CIBLE}', exact) :", page.get_by_text(CIBLE, exact=True).count())
    except Exception as e:
        print("  get_by_text : erreur", e)


with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = types.SimpleNamespace(page=b.new_page(), odoo_url=config.ODOO_URL,
        odoo_db=config.ODOO_DB, odoo_user=config.ODOO_USER, odoo_password=config.ODOO_PASSWORD)

    H.playwright_login(ctx)
    print("=== 1) APRÈS playwright_login (là où le step d'auth dépose) ===")
    etat(ctx.page)

    print("\n=== 2) APRÈS goto explicite vers /myservices (exactement ce que fait la v10) ===")
    # v10 : step_navigate_portail -> page.goto(url, wait_until="networkidle", timeout=30000)
    try:
        ctx.page.goto(f"{config.ODOO_URL}/myservices", wait_until="networkidle", timeout=30000)
    except Exception as e:
        print("  (networkidle non atteint —", str(e).splitlines()[0], "— on inspecte l'état courant)")
    etat(ctx.page)
    url_finale = ctx.page.url

    print("\n=== 3) Ce que l'annuaire dit de « Ordinateurs » sur /myservices ===")
    modele = json.load(open("data/domain/odoo.json", encoding="utf-8"))
    ms = modele["pages"].get("/myservices", {})
    liens = [l for l in ms.get("liens", []) if CIBLE.lower() in str(l.get("text", "")).lower()]
    print("  liens dont le texte contient 'Ordinateur' :", json.dumps(liens, ensure_ascii=False) or "AUCUN")

    print("\n=== VERDICT ===")
    if "/myservices" not in url_finale:
        print(f"  PISTE 1 : goto /myservices a atterri sur {url_finale} → mauvais atterrissage.")
    else:
        trouve = any(ctx.page.locator(s.format(t=CIBLE)).count() > 0 for s in SELECTEURS_CSS)
        if trouve:
            print("  NI l'une NI l'autre au niveau navigation : bonne page ET un sélecteur CSS trouve l'onglet.")
            print("  → le timeout d'exec 30 vient d'ailleurs (timing/ordre des sélecteurs), à creuser.")
        else:
            print("  PISTE 2 : on est bien sur /myservices mais AUCUN sélecteur ne trouve l'onglet")
            print("  → bonne page, mauvais sélecteur (l'onglet n'est pas ce que le step cherche).")
    b.close()
