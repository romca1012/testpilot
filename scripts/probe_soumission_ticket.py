"""Diagnostic AVEC PREUVE : le ticket non créé (compteur 26216 attendu / 26215 obtenu) vient-il
(1) d'un formulaire généré incomplet / jamais soumis (défaut du TEST), ou (2) d'un vrai
comportement défaillant de l'application à la soumission (défaut APPLICATIF) ?

On regarde la RÉPONSE HTTP/Odoo réelle, pas le compteur avant/après :
  A. on réplique le parcours du test jusqu'au formulaire, on remplit `name` + `types_demandes` ;
  B. on ATTEND comme le fait le test (`wait_form_submission` ne fait qu'attendre) → un POST de
     soumission part-il TOUT SEUL ? (le test ne clique aucun bouton Envoyer) ;
  C. puis on clique nous-mêmes le bouton d'envoi et on capture le POST + la réponse d'Odoo
     (statut, redirection, erreur de validation) ;
  D. on interroge odoorpc : un ticket a-t-il été créé ?

Marqueur distinctif `PROBE-SUBMIT-DIAG` + suppression du ticket créé en fin (ne pas polluer).
Usage : PYTHONUTF8=1 python scripts/probe_soumission_ticket.py
"""
import sys, time, types
from pathlib import Path
sys.path.insert(0, str(Path("src").resolve()))
sys.path.insert(0, str(Path("behave_runtime/steps_library").resolve()))
from playwright.sync_api import sync_playwright
from testpilot import config

MARQUEUR = f"PROBE-SUBMIT-DIAG {int(time.time())}"
POSTS = []   # (méthode, url, statut) des requêtes non-GET


def rpc():
    import odoorpc
    o = odoorpc.ODOO("localhost", protocol="jsonrpc", port=10017)
    o.login(config.ODOO_DB, config.ODOO_USER, config.ODOO_PASSWORD)
    return o


def login(page):
    page.goto(f"{config.ODOO_URL}/web/login?db={config.ODOO_DB}", wait_until="domcontentloaded")
    page.wait_for_selector("input[name='login']", state="attached", timeout=15000)
    page.locator("input[name='login']").fill(config.ODOO_USER, force=True)
    page.locator("input[name='password']").fill(config.ODOO_PASSWORD, force=True)
    page.locator("input[name='password']").press("Enter")
    page.wait_for_url(lambda u: "/web/login" not in u, timeout=15000)


def clic(page, selecteurs, quoi, timeout=8000):
    for s in selecteurs:
        try:
            page.locator(s).first.click(timeout=timeout // len(selecteurs) + 1500)
            return True
        except Exception:
            continue
    print(f"   ⚠️ {quoi} introuvable ({page.url})")
    return False


def main():
    o = rpc()
    modele = o.env["helpdesk.ticket"]
    n0 = modele.search_count([])
    print(f"tickets helpdesk au départ : {n0}")

    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page()
        page.on("response", lambda r: POSTS.append((r.request.method, r.url, r.status))
                if r.request.method != "GET" else None)

        login(page)
        print("A. Parcours jusqu'au formulaire (comme le test) …")
        page.goto(f"{config.ODOO_URL}/myservices", wait_until="domcontentloaded")
        clic(page, ["[role='tab']:has-text('Ordinateurs')", "a:has-text('Ordinateurs')"], "onglet Ordinateurs")
        page.wait_for_timeout(800)
        clic(page, ["a:has-text('PC Portable HP')"], "produit PC Portable HP")
        page.wait_for_timeout(800)
        clic(page, [".btn-Demander", ":is(button,a):has-text('Demander')"], "bouton Demander")
        page.wait_for_load_state("domcontentloaded")
        print("   page du formulaire :", page.url)

        # Remplissage EXACT du test : name + types_demandes (rien d'autre).
        rempli = []
        for name, val in [("name", MARQUEUR), ("types_demandes", "nouvel_entrant")]:
            loc = page.locator(f"[name='{name}']")
            if loc.count() > 0:
                try:
                    if page.locator(f"select[name='{name}']").count() > 0:
                        page.locator(f"select[name='{name}']").first.select_option("nouvel_entrant")
                    else:
                        loc.first.fill(val, force=True)
                    rempli.append(name)
                except Exception as e:
                    print(f"   ⚠️ remplissage {name} : {e}")
        print("   champs remplis :", rempli)

        # Quels champs le formulaire exige-t-il ? (required non remplis = rejet silencieux probable)
        requis = page.eval_on_selector_all(
            "form [required], form [name][data-required], form .o_website_form_required input",
            "els => els.map(e => e.getAttribute('name')).filter(Boolean)")
        print("   champs REQUIS du formulaire :", sorted(set(requis)) or "(aucun détecté)")

        # B. On ATTEND comme le test — un POST de soumission part-il tout seul ?
        posts_avant = len(POSTS)
        page.wait_for_timeout(2500)
        n_apres_attente = modele.search_count([])
        posts_pendant_attente = POSTS[posts_avant:]
        print("\nB. APRÈS la seule attente (ce que fait le test) :")
        print("   POST partis pendant l'attente :", posts_pendant_attente or "AUCUN")
        print("   tickets créés par la seule attente :", n_apres_attente - n0)

        # C. On clique NOUS-MÊMES le bouton d'envoi et on capture la réponse.
        print("\nC. Clic RÉEL sur le bouton d'envoi :")
        boutons = page.eval_on_selector_all(
            "button, input[type=submit], a.btn",
            "els => els.map(e => (e.innerText||e.value||'').trim()).filter(Boolean)")
        print("   boutons présents sur le formulaire :", boutons[:12])
        posts_avant = len(POSTS)
        envoye = clic(page, ["button[type=submit]", ".s_website_form_send",
                             "button:has-text('Envoyer')", "a:has-text('Envoyer')",
                             "button:has-text('Soumettre')", "input[type=submit]"], "bouton Envoyer")
        page.wait_for_timeout(3000)
        posts_apres_clic = POSTS[posts_avant:]
        print("   POST partis après le clic Envoyer :")
        for m, u, s in posts_apres_clic:
            print(f"      {m} {s}  {u[:90]}")
        # Erreur de validation affichée ?
        err = page.eval_on_selector_all(
            ".o_website_form_error, .has-error, .alert-danger, .o_notification.border-danger, [class*='error']",
            "els => els.map(e => (e.innerText||'').trim()).filter(Boolean)")
        print("   messages d'erreur à l'écran :", [e[:120] for e in err][:6] or "AUCUN")
        print("   URL après envoi :", page.url)

        b.close()

    # D. Un ticket a-t-il été créé (RPC) ?
    time.sleep(1)
    n_final = o.env["helpdesk.ticket"].search_count([])
    crees = o.env["helpdesk.ticket"].search([("name", "like", "PROBE-SUBMIT-DIAG%")])
    print("\nD. VÉRIFICATION RPC :")
    print(f"   tickets au total : {n0} → {n_final}  (delta {n_final - n0})")
    print(f"   tickets à mon marqueur : {crees}")

    # ---- Nettoyage + verdict ----
    if crees:
        o.env["helpdesk.ticket"].browse(crees).unlink()
        print(f"   (nettoyé : {len(crees)} ticket(s) de sonde supprimé(s))")

    print("\n" + "=" * 60)
    print("LECTURE :")
    print(" - Si l'attente seule ne crée rien ET un clic Envoyer crée un ticket → le TEST ne")
    print("   soumet pas (défaut 1), l'app fonctionne.")
    print(" - Si le clic Envoyer renvoie une ERREUR de validation → formulaire incomplet (défaut 1).")
    print(" - Si le clic Envoyer réussit SANS créer de ticket → défaut APPLICATIF (défaut 2).")


if __name__ == "__main__":
    main()
