# Spécification — Valider une facture la passe à l'état « Comptabilisé » (banc de mesure Odoo)

## Contexte technique

Instance Odoo Community de RÉFÉRENCE du banc de mesure (lot 04), base `banc`, données de démo, langue `fr_FR`.
Comptes de test : `banc_commercial` (Ventes / Utilisateur), `banc_manager` (Ventes / Administrateur, Stock,
Facturation). Module requis : `account`.

## Besoin

Valider (comptabiliser) une facture client brouillon doit la faire passer à l'état `posted`.

## Parcours

1. Créer une facture client brouillon d'une ligne de 50 €.
2. La valider.

## Critère de réussite

L'état de la facture est `posted`.
