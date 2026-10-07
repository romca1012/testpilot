# Spécification — Créer un client avec un nom valide (banc d'agents web)

## Contexte technique

Application web locale de RÉFÉRENCE du banc d'agents web (lot Q2-b) : une petite boutique (connexion, produits, clients, panier, commandes), servie en local, connecteur `web` générique, aucune base de données ni back-office. Au début du cas l'application est dans son état INITIAL : panier vide, aucun client, aucune commande. Compte de test du projet : « testeur » (identifiants fournis par la configuration du projet, jamais écrits dans une spec). Vérification indépendante côté serveur : l'oracle HTTP du projet, requête `etat` (`GET /__etat`), qui rend les listes `commandes`, `enregistrements` et l'objet `panier`.

## Besoin

Un client créé avec un nom valide doit être confirmé à l'écran ET figurer ensuite dans la liste des clients.

## Parcours

1. Se connecter avec le compte de test.
2. Ouvrir « Clients », cliquer « Nouveau client ».
3. Saisir le nom « Dupont SARL » et la ville « Lyon », puis cliquer « Enregistrer ».
4. Ouvrir la liste des clients.

## Critère de réussite

Le message « Le client « Dupont SARL » a été créé. » est visible, et la liste des clients contient une ligne avec « Dupont SARL » et « Lyon ».
