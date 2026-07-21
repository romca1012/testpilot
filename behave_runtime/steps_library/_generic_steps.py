"""Steps génériques réutilisables par tous les modules.
ZÉRO step spécifique — uniquement les décorateurs partagés.
Les helpers viennent de _base_helpers.py.
"""
from behave import given, when, then
# Import mis au PLAT (layout d'exécution sans package features/ — voir environment.py).
from _base_helpers import (
    fill_field, select_field_value, click_button,
    attach_file, leave_field_empty,
    memorize_record_count, check_count_not_increased, check_count_increased_by_one,
    no_duplicate, no_error_with_keywords, validation_error_inline,
    wait_form_submission, force_name_field,
)


@given('le nombre d\'enregistrements dans le modèle "{model}" est enregistré pour comparaison')
def step_record_count(context, model):
    memorize_record_count(context, model)


@when('je renseigne le champ "{field}" avec la valeur "{value}"')
def step_fill(context, field, value):
    fill_field(context.page, field, value)


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


@then('aucun enregistrement en double avec le champ "{field}" égal à "{value}" '
      'n\'existe dans le modèle "{model}"')
def step_no_dup(context, field, value, model):
    no_duplicate(context.odoo.env, model, field, value)


@then("une erreur de validation est affichée dans le formulaire")
def step_validation_error(context):
    validation_error_inline(context.page)


@then('le nombre total d\'enregistrements dans le modèle "{model}" n\'a pas augmenté')
def step_count_not_inc(context, model):
    check_count_not_increased(context, model)


@then('le nombre total d\'enregistrements dans le modèle "{model}" augmente de 1')
def step_count_increased_by_one(context, model):
    check_count_increased_by_one(context, model)


@then('aucune erreur mentionnant "{kw1}" ou "{kw2}" n\'est affichée dans l\'interface')
def step_no_error(context, kw1, kw2):
    no_error_with_keywords(context.page, kw1, kw2)
