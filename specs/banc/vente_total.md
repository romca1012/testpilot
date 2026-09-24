# Spécification — Le total d'une commande est la somme de ses lignes (banc de mesure Odoo)

## Contexte technique

Instance Odoo Community de RÉFÉRENCE du banc de mesure (lot 04), base `banc`, données de démo, langue `fr_FR`.
Comptes de test : `banc_commercial` (Ventes / Utilisateur), `banc_manager` (Ventes / Administrateur, Stock,
Facturation). Module requis : `sale_management`.

## Besoin

Le montant total d'une commande de vente doit être exactement la somme des totaux de ses lignes.

## Parcours

1. Créer un devis de 2 unités d'un produit à 100 € sans taxe.
2. Lire son total et celui de ses lignes.

## Critère de réussite

`amount_total` égale la somme des `price_total` des lignes, au centime.
