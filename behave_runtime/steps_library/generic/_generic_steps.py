"""Steps VRAIMENT génériques — aucun ne touche `context.odoo` ni une variable `ODOO_*`.

Réutilisables tel quel par n'importe quel connecteur web (Playwright + formulaire HTML). Critère
de classement (audit DA 2026-08-13, ex-`_generic_steps.py`/`_base_steps.py`/`_background_steps.py`
mélangeaient ce fichier avec des steps Odoo sans le signaler — `_generic_steps.py` affirmait même
« ZÉRO step spécifique » alors qu'il appelait `context.odoo.env` directement) : un step vit ici
s'il n'appelle que `context.page` (Playwright) ou ne fait rien (`pass`) — dès qu'il touche
`context.odoo`/`ODOO_*`/un sélecteur du web client Odoo, il va dans `../odoo/`.
"""
from behave import given, when, then
# Import mis au PLAT (layout d'exécution sans package features/ — voir environment.py) :
# _base_helpers.py reste à la racine de steps_library/, copié à plat par _assemble() quel que
# soit le sous-dossier d'origine de CE fichier.
from _base_helpers import (
    fill_field, select_field_value, click_button,
    attach_file, leave_field_empty, click_first_actionable,
    no_error_with_keywords, validation_error_inline,
    wait_form_submission, force_name_field, remplir_formulaire_valide,
)


@when('je renseigne le champ "{field}" avec la valeur "{value}"')
def step_fill(context, field, value):
    fill_field(context.page, field, value)


@when('je remplis le formulaire de "{route}" avec des données valides')
def step_remplir_formulaire_valide(context, route):
    """Chemin NOMINAL (§2bis) : le déterministe remplit tout — le LLM ne nomme aucun champ.
    Pour un scénario NÉGATIF (tester un refus), on garde les steps fins « je renseigne le
    champ … avec la valeur … », où la mauvaise valeur EST le sujet du test."""
    remplir_formulaire_valide(context, route)


@when('je joins un fichier au champ "{field}"')
def step_attach(context, field):
    """Téléverse une pièce jointe de test dans un champ fichier (`<input type="file">`).

    ⚠️ Un champ fichier ne se remplit PAS avec « je renseigne le champ … avec la valeur … » au
    sens d'un texte : le navigateur refuse (`InvalidStateError`). Utilise CE step pour toute
    pièce jointe — 13 des 37 routes du portail en exigent une.
    """
    attach_file(context.page, field)


@when('je sélectionne "{value}" dans le champ "{field}"')
def step_select(context, value, field):
    select_field_value(context.page, value, field)


@when('je clique sur le bouton "{label}"')
def step_click(context, label):
    click_button(context.page, label)


@when('je laisse le champ "{field}" vide')
def step_leave_empty(context, field):
    leave_field_empty(context.page, field)


@when('je force le nom du ticket à "{value}"')
def step_force_name(context, value):
    force_name_field(context.page, value)


@when("j'attends la soumission du formulaire")
@then("j'attends la soumission du formulaire")
def step_wait_form(context):
    wait_form_submission(context.page)


@then("une erreur de validation est affichée dans le formulaire")
def step_validation_error(context):
    validation_error_inline(context.page)


@then('aucune erreur mentionnant "{kw1}" ou "{kw2}" n\'est affichée dans l\'interface')
def step_no_error(context, kw1, kw2):
    no_error_with_keywords(context.page, kw1, kw2)


# ── Navigation portail — steps génériques (ex-_base_steps.py, aucun n'appelle context.odoo) ──

_PRODUCT_PATHS = ("/description/", "/product/", "/detail/", "/formulaire-applicatif/")


@given('je clique sur l\'onglet "{name}"')
@when('je clique sur l\'onglet "{name}"')
def step_click_portal_onglet(context, name):
    click_first_actionable(context.page, [
        f".nav-link:has-text('{name}')", f".nav-item a:has-text('{name}')",
        f"[role='tab']:has-text('{name}')", f"li a:has-text('{name}')",
        f"a:has-text('{name}')", f"button:has-text('{name}')",
    ], quoi=f"Onglet '{name}'")


@when('je sélectionne le produit "{name}" dans la liste')
def step_select_product_in_list(context, name):
    click_first_actionable(context.page,
        [f"a[href*='{p}']:has-text('{name}')" for p in _PRODUCT_PATHS],
        quoi=f"Produit '{name}'")


@when('je sélectionne le produit dans la liste contenant "{partial}"')
def step_select_product_partial(context, partial):
    # `:has-text` fait le « contient » (sous-chaîne, insensible à la casse) — plus tolérant que
    # l'ancien `partial in inner_text`, et sans course au rendu.
    click_first_actionable(context.page,
        [f"a[href*='{p}']:has-text('{partial}')" for p in _PRODUCT_PATHS],
        quoi=f"Produit contenant '{partial}'")


@when('je clique sur le bouton "{label}" avec accessoires')
def step_click_button_with_accessoires(context, label):
    click_first_actionable(context.page,
        [f".btn-{label}", f":is(button, a):has-text('{label}')"],
        quoi=f"Bouton '{label}' (accessoires)")


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


# ── Déclaration de teardown (ex-_background_steps.py) — `pass` : aucune dépendance connecteur ──

@given('tous les enregistrements créés durant ce scénario seront supprimés '
       'après exécution via leurs identifiants enregistrés')
def step_declare_teardown(context):
    pass
