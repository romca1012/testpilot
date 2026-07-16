
"""Steps Behave — assertions OdooRPC et navigation Playwright.

Ce fichier contient uniquement les steps qui ne sont pas dans :
  - _background_steps.py (5 steps Contexte communs)
  - _generic_steps.py    (UI générique : fill, click, count, erreurs)
"""

import sys

from behave import given, then, when


# ── Nettoyage de données de test ─────────────────────────────────────────────

@given('je nettoie les enregistrements "{prefix}" du modèle "{models}"')
def step_cleanup_test_records(context, prefix, models):
    for model_name in models.split(" et du modèle "):
        Model = context.odoo.env[model_name.strip('"')]
        old_ids = Model.search([("name", "ilike", prefix)])
        for tid in old_ids:
            Model.unlink(tid)


# ── Assertions sur les enregistrements (OdooRPC) ─────────────────────────────

@then('un enregistrement avec le champ "{field}" égal à "{value}" existe '
      'dans le modèle "{model}"')
def step_record_exists_field_value(context, field, value, model):
    ids = context.odoo.env[model].search([(field, "=", value)])
    assert ids, (
        f"Aucun enregistrement trouvé dans '{model}' avec {field}='{value}'."
    )
    context.last_record_ids = ids
    context.last_record_model = model


@then('un enregistrement avec {field} contenant "{value}" existe '
      'dans le modèle "{model}"')
def step_record_exists_contains(context, field, value, model):
    import re
    m = re.search(r'"([^"]+)"', field)
    actual_field = m.group(1) if m else field.strip()
    ids = context.odoo.env[model].search([(actual_field, "ilike", value)])
    assert ids, (
        f"Aucun enregistrement trouvé dans '{model}' où {actual_field} contient '{value}'."
    )
    context.last_record_ids = ids
    context.last_record_model = model


@then('le champ "{field}" de cet enregistrement dans le modèle "{model}" '
      'est égal à "{expected}"')
def step_field_equals(context, field, model, expected):
    assert hasattr(context, "last_record_ids"), (
        "Aucun enregistrement en contexte. Utilisez d'abord un step 'existe dans le modèle'."
    )
    record = context.odoo.env[model].browse(context.last_record_ids[0])
    actual = record.read([field])[0][field]
    assert str(actual) == expected, (
        f"Champ '{field}' dans '{model}' : attendu '{expected}', obtenu '{actual}'."
    )


@then('le champ "{field}" de cet enregistrement est égal à "{expected}"')
def step_field_equals_simple(context, field, expected):
    assert hasattr(context, "last_record_ids") and hasattr(context, "last_record_model"), (
        "Aucun enregistrement en contexte. Utilisez d'abord un step qui crée ou trouve un enregistrement."
    )
    record = context.odoo.env[context.last_record_model].browse(context.last_record_ids[0])
    actual = record.read([field])[0][field]
    assert str(actual) == expected, (
        f"Champ '{field}' : attendu '{expected}', obtenu '{actual}'."
    )


@then('le champ "{field}" de cet enregistrement n\'est pas vide')
def step_field_not_empty(context, field):
    assert hasattr(context, "last_record_ids") and hasattr(context, "last_record_model")
    record = context.odoo.env[context.last_record_model].browse(context.last_record_ids[0])
    value = record.read([field])[0][field]
    assert value not in (False, None, "", []), f"Le champ '{field}' est vide."


@then('le champ "{field}" de cet enregistrement dans le modèle "{model}" pointe vers "{expected}"')
def step_field_m2o_equals(context, field, model, expected):
    Model = context.odoo.env[model]
    record_data = Model.browse(context.last_record_ids[0]).read([field])[0]
    actual = record_data[field]
    if isinstance(actual, (list, tuple)) and len(actual) > 0:
        related_id = actual[0]
        related_model_name = Model.fields_get([field])[field]["relation"]
        actual_name = context.odoo.env[related_model_name].browse(related_id).read(["name"])[0]["name"]
    else:
        actual_name = str(actual)
    assert actual_name == expected, (
        f"Champ '{field}' : attendu '{expected}', obtenu '{actual_name}' (display: {actual})"
    )


@then('le champ "{field}" de cet enregistrement contient le nom "{partial}"')
def step_field_m2o_contains(context, field, partial):
    Model = context.odoo.env[context.last_record_model]
    record_data = Model.browse(context.last_record_ids[0]).read([field])[0]
    actual = record_data[field]
    if isinstance(actual, (list, tuple)) and len(actual) > 0:
        related_id = actual[0]
        related_model_name = Model.fields_get([field])[field]["relation"]
        actual_name = context.odoo.env[related_model_name].browse(related_id).read(["name"])[0]["name"]
    else:
        actual_name = str(actual)
    assert partial in actual_name, (
        f"Champ '{field}' : '{partial}' introuvable dans '{actual_name}' (display: {actual})"
    )


# ── Préconditions de données ──────────────────────────────────────────────────

@given('aucun enregistrement dont le nom commence par "{prefix}" n\'existe '
       'dans le modèle "{model}"')
def step_no_test_records(context, prefix, model):
    try:
        Model = context.odoo.env[model]
        try:
            available = Model.fields_get(["name"])
            if "name" not in available:
                return
        except Exception:
            pass
        ids = Model.search([("name", "=like", f"{prefix}%")])
        assert not ids, (
            f"Des enregistrements résiduels existent dans '{model}' "
            f"(préfixe '{prefix}', IDs : {list(ids)}). "
            "Supprimez-les manuellement dans Odoo avant de relancer les tests."
        )
    except AssertionError:
        raise
    except Exception as exc:
        print(
            f"[WARN odoo-autotest] Vérification pré-test impossible sur '{model}' : {exc}",
            file=sys.stderr,
        )


# ── Assertions négatives ──────────────────────────────────────────────────────
#
# ⚠️ SUPPRIMÉ (décision 0010) : le step
#     @then("aucun enregistrement inattendu n'est créé dans aucun modèle Odoo
#            comme effet de bord de cette action")
# faisait `pass` — une VÉRIFICATION qui ne vérifiait rien, donc un « conforme » déclaratif
# (§4.2) et une fabrique à faux-négatifs (§4.4). Aggravant : il était AU CATALOGUE, donc montré
# à l'agent et proposé à la réutilisation (0003) — le pipeline invitait à s'appuyer dessus.
#
# Il n'a pas été réimplémenté : sa promesse (« aucun modèle Odoo », soit des centaines) n'est
# pas tenable — un instantané avant/après serait lent et structurellement faux-positif (journaux,
# séquences, mail.message bougent à chaque action). Le `pass` n'était pas un oubli, c'était la
# seule façon de faire « passer » une promesse impossible.
#
# Le besoin réel est couvert par les steps CIBLÉS ci-dessous et dans _generic_steps, qui eux
# vérifient vraiment, modèle par modèle :
#   - « le nombre total d'enregistrements dans le modèle "{model}" n'a pas augmenté »
#   - « aucun enregistrement partiel avec le champ "{field}" vide … »
#   - « aucun enregistrement en double avec le champ "{field}" égal à "{value}" … »
# Ne pas le réintroduire sans lire 0010.

@then('aucun enregistrement partiel avec le champ "{field}" vide n\'est '
      'persisté dans le modèle "{model}"')
def step_no_partial_record(context, field, model):
    ids = context.odoo.env[model].search([(field, "in", [False, ""])])
    assert not ids, (
        f"Enregistrements avec '{field}' vide dans '{model}' : {ids}"
    )


# ── Navigation Playwright — backend ──────────────────────────────────────────

@given('je navigue vers le menu Odoo "{menu_path}"')
@when('je navigue vers le menu Odoo "{menu_path}"')
def step_navigate_menu(context, menu_path):
    context.page.goto(context.odoo_url)
    for part in [p.strip() for p in menu_path.split(">")]:
        context.page.get_by_text(part, exact=True).first.click()
        context.page.wait_for_load_state("networkidle")


def _playwright_login(context):
    login_url = f"{context.odoo_url.rstrip('/')}/web/login?db={context.odoo_db}"
    context.page.goto(login_url)
    context.page.wait_for_selector("input[name='login']", state="attached", timeout=15000)
    context.page.locator("input[name='login']").fill(context.odoo_user, force=True)
    context.page.locator("input[name='password']").fill(context.odoo_password, force=True)
    context.page.locator("input[name='password']").press("Enter")
    context.page.wait_for_load_state("networkidle")


@given('je navigue vers l\'URL du portail "{url}"')
@when('je navigue vers l\'URL du portail "{url}"')
def step_navigate_url(context, url):
    full_url = url if url.startswith("http") else f"{context.odoo_url.rstrip('/')}{url}"
    if context.page.url in ("about:blank", ""):
        _playwright_login(context)
    context.page.goto(full_url)
    context.page.wait_for_load_state("networkidle")


@given('je me connecte avec mes identifiants utilisateur')
@when('je me connecte avec mes identifiants utilisateur')
def step_login_portal(context):
    """CONNECTE réellement le NAVIGATEUR (Playwright) : indispensable AVANT toute navigation sur une page du portail, sinon la session est anonyme et la page ne se rend pas."""
    _playwright_login(context)
    context.page.goto(context.odoo_url)
    context.page.wait_for_load_state("networkidle")


@when('j\'accède à la section "{section_name}" du portail')
@given('j\'accède à la section "{section_name}" du portail')
def step_access_portal_section(context, section_name):
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    try:
        context.page.get_by_text(section_name, exact=False).first.click(timeout=8000)
    except PlaywrightTimeout:
        raise AssertionError(
            f"PRÉREQUIS MANQUANT : la section '{section_name}' est absente de {context.page.url}. "
            "Vérifiez que des produits avec portal_active=True et la catégorie correspondante "
            "existent dans Odoo."
        )
    context.page.wait_for_load_state("networkidle")


# ── Navigation portail — steps génériques ────────────────────────────────────

@given('je clique sur l\'onglet "{name}"')
@when('je clique sur l\'onglet "{name}"')
def step_click_portal_onglet(context, name):
    link = context.page.locator(f"a:has-text('{name}')").first
    assert link.count() > 0, f"Onglet '{name}' introuvable sur {context.page.url}"
    link.click()
    context.page.wait_for_load_state("networkidle")


@when('je sélectionne le produit "{name}" dans la liste')
def step_select_product_in_list(context, name):
    for path in ["/description/", "/product/", "/detail/", "/formulaire-applicatif/"]:
        link = context.page.locator(f"a[href*='{path}']:has-text('{name}')").first
        if link.count() > 0:
            link.click()
            context.page.wait_for_load_state("networkidle")
            return
    raise AssertionError(f"Produit '{name}' introuvable dans la liste")


@when('je sélectionne le produit dans la liste contenant "{partial}"')
def step_select_product_partial(context, partial):
    for path in ["/description/", "/product/", "/detail/", "/formulaire-applicatif/"]:
        links = context.page.locator(f"a[href*='{path}']")
        for i in range(links.count()):
            link = links.nth(i)
            if partial in link.inner_text():
                link.click()
                context.page.wait_for_load_state("networkidle")
                return
    raise AssertionError(f"Aucun produit contenant '{partial}' trouvé dans la liste")


@when('je clique sur le bouton "{label}" avec accessoires')
def step_click_button_with_accessoires(context, label):
    for selector in [f".btn-{label}", f"text={label}", f"button:has-text('{label}')", f"a:has-text('{label}')"]:
        btn = context.page.locator(selector)
        if btn.count() > 0 and btn.first.is_visible():
            btn.first.click()
            context.page.wait_for_load_state("networkidle")
            return
    raise AssertionError(f"Aucun bouton '{label}' avec accessoires trouvé sur {context.page.url}")


@then('une notification d\'erreur de validation est affichée dans l\'interface Odoo')
def step_validation_error_shown(context):
    error = context.page.locator(".o_notification_manager .o_notification.border-danger").first
    assert error.is_visible(), "Aucune notification d'erreur visible dans l'interface."
