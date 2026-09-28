"""Steps de gestion ERP Odoo (lot 08a, sous-lot 08b, C6) — le vocabulaire au-delà du portail :
ouvrir un formulaire par modèle technique, renseigner une relation, ajouter une ligne x2many,
enregistrer/annuler, cliquer un bouton d'action, valider un assistant, lire la barre d'état,
filtrer une liste.

Tous ici, jamais dans `generic/` (chaque step touche `context.odoo` et/ou un sélecteur DOM propre
au web client Odoo — voir `../generic/_generic_steps.py` pour le critère complet).

⚠️ **NON VÉRIFIÉ SUR BANC RÉEL** (2026-09-28) — voir la docstring de `_selecteurs.py` et le
rapport du lot 08 : cet environnement cloud n'a pas de démon Docker pour rejouer ces steps contre
une vraie instance Odoo avant de les figer. Chaque step affirmatif utilise `constater`/
`constater_texte` (jamais un `pass`) ; les tests unitaires de ce lot prouvent le MÉCANISME (avec
des pages Playwright simulées), pas l'exactitude contre un DOM Odoo réel — à confirmer par le
porteur avant une génération réelle contre le banc.
"""

from __future__ import annotations

from behave import given, then, when

from _base_helpers import (
    ElementIntrouvableError,
    PreconditionNonRemplieError,
    click_first_actionable,
    constater,
    constater_texte,
    fill_field,
    select_field_value,
)
from _selecteurs import id_depuis_url, odoo_attendre_inactif, odoo_url_action, selecteurs


def _resoudre_action_fenetre(context, modele: str) -> int:
    """L'id de la première action fenêtre (`ir.actions.act_window`) du modèle — résolution RPC,
    jamais devinée : un modèle sans action de fenêtre associée est un prérequis manquant (le test
    vise le mauvais modèle, ou l'action n'est pas installée sur cette instance), jamais un défaut
    applicatif à faire échouer en `non_conforme`."""
    Action = context.odoo.env["ir.actions.act_window"]
    ids = Action.search([("res_model", "=", modele)], limit=1)
    if not ids:
        raise PreconditionNonRemplieError(
            f"Aucune action de fenêtre trouvée pour le modèle '{modele}' — vérifiez le nom "
            "technique du modèle (pas son libellé affiché).")
    return ids[0]


@given('j\'ouvre le formulaire de création du modèle "{modele}"')
@when('j\'ouvre le formulaire de création du modèle "{modele}"')
def step_ouvrir_creation(context, modele):
    action_id = _resoudre_action_fenetre(context, modele)
    url = odoo_url_action(context, action=action_id, model=modele, view_type="form")
    context.page.goto(url, wait_until="domcontentloaded")
    odoo_attendre_inactif(context.page)
    context.last_record_model = modele
    context.last_record_ids = []  # pas encore créé — posé par « j'enregistre le document »


@given('j\'ouvre l\'enregistrement "{nom}" du modèle "{modele}"')
@when('j\'ouvre l\'enregistrement "{nom}" du modèle "{modele}"')
def step_ouvrir_enregistrement(context, nom, modele):
    Model = context.odoo.env[modele]
    trouves = Model.name_search(name=nom, operator="=", limit=1)
    if not trouves:
        trouves = Model.name_search(name=nom, operator="ilike", limit=1)
    if not trouves:
        raise PreconditionNonRemplieError(
            f"Aucun enregistrement nommé '{nom}' trouvé dans le modèle '{modele}'.")
    record_id = trouves[0][0]
    action_id = _resoudre_action_fenetre(context, modele)
    url = odoo_url_action(context, action=action_id, model=modele, view_type="form",
                          record_id=record_id)
    context.page.goto(url, wait_until="domcontentloaded")
    odoo_attendre_inactif(context.page)
    context.last_record_model = modele
    context.last_record_ids = [record_id]


@given('je renseigne la relation "{champ}" avec "{valeur}"')
@when('je renseigne la relation "{champ}" avec "{valeur}"')
def step_renseigner_relation(context, champ, valeur):
    # many2one : autocomplétion, « Rechercher plus… » déjà gérés par `select_field_value`
    # (mesuré en run réel, Parc IT, 2026-09-18 — voir sa docstring).
    select_field_value(context.page, valeur, champ)


@when('j\'ajoute une ligne à "{champ}" avec :')
def step_ajouter_ligne_x2many(context, champ):
    """`context.table` porte les colonnes `| champ | valeur |` de la ligne à ajouter — remplies
    DANS la ligne nouvellement ouverte (`.o_selected_row`, convention Odoo pour la ligne en cours
    d'édition d'une liste x2many), jamais sur la première ligne venue."""
    page = context.page
    conteneur = page.locator(f'.o_field_widget[name="{champ}"]')
    bouton_ajout = conteneur.locator(selecteurs("ligne_x2many_ajout", context.odoo_version)[0])
    click_first_actionable(page, [bouton_ajout], quoi=f"ajouter une ligne à '{champ}'")
    ligne = page.locator(".o_selected_row").first
    for ligne_table in context.table:
        fill_field(ligne, ligne_table["champ"], ligne_table["valeur"])


@when("j'enregistre le document")
def step_enregistrer_document(context):
    """Échec bruyant si l'id créé n'est pas lisible dans l'URL post-sauvegarde — mesuré en run
    réel (staging Parc IT, 2026-09-28) : le silence laissait `context.last_record_ids` vide, et
    le vrai problème ne se voyait que deux steps plus loin, en `IndexError` sur
    `_record_courant` (`_odoo_effets_steps.py`) — un step sans rapport avec la cause réelle.
    L'URL est dans le message : la prochaine mesure dira si `id_depuis_url` doit apprendre un
    nouveau motif, plutôt que de deviner un motif non observé."""
    page = context.page
    click_first_actionable(page, selecteurs("enregistrer", context.odoo_version),
                           quoi="bouton Enregistrer")
    odoo_attendre_inactif(page)
    id_cree = id_depuis_url(page.url)
    if id_cree is None:
        raise RuntimeError(
            "j'enregistre le document : aucun id d'enregistrement lisible dans l'URL après "
            f"l'enregistrement ({page.url!r}) — la sauvegarde a-t-elle réellement eu lieu ?")
    context.last_record_ids = [id_cree]


@when("j'annule les modifications")
def step_annuler_modifications(context):
    page = context.page
    click_first_actionable(page, selecteurs("ignorer", context.odoo_version),
                           quoi="bouton Ignorer/Annuler")
    odoo_attendre_inactif(page)


@when('je clique sur le bouton d\'action "{methode}"')
def step_bouton_action(context, methode):
    page = context.page
    candidats = selecteurs("bouton_action", context.odoo_version, methode=methode)
    # `ident=methode` : repli sur le libellé via la résolution adaptative déjà intégrée à
    # `click_first_actionable` (même mécanisme que `locate_field`/`navigate_menu`) si aucun
    # candidat technique n'est actionnable — c'est CE repli que le lot demande, pas une
    # réimplémentation locale.
    click_first_actionable(page, candidats, quoi=f"bouton d'action '{methode}'", ident=methode)
    odoo_attendre_inactif(page)


@when("je valide l'assistant")
@when("je confirme la boîte de dialogue")
def step_confirmer_dialogue(context):
    page = context.page
    click_first_actionable(page, selecteurs("dialogue_bouton_principal", context.odoo_version),
                           quoi="bouton principal de la boîte de dialogue")
    odoo_attendre_inactif(page)


@then('l\'étape affichée est "{libelle}"')
def step_etape_affichee(context, libelle):
    page = context.page
    loc = page.locator(selecteurs("barre_etat_courante", context.odoo_version)[0])
    constater_texte(loc, libelle,
                    message=f"Étape affichée sur la barre de statut : attendu '{libelle}'.")


@when('je filtre la liste "{menu}" par "{texte}"')
def step_filtrer_liste(context, menu, texte):
    page = context.page
    try:
        recherche = page.locator(".o_searchview_input")
        recherche.first.fill(texte)
        recherche.first.press("Enter")
    except Exception as exc:
        raise ElementIntrouvableError(
            f"Barre de recherche de la liste '{menu}' introuvable sur {page.url} : {exc}") from exc
    odoo_attendre_inactif(page)


@then('la liste affiche {n:d} enregistrement(s)')
def step_liste_n_enregistrements(context, n):
    page = context.page
    lignes = page.locator(".o_data_row")
    obtenu = lignes.count()
    constater(obtenu == n, f"Liste : attendu {n} enregistrement(s), obtenu {obtenu}.")
