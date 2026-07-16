"""Les 5 « Non conforme » du cas 6 sont-ils de VRAIS bugs applicatifs, ou des tests fautifs ?

Le cas TOURNE maintenant (0012 a levé la barrière technique) et remonte 4 « non conforme » + 1
« indéterminable ». Un « non conforme » se remonte DIRECTEMENT au métier (§4.4) : il faut donc
qu'il soit vrai. Un faux « non conforme » ferait chercher un bug qui n'existe pas.

Trois familles d'échec à départager :
  A. [NOMINAL] / [LIMITE] : « le ticket n'a pas été créé » (26205 au lieu de 26206) ;
  B. [ERREUR] dénomination / agence : « le blocage JS toggleSubmitButton() ne fonctionne pas » ;
  C. [ERREUR] accès refusé : « le formulaire est rendu MALGRÉ l'absence du rôle ».

Hypothèse à tester pour C : `admin` est SUPER-UTILISATEUR Odoo — il contourne les règles d'accès
quel que soit son rôle. Le scénario serait alors intestable avec ce compte, et son « échec »
ne dirait rien de l'application.

Usage : PYTHONUTF8=1 python scripts/probe_achat_vehicule_nonconforme.py
"""

from urllib.parse import urlparse

import odoorpc
from playwright.sync_api import sync_playwright

from testpilot import config
from testpilot.api.services.run_service import resolve_connection
from testpilot.store.db import get_initialized_db

CASE_ID = 6
SERVICE_ID = 114


def main() -> None:
    conn = get_initialized_db(config.DB_PATH)
    cx = resolve_connection(conn, CASE_ID)
    conn.close()
    url = cx.get("ODOO_URL", "http://localhost:10017").rstrip("/")
    db, user, pwd = cx.get("ODOO_DB"), cx.get("ODOO_USER"), cx.get("ODOO_PASSWORD")

    p = urlparse(url)
    odoo = odoorpc.ODOO(p.hostname or "localhost", protocol="jsonrpc", port=p.port or 8069)
    odoo.login(db, user, pwd)

    print("=" * 72)
    print("C. LE COMPTE DE TEST CONTOURNE-T-IL LES RÈGLES D'ACCÈS ?")
    uid = odoo.env.uid
    u = odoo.env["res.users"].browse(uid)
    print(f"   utilisateur : {u.login} (uid={uid})")
    # uid=1 = superuser historique ; uid=2 = admin, membre de base.group_system.
    groupes = [g.full_name for g in u.groups_id]
    admin_sys = any("Settings" in g or "Administration" in g or "group_system" in g
                    for g in groupes)
    print(f"   uid == 1 (superuser)        : {uid == 1}")
    print(f"   membre d'un groupe Admin/Settings : {admin_sys}")
    interessants = [g for g in groupes if "Settings" in g or "Access" in g or "Administration" in g]
    print(f"   groupes d'admin détenus     : {interessants or 'aucun'}")

    print()
    print("=" * 72)
    print("B. LE BLOCAGE JS EXISTE-T-IL SUR LA PAGE ?")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"{url}/web/login?db={db}")
        page.wait_for_selector("input[name='login']", state="attached", timeout=15000)
        page.locator("input[name='login']").fill(user, force=True)
        page.locator("input[name='password']").fill(pwd, force=True)
        page.locator("input[name='password']").press("Enter")
        page.wait_for_load_state("networkidle")

        page.goto(f"{url}/achat_vehicule/{SERVICE_ID}", wait_until="networkidle")
        page.wait_for_timeout(800)
        print("   URL          :", page.url)
        contenu = page.content()
        print("   toggleSubmitButton présent dans le HTML :", "toggleSubmitButton" in contenu)

        # Le bouton de soumission est-il désactivé au chargement (formulaire vide) ?
        bouton = page.locator("button[type='submit'], input[type='submit'], .s_website_form_send")
        print("   boutons de soumission trouvés :", bouton.count())
        if bouton.count():
            b = bouton.first
            print("   désactivé au chargement (form vide) :",
                  b.is_disabled() if b.is_visible() else "(non visible)")

        # On dépasse volontairement les 25 caractères : l'app bloque-t-elle ?
        champ = page.locator("[name='denomination']")
        if champ.count():
            champ.first.fill("X" * 40, force=True)
            page.wait_for_timeout(600)
            trop_long = page.eval_on_selector(
                "[name='denomination']",
                "e => ({valeur: e.value.length, maxlength: e.getAttribute('maxlength')})")
            print("   après saisie de 40 car. :", trop_long)
            if bouton.count() and bouton.first.is_visible():
                print("   bouton désactivé après saisie trop longue :", bouton.first.is_disabled())

        page.screenshot(path="data/_shots/probe_achat_nonconforme.png", full_page=True)
        browser.close()

    print()
    print("=" * 72)
    print("LECTURE")
    print("   C : si le compte est admin/superuser -> il contourne _get_access_dei() :")
    print("       le scénario « accès refusé » est INTESTABLE avec ce compte (test à réparer,")
    print("       pas un bug applicatif).")
    print("   B : si maxlength=25 est posé par le HTML, le navigateur TRONQUE la saisie —")
    print("       le test ne peut jamais dépasser 25 car., donc le blocage n'a pas à s'activer :")
    print("       le scénario teste une situation que le navigateur rend impossible.")


if __name__ == "__main__":
    main()
