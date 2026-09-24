# Spécification — Un commercial ne supprime pas une commande confirmée (banc de mesure Odoo)

## Contexte technique

Instance Odoo Community de RÉFÉRENCE du banc de mesure (lot 04), base `banc`, données de démo, langue `fr_FR`.
Comptes de test : `banc_commercial` (Ventes / Utilisateur), `banc_manager` (Ventes / Administrateur, Stock,
Facturation). Module requis : `sale_management`.

## Besoin

Un utilisateur Ventes / Utilisateur ne doit pas pouvoir supprimer une commande de vente confirmée.

## Parcours

1. En tant que `banc_commercial`, créer puis confirmer une commande.
2. Tenter de la supprimer avec le même compte.

## Critère de réussite

La suppression est refusée et la commande existe toujours.
