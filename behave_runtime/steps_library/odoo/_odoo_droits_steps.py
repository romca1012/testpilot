"""Utilisateurs, sociétés, droits (lot 08a, sous-lot 08d) — au-delà de « je me connecte en tant
que "<libellé>" » (déjà partagé avec le lot 07b-1, `_odoo_steps.py::step_connect_as`, non
dupliqué ici) : refus d'accès et société de travail (multi-société).

⚠️ **NON VÉRIFIÉ SUR BANC RÉEL** — mêmes réserves que le reste du lot 08 (voir `_selecteurs.py`).
"""

from __future__ import annotations

from behave import given, then, when

from _base_helpers import ElementIntrouvableError, constater, constater_visible
from _odoo_steps import _exiger_enregistrement_en_contexte
from _selecteurs import odoo_attendre_inactif, selecteurs


@then('l\'action "{methode}" est refusée pour cet utilisateur')
def step_action_refusee(context, methode):
    """Un refus attendu n'est PAS un `blocked` (échec technique) : c'est un CONSTAT — deux
    preuves, jamais une seule :
    1. Une erreur d'accès VISIBLE à l'écran (le compte a bien tenté l'action, l'UI le dit).
    2. L'appel RPC de `methode`, tenté directement sur le document courant, échoue lui aussi —
       la preuve que le refus est réellement appliqué CÔTÉ SERVEUR, pas seulement un bouton
       grisé côté client que l'utilisateur aurait pu contourner autrement.
    """
    page = context.page
    erreur = page.locator(selecteurs("notification_erreur", context.odoo_version)[0])
    constater_visible(erreur, f"Aucune erreur d'accès visible à l'écran après '{methode}'.")

    _exiger_enregistrement_en_contexte(
        context, "Aucun enregistrement en contexte — impossible de vérifier le refus côté RPC.",
        avec_modele=True)
    Model = context.odoo.env[context.last_record_model]
    refuse = False
    try:
        getattr(Model.browse(context.last_record_ids[0]), methode)()
    except Exception:
        refuse = True
    constater(refuse,
             f"L'appel RPC direct de '{methode}' a RÉUSSI malgré le refus visible à l'écran — "
             "l'action n'est pas réellement bloquée côté serveur.")


@given('je travaille dans la société "{nom}"')
@when('je travaille dans la société "{nom}"')
def step_travailler_dans_la_societe(context, nom):
    page = context.page
    try:
        page.locator(".o_switch_company_menu, .o_menu_systray .dropdown-toggle").first.click(
            timeout=5000)
        page.get_by_text(nom, exact=False).first.click(timeout=5000)
    except Exception as exc:
        raise ElementIntrouvableError(
            f"Sélecteur de société introuvable, ou société '{nom}' absente, sur {page.url} : "
            f"{exc}") from exc
    odoo_attendre_inactif(page)
