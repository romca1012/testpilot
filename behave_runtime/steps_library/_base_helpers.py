"""Helpers réutilisables — ZÉRO décorateur Behave.

Chaque module *steps.py importe les helpers dont il a besoin
et les encapsule dans ses propres @given/@when/@then.
"""

import logging
import sys
import warnings
import re
from playwright.sync_api import TimeoutError as PlaywrightTimeout

logger = logging.getLogger(__name__)

# Marqueur du repli « libellé → nom technique » (décision 0007). Émis en clair dans la sortie
# behave pour être (a) visible en mode dev, (b) capté par le rapport (phase B+). Ne pas changer
# sans mettre à jour le parseur côté rapport.
FIELD_FALLBACK_MARKER = "[TP_FIELD_FALLBACK]"


# ── OdooRPC helpers ──────────────────────────────────────────────────────────

def record_exists(env, model, field, value):
    ids = env[model].search([(field, "=", value)])
    return ids


def record_exists_contains(env, model, field, value):
    m = re.search(r'"([^"]+)"', field)
    actual_field = m.group(1) if m else field.strip()
    return env[model].search([(actual_field, "ilike", value)])


def field_equals(env, model, record_id, field, expected):
    record = env[model].browse(record_id)
    actual = record.read([field])[0][field]
    assert str(actual) == expected, (
        f"Champ '{field}' dans '{model}' : attendu '{expected}', obtenu '{actual}'."
    )


def field_not_empty(env, model, record_id, field):
    record = env[model].browse(record_id)
    value = record.read([field])[0][field]
    assert value not in (False, None, "", []), f"Le champ '{field}' est vide."


def record_count_not_increased(env, model, initial_count):
    current = env[model].search_count([])
    assert current <= initial_count, (
        f"Nombre d'enregistrements dans '{model}' a augmenté ({initial_count} → {current})."
    )


def no_duplicate(env, model, field, value):
    ids = env[model].search([(field, "=", value)])
    assert len(ids) <= 1, (
        f"Doublon détecté dans '{model}' : {len(ids)} enregistrements avec {field}='{value}'."
    )


def no_partial_record(env, model, field):
    ids = env[model].search([(field, "in", [False, ""])])
    assert not ids, f"Enregistrements avec '{field}' vide dans '{model}' : {ids}"


def field_m2o_equals(env, model, record_id, field, expected):
    Model = env[model]
    record_data = Model.browse(record_id).read([field])[0]
    actual = record_data[field]
    if isinstance(actual, (list, tuple)) and len(actual) > 0:
        related_id = actual[0]
        field_info = Model.fields_get([field])
        related_model_name = field_info[field]["relation"]
        related_data = env[related_model_name].browse(related_id).read(["name"])[0]
        actual_name = related_data["name"]
    else:
        actual_name = str(actual)
    assert actual_name == expected, (
        f"Champ '{field}' : attendu '{expected}', obtenu '{actual_name}' (display: {actual})"
    )


def field_m2o_contains(env, model, record_id, field, partial):
    Model = env[model]
    record_data = Model.browse(record_id).read([field])[0]
    actual = record_data[field]
    if isinstance(actual, (list, tuple)) and len(actual) > 0:
        related_id = actual[0]
        field_info = Model.fields_get([field])
        related_model_name = field_info[field]["relation"]
        related_data = env[related_model_name].browse(related_id).read(["name"])[0]
        actual_name = related_data["name"]
    else:
        actual_name = str(actual)
    assert partial in actual_name, (
        f"Champ '{field}' : '{partial}' introuvable dans '{actual_name}' (display: {actual})"
    )


# ── Playwright / navigateur helpers ──────────────────────────────────────────

def playwright_login(context):
    login_url = f"{context.odoo_url.rstrip('/')}/web/login?db={context.odoo_db}"
    context.page.goto(login_url)
    context.page.wait_for_selector("input[name='login']", state="attached", timeout=15000)
    context.page.locator("input[name='login']").fill(context.odoo_user, force=True)
    context.page.locator("input[name='password']").fill(context.odoo_password, force=True)
    context.page.locator("input[name='password']").press("Enter")
    context.page.wait_for_load_state("networkidle")


def navigate(context, url):
    full_url = url if url.startswith("http") else f"{context.odoo_url.rstrip('/')}{url}"
    if context.page.url in ("about:blank", ""):
        playwright_login(context)
    context.page.goto(full_url)
    context.page.wait_for_load_state("networkidle")


def click_button(page, label):
    strategies = [
        page.get_by_role("button", name=label, exact=True),
        page.get_by_role("link", name=label, exact=True),
        page.get_by_role("button", name=label, exact=False),
        page.get_by_role("link", name=label, exact=False),
        page.locator(f':is(a, button, input[type="submit"]):has-text("{label}")'),
    ]
    for loc in strategies:
        try:
            loc.first.click(timeout=5000)
            page.wait_for_load_state("networkidle")
            return
        except PlaywrightTimeout:
            continue
    raise AssertionError(f"Bouton '{label}' introuvable sur {page.url}")


def resolve_field_name(page, ident):
    """Nom technique (`name`) du champ à cibler, à partir de `ident`.

    Tolérance décidée en 0007 : `ident` peut être l'attribut HTML `name` (cas nominal) OU — parce
    que l'agent de génération raisonne parfois en libellé UI — le LIBELLÉ humain du champ.
    Stratégie : `name` d'abord (sélecteur exact, le plus fiable) ; à défaut, on résout `ident`
    comme un libellé et on lit le `name` du contrôle associé.

    Le repli est **toujours TRACÉ** (jamais silencieux) : sans ça, un champ réellement renommé
    côté application serait retrouvé par son libellé et la régression passerait inaperçue
    (§4.6 / §5). Le marqueur permet aussi au rapport de le remonter (phase B+).
    """
    if page.locator(f'[name="{ident}"]').count() > 0:
        return ident
    labelled = page.get_by_label(ident, exact=False)
    if labelled.count() > 0:
        resolved = labelled.first.get_attribute("name")
        if resolved:
            logger.warning(
                "%s champ '%s' introuvable par attribut name ; résolu via son libellé -> "
                "name='%s'. Paramètre le step par le nom technique du champ.",
                FIELD_FALLBACK_MARKER, ident, resolved)
            return resolved
    return ident  # ni name ni libellé exploitable : on laisse échouer en aval (message d'origine)


def fill_field(page, name, value):
    name = resolve_field_name(page, name)
    safe = value.replace("\\", "\\\\").replace("'", "\\'")
    page.wait_for_selector(f'[name="{name}"]', timeout=10000, state="attached")
    el = page.locator(f'[name="{name}"]').first
    tag = el.evaluate("el => el.tagName.toLowerCase()")
    input_type = el.evaluate("el => (el.type || '').toLowerCase()")
    if tag == "select":
        el.select_option(value)
    elif input_type == "radio":
        page.locator(f"input[type='radio'][name='{name}'][value='{value}']").first.check(force=True)
    elif input_type == "checkbox":
        if value.lower() in ("true", "1", "yes", "oui"):
            el.check(force=True)
        else:
            el.uncheck(force=True)
    else:
        # Utiliser JS pour contourner les widgets Odoo et cibler le bon type d'élément
        page.evaluate(f"""
            const el = document.querySelector('textarea[name="{name}"], input[name="{name}"]');
            if (el) {{
                el.value = '{safe}';
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
            }}
        """)


def leave_field_empty(page, name):
    name = resolve_field_name(page, name)
    page.locator(f"[name='{name}']").fill("", force=True)


def select_field_value(page, value, field):
    field = resolve_field_name(page, field)
    select = page.locator(f"select[name='{field}']")
    if select.count() > 0:
        try:
            select.select_option(value, timeout=2000)
        except Exception:
            select.select_option(label=value, timeout=5000)
        page.wait_for_timeout(300)
        return
    radio = page.locator(f"input[type='radio'][name='{field}'][value='{value}']")
    if radio.count() > 0:
        radio.first.click(force=True)
        page.wait_for_timeout(300)
        return
    raise AssertionError(f"Champ select ou radio '{field}' introuvable (valeur: '{value}')")


def select_first_service_in_list(page):
    for path in ["/formulaire-applicatif/", "/description/", "/product/"]:
        links = page.locator(f"a[href*='{path}']")
        if links.count() > 0:
            links.first.click()
            page.wait_for_load_state("networkidle")
            return
    raise AssertionError("Aucun service trouvé dans la liste")


def select_product_in_list(page, name):
    for path in ["/description/", "/product/", "/detail/", "/formulaire-applicatif/"]:
        link = page.locator(f"a[href*='{path}']:has-text('{name}')").first
        if link.count() > 0:
            link.click()
            page.wait_for_load_state("networkidle")
            return
    raise AssertionError(f"Produit '{name}' introuvable dans la liste")


def select_product_partial(page, partial):
    for path in ["/description/", "/product/", "/detail/", "/formulaire-applicatif/"]:
        links = page.locator(f"a[href*='{path}']")
        for i in range(links.count()):
            link = links.nth(i)
            if partial in link.inner_text():
                link.click()
                page.wait_for_load_state("networkidle")
                return
    raise AssertionError(f"Aucun produit contenant '{partial}' trouvé dans la liste")


def click_onglet(page, name):
    link = page.locator(f"a:has-text('{name}')").first
    assert link.count() > 0, f"Onglet '{name}' introuvable"
    link.click()
    page.wait_for_load_state("networkidle")


def click_button_with_accessoires(page, label):
    for selector in [f".btn-{label}", f"text={label}", f"button:has-text('{label}')", f"a:has-text('{label}')"]:
        btn = page.locator(selector)
        if btn.count() > 0 and btn.first.is_visible():
            btn.first.click()
            page.wait_for_load_state("networkidle")
            return
    raise AssertionError(f"Aucun bouton '{label}' avec accessoires trouvé")


def force_name_field(page, value):
    """Set the hidden name field using the JS native setter to bypass Odoo auto-generation."""
    safe = value.replace("\\", "\\\\").replace("'", "\\'")
    page.evaluate(f"""
        (() => {{
            const el = document.querySelector('[name="name"]');
            if (el) {{
                const setter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value'
                ).set;
                setter.call(el, '{safe}');
            }}
        }})()
    """)


def select_first_agence(page):
    select = page.locator("select[name='agence']")
    assert select.count() > 0, "Champ 'agence' introuvable"
    options = select.locator("option")
    for i in range(options.count()):
        val = options.nth(i).get_attribute("value")
        if val and val.strip():
            select.select_option(val)
            page.wait_for_timeout(300)
            return
    raise AssertionError("Aucune option disponible dans le champ 'agence'")


def wait_form_submission(page):
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
        page.wait_for_timeout(1000)
    except PlaywrightTimeout:
        page.wait_for_timeout(3000)


def validation_error_inline(page):
    has_error = page.locator("[class*='s_website_form_field'].o_has_error").first
    assert has_error.is_visible(), "Aucune erreur de validation visible dans le formulaire."


def validation_error_notification(page):
    error = page.locator(".o_notification_manager .o_notification.border-danger").first
    assert error.is_visible(), "Aucune notification d'erreur visible dans l'interface."


def no_error_with_keywords(page, keyword1, keyword2):
    error_elements = page.locator(".alert-danger, .o_notification.border-danger, .text-danger")
    for i in range(error_elements.count()):
        error_text = error_elements.nth(i).inner_text().lower()
        assert keyword1.lower() not in error_text and keyword2.lower() not in error_text, \
            f"Erreur contenant '{keyword1}' ou '{keyword2}' trouvée : {error_text}"


def navigate_menu(context, menu_path):
    context.page.goto(context.odoo_url)
    for part in [p.strip() for p in menu_path.split(">")]:
        context.page.get_by_text(part, exact=True).first.click()
        context.page.wait_for_load_state("networkidle")


def access_portal_section(page, section_name):
    try:
        page.get_by_text(section_name, exact=False).first.click(timeout=8000)
    except PlaywrightTimeout:
        raise AssertionError(
            f"PRÉREQUIS MANQUANT : la section '{section_name}' est absente de {page.url}."
        )
    page.wait_for_load_state("networkidle")


def cleanup_test_records(env, prefix, models):
    for model_name in models.split(" et du modèle "):
        Model = env[model_name.strip('"')]
        old_ids = Model.search([("name", "ilike", prefix)])
        for tid in old_ids:
            Model.unlink(tid)


def memorize_record_count(context, model):
    attr = f"_initial_count_{model.replace('.', '_')}"
    try:
        setattr(context, attr, context.odoo.env[model].search_count([]))
    except Exception as exc:
        warnings.warn(f"[odoo-autotest] Impossible de mémoriser le count pour {model!r} : {exc}")


def check_count_not_increased(context, model):
    attr = f"_initial_count_{model.replace('.', '_')}"
    if not hasattr(context, attr):
        warnings.warn(f"[odoo-autotest] Aucun snapshot initial pour '{model}'.")
        return
    current = context.odoo.env[model].search_count([])
    initial = getattr(context, attr)
    assert current <= initial, (
        f"Nombre d'enregistrements dans '{model}' a augmenté ({initial} → {current})."
    )


def check_count_increased_by_one(context, model):
    attr = f"_initial_count_{model.replace('.', '_')}"
    if not hasattr(context, attr):
        warnings.warn(f"[odoo-autotest] Aucun snapshot initial pour '{model}'.")
        return
    current = context.odoo.env[model].search_count([])
    initial = getattr(context, attr)
    assert current == initial + 1, (
        f"Nombre d'enregistrements dans '{model}' devrait être {initial + 1}, obtenu {current}."
    )
