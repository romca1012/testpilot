# Spécification — La validation du panier donne un numéro de commande, un panier vide est refusé (banc d'agents web)

## Contexte technique

Application web locale de RÉFÉRENCE du banc d'agents web (lot Q2-b) : une petite boutique (connexion, produits, clients, panier, commandes), servie en local, connecteur `web` générique, aucune base de données ni back-office. Au début du cas l'application est dans son état INITIAL : panier vide, aucun client, aucune commande. Compte de test du projet : « testeur » (identifiants fournis par la configuration du projet, jamais écrits dans une spec). Vérification indépendante côté serveur : l'oracle HTTP du projet, requête `etat` (`GET /__etat`), qui rend les listes `commandes`, `enregistrements` et l'objet `panier`.

## Besoin

Valider un panier non vide affiche une confirmation avec un numéro de commande de la forme « CMD- » suivi de 4 chiffres, et le panier est ensuite vide. Valider un panier vide est refusé avec un message. Ce cas ne contrôle pas les montants et ne regarde que ce que l'écran affiche.

## Parcours

1. Se connecter avec le compte de test.
2. Valider le panier encore vide : ouvrir « Panier », cliquer « Valider la commande ».
3. Ajouter 1 « Souris sans fil », ouvrir « Panier », cliquer « Valider la commande ».
4. Rouvrir « Panier ».

## Critère de réussite

Étape 2 : le message « Le panier est vide. » est visible et aucune confirmation n'est affichée. Étape 3 : le titre « Commande confirmée » et un numéro de la forme « CMD-0001 » sont visibles. Étape 4 : « Votre panier est vide. » est visible.
