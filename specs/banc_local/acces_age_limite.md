# Spécification — Le contrôle d'accès est réservé aux 18 ans et plus (banc d'agents web)

## Contexte technique

Application web locale de RÉFÉRENCE du banc d'agents web (lot Q2-b) : une petite boutique (connexion, produits, clients, panier, commandes, contrôle d'accès), servie en local, connecteur `web` générique, aucune base de données ni back-office. Au début du cas l'application est dans son état INITIAL. Compte de test du projet : « testeur » (identifiants fournis par la configuration du projet, jamais écrits dans une spec). Le contrôle d'accès ne laisse aucune trace côté serveur : seule la page de résultat fait foi.

## Besoin

L'accès est réservé aux personnes de 18 ans et plus. Un client de moins de 18 ans est refusé avec le message « Accès refusé : il faut avoir 18 ans ou plus. » ; à 18 ans et plus, la page souhaite la bienvenue au client par son nom.

## Parcours

1. Se connecter avec le compte de test.
2. Ouvrir « Contrôle d'accès ».
3. Saisir « Dupont SARL » comme nom du client et 17 comme âge, cliquer « Vérifier l'accès ».
4. Revenir à « Contrôle d'accès », saisir « Dupont SARL » et 18, cliquer « Vérifier l'accès ».

## Critère de réussite

À 17 ans : le message « Accès refusé : il faut avoir 18 ans ou plus. » est visible. À 18 ans : le message « Bienvenue, Dupont SARL ! » est visible.
