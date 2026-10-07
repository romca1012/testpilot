# Spécification — La longueur maximale du nom d'un client est appliquée (banc d'agents web)

## Contexte technique

Application web locale de RÉFÉRENCE du banc d'agents web (lot Q2-b) : une petite boutique (connexion, produits, clients, panier, commandes), servie en local, connecteur `web` générique, aucune base de données ni back-office. Au début du cas l'application est dans son état INITIAL : panier vide, aucun client, aucune commande. Compte de test du projet : « testeur » (identifiants fournis par la configuration du projet, jamais écrits dans une spec). Vérification indépendante côté serveur : l'oracle HTTP du projet, requête `etat` (`GET /__etat`), qui rend les listes `commandes`, `enregistrements` et l'objet `panier`.

## Besoin

Le nom d'un client est limité à 40 caractères : 41 caractères sont refusés avec un message visible et ne créent rien ; 40 caractères sont acceptés.

## Parcours

1. Se connecter avec le compte de test.
2. Ouvrir « Clients », cliquer « Nouveau client ».
3. Saisir comme nom 41 fois la lettre « N », cliquer « Enregistrer ».
4. Recommencer avec un nom de 40 fois la lettre « N ».

## Critère de réussite

Avec 41 caractères : le message « Le nom ne doit pas dépasser 40 caractères. » est visible et aucun client n'est créé. Avec 40 caractères : le message « a été créé. » est visible.
