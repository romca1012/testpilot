# Spécification — Un champ requis vide affiche une erreur visible (banc de mesure Odoo)

## Contexte technique

Instance Odoo Community de RÉFÉRENCE du banc de mesure (lot 04), base `banc`, données de démo, langue `fr_FR`.
Comptes de test : `banc_commercial` (Ventes / Utilisateur), `banc_manager` (Ventes / Administrateur, Stock,
Facturation). Module requis : `sale_management`.

## Besoin

Confirmer un devis sans client depuis l'interface doit afficher un message d'erreur de validation.

## Parcours

1. Se connecter.
2. Ouvrir Ventes / Commandes / Devis.
3. Cliquer « Nouveau » puis « Confirmer » sans client.

## Critère de réussite

Une notification d'erreur de validation est visible.
