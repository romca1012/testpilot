# Spécification — La recherche filtre la liste des produits (banc d'agents web)

## Contexte technique

Application web locale de RÉFÉRENCE du banc d'agents web (lot Q2-b) : une petite boutique (connexion, produits, clients, panier, commandes), servie en local, connecteur `web` générique, aucune base de données ni back-office. Au début du cas l'application est dans son état INITIAL : panier vide, aucun client, aucune commande. Compte de test du projet : « testeur » (identifiants fournis par la configuration du projet, jamais écrits dans une spec). Vérification indépendante côté serveur : l'oracle HTTP du projet, requête `etat` (`GET /__etat`), qui rend les listes `commandes`, `enregistrements` et l'objet `panier`.

## Besoin

Le champ de recherche de la liste des produits doit ne garder que les produits dont le nom contient le texte saisi (sans tenir compte des majuscules), et dire clairement quand rien ne correspond. Le catalogue contient 6 produits, dont deux noms contiennent « souris » : « Souris sans fil » et « Tapis de souris ».

## Parcours

1. Se connecter avec le compte de test.
2. Sur la page « Produits », saisir « souris » dans « Rechercher un produit » et cliquer « Rechercher ».
3. Relancer une recherche avec le texte « zzz ».

## Critère de réussite

Pour « souris » : exactement 2 produits sont listés, « Souris sans fil » et « Tapis de souris » ; « Clavier mécanique » n'est pas affiché. Pour « zzz » : aucun produit n'est listé et le message « Aucun produit ne correspond à « zzz ». » est visible.
