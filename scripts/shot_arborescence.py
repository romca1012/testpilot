"""Preuve À L'ÉCRAN de la navigation en arborescence (chantier 1).

Un test de composant ne prouve pas qu'un utilisateur voit la bonne chose (§8.8). Ce script pilote
la vraie SPA servie par l'API et capture les trois surfaces de l'explorateur :
  1. la vue Modules (première vue du projet) ;
  2. un module ouvert (ses cas) ;
  3. un cas ouvert dans le panneau droit, l'arbre restant visible à gauche.

Prérequis : `python -m uvicorn testpilot.api.app:app --port 8011` (front buildé).
Usage : PYTHONUTF8=1 python scripts/shot_arborescence.py
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
        page = browser.new_page(viewport={"width": 1600, "height": 1100})

        # 1. Première vue du projet = les MODULES.
        page.goto(f"{BASE}/projects/{PID}/cases", wait_until="networkidle")
        page.wait_for_timeout(1200)
        print("=" * 72)
        print("1. Première vue du projet")
        body = page.inner_text("body").lower()
        print("   titre « Modules »            :", "modules" in body)
        print("   arbre « Structure »          :", "structure" in body)
        print("   porte vers « Tous les cas »  :", "tous les cas" in body)
        page.screenshot(path=str(OUT / "arbre_1_modules.png"), full_page=True)

        # 2. Tout déplier → les cas apparaissent DANS l'arbre.
        page.click("text=Tout déplier")
        page.wait_for_timeout(600)
        # ⚠️ `inner_text` rend le texte AFFICHÉ : les libellés en `uppercase` CSS remontent en
        # majuscules. On compare donc sans casse, sinon on lit des faux négatifs.
        texte = page.inner_text("body").lower()
        print()
        print("2. Arbre déplié")
        print("   cas visibles dans l'arbre    :", "validation champ requis" in texte)
        print("   bascule en « Tout replier »  :", "tout replier" in texte)
        page.screenshot(path=str(OUT / "arbre_2_deplie.png"), full_page=True)

        # 3. Clic sur un cas DANS l'arbre → détail à droite, arbre toujours là.
        page.click("aside >> text=Validation champ requis")
        page.wait_for_timeout(1500)
        # ⚠️ `inner_text` rend le texte AFFICHÉ : les libellés en `uppercase` CSS remontent en
        # majuscules. On compare donc sans casse, sinon on lit des faux négatifs.
        texte = page.inner_text("body").lower()
        print()
        print("3. Cas ouvert depuis l'arbre")
        print("   URL                          :", page.url)
        print("   détail du cas affiché        :", "dernier résultat" in texte)
        print("   arbre TOUJOURS visible       :", "structure" in texte)
        page.screenshot(path=str(OUT / "arbre_3_cas_ouvert.png"), full_page=True)

        print()
        print("captures ->", OUT)
        browser.close()


if __name__ == "__main__":
    main()
