"""Décision 0008 — lint des assertions infalsifiables (phase C).

Deux exigences du porteur, explicitement couvertes ici :
- l'anti-faux-positif ne se limite PAS aux cas triviaux : il couvre des **variantes légitimes**
  du motif contextuel (`assert ... or X not in Y` dans le `else` d'un `if X in Y`) qui, elles,
  ne sont PAS des tautologies (`test_pas_de_faux_positif_sur_variantes_du_motif_contextuel`) ;
- la preuve finale rejoue le **contenu exact de l'écart 2**, pas une version simplifiée
  (`test_contenu_exact_ecart_2_est_signale`).
"""

from testpilot.generation import assertion_lint as al


def _kinds(src: str) -> set[str]:
    return {w["kind"] for w in al.lint_steps(src)}


# ── 1. Sous-ensemble trivial ───────────────────────────────────────────────────
def test_assert_constante_vraie():
    src = """
from behave import then
@then("truc")
def s(context):
    assert True
"""
    assert al.ALWAYS_TRUE_CONSTANT in _kinds(src)


def test_or_avec_constante_vraie():
    src = """
from behave import then
@then("truc")
def s(context):
    assert context.ok or True
"""
    assert al.ALWAYS_TRUE_CONSTANT in _kinds(src)


# ── 2. Motif contextuel — CONTENU EXACT de l'écart 2 (preuve finale) ────────────
# Reconstruction fidèle du step `step_long_string_coherent` généré au run #2 (cas 2).
_ECART_2_EXACT = '''
from behave import then

@then("le formulaire traite la chaîne longue de manière cohérente")
def step_long_string_coherent(context):
    page = context.page
    current_url = page.url
    if "/your-ticket-has-been-submitted" in current_url:
        context.long_string_accepted = True
    else:
        error_visible = (
            page.locator(".s_website_form_field_is_invalid, .o_field_invalid").count() > 0
            or page.locator("text=Ce champ est requis").count() > 0
            or page.locator("text=required").count() > 0
        )
        context.long_string_accepted = False
        assert error_visible or "/your-ticket-has-been-submitted" not in current_url, (
            "Comportement incohérent : ni redirection de succès ni erreur de validation visible."
        )
'''


def test_contenu_exact_ecart_2_est_signale():
    warnings = al.lint_steps(_ECART_2_EXACT)
    kinds = {w["kind"] for w in warnings}
    assert al.TAUTOLOGY_NEGATION_IN_ELSE in kinds, (
        "le motif exact de l'écart 2 doit être détecté — sinon le dossier n'est pas fermé")
    # Le libellé Gherkin du step fautif doit remonter (le relecteur doit savoir OÙ).
    tauto = next(w for w in warnings if w["kind"] == al.TAUTOLOGY_NEGATION_IN_ELSE)
    assert "cohérente" in tauto["step"]


def test_negation_simple_dans_else_sans_or():
    # `assert X not in Y` seul, dans le else d'un `if X in Y` → toujours vrai aussi.
    src = '''
from behave import then
@then("truc")
def s(context):
    if "ok" in context.page.url:
        pass
    else:
        assert "ok" not in context.page.url
'''
    assert al.TAUTOLOGY_NEGATION_IN_ELSE in _kinds(src)


# ── 3. @then sans assertion — filtré par décorateur ─────────────────────────────
def test_then_sans_assertion():
    src = """
from behave import then
@then("verifie quelque chose")
def s(context):
    context.flag = True
"""
    assert al.THEN_WITHOUT_ASSERTION in _kinds(src)


def test_when_action_sans_assertion_nest_pas_signale():
    # Un @when d'action n'affirme légitimement rien.
    src = """
from behave import when
@when("je remplis le champ")
def s(context):
    context.page.fill("[name='x']", "v")
"""
    assert al.THEN_WITHOUT_ASSERTION not in _kinds(src)


def test_then_qui_delegue_a_un_helper_dassertion_nest_pas_signale():
    src = """
from behave import then
@then("le ticket existe")
def s(context):
    assert_record_exists(context, "helpdesk.ticket")
"""
    assert al.THEN_WITHOUT_ASSERTION not in _kinds(src)


# ── 4. ANTI-FAUX-POSITIF — variantes LÉGITIMES du motif contextuel ──────────────
def test_pas_de_faux_positif_sur_variantes_du_motif_contextuel():
    """Du code qui RESSEMBLE structurellement au motif (else + or + `not in`) mais n'est PAS
    une tautologie ne doit produire AUCUN avertissement de tautologie."""

    # a) La négation porte sur une AUTRE variable que le `if` → pas toujours vrai.
    autre_variable = '''
from behave import then
@then("t")
def s(context):
    if "/succes" in context.url_a:
        pass
    else:
        assert context.ok or "/succes" not in context.url_b
'''
    # b) Même gauche mais comparateur DIFFÉRENT (url_b au lieu de url_a).
    autre_comparateur = '''
from behave import then
@then("t")
def s(context):
    if "/x" in context.a:
        pass
    else:
        assert context.ok or "/x" not in context.b
'''
    # c) `or` sans aucune négation de la condition.
    sans_negation = '''
from behave import then
@then("t")
def s(context):
    if "/x" in context.a:
        pass
    else:
        assert context.redirige or context.erreur
'''
    # d) `not in` présent mais HORS d'un `else` (aucun `if` englobant).
    hors_else = '''
from behave import then
@then("t")
def s(context):
    assert context.ok or "/x" not in context.a
'''
    for src in (autre_variable, autre_comparateur, sans_negation, hors_else):
        assert al.TAUTOLOGY_NEGATION_IN_ELSE not in _kinds(src), src


def test_disjonction_falsifiable_regeneree_ne_declenche_rien():
    """Le `[Limite]` re-généré après la phase A (disjonction d'états réels + invariant) est
    FALSIFIABLE : aucun avertissement attendu."""
    src = '''
from behave import then
@then("le formulaire est traité de manière cohérente sans ticket partiel")
def step_assert_limit_coherent(context):
    delta = context.count - context.baseline
    redirect_ok = "/your-ticket-has-been-submitted" in context.page.url
    validation_error = context.page.locator(".alert-danger").count() > 0
    partial = context.odoo.env["helpdesk.ticket"].search_count([("name", "=", False)])
    assert partial == 0, "ticket partiel"
    issue_a = redirect_ok and delta == 1
    issue_b = (not redirect_ok) and delta == 0 and validation_error
    issue_c = (not redirect_ok) and delta == 0
    assert issue_a or issue_b or issue_c, "issue inattendue"
'''
    assert al.lint_steps(src) == []


def test_assertion_normale_ne_declenche_rien():
    src = """
from behave import then
@then("le total vaut 3")
def s(context):
    assert context.total == 3
"""
    assert al.lint_steps(src) == []


def test_contenu_vide_ou_illisible_tolere():
    assert al.lint_steps("") == []
    assert al.lint_steps("def (((") == []
