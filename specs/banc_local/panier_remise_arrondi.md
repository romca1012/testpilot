# Spécification — La remise du panier est arrondie au centime et bornée de 0 à 100 % (banc d'agents web)

## Contexte technique

Application web locale de RÉFÉRENCE du banc d'agents web (lot Q2-b) : une petite boutique (connexion, produits, clients, panier, commandes), servie en local, connecteur `web` générique, aucune base de données ni back-office. Au début du cas l'application est dans son état INITIAL : panier vide, aucun client, aucune commande. Compte de test du projet : « testeur » (identifiants fournis par la configuration du projet, jamais écrits dans une spec). Vérification indépendante côté serveur : l'oracle HTTP du projet, requête `etat` (`GET /__etat`), qui rend les listes `commandes`, `enregistrements` et l'objet `panier`.

## Besoin

Le champ « Remise (%) » du panier applique une remise en pourcentage sur le sous-total HT ; le montant de remise est arrondi au centime (un demi-centime est arrondi vers le haut), puis la TVA de 18 % est calculée sur le total HT après remise et arrondie de la même façon. Une remise hors de 0 à 100 est refusée avec un message et ne change aucun total. Prix du catalogue : « Câble HDMI » 9,95 €.

## Parcours

1. Se connecter avec le compte de test.
2. Ajouter 1 « Câble HDMI », ouvrir « Panier », saisir la remise 10 et cliquer « Recalculer ».
3. Remettre la remise à 0 (« Recalculer »), puis saisir la remise 120 et cliquer « Recalculer ».

## Critère de réussite

Après l'étape 2 : remise 1,00 € (0,995 arrondi vers le haut) ; total HT après remise 8,95 € ; TVA (18 %) 1,61 € ; total TTC 10,56 €. Après l'étape 3 : le message « La remise doit être comprise entre 0 et 100. » est visible et le total TTC reste 11,74 € (9,95 € + TVA 1,79 €).
