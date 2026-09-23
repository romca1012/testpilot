"""Connexion UI Odoo partagée par génération et exécution."""
import re


def playwright_login(context):
    """Connexion Odoo — `/web/login`, robuste face à un formulaire replié derrière un SSO.

    ⚠️ **Bug réel mesuré (instance Sapian, 2026-09-17).** Le template `web.login` STANDARD
    d'Odoo (`addons/web/views/webclient_templates.xml`) rend `.field-login` visible par défaut,
    même avec des fournisseurs OAuth configurés (`o_login_auth`) — vérifié sur la source Odoo
    17.0 officielle avant de généraliser quoi que ce soit, pas supposé. Certaines instances
    personnalisent par-dessus : Sapian masque `.field-login` en CSS et exige un clic sur un
    <details>/<summary> ("Connexion externe par email") pour l'ouvrir — SANS que cliquer ce
    <summary> suffise réellement (le <details> s'ouvre, mais la classe qui montre le champ,
    `.oe_login_form.sapian-open`, n'apparaît qu'en la posant directement).

    Deux formulations différentes du même problème existent donc dans la nature (Odoo nu :
    rien à faire ; Sapian : un clic ET une classe). **Motif officiel Playwright pour "l'un OU
    l'autre selon le site, sans convention fixe"** (doc Locators, `.or_()`) : attendre le champ
    de connexion OU un indice de repli SSO, plutôt que de figer une seule hypothèse.

    ⚠️ **Marges relevées après mesure réelle de la variance de l'instance d'essai** (Sapian,
    2026-09-23 — instance `dev.odoo.com`, publique/partagée, performance hors de notre contrôle).
    Un navigateur VRAIMENT neuf (jamais réutilisé, comme chaque scénario de campagne en lance
    un) a mis 16,83 s pour la connexion COMPLÈTE lors d'une mesure, contre 2,06 s sur une autre —
    un facteur ×8 mesuré, pas supposé. Les anciennes marges (15 s / 5 s) laissaient trop peu de
    place à cette variance ; relevées avec une marge confortable au-dessus du pire cas observé.
    """
    login_url = f"{context.odoo_url.rstrip('/')}/web/login?db={context.odoo_db}"
    context.page.goto(login_url, wait_until="domcontentloaded")

    login_field = context.page.locator("input[name='login']")
    # Texte volontairement large (FR/EN, plusieurs formulations) — jamais le texte EXACT d'une
    # seule instance : c'est justement ce qui a manqué la première fois.
    repli_sso = context.page.get_by_text(re.compile(
        r"connexion.*email|login.*email|external.*email|par\s*email", re.IGNORECASE))
    # `.wait_for()` sur le résultat de `.or_()`, jamais `expect(...)` : `expect()` exige un VRAI
    # objet Playwright (il lève sur tout le reste, y compris un bouchon de test) — `.wait_for()`
    # est une méthode de Locator ordinaire, compatible avec les deux.
    login_field.or_(repli_sso).first.wait_for(state="visible", timeout=25000)

    if not login_field.is_visible():
        try:
            repli_sso.first.click(timeout=10000)
        except Exception:
            pass
        # Best-effort, sans condition sur le texte cliqué : une classe `sapian-open` absente du
        # DOM d'une autre instance ne fait simplement rien (`querySelectorAll` sur 0 élément).
        try:
            context.page.evaluate(
                "document.querySelectorAll('.oe_login_form')"
                ".forEach(f => f.classList.add('sapian-open'))")
        except Exception:
            pass

    # `state="visible"`, pas `"attached"` : un champ attaché mais masqué se faisait remplir par
    # `force=True` en pure perte (bug d'origine, avant ce correctif).
    login_field.wait_for(state="visible", timeout=25000)
    context.page.locator("input[name='login']").fill(context.odoo_user, force=True)
    context.page.locator("input[name='password']").fill(context.odoo_password, force=True)
    context.page.locator("input[name='password']").press("Enter")
    # Post-condition CONCRÈTE d'un login réussi : on a QUITTÉ la page de login (session établie).
    # Remplace `networkidle`, que le bus long-polling d'Odoo ne stabilise jamais.
    context.page.wait_for_url(lambda url: "/web/login" not in url, timeout=25000)

