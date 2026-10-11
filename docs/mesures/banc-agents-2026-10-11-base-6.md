# Banc d'agents web — 2026-10-11 — base-6

Échantillon : **10 cas × k = 3 essais** → 30/30 essais lancés, 57 jeux (couples cas/variante). Commit `8839d98` · modèle de génération `claude-sonnet-4-6` · testpilot `0.1.0` · behave `1.3.3` · playwright `1.62.0`.

## Indicateurs

| Indicateur | Valeur |
|---|---|
| **Faux verts** (défaut injecté, attendu non_conforme, obtenu conforme) | 0/21 (0,0 %, IC95 % 0,0–15,5 %) ; 6 non concluants |
| Faux rouges (saine, attendu conforme, obtenu non_conforme) | 1/19 (5,3 %, IC95 % 0,9–24,6 %) ; 11 non concluants |
| pass@1 — le test généré s'exécute sans erreur technique | 6/10 (60,0 %, IC95 % 31,3–83,2 %) |
| pass@3 — au moins un essai sur 3 | 9/10 (90,0 %, IC95 % 59,6–98,2 %) |
| pass^3 — tous les essais | 4/10 (40,0 %, IC95 % 16,8–68,7 %) |
| pass@1 — résultat juste partout (saine ET défauts) | 5/10 (50,0 %, IC95 % 23,7–76,3 %) |
| pass@3 — résultat juste partout | 9/10 (90,0 %, IC95 % 59,6–98,2 %) |
| pass^3 — résultat juste partout, à chaque essai | 4/10 (40,0 %, IC95 % 16,8–68,7 %) |

« non mesuré » signifie qu'aucun jeu concluant n'existe pour cet indicateur : ce n'est PAS 0 %. Un taux de faux verts faible obtenu avec beaucoup de non concluants ne prouve rien : lire la ligne suivante et les intervalles (Wilson 95 %).

## Résultats non concluants (comptés, jamais retirés)

| Verdict | Jeux |
|---|---|
| blocked | 2 |
| technical_error | 15 |

## Détection par défaut

| Défaut | Jeux | Concluants | Détectés (non_conforme) | dont fiables (saine du même essai conforme) | Faux verts | Non concluants |
|---|---|---|---|---|---|---|
| `etat_non_enregistre` | 6 | 6 | 6/6 (100,0 %, IC95 % 61,0–100,0 %) | 4/6 (66,7 %, IC95 % 30,0–90,3 %) | 0 | 0 |
| `filtre_ignore` | 3 | 3 | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 0 | 0 |
| `login_accepte_tout` | 3 | 3 | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 0 | 0 |
| `message_erreur_absent` | 6 | 5 | 5/5 (100,0 %, IC95 % 56,6–100,0 %) | 4/5 (80,0 %, IC95 % 37,6–96,4 %) | 0 | 1 |
| `total_faux` | 6 | 1 | 1/1 (100,0 %, IC95 % 20,7–100,0 %) | 1/1 (100,0 %, IC95 % 20,7–100,0 %) | 0 | 5 |
| `validation_absente` | 3 | 3 | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 0 | 0 |

## Après UNE réparation (D23)

Pour chaque essai dont le jeu sur l'application saine sort en `technical_error`, l'agent de réparation reçoit l'échec observé (jamais un diagnostic) et propose UNE correction ; la version réparée est rejouée sur toutes les variantes. Les autres essais restent tels quels. Le nombre de tentatives par essai est celui du budget de réparation du produit (`--tentatives-reparation`) ; le circuit complet (arrêt sur régression, couverture perdue) n'est pas rejoué ici.

| Indicateur | Avant réparation | Après une réparation |
|---|---|---|
| Faux verts | 0/21 (0,0 %, IC95 % 0,0–15,5 %) ; 6 non concluants | 0/21 (0,0 %, IC95 % 0,0–15,5 %) ; 6 non concluants |
| Faux rouges | 1/19 (5,3 %, IC95 % 0,9–24,6 %) ; 11 non concluants | 1/19 (5,3 %, IC95 % 0,9–24,6 %) ; 11 non concluants |
| pass@1 — s'exécute sans erreur technique | 6/10 (60,0 %, IC95 % 31,3–83,2 %) | 6/10 (60,0 %, IC95 % 31,3–83,2 %) |
| pass@1 — résultat juste partout | 5/10 (50,0 %, IC95 % 23,7–76,3 %) | 5/10 (50,0 %, IC95 % 23,7–76,3 %) |
| pass^k — résultat juste partout, à chaque essai | 4/10 (40,0 %, IC95 % 16,8–68,7 %) | 4/10 (40,0 %, IC95 % 16,8–68,7 %) |

Réparations : 7 essai(s) à réparer, 4 tenté(s) en 5 tentative(s), 1 avec une correction rejouable ; saine exécutable après : 0, conforme après : 0 ; coût des réparations : **0.736 $**.

- commande_confirmation essai 1 : circuit du produit : échec sous un « Alors » — décision humaine, aucune réparation automatique
- panier_total_tva essai 1 : l'agent n'a rien réécrit
- client_creation_nom_limite essai 2 : circuit du produit : échec sous un « Alors » — décision humaine, aucune réparation automatique
- commande_confirmation essai 3 : l'agent n'a rien réécrit
- commande_persistance_serveur essai 3 : circuit du produit : échec sous un « Alors » — décision humaine, aucune réparation automatique
- panier_total_tva essai 3 : l'agent n'a rien réécrit

## Coût

Total : **3.874 $** = 3.587 € (1 € = 1.08 $) pour 30 génération(s) ; par génération : 0.134 $ / 0.124 €.
Les jeux sur les variantes ne coûtent rien (aucun appel LLM) : tout le coût est celui des générations.
⚠️ 1 génération(s) sans coût consigné (non comptées comme 0).

| Cas | Coût moyen par génération ($) |
|---|---|
| client_creation_nom_limite | 0.106 |
| client_creation_nom_requis | 0.101 |
| client_creation_valide | 0.108 |
| commande_confirmation | 0.099 |
| commande_persistance_serveur | 0.340 |
| connexion_refusee | 0.156 |
| connexion_valide | 0.132 |
| panier_remise_arrondi | 0.108 |
| panier_total_tva | 0.107 |
| produits_recherche | 0.079 |

## Intégrité : le MÊME test est joué partout

Jeux dont les empreintes sha256 des fichiers joués égalent celles de la génération : **52** ; divergentes : **0** ; non rapportées : 0.

## Anomalies du harnais

- connexion_valide essai 1 : coût de génération non consigné (compté au PIRE connu dans le cumul du plafond, mais « non consigné » dans le rapport — jamais 0)

## Écarts aux attendus (à instruire : le test généré, le défaut ou le verdict — jamais l'attendu)

| Cas | Variante | Essai | Attendu | Obtenu | Cause |
|---|---|---|---|---|---|
| commande_confirmation | saine | 1 | conforme | technical_error | broken_test_code |
| commande_persistance_serveur | saine | 1 | conforme | non_conforme | assertion_mismatch |
| connexion_valide | saine | 1 | conforme | technical_error | generation_echouee |
| panier_remise_arrondi | saine | 1 | conforme | technical_error | generation_echouee |
| panier_remise_arrondi | total_faux | 1 | non_conforme | technical_error | generation_echouee |
| panier_total_tva | saine | 1 | conforme | technical_error | wrong_field_name |
| panier_total_tva | total_faux | 1 | non_conforme | technical_error | wrong_field_name |
| client_creation_nom_limite | saine | 2 | conforme | technical_error | broken_test_code |
| panier_remise_arrondi | saine | 2 | conforme | technical_error | generation_echouee |
| panier_remise_arrondi | total_faux | 2 | non_conforme | technical_error | generation_echouee |
| panier_total_tva | saine | 2 | conforme | technical_error | wrong_field_name |
| panier_total_tva | total_faux | 2 | non_conforme | technical_error | wrong_field_name |
| client_creation_nom_limite | saine | 3 | conforme | blocked | precondition_non_remplie |
| client_creation_nom_limite | message_erreur_absent | 3 | non_conforme | blocked | precondition_non_remplie |
| commande_confirmation | saine | 3 | conforme | technical_error | wrong_field_name |
| commande_persistance_serveur | saine | 3 | conforme | technical_error | wrong_field_name |
| panier_total_tva | saine | 3 | conforme | technical_error | wrong_field_name |
| panier_total_tva | total_faux | 3 | non_conforme | technical_error | wrong_field_name |

## Refus des gardes d'écriture pendant la génération (lot VH-04)

Chaque refus renvoie l'agent corriger dans la même génération : il coûte des tours, il ne casse rien.

| Code du refus | Nombre |
|---|---|
| `LITTERAL_NON_OBSERVE` | 12 |
| `ECHAPPEMENT_LITTERAL` | 1 |

## Code libre (lot VH-06)

Tests générés sans AUCUN step écrit à la main : **25/27** ; steps définis par les tests : 2 au total (maximum 1 dans un test). Un step écrit à la main n'a ni test de falsifiabilité ni résolution éprouvée : la cible est zéro.

## Génération par essai

| Cas | Essai | Généré | Coût ($) | Refus à l'écriture | Steps écrits à la main | Empreinte du test (sha256) |
|---|---|---|---|---|---|---|
| client_creation_nom_limite | 1 | oui | 0.150 | — | 0 | `9d33be6c8fd9f2c9` |
| client_creation_nom_requis | 1 | oui | 0.088 | — | 0 | `974d62320288b6b7` |
| client_creation_valide | 1 | oui | 0.106 | — | 0 | `7e0a4625c61f01b7` |
| commande_confirmation | 1 | oui | 0.112 | — | 0 | `85498772fae8b998` |
| commande_persistance_serveur | 1 | oui | 0.310 | LITTERAL_NON_OBSERVE ×2 | 0 | `69f0e1b44ce06fed` |
| connexion_refusee | 1 | oui | 0.180 | LITTERAL_NON_OBSERVE ×2 | 1 | `5a6b310d30d99fca` |
| connexion_valide | 1 | NON : Connection error. | non consigné | LITTERAL_NON_OBSERVE ×1 | — | `—` |
| panier_remise_arrondi | 1 | NON : génération sans essai à blanc passé | 0.123 | — | — | `—` |
| panier_total_tva | 1 | oui | 0.100 | — | 0 | `8f023114d99b1776` |
| produits_recherche | 1 | oui | 0.074 | — | 0 | `8b41afa5cdb902f7` |
| client_creation_nom_limite | 2 | oui | 0.078 | — | 0 | `bb89528a1aebb196` |
| client_creation_nom_requis | 2 | oui | 0.115 | — | 0 | `d4a14bcfaa5103ac` |
| client_creation_valide | 2 | oui | 0.116 | — | 0 | `622014a7b24899a2` |
| commande_confirmation | 2 | oui | 0.106 | — | 0 | `4ab0ca502a5ff945` |
| commande_persistance_serveur | 2 | oui | 0.312 | LITTERAL_NON_OBSERVE ×1 | 0 | `743d9394b145c35d` |
| connexion_refusee | 2 | oui | 0.074 | — | 0 | `19c6b37b15df0585` |
| connexion_valide | 2 | oui | 0.158 | LITTERAL_NON_OBSERVE ×1 | 0 | `61f38760b3332f9d` |
| panier_remise_arrondi | 2 | NON : génération sans essai à blanc passé | 0.115 | — | — | `—` |
| panier_total_tva | 2 | oui | 0.122 | — | 0 | `0bfc621c55eec41a` |
| produits_recherche | 2 | oui | 0.106 | — | 0 | `822d8c8ee1de1772` |
| client_creation_nom_limite | 3 | oui | 0.090 | — | 0 | `110701603e6b6a9d` |
| client_creation_nom_requis | 3 | oui | 0.100 | — | 0 | `c3884750273a1d23` |
| client_creation_valide | 3 | oui | 0.102 | ECHAPPEMENT_LITTERAL ×1 | 0 | `0d0ced13e8e68bdf` |
| commande_confirmation | 3 | oui | 0.078 | — | 0 | `631950a1d59f8380` |
| commande_persistance_serveur | 3 | oui | 0.396 | LITTERAL_NON_OBSERVE ×3 | 0 | `f10fc2ee96330f95` |
| connexion_refusee | 3 | oui | 0.214 | LITTERAL_NON_OBSERVE ×2 | 1 | `bc27e97d34366b49` |
| connexion_valide | 3 | oui | 0.105 | — | 0 | `5fed34cac08dcfdd` |
| panier_remise_arrondi | 3 | oui | 0.086 | — | 0 | `a032fe391d04503e` |
| panier_total_tva | 3 | oui | 0.099 | — | 0 | `de1b1d976da6188f` |
| produits_recherche | 3 | oui | 0.057 | — | 0 | `51fe2d6c56b07c38` |
