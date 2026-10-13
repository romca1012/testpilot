# Mesure sans IA du step « le nombre affiché pour … vaut … » — méthode (2026-10-13)

Complète `banc-agents-2026-10-13-pt03-step-nombre-sans-ia.md` (lot PT-03 des paramètres de test). Décision du porteur du
2026-10-13 : vérifier d'abord le step lui-même, sans dépense (« option A ») ; la mesure avec l'IA (premier essai, coût,
faux verts sur des tests GÉNÉRÉS) sera groupée avec la campagne du lot PT-02d (« option C »). D'ici là l'interrupteur
`TESTPILOT_STEP_NOMBRE` reste éteint.

## Ce qui a été joué

Les deux cas à montants du banc d'agents web (`specs/banc_local/`), deux tests écrits À LA MAIN par cas, rejoués par
`--generations-depuis` : aucune génération, aucun appel à l'IA (aucune clé dans l'environnement), coût 0 $. Essai 1 : les
valeurs écrites comme la spécification (« 129,51 € »). Essai 2 : les mêmes valeurs écrites autrement (« 129.51 EUR »,
« 1 EUR », « 0 € »). Chaque test est joué sur l'application saine puis avec le défaut `total_faux` (total TTC majoré de 1 %).

```bash
python scripts/banc_agents.py --reel --plafond-cout 0.5 --essais 2 --cas panier_total_tva,panier_remise_arrondi \
    --generations-depuis <dossier des quatre tests> --etiquette pt03-step-nombre-sans-ia
```

## Résultat

8 jeux sur 8 conformes à l'attendu écrit par un humain (`attendus.yaml`) : 4 `conforme` sur l'application saine, 4
`non_conforme` sous `total_faux`. Aucun faux vert, aucun faux rouge, aucun non concluant — dans les deux écritures.

## Ce que cette mesure ne dit pas

- Si l'IA emploie bien ce step quand elle écrit un test, ni ce que cela change au coût et au premier essai : option C.
- L'échantillon est petit (4 jeux fautifs : intervalle à 95 % de 0 à 49 % sur le taux de faux verts).
- Constat annexe : les trois tests GÉNÉRÉS le 2026-10-07 pour `panier_total_tva` échouaient sur leurs gestes (le second
  produit était cherché sur la page du panier). Les gestes de ce cas ont donc été écrits à la main ici ; ceux de
  `panier_remise_arrondi` sont repris d'un test généré.

## Les quatre tests joués

### banc-agents-panier_remise_arrondi-t1

```gherkin
# language: fr
Fonctionnalité: La remise du panier est arrondie au centime et bornée de 0 à 100 %

  Scénario: Remise arrondie au centime et rejetée hors bornes
    Soit j'accède à la page d'accueil de l'application
    Et j'ouvre la page "/produits"
    Et je clique sur le bouton "Ajouter Câble HDMI au panier"
    Et j'ouvre la page "/panier"
    Et je renseigne le champ "remise" avec la valeur "10"
    Et je clique sur le bouton "Recalculer"
    Alors le nombre affiché pour "Remise (10 %)" vaut "1,00 €"
    Et le nombre affiché pour "Total HT après remise" vaut "8,95 €"
    Et le nombre affiché pour "TVA (18 %)" vaut "1,61 €"
    Et le nombre affiché pour "Total TTC" vaut "10,56 €"
    Quand je renseigne le champ "remise" avec la valeur "0"
    Et je clique sur le bouton "Recalculer"
    Et je renseigne le champ "remise" avec la valeur "120"
    Et je clique sur le bouton "Recalculer"
    Alors la page affiche le texte "La remise doit être comprise entre 0 et 100."
    Et le nombre affiché pour "Total TTC" vaut "11,74 €"
```

### banc-agents-panier_remise_arrondi-t2

```gherkin
# language: fr
Fonctionnalité: La remise du panier est arrondie au centime et bornée de 0 à 100 %

  Scénario: Remise arrondie au centime et rejetée hors bornes
    Soit j'accède à la page d'accueil de l'application
    Et j'ouvre la page "/produits"
    Et je clique sur le bouton "Ajouter Câble HDMI au panier"
    Et j'ouvre la page "/panier"
    Et je renseigne le champ "remise" avec la valeur "10"
    Et je clique sur le bouton "Recalculer"
    Alors le nombre affiché pour "Remise (10 %)" vaut "1 EUR"
    Et le nombre affiché pour "Total HT après remise" vaut "8.95 EUR"
    Et le nombre affiché pour "TVA (18 %)" vaut "1.61 EUR"
    Et le nombre affiché pour "Total TTC" vaut "10.56 EUR"
    Quand je renseigne le champ "remise" avec la valeur "0"
    Et je clique sur le bouton "Recalculer"
    Et je renseigne le champ "remise" avec la valeur "120"
    Et je clique sur le bouton "Recalculer"
    Alors la page affiche le texte "La remise doit être comprise entre 0 et 100."
    Et le nombre affiché pour "Total TTC" vaut "11.74 EUR"
```

### banc-agents-panier_total_tva-t1

```gherkin
# language: fr
Fonctionnalité: Le total du panier applique la TVA à 18 % et arrondit au centime

  Scénario: TVA 18 % et arrondi au centime, puis vidage du panier
    Soit j'accède à la page d'accueil de l'application
    Et j'ouvre la page "/produits"
    Et je mets "2" dans la quantité de "Clavier mécanique"
    Et je clique sur le bouton "Ajouter Clavier mécanique au panier"
    Et j'ouvre la page "/produits"
    Et je mets "1" dans la quantité de "Câble HDMI"
    Et je clique sur le bouton "Ajouter Câble HDMI au panier"
    Quand j'ouvre la page "/panier"
    Alors le nombre affiché pour "Sous-total HT" vaut "109,75 €"
    Et le nombre affiché pour "TVA (18 %)" vaut "19,76 €"
    Et le nombre affiché pour "Total TTC" vaut "129,51 €"
    Quand je mets "0" dans la quantité de "Câble HDMI"
    Et je clique sur le bouton "Recalculer"
    Et je mets "0" dans la quantité de "Clavier mécanique"
    Et je clique sur le bouton "Recalculer"
    Alors la page affiche le texte "Votre panier est vide."
    Et le nombre affiché pour "Total TTC" vaut "0,00 €"
```

### banc-agents-panier_total_tva-t2

```gherkin
# language: fr
Fonctionnalité: Le total du panier applique la TVA à 18 % et arrondit au centime

  Scénario: TVA 18 % et arrondi au centime, puis vidage du panier
    Soit j'accède à la page d'accueil de l'application
    Et j'ouvre la page "/produits"
    Et je mets "2" dans la quantité de "Clavier mécanique"
    Et je clique sur le bouton "Ajouter Clavier mécanique au panier"
    Et j'ouvre la page "/produits"
    Et je mets "1" dans la quantité de "Câble HDMI"
    Et je clique sur le bouton "Ajouter Câble HDMI au panier"
    Quand j'ouvre la page "/panier"
    Alors le nombre affiché pour "Sous-total HT" vaut "109.75 EUR"
    Et le nombre affiché pour "TVA (18 %)" vaut "19.76 EUR"
    Et le nombre affiché pour "Total TTC" vaut "129.51 EUR"
    Quand je mets "0" dans la quantité de "Câble HDMI"
    Et je clique sur le bouton "Recalculer"
    Et je mets "0" dans la quantité de "Clavier mécanique"
    Et je clique sur le bouton "Recalculer"
    Alors la page affiche le texte "Votre panier est vide."
    Et le nombre affiché pour "Total TTC" vaut "0 €"
```
