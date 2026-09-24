# Spécification — L'espace personnel du portail est accessible (banc de mesure Odoo)

## Contexte technique

Instance Odoo Community de RÉFÉRENCE du banc de mesure (lot 04), base `banc`, données de démo, langue `fr_FR`.
Comptes de test : `banc_commercial` (Ventes / Utilisateur), `banc_manager` (Ventes / Administrateur, Stock,
Facturation). Module requis : `sale_management`.

## Besoin

Un utilisateur connecté doit accéder à son espace personnel du portail (`/my`).

## Parcours

1. Se connecter.
2. Ouvrir `/my`.

## Critère de réussite

La page `/my` s'affiche sans redirection vers la connexion.
