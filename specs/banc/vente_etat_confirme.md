# Spécification — Une commande confirmée passe à l'état « Bon de commande » (banc de mesure Odoo)

## Contexte technique

Instance Odoo Community de RÉFÉRENCE du banc de mesure (lot 04), base `banc`, données de démo, langue `fr_FR`.
Comptes de test : `banc_commercial` (Ventes / Utilisateur), `banc_manager` (Ventes / Administrateur, Stock,
Facturation). Module requis : `sale_management`.

## Besoin

Après confirmation, une commande de vente doit être à l'état `sale` (Bon de commande).

## Parcours

1. Créer un devis.
2. Le confirmer.
3. Lire son état.

## Critère de réussite

L'état de la commande est `sale`.
