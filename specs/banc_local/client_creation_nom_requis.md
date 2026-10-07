# Spécification — Un client sans nom est refusé avec un message visible (banc d'agents web)

## Contexte technique

Application web locale de RÉFÉRENCE du banc d'agents web (lot Q2-b) : une petite boutique (connexion, produits, clients, panier, commandes), servie en local, connecteur `web` générique, aucune base de données ni back-office. Au début du cas l'application est dans son état INITIAL : panier vide, aucun client, aucune commande. Compte de test du projet : « testeur » (identifiants fournis par la configuration du projet, jamais écrits dans une spec). Vérification indépendante côté serveur : l'oracle HTTP du projet, requête `etat` (`GET /__etat`), qui rend les listes `commandes`, `enregistrements` et l'objet `panier`.

## Besoin

Le nom d'un client est obligatoire : une création sans nom doit être REFUSÉE, avec un message d'erreur visible à côté du champ, et ne doit rien créer.

## Parcours

1. Se connecter avec le compte de test.
2. Ouvrir « Clients », cliquer « Nouveau client ».
3. Laisser « Nom du client » vide, saisir la ville « Lyon », cliquer « Enregistrer ».
4. Ouvrir la liste des clients.

## Critère de réussite

Le formulaire reste affiché avec le message « Le nom est obligatoire. » visible, et aucun client n'existe : la liste des clients est vide et l'état serveur ne contient aucun enregistrement.
