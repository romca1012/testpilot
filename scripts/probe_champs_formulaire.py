"""Sonde : quels sont les VRAIS noms techniques des champs du formulaire sous test ?

Question tranchée par ce script : « Raison de la demande » échoue-t-elle parce que le champ
n'existe pas (→ vrai bug applicatif) ou parce qu'il existe sous un autre attribut `name`
(→ erreur de PARAMÉTRAGE du step, test_a_reparer) ? La réponse départage la classification
du §5 et conditionne le correctif de la future décision 0007.

Usage : PYTHONUTF8=1 python scripts/probe_champs_formulaire.py
"""

from playwright.sync_api import sync_playwright

from testpilot.api.services.run_service import resolve_connection
from testpilot.store.db import get_initialized_db
from testpilot import config

CASE_ID = 2
LIBELLE_ATTENDU_PAR_LAGENT = "Raison de la demande"


def main() -> None:
    conn = get_initialized_db(config.DB_PATH)
    connection = resolve_connection(conn, CASE_ID)
    conn.close()

    url = connection.get("ODOO_URL", "http://localhost:10017")
    user = connection.get("ODOO_USER", "admin")
    password = connection.get("ODOO_PASSWORD", "admin")
    print("URL projet :", url, "| user :", user)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Connexion à l'identique du harnais (_base_helpers._playwright_login) : le ?db=
        # et le force=True sont nécessaires — le champ est attaché mais non « visible ».
        db = connection.get("ODOO_DB", "odoo_test")
        page.goto(f"{url.rstrip('/')}/web/login?db={db}")
        page.wait_for_selector("input[name='login']", state="attached", timeout=15000)
        page.locator("input[name='login']").fill(user, force=True)
        page.locator("input[name='password']").fill(password, force=True)
        page.locator("input[name='password']").press("Enter")
        page.wait_for_load_state("networkidle")

        # Même parcours que le Gherkin généré.
        page.goto(f"{url}/myservices", wait_until="domcontentloaded")
        page.click("text=Ordinateurs")
        page.wait_for_timeout(1500)
        page.click("text=PC Portable HP")
        page.wait_for_timeout(1500)
        page.click("text=Demander")
        page.wait_for_timeout(2500)

        print("URL du formulaire :", page.url)
        print("=" * 72)
        print("CHAMPS RÉELS DU FORMULAIRE (attribut `name` = ce qu'attend le step) :")
        fields = page.evaluate("""() => {
            const out = [];
            document.querySelectorAll('input, textarea, select').forEach(el => {
                const name = el.getAttribute('name');
                if (!name) return;
                let label = '';
                if (el.id) {
                    const l = document.querySelector(`label[for="${el.id}"]`);
                    if (l) label = l.innerText.trim();
                }
                if (!label) {
                    const l = el.closest('div')?.querySelector('label');
                    if (l) label = l.innerText.trim();
                }
                out.push({name, tag: el.tagName.toLowerCase(),
                          type: el.getAttribute('type') || '', label,
                          visible: !!(el.offsetParent)});
            });
            return out;
        }""")
        for f in fields:
            vis = "visible" if f["visible"] else "caché  "
            print(f"   [{vis}] name={f['name']!r:28} <{f['tag']}{'/' + f['type'] if f['type'] else ''}>"
                  f"  libellé affiché : {f['label'][:40]!r}")

        print()
        print("=" * 72)
        print("VERDICT DE LA SONDE")
        names = [f["name"] for f in fields]
        print(f"   Sélecteur tenté par l'agent : [name='{LIBELLE_ATTENDU_PAR_LAGENT}']")
        print("   Existe-t-il ?               :", LIBELLE_ATTENDU_PAR_LAGENT in names)
        match = [f for f in fields if LIBELLE_ATTENDU_PAR_LAGENT.lower() in (f["label"] or "").lower()]
        if match:
            print("   Champ portant CE libellé    : name =", repr(match[0]["name"]),
                  "→ le champ EXISTE, sous un autre nom technique")
            print("   => erreur de PARAMÉTRAGE du step, pas un bug applicatif")
        else:
            print("   Aucun champ ne porte ce libellé — à examiner")

        browser.close()


if __name__ == "__main__":
    main()
