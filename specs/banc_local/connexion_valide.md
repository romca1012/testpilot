# Spécification — Un utilisateur connu se connecte et accède aux produits (banc d'agents web)

## Contexte technique

Application web locale de RÉFÉRENCE du banc d'agents web (lot Q2-b) : une petite boutique (connexion, produits, clients, panier, commandes), servie en local, connecteur `web` générique, aucune base de données ni back-office. Au début du cas l'application est dans son état INITIAL : panier vide, aucun client, aucune commande. Compte de test du projet : « testeur » (identifiants fournis par la configuration du projet, jamais écrits dans une spec). Vérification indépendante côté serveur : l'oracle HTTP du projet, requête `etat` (`GET /__etat`), qui rend les listes `commandes`, `enregistrements` et l'objet `panier`.

## Besoin

Un utilisateur qui saisit ses identifiants corrects sur la page de connexion doit accéder à la liste des produits.

## Parcours

1. Ouvrir la page d'accueil de l'application : elle mène à la page de connexion.
2. Saisir l'identifiant « testeur » et son mot de passe, puis cliquer « Se connecter ».

## Critère de réussite

La page « Produits » s'affiche (titre de niveau 1 « Produits ») et le texte « Connecté en tant que testeur » est visible.
