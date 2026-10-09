# Banc d'agents web — 2026-10-09 — base-4 (bilan fusionné) comparé à base-3

Campagne en deux morceaux, même commit `b325077` (lots VH-01, VH-02, VH-03, VH-05, D30-D32) :
- `banc-agents-2026-10-09-base-4.md` : 25 essais sur 30, arrêtée par le plafond de coût (4,50 $, réglé avant le départ ;
  le banc ajoute au cumul le coût de l'essai le plus cher vu, 0,535 $) ;
- `banc-agents-2026-10-09-base-4-complement.md` : les 5 essais manquants (3e essai de 5 cas), joués comme « essai 1 » d'une
  campagne séparée, renumérotés 3 dans la fusion (`banc-agents-2026-10-09-base-4-fusion.json`, mêmes fonctions `banc_stats`).
Mode strict (VH-01), réparation Sonnet 4.6 à 2 tentatives. Une réparation (commande_persistance_serveur, essai 3) n'a pas été
tentée faute de budget.

## Indicateurs (30 essais, 10 cas × 3) — mêmes formules pour les deux campagnes

| Indicateur | base-3 avant réparation | **base-4 avant réparation** | base-3 après | **base-4 après** |
|---|---|---|---|---|
| Faux verts | 0/21 (6 non concluants) | **0/21** (6 n.c.) | 0/23 | **0/23** |
| Faux rouges | 6/23 = 26 % (7 n.c.) | **2/19 = 11 %** (11 n.c.) | 7/25 = 28 % | **2/22 = 9 %** |
| Essais qui s'exécutent sans erreur technique | 23/30 | **19/30** | 25/30 | **22/30** |
| Essais justes partout (saine et défauts) | 17/30 | **17/30** | 18/30 | **19/30** |
| pass^3 — juste partout à chaque essai | 3/10 | **2/10** | — | **2/10** |
| Coût (générations + réparations) | 3,01 + 0,41 = 3,42 $ | | | **3,96 + 0,70 = 4,66 $** |

Échantillon petit : les intervalles (Wilson 95 %) se recouvrent sur toutes les lignes sauf la tendance des faux rouges.

## Lecture

- **Faux verts : toujours 0.** Aucun bug injecté n'a été déclaré conforme.
- **Faux rouges : 6-7 → 2.** Les deux restants : `client_creation_valide` essai 2 (message de succès attendu avec des
  espaces insécables sur la page du formulaire, alors qu'il s'affiche ailleurs ou autrement) et `client_creation_nom_requis`
  essai 3 (comptage de l'oracle « etat » sur un objet unique — déjà vu en base-2, lot 4).
- **Erreurs techniques : en hausse (7 → 11 essais avant réparation).** Causes :
  - **la page a changé** (4 essais) : le test cherche un champ ou un bouton sur la mauvaise page — quantité cherchée sur
    `/panier` au lieu de `/produits` (panier_total_tva ×3), bouton « Nouveau client » sur `/clients/nouveau`, produit non
    actionnable sur `/produits`. C'est la limite connue de l'écriture « à l'aveugle » : lot 6 (suivi de route) et lot 7
    (exécuter puis écrire, D26) ;
  - **adresse relative** vers l'oracle (`page.goto("/__etat")`, 2 essais commande_persistance_serveur) : lot 4 (oracle par
    un step partagé) ;
  - **générations échouées** (2) : l'agent n'a pas obtenu un essai à blanc qui passe (commande_persistance_serveur 0,54 $,
    panier_remise_arrondi) — à instruire : les gardes d'écriture plus strictes peuvent prolonger la génération ;
  - **compte inventé** (connexion_valide ×2, `blocked`) : le test se connecte avec « testeur », le projet ne déclare que
    « principal » — verdict honnête (bloqué, jamais conforme), mais génération à corriger.
- **Réparation** : 6 essais à réparer, 3 rattrapés (panier_total_tva ×3 dont 2 deviennent justes partout). Le gel total des
  vérifications (VH-03) a bloqué deux réparations dont la cause était dans un `Alors` (adresse relative) : c'est voulu — en
  produit, le circuit envoie ces échecs à un humain ; le banc ne rejoue pas ce circuit et dépense donc la tentative (0,24 $).
- **Coût par génération** : 0,132 $ (base-3 : 0,100 $), tiré par commande_persistance_serveur (0,38 $ en moyenne). Reste
  sous le §9 (moins de 1 € par cas).

## Ce que ça dit du plan

Le verdict ment moins (faux rouges divisés par trois, aucun faux vert). L'écart restant vers « zéro erreur technique après
génération » est dominé par une seule famille — la page change après une action — que les contrôles à l'écriture ne
peuvent pas voir : c'est l'objet des lots 6 et 7 (D26). Le lot 4 ferme l'adresse relative et le comptage d'oracle.
