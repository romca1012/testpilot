# Spécification — Un mot de passe erroné est refusé avec un message visible (banc d'agents web)

## Contexte technique

Application web locale de RÉFÉRENCE du banc d'agents web (lot Q2-b) : une petite boutique (connexion, produits, clients, panier, commandes), servie en local, connecteur `web` générique, aucune base de données ni back-office. Au début du cas l'application est dans son état INITIAL : panier vide, aucun client, aucune commande. Compte de test du projet : « testeur » (identifiants fournis par la configuration du projet, jamais écrits dans une spec). Vérification indépendante côté serveur : l'oracle HTTP du projet, requête `etat` (`GET /__etat`), qui rend les listes `commandes`, `enregistrements` et l'objet `panier`.

## Besoin

Un utilisateur qui saisit un mot de passe erroné ne doit pas être connecté : la page de connexion reste affichée avec un message d'erreur. Ce cas ne s'authentifie pas au préalable : il teste la page de connexion elle-même.

## Parcours

1. Ouvrir la page de connexion de l'application.
2. Saisir l'identifiant « testeur » et le mot de passe « mauvais-mot-de-passe-1 », puis cliquer « Se connecter ».

## Critère de réussite

Le message « Identifiant ou mot de passe incorrect. » est visible, le formulaire de connexion est toujours affiché et le titre « Produits » n'apparaît pas.
