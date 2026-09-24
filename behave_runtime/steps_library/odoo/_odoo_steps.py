"""Steps spécifiques au connecteur Odoo — assertions OdooRPC et navigation portail Odoo.

Un step vit ici s'il touche `context.odoo` (RPC), une variable `ODOO_*`, ou un sélecteur DOM
propre au web client Odoo (`.o_notification_manager`) — voir `../generic/_generic_steps.py` pour
le critère complet et pourquoi cette séparation existe (audit DA 2026-08-13).
"""
import re
import sys

from behave import given, then, when

# Import à PLAT (layout d'exécution sans package features/ — cf. environment.py), comme les
# autres fichiers de la bibliothèque.
from _base_helpers import (
    PreconditionNonRemplieError,
    memorize_record_count, check_count_not_increased, check_count_increased_by_one, no_duplicate,
    validation_error_notification, playwright_login, navigate_menu,
)


def _exiger_enregistrement_en_contexte(context, message: str, *, avec_modele: bool = False) -> None:
    """Un step qui lit « cet enregistrement » suppose qu'un step PRÉCÉDENT l'a mis en contexte.

    Son absence est un BUG DU TEST (le scénario est mal composé), jamais un constat sur
    l'application : `RuntimeError`, pas `AssertionError` — Behave écrit « ASSERT FAILED » pour une
    assertion, et un `then` en assertion devient `non_conforme` (lot 02, F2). Une `RuntimeError` reste
    un échec d'exécution à revérifier (`retest`).
    """
    manque = not hasattr(context, "last_record_ids") or (
        avec_modele and not hasattr(context, "last_record_model"))
    if manque:
        raise RuntimeError(message)


# ── Comptage / dédoublonnage (ex-_generic_steps.py — appelaient context.odoo malgré le nom) ──

@given('le nombre d\'enregistrements dans le modèle "{model}" est enregistré pour comparaison')
def step_record_count(context, model):
    memorize_record_count(context, model)


@then('aucun enregistrement en double avec le champ "{field}" égal à "{value}" '
      'n\'existe dans le modèle "{model}"')
def step_no_dup(context, field, value, model):
    no_duplicate(context.odoo.env, model, field, value)


@then('le nombre total d\'enregistrements dans le modèle "{model}" n\'a pas augmenté')
def step_count_not_inc(context, model):
    check_count_not_increased(context, model)


@then('le nombre total d\'enregistrements dans le modèle "{model}" augmente de 1')
def step_count_increased_by_one(context, model):
    check_count_increased_by_one(context, model)


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
    _exiger_enregistrement_en_contexte(
        context, "Aucun enregistrement en contexte. Utilisez d'abord un step 'existe dans le modèle'.")
    record = context.odoo.env[model].browse(context.last_record_ids[0])
    actual = record.read([field])[0][field]
    assert str(actual) == expected, (
        f"Champ '{field}' dans '{model}' : attendu '{expected}', obtenu '{actual}'."
    )


@then('le champ "{field}" de cet enregistrement est égal à "{expected}"')
def step_field_equals_simple(context, field, expected):
    _exiger_enregistrement_en_contexte(
        context, "Aucun enregistrement en contexte. Utilisez d'abord un step qui crée ou trouve un "
                 "enregistrement.", avec_modele=True)
    record = context.odoo.env[context.last_record_model].browse(context.last_record_ids[0])
    actual = record.read([field])[0][field]
    assert str(actual) == expected, (
        f"Champ '{field}' : attendu '{expected}', obtenu '{actual}'."
    )


@then('le champ "{field}" de cet enregistrement n\'est pas vide')
def step_field_not_empty(context, field):
    _exiger_enregistrement_en_contexte(
        context, "Aucun enregistrement en contexte. Utilisez d'abord un step qui crée ou trouve un "
                 "enregistrement.", avec_modele=True)
    record = context.odoo.env[context.last_record_model].browse(context.last_record_ids[0])
    value = record.read([field])[0][field]
    assert value not in (False, None, "", []), f"Le champ '{field}' est vide."


@then('le champ "{field}" de cet enregistrement dans le modèle "{model}" pointe vers "{expected}"')
def step_field_m2o_equals(context, field, model, expected):
    _exiger_enregistrement_en_contexte(
        context, "Aucun enregistrement en contexte. Utilisez d'abord un step 'existe dans le modèle' — ou "
                 "une vérification de comptage qui en trouve un (0022 A+, 2026-08-07).")
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
    _exiger_enregistrement_en_contexte(
        context, "Aucun enregistrement en contexte. Utilisez d'abord un step qui crée ou trouve un "
                 "enregistrement.", avec_modele=True)
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
    except Exception as exc:
        print(
            f"[WARN odoo-autotest] Vérification pré-test impossible sur '{model}' : {exc}",
            file=sys.stderr,
        )
        return
    # ⚠️ HORS du `try` : `PreconditionNonRemplieError` est une `Exception`, le `except Exception` ci-dessus
    # l'aurait avalée en simple avertissement — le prérequis aurait « passé » sans rien vérifier.
    if ids:
        raise PreconditionNonRemplieError(
            f"Des enregistrements résiduels existent dans '{model}' "
            f"(préfixe '{prefix}', IDs : {list(ids)}). "
            "Supprimez-les manuellement dans Odoo avant de relancer les tests."
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
# Le besoin réel est couvert par les steps CIBLÉS ci-dessus et dans generic/_generic_steps.py,
# qui eux vérifient vraiment, modèle par modèle :
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


# ── Navigation Playwright — backend Odoo ──────────────────────────────────────

@given('je navigue vers le menu Odoo "{menu_path}"')
@when('je navigue vers le menu Odoo "{menu_path}"')
def step_navigate_menu(context, menu_path):
    navigate_menu(context, menu_path)


@given('je navigue vers l\'URL du portail "{url}"')
@when('je navigue vers l\'URL du portail "{url}"')
def step_navigate_url(context, url):
    full_url = url if url.startswith("http") else f"{context.odoo_url.rstrip('/')}{url}"
    if context.page.url in ("about:blank", ""):
        playwright_login(context)
    # domcontentloaded (fiable) ; l'interaction suivante auto-attendra sa cible.
    context.page.goto(full_url, wait_until="domcontentloaded")


@given('je me connecte avec mes identifiants utilisateur')
@when('je me connecte avec mes identifiants utilisateur')
def step_login_portal(context):
    """CONNECTE réellement le NAVIGATEUR (Playwright) et TERMINE sur l'accueil du portail (context.odoo_url), PAS sur le catalogue : pour cliquer un onglet de service (ex. « Ordinateurs », qui vit sur /myservices), NAVIGUE d'abord vers sa page avec « je navigue vers l'URL du portail "…" » — sinon le clic expire, l'onglet n'est pas là où le step d'auth t'a déposé (0020). Indispensable AVANT toute navigation sur une page du portail, sinon la session est anonyme et la page ne se rend pas.

    ⚠️ Délègue à `_base_helpers.playwright_login` — NE RÉIMPLÉMENTE JAMAIS l'authentification ici.
    Un doublon local a existé (avant le 2026-09-18) : il rendait `input[name='login']` seulement
    `state="attached"`, jamais `"visible"` — sur un formulaire replié derrière un SSO (Sapian), le
    champ reste attaché mais masqué, le `fill(force=True)` s'exécute en pure perte, et Playwright
    finit par expirer en attendant la navigation post-login (`Timeout 15000ms exceeded`) — mesuré
    en RUN RÉEL (résultat #1, cas « Refus de création d'un équipement… », staging Sapian) alors
    que le correctif SSO (`3ceee7c`) n'avait été appliqué qu'au chemin du CRAWL, jamais à ce step
    d'exécution — deux implémentations séparées du même geste, une seule corrigée."""
    playwright_login(context)
    context.page.goto(context.odoo_url, wait_until="domcontentloaded")


@then('une notification d\'erreur de validation est affichée dans l\'interface Odoo')
def step_validation_error_shown(context):
    # Délègue à `_base_helpers.validation_error_notification` — ce step réimplémentait le MÊME
    # sélecteur + la MÊME assertion en double (audit fiabilité, 2026-09-17), avec le défaut que le
    # helper partagé vient de corriger (assertion non-rétentative, `expect()` désormais).
    validation_error_notification(context.page)
