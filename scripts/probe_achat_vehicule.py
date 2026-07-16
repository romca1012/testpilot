"""Sonde : que rend RÉELLEMENT /achat_vehicule/<id> ? Vrai bug, test à réparer, ou prérequis absent ?

Les 5 scénarios du cas importé échouent, et le verdict dit « Rôle/permission manquant ». ⚠️ Ce
verdict ne prouve RIEN par lui-même : le message d'assertion contient le mot « role », et la
taxonomie classe par mots-clés — même piège qu'en `0007` (« timeout » suffisait à produire
`wrong_field_name`). Il faut regarder la page.

Contradiction à trancher, relevée dans les résultats :
  - 4 scénarios : « le formulaire n'est pas rendu » ;
  - 1 scénario  : attend une redirection vers /home et constate qu'on est RESTÉ sur l'URL.
Donc la page ne redirige pas ET n'affiche pas le formulaire. Que renvoie-t-elle ?

Usage : PYTHONUTF8=1 python scripts/probe_achat_vehicule.py
"""

from playwright.sync_api import sync_playwright

from testpilot import config
from testpilot.api.services.run_service import resolve_connection
from testpilot.store.db import get_initialized_db

CASE_ID = 5
SERVICE_ID = 114


def main() -> None:
    conn = get_initialized_db(config.DB_PATH)
    cx = resolve_connection(conn, CASE_ID)
    conn.close()

    url = cx.get("ODOO_URL", "http://localhost:10017")
    db = cx.get("ODOO_DB", "odoo_test")
    user = cx.get("ODOO_USER", "admin")
    pwd = cx.get("ODOO_PASSWORD", "admin")

    # ── 1. Côté RPC : les prérequis existent-ils seulement ? ─────────────────
    import odoorpc
    from urllib.parse import urlparse
    p = urlparse(url)
    odoo = odoorpc.ODOO(p.hostname or "localhost", protocol="jsonrpc",
                        port=p.port or 8069)
    odoo.login(db, user, pwd)
    print("=" * 72)
    print("1. PRÉREQUIS (RPC)")

    mods = odoo.env["ir.module.module"].search_read(
        [("name", "=", "custom_website")], ["name", "state"])
    print("   module custom_website :", mods or "ABSENT DE L'INSTANCE")

    try:
        tmpl = odoo.env["product.template"].browse(SERVICE_ID)
        print(f"   product.template {SERVICE_ID} :", repr(tmpl.name))
    except Exception as exc:
        print(f"   product.template {SERVICE_ID} : INTROUVABLE ({exc})")

    uid = odoo.env.uid
    u = odoo.env["res.users"].browse(uid)
    print("   utilisateur du test  :", u.login, f"(uid={uid})")
    try:
        roles = u.employee_front_role_ids
        noms = [(r.name, getattr(r, "front_role", "?")) for r in roles]
        print("   employee_front_role_ids :", noms or "AUCUN RÔLE")
        a_le_role = any(fr == "group_expert_metier" for _, fr in noms)
        print("   a group_expert_metier   :", a_le_role)
    except Exception as exc:
        print("   employee_front_role_ids : champ absent ou illisible :", exc)

    # ── 2. Côté HTTP : ce que la page renvoie vraiment ──────────────────────
    print()
    print("=" * 72)
    print("2. LA PAGE (navigateur, comme le test)")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"{url.rstrip('/')}/web/login?db={db}")
        page.wait_for_selector("input[name='login']", state="attached", timeout=15000)
        page.locator("input[name='login']").fill(user, force=True)
        page.locator("input[name='password']").fill(pwd, force=True)
        page.locator("input[name='password']").press("Enter")
        page.wait_for_load_state("networkidle")

        cible = f"{url.rstrip('/')}/achat_vehicule/{SERVICE_ID}"
        resp = page.goto(cible, wait_until="domcontentloaded")
        page.wait_for_timeout(1200)
        print("   URL demandée :", cible)
        print("   HTTP         :", resp.status if resp else "?")
        print("   URL finale   :", page.url)
        print("   redirigé vers /home ?", "/home" in page.url)
        print("   titre        :", repr(page.title()[:70]))

        formulaire = page.locator("form").count()
        champs = page.eval_on_selector_all(
            "input[name], select[name], textarea[name]",
            "els => els.map(e => e.getAttribute('name'))")
        print("   <form> sur la page :", formulaire)
        print("   champs nommés      :", champs[:12] or "AUCUN")

        texte = page.inner_text("body")[:400].replace("\n", " | ")
        print("   texte visible      :", texte[:300])
        page.screenshot(path="data/_shots/probe_achat_vehicule.png", full_page=True)
        browser.close()

    print()
    print("=" * 72)
    print("LECTURE")
    print("   • redirigé vers /home        -> le rôle manque VRAIMENT (test à réparer : prérequis)")
    print("   • page d'erreur / 404        -> la route ou le service_id n'existe pas ici")
    print("   • formulaire rendu           -> le step de détection du test est fautif")
    print("   • page vide sans redirection -> comportement applicatif à qualifier (vrai bug ?)")


if __name__ == "__main__":
    main()
