---
description: Lot 08 — Odoo ERP au-delà du portail : version, sélecteurs par version, vocabulaire de gestion, effets en chaîne (C6, C7)
argument-hint: "[sous-lot : a | b | c | d — vide = tous, dans l'ordre]"
---

# Lot 08 — Vocabulaire ERP Odoo

Lis `CLAUDE.md`, C6-C7 du plan. Décisions requises : **D8, D9**. Dépend du lot 04 (banc : tout
sélecteur est relevé et testé sur 16.0, 17.0 et 18.0). Sous-lot : `$ARGUMENTS`.

## Pourquoi

La bibliothèque Odoo couvre « soumettre un formulaire, vérifier l'enregistrement ». Un ERP se
teste sur des flux de gestion : boutons de workflow, barre d'état, lignes de commande, assistants,
effets sur d'autres documents. Sans vocabulaire, l'agent réécrit ces gestes en Python à chaque cas,
ce qui explique une grande partie des erreurs techniques au premier passage.

## À lire d'abord

- `behave_runtime/steps_library/odoo/_odoo_steps.py`, `_base_helpers.py` (`locate_field`,
  `navigate_menu`, `navigate`, `click_first_actionable`, gestion des dialogues `.o_dialog`).
- `src/testpilot/connectors/odoo.py` (formes d'URL `/odoo/…` et `/web#…`), `odoo_login.py`.
- `tests/test_odoo_connector.py`, `tests/test_calibration_ecriture_odoo.py`.

## 08a — Détection de version et table de sélecteurs (C7)

1. `before_all` (connecteur odoo) : lit `server_version_info` via la session RPC (ou
   `/web/webclient/version_info`), pose `context.odoo_version = (majeur, mineur)`.
2. Module `odoo/_selecteurs.py` : **une seule** table `{clé logique: {version: [sélecteurs
   candidats]}}` — `bouton_action`, `barre_etat_courante`, `ligne_x2many_ajout`,
   `ligne_x2many_cellule`, `dialogue`, `dialogue_bouton_principal`, `notification_erreur`,
   `indicateur_chargement`, `fil_ariane`, `recherche_facette`, `enregistrer`, `ignorer`.
   Candidats de départ à **vérifier sur le banc** avant de les figer (relève le DOM réel de
   chaque version, colle les preuves dans le rapport) :
   `.o_form_view button[name="<methode>"]`, `.o_statusbar_status [aria-checked="true"]`,
   `.o_statusbar_status .o_arrow_button_current`, `.o_field_x2many_list_row_add a`,
   `.modal .modal-footer .btn-primary`, `.o_form_button_save`, `.o_loading_indicator`.
3. Helpers `odoo_attendre_inactif(page)` (indicateur de chargement masqué) et
   `odoo_url_action(context, …)` qui produit `/odoo/…` (≥ 17.2) ou `/web#…`.

## 08b — Steps de gestion (C6)

Tous dans `odoo/`, jamais dans `generic/`. Chaque step d'action s'appuie sur les **noms
techniques** (attribut `name`), avec repli par libellé tracé dans les paliers. Chaque step
affirmatif utilise `constater_*` et a un test de falsifiabilité sur le banc.

- `j'ouvre le formulaire de création du modèle "<modèle>"` /
  `j'ouvre l'enregistrement "<nom>" du modèle "<modèle>"` (résolution de l'action par RPC) ;
- `je renseigne la relation "<champ>" avec "<valeur>"` (many2one, autocomplétion, « Rechercher
  plus… » déjà géré par les helpers) ;
- `j'ajoute une ligne à "<champ x2many>" avec :` + table Gherkin `| champ | valeur |` ;
- `j'enregistre le document` / `j'annule les modifications` ;
- `je clique sur le bouton d'action "<méthode>"` (ex. `action_confirm`), repli sur le libellé ;
- `je valide l'assistant` / `je confirme la boîte de dialogue` ;
- `l'étape affichée est "<libellé>"` (UI) ;
- `je filtre la liste "<menu>" par "<texte>"` / `la liste affiche <n> enregistrement(s)`.

## 08c — Effets vérifiés côté serveur (C6)

Steps RPC, tous sur `last_record_ids` / `last_record_model` (lot 01) :

- `l'état technique de ce document est "<valeur>"` (champ `state` ou champ de statut déclaré) ;
- `le champ "<champ>" de ce document vaut <nombre>` avec tolérance d'arrondi de la devise ;
- `ce document a <n> "<modèle lié>" lié(s) par "<champ>"` (ex. `stock.picking` via
  `picking_ids`) et `le document lié "<modèle>" est à l'état "<valeur>"` ;
- `la facture liée est comptabilisée` (raccourci documenté de la règle précédente) ;
- `un rapport PDF "<nom de rapport>" est généré pour ce document` (téléchargement réel via
  l'UI, contrôle `%PDF` et texte extrait).

## 08d — Utilisateurs, sociétés, droits

- `je me connecte en tant que "<libellé>"` (D8, partagé avec le lot 07b) ;
- `l'action "<méthode>" est refusée pour cet utilisateur` : affirme une erreur d'accès **visible**
  (dialogue d'erreur Odoo) **et** l'absence d'effet côté RPC — un refus attendu n'est pas un
  `blocked` : c'est un constat en `Alors` ;
- `je travaille dans la société "<nom>"` (sélecteur de société, multi-société).

## Tests exigés

- Conformité Odoo sur le banc (`-m conformance_odoo`, nouveau marqueur exclu par défaut) :
  scénario de bout en bout **devis → commande → livraison → facture comptabilisée** sur 16/17/18.
- Falsifiabilité : chaque défaut de `tp_bugs_injectes` fait échouer au moins un scénario de
  conformité, avec la cause `assertion_mismatch` et un step `then`.
- Table de sélecteurs : un test vérifie que chaque clé a une entrée pour chaque version de D9.

## Critères d'acceptation

- [ ] Le flux bout en bout s'écrit sans aucun step Python propre au cas.
- [ ] I1 = 0 sur le banc pour les défauts couverts par ces steps (mesure dans le rapport).

Rapport par sous-lot au format `CLAUDE.md` §10 ; lance `verdict-reviewer`.
