"""Preuve À L'ÉCRAN de l'arbitrage humain des diagnostics (décision 0013).

Vérifie ce qui compte vraiment :
  1. l'onglet Confirmations existe, avec le compteur de la file ;
  2. la machine et l'humain sont montrés CÔTE À CÔTE (jamais l'un à la place de l'autre) ;
  3. « Bug dans l'application » porte une infobulle qui dit que c'est une DÉDUCTION ;
  4. un `not_required` (irrévocable jusqu'ici) est bien arbitrable via « Tous ».

⚠️ N'ARBITRE RIEN : trancher un diagnostic est un jugement humain, pas quelque chose que l'agent
s'accorde à lui-même. On regarde l'écran, on ne clique pas « Confirmer ».

Prérequis : `python -m uvicorn testpilot.api.app:app --port 8011` (front buildé).
Usage : PYTHONUTF8=1 python scripts/shot_confirmations.py
"""

from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://localhost:8011"
PID = 1
OUT = Path("data/_shots")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1500, "height": 1100})

        page.goto(f"{BASE}/projects/{PID}/confirmations", wait_until="networkidle")
        page.wait_for_timeout(1500)
        body = page.inner_text("body").lower()

        print("=" * 72)
        print("1. L'onglet et la file")
        print("   onglet « Confirmations »      :", "confirmations" in body)
        print("   titre de la page              :", "origine des défauts" in body)

        print()
        print("2. Machine et humain CÔTE À CÔTE")
        print("   « la machine a déduit »       :", "la machine a déduit" in body)
        print("   cause lisible (pas d'enum)    :", "assertion" not in page.inner_text("body")
              or "cause :" in body)

        print()
        print("3. « Bug dans l'application » est-il présenté comme une DÉDUCTION ?")
        infobulles = page.locator('[role="tooltip"]').all_inner_texts()
        deduction = [t for t in infobulles if "éduit de l'échec" in t or "à confirmer ou infirmer" in t.lower()]
        print("   infobulle « déduit, pas constaté » :", bool(deduction))
        if deduction:
            print("      >", deduction[0][:110])

        page.screenshot(path=str(OUT / "confirmations_pending.png"), full_page=True)

        # 4. Un not_required est-il arbitrable ? (le cas 6, irrévocable jusqu'ici)
        page.click("text=Tous")
        page.wait_for_timeout(1200)
        body_all = page.inner_text("body")
        print()
        print("4. Un « vrai bug » (not_required) est-il infirmable ?")
        print("   « Achat véhicule » dans la file :", "Achat véhicule" in body_all)
        print("   bouton « Trancher… »            :", page.locator("text=Trancher").count())
        page.screenshot(path=str(OUT / "confirmations_all.png"), full_page=True)

        # On OUVRE le formulaire pour le montrer — sans jamais soumettre.
        if page.locator("text=Trancher").count():
            page.locator("text=Trancher").first.click()
            page.wait_for_timeout(600)
            txt = page.inner_text("body")
            print()
            print("5. Le formulaire dit-il ce qu'il fait ?")
            print("   « s'ajoute au diagnostic »      :", "s'ajoute au diagnostic" in txt)
            print("   « ne change pas le résultat »   :", "ne change pas le résultat" in txt)
            page.screenshot(path=str(OUT / "confirmations_form.png"), full_page=True)

        browser.close()
        print()
        print("captures ->", OUT, "(aucun arbitrage soumis)")


if __name__ == "__main__":
    main()
