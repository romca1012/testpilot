"""Preuve À L'ÉCRAN du glisser-déposer des cas (décision 0009) + de la vue liste des modules.

Un test vert ne prouve pas qu'un glissement fonctionne dans un vrai navigateur (§8.8) : le drag
HTML5 dépend d'événements que seul le navigateur produit. Ce script pilote la vraie SPA servie par
l'API, exécute un vrai glisser-déposer, et vérifie que le nouvel ordre PERSISTE au rechargement.

Prérequis : `python -m uvicorn testpilot.api.app:app --port 8011` (front buildé).
Usage : PYTHONUTF8=1 python scripts/shot_reorder_cas.py
"""

from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://localhost:8011"
PID, MID = 1, 1
OUT = Path("data/_shots")


# ⚠️ Cibler les lignes de CAS par leur POIGNÉE : un `section ul > li` naïf attrape aussi les
# <li> des scénarios dépliés à l'intérieur de chaque cas (14 éléments au lieu de 2).
_LIGNES = 'li:has(> span[draggable="true"])'


def _lignes(page):
    return page.locator(_LIGNES)


def _titres(page) -> list[str]:
    n = _lignes(page).count()
    return [_lignes(page).nth(i).locator(".font-medium").first.inner_text().strip()
            for i in range(n)]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1500, "height": 1000})

        # ── Vue liste des modules ────────────────────────────────────────────
        page.goto(f"{BASE}/projects/{PID}/cases", wait_until="networkidle")
        page.wait_for_timeout(1000)
        page.click("text=Liste")
        page.wait_for_timeout(400)
        print("=" * 72)
        print("1. Vue LISTE des modules")
        print("   bascule Grille/Liste présente :", page.locator("text=Grille").count() > 0)
        print("   module listé                  :", "Demande materiel" in page.inner_text("body"))
        page.screenshot(path=str(OUT / "modules_vue_liste.png"), full_page=True)

        # ── Glisser-déposer dans la liste du module ─────────────────────────
        page.goto(f"{BASE}/projects/{PID}/modules/{MID}", wait_until="networkidle")
        page.wait_for_timeout(1000)
        avant = _titres(page)
        print()
        print("=" * 72)
        print("2. Glisser-déposer — ordre AVANT :", avant)
        if len(avant) < 2:
            print("   (moins de 2 cas : glissement sans objet)"); browser.close(); return

        poignees = page.locator('span[draggable="true"]')
        print("   poignées trouvées :", poignees.count())

        # Glisse le PREMIER cas sur le DERNIER (drag HTML5 réel, pas un appel d'API).
        poignees.nth(0).drag_to(_lignes(page).nth(len(avant) - 1))
        page.wait_for_timeout(1200)
        apres = _titres(page)
        print("   ordre APRÈS        :", apres)
        page.screenshot(path=str(OUT / "module_reorder.png"), full_page=True)

        # ── L'ordre PERSISTE-t-il ? (le seul vrai juge) ─────────────────────
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(1000)
        recharge = _titres(page)
        print()
        print("=" * 72)
        print("3. Après RECHARGEMENT :", recharge)
        print()
        print("VERDICT")
        if apres != avant and recharge == apres:
            print("   ORDRE CHANGÉ ET PERSISTÉ : le glissement écrit réellement en base.")
        elif apres == avant:
            print("   L'ordre n'a PAS changé — le glissement n'a rien déclenché.")
        else:
            print("   L'ordre a changé À L'ÉCRAN mais N'A PAS persisté → « affiché ≠ réel » (4.6).")

        # Infobulle d'honnêteté — exigence CENTRALE de 0009 : un tri manuel muet laisserait
        # croire qu'il ordonne l'exécution. `Hint` rend son texte dans [role="tooltip"]
        # (masqué par opacity, révélé au survol), pas dans un attribut `title`.
        infobulles = page.locator('[role="tooltip"]').all_inner_texts()
        honnete = [t for t in infobulles if "ordonne PAS l'exécution" in t]
        print()
        print("   infobulle « ordre de lecture, PAS d'exécution » :", bool(honnete))
        if honnete:
            print("      >", honnete[0][:120])

        browser.close()
        print()
        print("captures ->", OUT)


if __name__ == "__main__":
    main()
