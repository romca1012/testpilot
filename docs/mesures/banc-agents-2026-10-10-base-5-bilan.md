# Banc d'agents web — 2026-10-10 — base-5 : effet du lot VH-04, comparé à base-3 et base-4

Rapport brut : `banc-agents-2026-10-10-base-5.md` (30 essais sur 30, commit `ea5fd91`, mode strict, réparation Sonnet 4.6 à
2 tentatives, plafond 5,50 $). D33 n'est pas mesurable ici : le banc joue déjà sans aucun repli par le modèle de langage (VH-01).

## Indicateurs (30 essais, 10 cas × 3) — mêmes formules pour les trois campagnes

| Indicateur | base-3 (avant le plan) | base-4 (lots 1, 2, 3, 5) | **base-5 (+ lot 4)** |
|---|---|---|---|
| Faux verts | 0/21 | 0/21 | **0/21** |
| Faux rouges | 6/23 = 26 % | 2/19 = 11 % | **2/23 = 9 %** |
| Essais qui s'exécutent sans erreur technique | 23/30 | 19/30 | **23/30** |
| Essais justes partout (saine et défauts) | 17/30 | 17/30 | **21/30** |
| pass^3 — juste partout à chaque essai | 3/10 | 2/10 | **5/10** |
| Après réparation — sans erreur technique | 25/30 | 22/30 | **26/30** |
| Après réparation — justes partout | 18/30 | 19/30 | **23/30** |
| Coût (générations + réparations) | 3,42 $ | 4,66 $ | **4,57 $** |

Échantillon petit : seuls la baisse des faux rouges depuis base-3 et le gain de « justes partout » sortent du bruit de façon
plausible ; les intervalles de Wilson se recouvrent sur les autres lignes.

## Lecture

- **Faux verts : toujours 0.** Détection des défauts injectés : 21/21 concluants, dont `message_erreur_absent` 6/6 fiables
  (4/6 en base-4).
- **Le lot 4 a rendu les essais perdus par base-4** : l'adresse relative vers l'oracle ne plante plus ; compter un objet de l'oracle
  ne donne plus un faux rouge mais une erreur du test (commande_persistance_serveur essai 1).
- **Ce qui reste (9 essais non justes avant réparation)** :
  - **panier_total_tva ×3** — la quantité est cherchée sur la page du panier alors que le champ est sur la page des produits :
    la page a changé après une action. Code écrit à la main (`get_by_role("spinbutton", name="Quantité de Câble HDMI")`). Lot 6
    (« saisir dans la ligne contenant ») et surtout lot 7 (jouer l'action avant d'écrire). La réparation en rattrape 2 sur 3.
  - **commande_persistance_serveur ×3** — trois défauts différents, tous du code écrit à la main autour de l'oracle : compter un
    objet, comparer le numéro de l'oracle à un texte mal lu (`'s'`), appeler `context.oracle` comme une fonction. Lot 6 (step
    « la liste … contient un élément dont … », relevé d'une valeur) et interdiction de `context.oracle` en code libre.
  - **client_creation_valide essai 1 (faux rouge)** — le Gherkin contient des séquences d'échappement littérales
    (`\\u00ab\\u00a0Dupont SARL…`) au lieu des caractères : le texte cherché n'existe nulle part. Déjà vu en base-4 (essai 2).
    Garde d'écriture à ajouter (lot 6).
  - **connexion_valide essai 1** — sélecteur écrit à la main (`input[name="username"]`) ; réparé, mais la version réparée sort
    `non_conforme` sur l'application saine (un faux rouge créé par la réparation : 3/26 après réparation).
  - **panier_remise_arrondi essai 2** — génération sans essai à blanc passé.
- **Refus des gardes d'écriture (première mesure)** : 15 refus sur 7 essais — `LITTERAL_NON_OBSERVE` 9, `ASSERTION_MAL_PLACEE` 3,
  `TRANSPORT_INTERDIT` 3. Les gardes ne font donc pas « tourner l'agent en rond » : 23 essais sur 30 n'en reçoivent aucun.
- **Réparation** : le banc n'a plus payé les deux réparations sous un « Alors » que le produit refuse (0,53 $ contre 0,70 $).
- **Coût par génération** : 0,135 $ (base-4 : 0,132 $), toujours sous le §9.

## Ce que ça dit de la suite

Les 9 essais restants ont presque tous la même racine : **du code écrit à la main par l'agent** (repères Playwright, lecture de
l'oracle) sur une page qu'il n'a pas vue. C'est exactement la cible des lots 6 (steps manquants, code libre mesuré) et 7
(« exécuter puis écrire », D26).
