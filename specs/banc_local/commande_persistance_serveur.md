# Spécification — Une commande confirmée est enregistrée côté serveur (banc d'agents web)

## Contexte technique

Application web locale de RÉFÉRENCE du banc d'agents web (lot Q2-b) : une petite boutique (connexion, produits, clients, panier, commandes), servie en local, connecteur `web` générique, aucune base de données ni back-office. Au début du cas l'application est dans son état INITIAL : panier vide, aucun client, aucune commande. Compte de test du projet : « testeur » (identifiants fournis par la configuration du projet, jamais écrits dans une spec). Vérification indépendante côté serveur : l'oracle HTTP du projet, requête `etat` (`GET /__etat`), qui rend les listes `commandes`, `enregistrements` et l'objet `panier`. Forme d'une commande : `numero`, puis `lignes`, une liste dont chaque ligne porte `nom` (le libellé du produit, p. ex. « Tapis de souris »), `produit` (son code interne, jamais un libellé) et `quantite`.

## Besoin

Quand l'écran confirme une commande, le serveur doit l'avoir réellement enregistrée : l'écran seul ne prouve rien, la vérification se fait sur l'état serveur (oracle `etat`). Ce cas ne contrôle pas les montants.

## Parcours

1. Se connecter avec le compte de test ; relever que l'état serveur ne contient aucune commande.
2. Ajouter 3 « Tapis de souris », ouvrir « Panier », cliquer « Valider la commande ».
3. Relever le numéro de commande affiché, puis lire l'état serveur.

## Critère de réussite

L'état serveur contient exactement 1 commande, dont le numéro est celui affiché et dont l'unique ligne porte sur « Tapis de souris » en quantité 3 ; le panier côté serveur est vide.
