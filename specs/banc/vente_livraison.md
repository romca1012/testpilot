# Spécification — Confirmer un devis crée un bon de livraison (banc de mesure Odoo)

## Contexte technique

Instance Odoo Community de RÉFÉRENCE du banc de mesure (lot 04), base `banc`, données de démo, langue `fr_FR`.
Comptes de test : `banc_commercial` (Ventes / Utilisateur), `banc_manager` (Ventes / Administrateur, Stock,
Facturation). Module requis : `sale_management`.

## Besoin

Confirmer un devis de vente de produits livrables doit créer le bon de livraison correspondant.

## Parcours

1. Créer un devis de 2 unités d'un produit pour un client.
2. Le confirmer.

## Critère de réussite

Un bon de livraison est lié à la commande confirmée.
