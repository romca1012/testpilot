# Spécification — Enregistrer un devis sans client est refusé avec un message visible (banc de mesure Odoo)

## Contexte technique

Instance Odoo Community de RÉFÉRENCE du banc de mesure (lot 04), base `banc`, données de démo, langue `fr_FR`.
Comptes de test : `banc_commercial` (Ventes / Utilisateur), `banc_manager` (Ventes / Administrateur, Stock,
Facturation). Module requis : `sale_management`.

## Besoin

Enregistrer un devis sans client depuis l'interface doit être REFUSÉ par Odoo avec un message visible : c'est un vrai refus de sauvegarde du back-office (l'URL ne change pas), à ne pas confondre avec une donnée de test fautive.

## Parcours

1. Se connecter.
2. Ouvrir la liste des devis, cliquer « Nouveau ».
3. Cliquer « Enregistrer » sans client.

## Critère de réussite

Une notification d'erreur de validation est visible.
