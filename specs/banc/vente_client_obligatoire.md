# Spécification — Une commande sans client est refusée (banc de mesure Odoo)

## Contexte technique

Instance Odoo Community de RÉFÉRENCE du banc de mesure (lot 04), base `banc`, données de démo, langue `fr_FR`.
Comptes de test : `banc_commercial` (Ventes / Utilisateur), `banc_manager` (Ventes / Administrateur, Stock,
Facturation). Module requis : `sale_management`.

## Besoin

Le client est obligatoire sur une commande de vente : une commande sans client doit être refusée.

## Parcours

1. Tenter de créer une commande de vente sans renseigner le client.

## Critère de réussite

La création est refusée (aucune commande sans client n'est enregistrée).
