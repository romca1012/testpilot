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
    select_product_in_list, select_product_partial, NavigationImpossibleError,
)

# ⚠️ Chaque step d'ACTION ci-dessous est déclaré sous `@given` ET `@when` (bug SauceDemo,
# 2026-09-14) — jamais un seul. Le prompt système (`generation/prompts/system_prompt.md`,
# tableau « Décorateurs — correspondance absolue ») dit lui-même à l'IA que `Et`/`Mais` HÉRITE
# du type du step précédent : rien n'empêche (ni ne devrait empêcher) l'IA d'écrire
# « Soit j'accède à la page d'accueil … / Et je renseigne le champ … » (chaîne au type Given)
# aussi légitimement que « Quand je renseigne le champ … / Et … » (chaîne au type When). Avant
# ce correctif, `je renseigne le champ`/`je clique sur le bouton`/etc. n'étaient enregistrés
# qu'en `@when` : la première forme échouait en step UNDEFINED, un `dry_run_stalled` qui n'avait
# rien à voir avec la vraie cause (mesuré : 9 cas sur 15 contre SauceDemo). Un step enregistré
# deux fois ne perd rien : la fonction est la même, seul le mot-clé Gherkin qui l'invoque change.


@given('je renseigne le champ "{field}" avec la valeur "{value}"')
@when('je renseigne le champ "{field}" avec la valeur "{value}"')
def step_fill(context, field, value):
    fill_field(context.page, field, value)


@given('je remplis le formulaire de "{route}" avec des données valides')
@when('je remplis le formulaire de "{route}" avec des données valides')
def step_remplir_formulaire_valide(context, route):
    """Chemin NOMINAL (§2bis) : le déterministe remplit tout — le LLM ne nomme aucun champ.
    Pour un scénario NÉGATIF (tester un refus), on garde les steps fins « je renseigne le
    champ … avec la valeur … », où la mauvaise valeur EST le sujet du test."""
    remplir_formulaire_valide(context, route)


@given('je joins un fichier au champ "{field}"')
@when('je joins un fichier au champ "{field}"')
def step_attach(context, field):
    """Téléverse une pièce jointe de test dans un champ fichier (`<input type="file">`).

    ⚠️ Un champ fichier ne se remplit PAS avec « je renseigne le champ … avec la valeur … » au
    sens d'un texte : le navigateur refuse (`InvalidStateError`). Utilise CE step pour toute
    pièce jointe — 13 des 37 routes du portail en exigent une.
    """
    attach_file(context.page, field)


@given('je sélectionne "{value}" dans le champ "{field}"')
@when('je sélectionne "{value}" dans le champ "{field}"')
def step_select(context, value, field):
    select_field_value(context.page, value, field)


@given('je clique sur le bouton "{label}"')
@when('je clique sur le bouton "{label}"')
def step_click(context, label):
    click_button(context.page, label)


@given('je laisse le champ "{field}" vide')
@when('je laisse le champ "{field}" vide')
def step_leave_empty(context, field):
    leave_field_empty(context.page, field)


@given('je force le nom du ticket à "{value}"')
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

@given("j'accède à la page d'accueil de l'application")
@when("j'accède à la page d'accueil de l'application")
def step_access_home_page(context):
    """Navigation INITIALE d'un connecteur `web` générique — le SEUL step qui charge une page
    dans le navigateur avant toute interaction (bug SauceDemo, 2026-09-13).

    ⚠️ **Pourquoi il fallait EXISTER, pas juste être appelé.** `context.page` démarre sur
    `about:blank` (voir `environment.py::playwright_browser`) ; sans ce step, RIEN dans la
    bibliothèque `generic/` ne charge jamais l'application. Avant ce step, l'IA détournait
    « j'accède à la section "…" du portail » (pensé pour cliquer un ONGLET d'un portail
    DÉJÀ chargé, pas pour naviguer) en lui passant "/" — sur une page blanche, ce clic
    échoue ou ne fait rien, et le scénario continue à l'aveugle jusqu'à l'assertion finale,
    qui échoue pour une raison qui n'a plus rien à voir avec la vraie cause.
    """
    if not context.web_url:
        # ⚠️ `NavigationImpossibleError`, pas `AssertionError` (correctif 2026-09-14, même famille
        # que le cas C45) : une connexion de projet incomplète est un problème d'ENVIRONNEMENT,
        # jamais une preuve que l'application se comporte mal — voir defect_taxonomy.
        raise NavigationImpossibleError(
            "URL de l'application introuvable (WEB_URL absent) — vérifiez la connexion du "
            "projet (adresse renseignée dans ses réglages).")
    context.page.goto(context.web_url, wait_until="domcontentloaded")


@given('je clique sur l\'onglet "{name}"')
@when('je clique sur l\'onglet "{name}"')
def step_click_portal_onglet(context, name):
    click_first_actionable(context.page, [
        f".nav-link:has-text('{name}')", f".nav-item a:has-text('{name}')",
        f"[role='tab']:has-text('{name}')", f"li a:has-text('{name}')",
        f"a:has-text('{name}')", f"button:has-text('{name}')",
    ], quoi=f"Onglet '{name}'")


@given('je sélectionne le produit "{name}" dans la liste')
@when('je sélectionne le produit "{name}" dans la liste')
def step_select_product_in_list(context, name):
    # ⚠️ Délègue à `_base_helpers.select_product_in_list` — ce step avait sa PROPRE copie inline
    # de `_PRODUCT_PATHS`/la logique de clic, désynchronisée du helper partagé : un correctif posé
    # sur l'un (le repli générique `a:has-text(...)`, cas C45) restait sans AUCUN effet sur
    # l'autre, réellement utilisé ici. Trouvé en reproduisant le bug en conditions réelles contre
    # SauceDemo — le correctif « marchait » en isolation et jamais via ce step. Une seule
    # implémentation, désormais : plus de duplication à faire diverger en silence.
    select_product_in_list(context.page, name)


@given('je sélectionne le produit dans la liste contenant "{partial}"')
@when('je sélectionne le produit dans la liste contenant "{partial}"')
def step_select_product_partial(context, partial):
    select_product_partial(context.page, partial)


@given('je clique sur le bouton "{label}" avec accessoires')
@when('je clique sur le bouton "{label}" avec accessoires')
def step_click_button_with_accessoires(context, label):
    click_first_actionable(context.page,
        [f".btn-{label}", f":is(button, a):has-text('{label}')"],
        quoi=f"Bouton '{label}' (accessoires)")


@when('j\'accède à la section "{section_name}" du portail')
@given('j\'accède à la section "{section_name}" du portail')
def step_access_portal_section(context, section_name):
    """Clique un ONGLET/lien d'un portail DÉJÀ CHARGÉ — ne navigue vers AUCUNE URL.

    ⚠️ Jamais pour une navigation INITIALE (bug SauceDemo, 2026-09-13) : sur `about:blank`, ce
    clic échoue à trouver quoi que ce soit. Utilisez « j'accède à la page d'accueil de
    l'application » pour charger l'application pour la première fois.
    """
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
