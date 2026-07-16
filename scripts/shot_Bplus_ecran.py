"""Preuve À L'ÉCRAN de la phase B+ (décision 0007) : le repli est-il VU par un humain ?

L'API peut rendre `field_fallbacks` sans que l'utilisateur le voie : un test vert ne prouve pas
qu'un utilisateur voit la bonne chose (§8.8). Ce script pilote la vraie SPA servie par l'API et
capture la page du cas 2 après le run avec correctif sidecar.

Vérifie deux surfaces, celles arbitrées par le porteur :
  - le BANDEAU sur le dernier résultat (FieldFallbackNotice) ;
  - la PASTILLE dans l'historique, uniquement sur les lignes qui portent un repli.

Prérequis : `python -m uvicorn testpilot.api.app:app --port 8011` (front buildé).
Usage : PYTHONUTF8=1 python scripts/shot_Bplus_ecran.py
"""

from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://localhost:8011"
CASE_URL = f"{BASE}/projects/1/cases/2"
OUT = Path("data/_shots")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 1600})
        page.goto(CASE_URL, wait_until="networkidle")
        page.wait_for_timeout(1500)  # laisse la SPA charger le détail du cas

        texte = page.inner_text("body")

        print("=" * 72)
        print("BANDEAU (dernier résultat)")
        for phrase in ("résolu par son libellé", "pas par son nom technique",
                       "à corriger dans le test", "renommé côté"):
            print(f"   {phrase!r:34} visible ? {phrase in texte}")

        print()
        print("PASTILLE (historique)")
        pastilles = page.locator("text=Repli de champ")
        print("   occurrences de « Repli de champ » :", pastilles.count())
        print("   (attendu : 1 — seule l'exécution avec repli doit la porter)")

        print()
        print("CONTENU DU REPLI affiché")
        for ligne in texte.splitlines():
            if "Raison de la demande" in ligne and "name=" in ligne:
                print("   >", ligne.strip()[:150])

        shot = OUT / "case2_Bplus_repli.png"
        page.screenshot(path=str(shot), full_page=True)
        print()
        print("capture ->", shot)
        browser.close()


if __name__ == "__main__":
    main()
