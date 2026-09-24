# Spécification — Ouvrir un onglet d'un formulaire ne déclenche aucun faux refus (banc de mesure Odoo)

## Contexte technique

Instance Odoo Community de RÉFÉRENCE du banc de mesure (lot 04), base `banc`, données de démo, langue `fr_FR`.
Comptes de test : `banc_commercial` (Ventes / Utilisateur), `banc_manager` (Ventes / Administrateur, Stock,
Facturation). Module requis : `sale_management`.

## Besoin

Cliquer sur un onglet d'un formulaire Odoo (notebook) ne change pas l'URL et ne soumet rien : le test ne doit pas accuser à tort le jeu de données (faux `donnee_invalide`, garde F7 du lot 11).

## Parcours

1. Se connecter.
2. Ouvrir la liste des devis, cliquer « Nouveau ».
3. Cliquer l'onglet « Autres informations ».

## Critère de réussite

L'onglet est affiché ; aucun refus de donnée n'est rapporté.
