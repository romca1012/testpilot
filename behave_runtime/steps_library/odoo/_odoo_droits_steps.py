"""Utilisateurs, sociétés, droits (lot 08a, sous-lot 08d) — au-delà de « je me connecte en tant
que "<libellé>" » (déjà partagé avec le lot 07b-1, `_odoo_steps.py::step_connect_as`, non
dupliqué ici) : refus d'accès et société de travail (multi-société).

⚠️ **NON VÉRIFIÉ SUR BANC RÉEL** — mêmes réserves que le reste du lot 08 (voir `_selecteurs.py`).
"""

from __future__ import annotations

import re

from behave import given, then, when

from _base_helpers import (ConstatNonConcluantError, ElementIntrouvableError, constater, constater_visible,
                           derriere_interrupteur, session_rpc_du_compte_qui_agit)
from _odoo_steps import _exiger_enregistrement_en_contexte
from _selecteurs import odoo_attendre_inactif, selecteurs

_REFUS_D_ACCES = re.compile(r"\bAccess(Error|Denied)\b")
# Revue du lot (point 5) : dans le MESSAGE, seulement en tête (« odoo.exceptions.AccessError: … ») — ailleurs, il peut contenir
# des données du test.
_REFUS_D_ACCES_EN_TETE = re.compile(r"^\s*(odoo\.exceptions\.)?Access(Error|Denied)\b")


def _est_un_refus_d_acces(exc: BaseException) -> bool:
    """Le serveur a refusé PAR DROITS : classe `AccessError`/`AccessDenied`, ou nom d'exception Odoo transmis par l'erreur RPC
    (`info["data"]["name"]`, ou en tête de son message, écrit par le serveur — jamais par l'agent)."""
    if type(exc).__name__ in ("AccessError", "AccessDenied"):
        return True
    info = getattr(exc, "info", None)
    nom = ((info or {}).get("data") or {}).get("name", "") if isinstance(info, dict) else ""
    return bool(_REFUS_D_ACCES.search(str(nom)) or _REFUS_D_ACCES_EN_TETE.match(str(exc)))


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
    if methode.startswith("_"):
        # Revue du lot (point 5) : Odoo refuse l'appel distant d'une méthode PRIVÉE à TOUT utilisateur (« Private methods
        # cannot be called remotely », un `AccessError`) — le refus ne prouverait rien sur les droits de CE compte.
        raise RuntimeError(f"« {methode} » est une méthode privée : Odoo la refuse à tout utilisateur, son refus ne prouve "
                           "rien sur les droits. Nommez la méthode publique de l'action (ex. `action_confirm`).")
    # A76 : le refus se prouve avec le compte qui AGIT — le principal (A73) réussirait l'appel sur une application saine.
    Model = session_rpc_du_compte_qui_agit(context).env[context.last_record_model]
    identifiant = context.last_record_ids[0]
    # A76 (revue de l'étape 4, 2026-10-21) : depuis A73 l'enregistrement est créé par le principal ; un compte qui ne le VOIT pas
    # (règle « ses propres documents ») est refusé dès la lecture — ce refus ne dit rien de l'ACTION. Non concluant, jamais vert.
    try:
        lisible = bool(Model.search_count([("id", "=", identifiant)]))
    except Exception as exc:
        if not _est_un_refus_d_acces(exc):
            raise
        lisible = False
    if not lisible:
        raise ConstatNonConcluantError(
            f"Ce compte ne voit pas l'enregistrement {context.last_record_model} #{identifiant} : le refus de '{methode}' ne "
            "peut pas être attribué à l'action. Créez l'enregistrement avec ce compte (ou un enregistrement qu'il voit).")
    refuse = False
    try:
        getattr(Model.browse(identifiant), methode)()
    except Exception as exc:
        # Lot VH-04 (audit V7) : seul un REFUS DE DROITS du serveur prouve le refus. Avant, TOUTE exception comptait — une
        # méthode mal orthographiée, une panne RPC, un enregistrement verrouillé passaient pour « l'action est refusée ».
        # Toute autre erreur remonte telle quelle (le test n'a rien prouvé : erreur technique, jamais un vert).
        if not _est_un_refus_d_acces(exc):
            raise
        refuse = True
    constater(refuse,
             f"L'appel RPC direct de '{methode}' a RÉUSSI malgré le refus visible à l'écran — "
             "l'action n'est pas réellement bloquée côté serveur.")


def _le_compte_qui_agit_voit(context) -> tuple[bool, str]:
    """(ce compte voit-il l'enregistrement courant ?, sa description) — lu avec la session du compte qui AGIT (A76) ; un
    refus de lecture vaut « ne voit pas ». L'enregistrement doit EXISTER pour le principal, qui voit tout (A73) : sinon
    « ne voit pas » serait vrai pour un enregistrement disparu — non concluant, jamais vert."""
    _exiger_enregistrement_en_contexte(
        context, "Aucun enregistrement en contexte — impossible de vérifier ce que voit ce compte.", avec_modele=True)
    modele, identifiant = context.last_record_model, context.last_record_ids[0]
    if not context.odoo.env[modele].search_count([("id", "=", identifiant)]):
        raise ConstatNonConcluantError(f"{modele} #{identifiant} n'existe plus (le compte principal ne le voit pas) : ce "
                                       "que voit ce compte ne peut pas être vérifié.")
    # Revue (bloquant) : la session du compte s'ouvre HORS du `try` — un refus de CONNEXION (`AccessDenied` : mot de passe
    # changé, compte archivé, délai d'Odoo après 5 échecs de connexion) remonte en erreur technique, jamais en « ne voit pas ».
    lecture = session_rpc_du_compte_qui_agit(context).env[modele]
    try:
        vu = bool(lecture.search_count([("id", "=", identifiant)]))
    except Exception as exc:
        if not _est_un_refus_d_acces(exc):
            raise
        vu = False
    return vu, f"{modele} #{identifiant}"


@then("cet utilisateur voit l'enregistrement")
@derriere_interrupteur("TESTPILOT_GENERATION_PAR_COMPTE")
def step_utilisateur_voit_enregistrement(context):
    """A89 : ce que voit le compte du test se prouve AVEC CE COMPTE (lecture serveur faite par lui), jamais par la session des
    vérifications — le compte principal voit tout, son « je la vois » passait pour celui du lecteur."""
    vu, quoi = _le_compte_qui_agit_voit(context)
    constater(vu, f"{quoi} n'est PAS visible pour ce compte — le serveur le lui cache.")


@then("cet utilisateur ne voit pas l'enregistrement")
@derriere_interrupteur("TESTPILOT_GENERATION_PAR_COMPTE")
def step_utilisateur_ne_voit_pas_enregistrement(context):
    """A89 : le pendant — un enregistrement que ce compte ne doit pas voir ; il existe (le principal le voit) mais le serveur
    le refuse à CE compte."""
    vu, quoi = _le_compte_qui_agit_voit(context)
    constater(not vu, f"{quoi} est VISIBLE pour ce compte alors qu'il ne devrait pas l'être.")


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
