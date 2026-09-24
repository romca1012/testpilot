# Spécification — Confirmer une demande de prix crée un bon de commande (banc de mesure Odoo)

## Contexte technique

Instance Odoo Community de RÉFÉRENCE du banc de mesure (lot 04), base `banc`, données de démo, langue `fr_FR`.
Comptes de test : `banc_commercial` (Ventes / Utilisateur), `banc_manager` (Ventes / Administrateur, Stock,
Facturation). Module requis : `purchase`.

## Besoin

Confirmer une demande de prix fournisseur doit la passer à l'état `purchase` (Bon de commande).

## Parcours

1. Créer une demande de prix de 3 unités.
2. La confirmer.

## Critère de réussite

L'état de la commande d'achat est `purchase`.
