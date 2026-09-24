# Spécification — Créer une commande augmente le nombre de commandes de 1 (banc de mesure Odoo)

## Contexte technique

Instance Odoo Community de RÉFÉRENCE du banc de mesure (lot 04), base `banc`, données de démo, langue `fr_FR`.
Comptes de test : `banc_commercial` (Ventes / Utilisateur), `banc_manager` (Ventes / Administrateur, Stock,
Facturation). Module requis : `sale_management`.

## Besoin

Créer une commande de vente doit augmenter de 1 le nombre de commandes (comptage cloisonné au scénario).

## Parcours

1. Relever le nombre de commandes.
2. En créer une.
3. Comparer.

## Critère de réussite

Le nombre total de commandes augmente de 1.
