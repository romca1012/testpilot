# Banc d'agents web — 2026-10-11 — base-7

Échantillon : **10 cas × k = 3 essais** → 30/30 essais lancés, 57 jeux (couples cas/variante). Commit `fa70e49` · modèle de génération `claude-sonnet-4-6` · testpilot `0.1.0` · behave `1.3.3` · playwright `1.62.0`.

## Indicateurs

| Indicateur | Valeur |
|---|---|
| **Faux verts** (défaut injecté, attendu non_conforme, obtenu conforme) | 0/25 (0,0 %, IC95 % 0,0–13,3 %) ; 2 non concluants |
| Faux rouges (saine, attendu conforme, obtenu non_conforme) | 0/23 (0,0 %, IC95 % 0,0–14,3 %) ; 7 non concluants |
| pass@1 — le test généré s'exécute sans erreur technique | 7/10 (70,0 %, IC95 % 39,7–89,2 %) |
| pass@3 — au moins un essai sur 3 | 9/10 (90,0 %, IC95 % 59,6–98,2 %) |
| pass^3 — tous les essais | 6/10 (60,0 %, IC95 % 31,3–83,2 %) |
| pass@1 — résultat juste partout (saine ET défauts) | 7/10 (70,0 %, IC95 % 39,7–89,2 %) |
| pass@3 — résultat juste partout | 9/10 (90,0 %, IC95 % 59,6–98,2 %) |
| pass^3 — résultat juste partout, à chaque essai | 6/10 (60,0 %, IC95 % 31,3–83,2 %) |

« non mesuré » signifie qu'aucun jeu concluant n'existe pour cet indicateur : ce n'est PAS 0 %. Un taux de faux verts faible obtenu avec beaucoup de non concluants ne prouve rien : lire la ligne suivante et les intervalles (Wilson 95 %).

## Résultats non concluants (comptés, jamais retirés)

| Verdict | Jeux |
|---|---|
| technical_error | 9 |

## Détection par défaut

| Défaut | Jeux | Concluants | Détectés (non_conforme) | dont fiables (saine du même essai conforme) | Faux verts | Non concluants |
|---|---|---|---|---|---|---|
| `etat_non_enregistre` | 6 | 6 | 6/6 (100,0 %, IC95 % 61,0–100,0 %) | 3/6 (50,0 %, IC95 % 18,8–81,2 %) | 0 | 0 |
| `filtre_ignore` | 3 | 3 | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 0 | 0 |
| `login_accepte_tout` | 3 | 3 | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 0 | 0 |
| `message_erreur_absent` | 6 | 6 | 6/6 (100,0 %, IC95 % 61,0–100,0 %) | 5/6 (83,3 %, IC95 % 43,6–97,0 %) | 0 | 0 |
| `total_faux` | 6 | 4 | 4/4 (100,0 %, IC95 % 51,0–100,0 %) | 4/4 (100,0 %, IC95 % 51,0–100,0 %) | 0 | 2 |
| `validation_absente` | 3 | 3 | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 2/3 (66,7 %, IC95 % 20,8–93,9 %) | 0 | 0 |

## Après UNE réparation (D23)

Pour chaque essai dont le jeu sur l'application saine sort en `technical_error`, l'agent de réparation reçoit l'échec observé (jamais un diagnostic) et propose UNE correction ; la version réparée est rejouée sur toutes les variantes. Les autres essais restent tels quels. Le nombre de tentatives par essai est celui du budget de réparation du produit (`--tentatives-reparation`) ; le circuit complet (arrêt sur régression, couverture perdue) n'est pas rejoué ici.

| Indicateur | Avant réparation | Après une réparation |
|---|---|---|
| Faux verts | 0/25 (0,0 %, IC95 % 0,0–13,3 %) ; 2 non concluants | 0/25 (0,0 %, IC95 % 0,0–13,3 %) ; 2 non concluants |
| Faux rouges | 0/23 (0,0 %, IC95 % 0,0–14,3 %) ; 7 non concluants | 0/23 (0,0 %, IC95 % 0,0–14,3 %) ; 7 non concluants |
| pass@1 — s'exécute sans erreur technique | 7/10 (70,0 %, IC95 % 39,7–89,2 %) | 7/10 (70,0 %, IC95 % 39,7–89,2 %) |
| pass@1 — résultat juste partout | 7/10 (70,0 %, IC95 % 39,7–89,2 %) | 7/10 (70,0 %, IC95 % 39,7–89,2 %) |
| pass^k — résultat juste partout, à chaque essai | 6/10 (60,0 %, IC95 % 31,3–83,2 %) | 6/10 (60,0 %, IC95 % 31,3–83,2 %) |

Réparations : 5 essai(s) à réparer, 0 tenté(s) en 0 tentative(s), 0 avec une correction rejouable ; saine exécutable après : 0, conforme après : 0 ; coût des réparations : **0.000 $**.

- client_creation_nom_requis essai 1 : circuit du produit : échec sous un « Alors » — décision humaine, aucune réparation automatique
- commande_confirmation essai 1 : circuit du produit : échec sous un « Alors » — décision humaine, aucune réparation automatique
- commande_persistance_serveur essai 1 : circuit du produit : échec sous un « Alors » — décision humaine, aucune réparation automatique
- commande_persistance_serveur essai 2 : circuit du produit : échec sous un « Alors » — décision humaine, aucune réparation automatique
- commande_persistance_serveur essai 3 : circuit du produit : échec sous un « Alors » — décision humaine, aucune réparation automatique

## Coût

Total : **4.981 $** = 4.612 € (1 € = 1.08 $) pour 30 génération(s) ; par génération : 0.166 $ / 0.154 €.
Les jeux sur les variantes ne coûtent rien (aucun appel LLM) : tout le coût est celui des générations.

| Cas | Coût moyen par génération ($) |
|---|---|
| client_creation_nom_limite | 0.101 |
| client_creation_nom_requis | 0.082 |
| client_creation_valide | 0.116 |
| commande_confirmation | 0.148 |
| commande_persistance_serveur | 0.474 |
| connexion_refusee | 0.116 |
| connexion_valide | 0.134 |
| panier_remise_arrondi | 0.152 |
| panier_total_tva | 0.215 |
| produits_recherche | 0.121 |

## Intégrité : le MÊME test est joué partout

Jeux dont les empreintes sha256 des fichiers joués égalent celles de la génération : **53** ; divergentes : **0** ; non rapportées : 0.

## Écarts aux attendus (à instruire : le test généré, le défaut ou le verdict — jamais l'attendu)

| Cas | Variante | Essai | Attendu | Obtenu | Cause |
|---|---|---|---|---|---|
| client_creation_nom_requis | saine | 1 | conforme | technical_error | wrong_field_name |
| commande_confirmation | saine | 1 | conforme | technical_error | broken_test_code |
| commande_persistance_serveur | saine | 1 | conforme | technical_error | broken_test_code |
| commande_persistance_serveur | saine | 2 | conforme | technical_error | wrong_field_name |
| panier_remise_arrondi | saine | 2 | conforme | technical_error | generation_echouee |
| panier_remise_arrondi | total_faux | 2 | non_conforme | technical_error | generation_echouee |
| commande_persistance_serveur | saine | 3 | conforme | technical_error | broken_test_code |
| panier_remise_arrondi | saine | 3 | conforme | technical_error | generation_echouee |
| panier_remise_arrondi | total_faux | 3 | non_conforme | technical_error | generation_echouee |

## Refus des gardes d'écriture pendant la génération (lot VH-04)

Chaque refus renvoie l'agent corriger dans la même génération : il coûte des tours, il ne casse rien.

| Code du refus | Nombre |
|---|---|
| `LITTERAL_NON_OBSERVE` | 8 |
| `TRANSPORT_INTERDIT` | 1 |
| `CONSTAT_SANS_LECTURE` | 1 |
| `ASSERTION_MAL_PLACEE` | 1 |

## Code libre (lot VH-06)

Tests générés sans AUCUN step écrit à la main : **26/28** ; steps définis par les tests : 2 au total (maximum 1 dans un test). Un step écrit à la main n'a ni test de falsifiabilité ni résolution éprouvée : la cible est zéro.

## Génération par essai

| Cas | Essai | Généré | Coût ($) | Refus à l'écriture | Steps écrits à la main | Empreinte du test (sha256) |
|---|---|---|---|---|---|---|
| client_creation_nom_limite | 1 | oui | 0.130 | — | 0 | `d1917feb4f2934ea` |
| client_creation_nom_requis | 1 | oui | 0.099 | — | 0 | `a9f7339a8bb881a6` |
| client_creation_valide | 1 | oui | 0.103 | — | 0 | `018b501ba6df8151` |
| commande_confirmation | 1 | oui | 0.151 | — | 0 | `d5f8e350da961cb1` |
| commande_persistance_serveur | 1 | oui | 0.479 | LITTERAL_NON_OBSERVE ×2, TRANSPORT_INTERDIT ×1 | 0 | `274dc8a95a7ba71d` |
| connexion_refusee | 1 | oui | 0.121 | — | 0 | `0936b205ca99c2a4` |
| connexion_valide | 1 | oui | 0.124 | — | 0 | `20bf31e9d4994fc9` |
| panier_remise_arrondi | 1 | oui | 0.170 | — | 0 | `f0b27ffb57c4cb06` |
| panier_total_tva | 1 | oui | 0.291 | — | 0 | `0671610ac060b5c7` |
| produits_recherche | 1 | oui | 0.099 | — | 0 | `448bec69ea300a69` |
| client_creation_nom_limite | 2 | oui | 0.096 | — | 0 | `302cd93c64198bc4` |
| client_creation_nom_requis | 2 | oui | 0.062 | — | 0 | `6994ca876eb60d17` |
| client_creation_valide | 2 | oui | 0.115 | — | 0 | `c3ab8f102a8c01b1` |
| commande_confirmation | 2 | oui | 0.154 | — | 0 | `437b48c25e9490f3` |
| commande_persistance_serveur | 2 | oui | 0.447 | LITTERAL_NON_OBSERVE ×3 | 1 | `e686a456c0c8d62b` |
| connexion_refusee | 2 | oui | 0.112 | — | 0 | `80f79f680535ac5e` |
| connexion_valide | 2 | oui | 0.130 | — | 0 | `ce9974da9fcd66a6` |
| panier_remise_arrondi | 2 | NON : génération sans essai à blanc passé | 0.146 | — | — | `—` |
| panier_total_tva | 2 | oui | 0.169 | — | 0 | `a5c08dccd94a7b55` |
| produits_recherche | 2 | oui | 0.097 | — | 0 | `e83be47b292a6b18` |
| client_creation_nom_limite | 3 | oui | 0.078 | — | 0 | `082e31f4c4cb04e3` |
| client_creation_nom_requis | 3 | oui | 0.086 | — | 0 | `8acbc4e2f0cc12b9` |
| client_creation_valide | 3 | oui | 0.130 | — | 0 | `85827f535be648b1` |
| commande_confirmation | 3 | oui | 0.140 | — | 0 | `13e686b99ae784a5` |
| commande_persistance_serveur | 3 | oui | 0.495 | LITTERAL_NON_OBSERVE ×3 | 0 | `e0860360c5a52dda` |
| connexion_refusee | 3 | oui | 0.115 | — | 0 | `b262dbd25470ddf1` |
| connexion_valide | 3 | oui | 0.148 | — | 0 | `0714afc64ea7ca00` |
| panier_remise_arrondi | 3 | NON : génération sans essai à blanc passé | 0.142 | — | — | `—` |
| panier_total_tva | 3 | oui | 0.187 | — | 0 | `2a88111985b8aa3d` |
| produits_recherche | 3 | oui | 0.168 | ASSERTION_MAL_PLACEE ×1, CONSTAT_SANS_LECTURE ×1 | 1 | `b4895fb50afaf9b7` |
