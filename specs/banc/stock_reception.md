# Spécification — Un achat confirmé crée une réception (banc de mesure Odoo)

## Contexte technique

Instance Odoo Community de RÉFÉRENCE du banc de mesure (lot 04), base `banc`, données de démo, langue `fr_FR`.
Comptes de test : `banc_commercial` (Ventes / Utilisateur), `banc_manager` (Ventes / Administrateur, Stock,
Facturation). Module requis : `stock`.

## Besoin

Confirmer un achat de produits stockables doit créer la réception (bon d'entrée) attendue.

## Parcours

1. Créer une demande de prix de 3 unités.
2. La confirmer.

## Critère de réussite

Une réception est liée à la commande d'achat.
