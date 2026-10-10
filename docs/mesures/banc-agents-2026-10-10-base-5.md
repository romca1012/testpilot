# Banc d'agents web — 2026-10-10 — base-5

Échantillon : **10 cas × k = 3 essais** → 30/30 essais lancés, 57 jeux (couples cas/variante). Commit `ea5fd91` · modèle de génération `claude-sonnet-4-6` · testpilot `0.1.0` · behave `1.3.3` · playwright `1.62.0`.

## Indicateurs

| Indicateur | Valeur |
|---|---|
| **Faux verts** (défaut injecté, attendu non_conforme, obtenu conforme) | 0/21 (0,0 %, IC95 % 0,0–15,5 %) ; 6 non concluants |
| Faux rouges (saine, attendu conforme, obtenu non_conforme) | 2/23 (8,7 %, IC95 % 2,4–26,8 %) ; 7 non concluants |
| pass@1 — le test généré s'exécute sans erreur technique | 7/10 (70,0 %, IC95 % 39,7–89,2 %) |
| pass@3 — au moins un essai sur 3 | 9/10 (90,0 %, IC95 % 59,6–98,2 %) |
| pass^3 — tous les essais | 6/10 (60,0 %, IC95 % 31,3–83,2 %) |
| pass@1 — résultat juste partout (saine ET défauts) | 6/10 (60,0 %, IC95 % 31,3–83,2 %) |
| pass@3 — résultat juste partout | 8/10 (80,0 %, IC95 % 49,0–94,3 %) |
| pass^3 — résultat juste partout, à chaque essai | 5/10 (50,0 %, IC95 % 23,7–76,3 %) |

« non mesuré » signifie qu'aucun jeu concluant n'existe pour cet indicateur : ce n'est PAS 0 %. Un taux de faux verts faible obtenu avec beaucoup de non concluants ne prouve rien : lire la ligne suivante et les intervalles (Wilson 95 %).

## Résultats non concluants (comptés, jamais retirés)

| Verdict | Jeux |
|---|---|
| technical_error | 13 |

## Détection par défaut

| Défaut | Jeux | Concluants | Détectés (non_conforme) | dont fiables (saine du même essai conforme) | Faux verts | Non concluants |
|---|---|---|---|---|---|---|
| `etat_non_enregistre` | 6 | 4 | 4/4 (100,0 %, IC95 % 51,0–100,0 %) | 2/4 (50,0 %, IC95 % 15,0–85,0 %) | 0 | 2 |
| `filtre_ignore` | 3 | 3 | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 0 | 0 |
| `login_accepte_tout` | 3 | 3 | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 0 | 0 |
| `message_erreur_absent` | 6 | 6 | 6/6 (100,0 %, IC95 % 61,0–100,0 %) | 6/6 (100,0 %, IC95 % 61,0–100,0 %) | 0 | 0 |
| `total_faux` | 6 | 2 | 2/2 (100,0 %, IC95 % 34,2–100,0 %) | 2/2 (100,0 %, IC95 % 34,2–100,0 %) | 0 | 4 |
| `validation_absente` | 3 | 3 | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 0 | 0 |

## Après UNE réparation (D23)

Pour chaque essai dont le jeu sur l'application saine sort en `technical_error`, l'agent de réparation reçoit l'échec observé (jamais un diagnostic) et propose UNE correction ; la version réparée est rejouée sur toutes les variantes. Les autres essais restent tels quels. Le nombre de tentatives par essai est celui du budget de réparation du produit (`--tentatives-reparation`) ; le circuit complet (arrêt sur régression, couverture perdue) n'est pas rejoué ici.

| Indicateur | Avant réparation | Après une réparation |
|---|---|---|
| Faux verts | 0/21 (0,0 %, IC95 % 0,0–15,5 %) ; 6 non concluants | 0/24 (0,0 %, IC95 % 0,0–13,8 %) ; 3 non concluants |
| Faux rouges | 2/23 (8,7 %, IC95 % 2,4–26,8 %) ; 7 non concluants | 3/26 (11,5 %, IC95 % 4,0–29,0 %) ; 4 non concluants |
| pass@1 — s'exécute sans erreur technique | 7/10 (70,0 %, IC95 % 39,7–89,2 %) | 8/10 (80,0 %, IC95 % 49,0–94,3 %) |
| pass@1 — résultat juste partout | 6/10 (60,0 %, IC95 % 31,3–83,2 %) | 6/10 (60,0 %, IC95 % 31,3–83,2 %) |
| pass^k — résultat juste partout, à chaque essai | 5/10 (50,0 %, IC95 % 23,7–76,3 %) | 5/10 (50,0 %, IC95 % 23,7–76,3 %) |

Réparations : 6 essai(s) à réparer, 5 tenté(s) en 5 tentative(s), 4 avec une correction rejouable ; saine exécutable après : 3, conforme après : 2 ; coût des réparations : **0.531 $**.

- commande_persistance_serveur essai 1 : circuit du produit : échec sous un « Alors » — décision humaine, aucune réparation automatique
- panier_total_tva essai 1 : circuit du produit : échec sous un « Alors » — décision humaine, aucune réparation automatique
- commande_persistance_serveur essai 3 : l'agent n'a rien réécrit

## Coût

Total : **4.040 $** = 3.741 € (1 € = 1.08 $) pour 30 génération(s) ; par génération : 0.135 $ / 0.125 €.
Les jeux sur les variantes ne coûtent rien (aucun appel LLM) : tout le coût est celui des générations.

| Cas | Coût moyen par génération ($) |
|---|---|
| client_creation_nom_limite | 0.098 |
| client_creation_nom_requis | 0.111 |
| client_creation_valide | 0.101 |
| commande_confirmation | 0.101 |
| commande_persistance_serveur | 0.290 |
| connexion_refusee | 0.188 |
| connexion_valide | 0.135 |
| panier_remise_arrondi | 0.128 |
| panier_total_tva | 0.118 |
| produits_recherche | 0.076 |

## Intégrité : le MÊME test est joué partout

Jeux dont les empreintes sha256 des fichiers joués égalent celles de la génération : **55** ; divergentes : **0** ; non rapportées : 0.

## Écarts aux attendus (à instruire : le test généré, le défaut ou le verdict — jamais l'attendu)

| Cas | Variante | Essai | Attendu | Obtenu | Cause |
|---|---|---|---|---|---|
| client_creation_valide | saine | 1 | conforme | non_conforme | assertion_mismatch |
| commande_persistance_serveur | saine | 1 | conforme | technical_error | broken_test_code |
| commande_persistance_serveur | etat_non_enregistre | 1 | non_conforme | technical_error | broken_test_code |
| connexion_valide | saine | 1 | conforme | technical_error | wrong_field_name |
| panier_total_tva | saine | 1 | conforme | technical_error | wrong_field_name |
| panier_total_tva | total_faux | 1 | non_conforme | technical_error | wrong_field_name |
| commande_persistance_serveur | saine | 2 | conforme | non_conforme | assertion_mismatch |
| panier_remise_arrondi | saine | 2 | conforme | technical_error | generation_echouee |
| panier_remise_arrondi | total_faux | 2 | non_conforme | technical_error | generation_echouee |
| panier_total_tva | saine | 2 | conforme | technical_error | wrong_field_name |
| panier_total_tva | total_faux | 2 | non_conforme | technical_error | wrong_field_name |
| commande_persistance_serveur | saine | 3 | conforme | technical_error | broken_test_code |
| commande_persistance_serveur | etat_non_enregistre | 3 | non_conforme | technical_error | broken_test_code |
| panier_total_tva | saine | 3 | conforme | technical_error | wrong_field_name |
| panier_total_tva | total_faux | 3 | non_conforme | technical_error | wrong_field_name |

## Refus des gardes d'écriture pendant la génération (lot VH-04)

Chaque refus renvoie l'agent corriger dans la même génération : il coûte des tours, il ne casse rien.

| Code du refus | Nombre |
|---|---|
| `LITTERAL_NON_OBSERVE` | 9 |
| `ASSERTION_MAL_PLACEE` | 3 |
| `TRANSPORT_INTERDIT` | 3 |

## Génération par essai

| Cas | Essai | Généré | Coût ($) | Refus à l'écriture | Empreinte du test (sha256) |
|---|---|---|---|---|---|
| client_creation_nom_limite | 1 | oui | 0.128 | — | `ce195d3f19a434bf` |
| client_creation_nom_requis | 1 | oui | 0.144 | ASSERTION_MAL_PLACEE ×1, LITTERAL_NON_OBSERVE ×1 | `963e81e5a6e257fd` |
| client_creation_valide | 1 | oui | 0.099 | — | `6929700e9e5d2dee` |
| commande_confirmation | 1 | oui | 0.106 | — | `5e9b5ffc787069db` |
| commande_persistance_serveur | 1 | oui | 0.264 | LITTERAL_NON_OBSERVE ×2, TRANSPORT_INTERDIT ×2 | `6c40fa8954133efe` |
| connexion_refusee | 1 | oui | 0.259 | LITTERAL_NON_OBSERVE ×2 | `7e6fd0a56c6ee306` |
| connexion_valide | 1 | oui | 0.121 | — | `61d60b4b2edd8a6f` |
| panier_remise_arrondi | 1 | oui | 0.162 | — | `d75b375c3fb2def6` |
| panier_total_tva | 1 | oui | 0.152 | LITTERAL_NON_OBSERVE ×1 | `40d283fcabf22cf3` |
| produits_recherche | 1 | oui | 0.065 | — | `40249afeb2b7a3c1` |
| client_creation_nom_limite | 2 | oui | 0.092 | — | `13a4eb4b377d2738` |
| client_creation_nom_requis | 2 | oui | 0.076 | — | `4cb431289f629ffd` |
| client_creation_valide | 2 | oui | 0.109 | — | `d663495d96d06044` |
| commande_confirmation | 2 | oui | 0.095 | — | `6a1032bc52d028dc` |
| commande_persistance_serveur | 2 | oui | 0.349 | ASSERTION_MAL_PLACEE ×1, LITTERAL_NON_OBSERVE ×2 | `5603ccfc5e4e53a5` |
| connexion_refusee | 2 | oui | 0.224 | LITTERAL_NON_OBSERVE ×1 | `34d3397c64823dce` |
| connexion_valide | 2 | oui | 0.178 | — | `1fc5eacbaf4a170e` |
| panier_remise_arrondi | 2 | NON : génération sans essai à blanc passé | 0.110 | — | `—` |
| panier_total_tva | 2 | oui | 0.083 | — | `2f216580fcebabc5` |
| produits_recherche | 2 | oui | 0.080 | — | `48a0198374481437` |
| client_creation_nom_limite | 3 | oui | 0.075 | — | `77f587ef0b3581d7` |
| client_creation_nom_requis | 3 | oui | 0.114 | — | `27a866535bf27a33` |
| client_creation_valide | 3 | oui | 0.094 | — | `53e27ddf54b6ba7d` |
| commande_confirmation | 3 | oui | 0.101 | — | `374d46b3f45663a8` |
| commande_persistance_serveur | 3 | oui | 0.258 | ASSERTION_MAL_PLACEE ×1, TRANSPORT_INTERDIT ×1 | `9107b8871d271a46` |
| connexion_refusee | 3 | oui | 0.081 | — | `8766376638604667` |
| connexion_valide | 3 | oui | 0.106 | — | `4d917997a7cb178c` |
| panier_remise_arrondi | 3 | oui | 0.112 | — | `eb934fed4b514f3b` |
| panier_total_tva | 3 | oui | 0.119 | — | `938a6b70e10a188d` |
| produits_recherche | 3 | oui | 0.084 | — | `bd36ccf6d2b35bd7` |
