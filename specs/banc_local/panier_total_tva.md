# Spécification — Le total du panier applique la TVA à 18 % et arrondit au centime (banc d'agents web)

## Contexte technique

Application web locale de RÉFÉRENCE du banc d'agents web (lot Q2-b) : une petite boutique (connexion, produits, clients, panier, commandes), servie en local, connecteur `web` générique, aucune base de données ni back-office. Au début du cas l'application est dans son état INITIAL : panier vide, aucun client, aucune commande. Compte de test du projet : « testeur » (identifiants fournis par la configuration du projet, jamais écrits dans une spec). Vérification indépendante côté serveur : l'oracle HTTP du projet, requête `etat` (`GET /__etat`), qui rend les listes `commandes`, `enregistrements` et l'objet `panier`.

## Besoin

Le panier calcule : total d'une ligne = quantité × prix unitaire ; sous-total HT = somme des lignes ; TVA = 18 % du total HT après remise, arrondie au centime (un demi-centime est arrondi vers le haut) ; total TTC = total HT après remise + TVA. Aucune remise dans ce cas. Prix du catalogue : « Clavier mécanique » 49,90 € ; « Câble HDMI » 9,95 €.

## Parcours

1. Se connecter avec le compte de test.
2. Sur « Produits », ajouter 2 « Clavier mécanique », puis ajouter 1 « Câble HDMI ».
3. Ouvrir « Panier ».
4. Mettre la quantité du « Câble HDMI » à 0 puis cliquer « Recalculer », puis faire de même pour le « Clavier mécanique ».

## Critère de réussite

Après l'étape 3 : total de la ligne « Clavier mécanique » 99,80 € ; total de la ligne « Câble HDMI » 9,95 € ; sous-total HT 109,75 € ; TVA (18 %) 19,76 € ; total TTC 129,51 €. Après l'étape 4 : le message « Votre panier est vide. » est visible et le total TTC est 0,00 €.
