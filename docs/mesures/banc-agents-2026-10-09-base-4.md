# Banc d'agents web — 2026-10-09 — base-4

Échantillon : **10 cas × k = 3 essais** → 25/30 essais lancés, 48 jeux (couples cas/variante). Commit `b325077` · modèle de génération `claude-sonnet-4-6` · testpilot `0.1.0` · behave `1.3.3` · playwright `1.62.0`.

## ⚠️ Campagne INCOMPLÈTE : plafond de coût : cumul 4.047 $ + essai le plus cher attendu 0.535 $ > plafond 4.500 $ (avant connexion_refusee, essai 3)

Les indicateurs portent sur les essais lancés seulement, jamais sur le corpus entier.

## Indicateurs

| Indicateur | Valeur |
|---|---|
| **Faux verts** (défaut injecté, attendu non_conforme, obtenu conforme) | 0/19 (0,0 %, IC95 % 0,0–16,8 %) ; 4 non concluants |
| Faux rouges (saine, attendu conforme, obtenu non_conforme) | 2/17 (11,8 %, IC95 % 3,3–34,3 %) ; 8 non concluants |
| pass@1 — le test généré s'exécute sans erreur technique | 7/10 (70,0 %, IC95 % 39,7–89,2 %) |
| pass@3 — au moins un essai sur 3 | 4/5 (80,0 %, IC95 % 37,6–96,4 %) ; 5 cas sans assez d'essais |
| pass^3 — tous les essais | 2/5 (40,0 %, IC95 % 11,8–76,9 %) ; 5 cas sans assez d'essais |
| pass@1 — résultat juste partout (saine ET défauts) | 7/10 (70,0 %, IC95 % 39,7–89,2 %) |
| pass@3 — résultat juste partout | 4/5 (80,0 %, IC95 % 37,6–96,4 %) ; 5 cas sans assez d'essais |
| pass^3 — résultat juste partout, à chaque essai | 0/5 (0,0 %, IC95 % 0,0–43,4 %) ; 5 cas sans assez d'essais |

« non mesuré » signifie qu'aucun jeu concluant n'existe pour cet indicateur : ce n'est PAS 0 %. Un taux de faux verts faible obtenu avec beaucoup de non concluants ne prouve rien : lire la ligne suivante et les intervalles (Wilson 95 %).

## Résultats non concluants (comptés, jamais retirés)

| Verdict | Jeux |
|---|---|
| blocked | 1 |
| technical_error | 11 |

## Détection par défaut

| Défaut | Jeux | Concluants | Détectés (non_conforme) | dont fiables (saine du même essai conforme) | Faux verts | Non concluants |
|---|---|---|---|---|---|---|
| `etat_non_enregistre` | 6 | 4 | 4/4 (100,0 %, IC95 % 51,0–100,0 %) | 2/4 (50,0 %, IC95 % 15,0–85,0 %) | 0 | 2 |
| `filtre_ignore` | 2 | 2 | 2/2 (100,0 %, IC95 % 34,2–100,0 %) | 2/2 (100,0 %, IC95 % 34,2–100,0 %) | 0 | 0 |
| `login_accepte_tout` | 2 | 2 | 2/2 (100,0 %, IC95 % 34,2–100,0 %) | 2/2 (100,0 %, IC95 % 34,2–100,0 %) | 0 | 0 |
| `message_erreur_absent` | 6 | 6 | 6/6 (100,0 %, IC95 % 61,0–100,0 %) | 4/6 (66,7 %, IC95 % 30,0–90,3 %) | 0 | 0 |
| `total_faux` | 4 | 2 | 2/2 (100,0 %, IC95 % 34,2–100,0 %) | 2/2 (100,0 %, IC95 % 34,2–100,0 %) | 0 | 2 |
| `validation_absente` | 3 | 3 | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 2/3 (66,7 %, IC95 % 20,8–93,9 %) | 0 | 0 |

## Après UNE réparation (D23)

Pour chaque essai dont le jeu sur l'application saine sort en `technical_error`, l'agent de réparation reçoit l'échec observé (jamais un diagnostic) et propose UNE correction ; la version réparée est rejouée sur toutes les variantes. Les autres essais restent tels quels. Le nombre de tentatives par essai est celui du budget de réparation du produit (`--tentatives-reparation`) ; le circuit complet (arrêt sur régression, couverture perdue) n'est pas rejoué ici.

| Indicateur | Avant réparation | Après une réparation |
|---|---|---|
| Faux verts | 0/19 (0,0 %, IC95 % 0,0–16,8 %) ; 4 non concluants | 0/21 (0,0 %, IC95 % 0,0–15,5 %) ; 2 non concluants |
| Faux rouges | 2/17 (11,8 %, IC95 % 3,3–34,3 %) ; 8 non concluants | 2/19 (10,5 %, IC95 % 2,9–31,4 %) ; 6 non concluants |
| pass@1 — s'exécute sans erreur technique | 7/10 (70,0 %, IC95 % 39,7–89,2 %) | 8/10 (80,0 %, IC95 % 49,0–94,3 %) |
| pass@1 — résultat juste partout | 7/10 (70,0 %, IC95 % 39,7–89,2 %) | 8/10 (80,0 %, IC95 % 49,0–94,3 %) |
| pass^k — résultat juste partout, à chaque essai | 0/5 (0,0 %, IC95 % 0,0–43,4 %) ; 5 cas sans assez d'essais | 0/5 (0,0 %, IC95 % 0,0–43,4 %) ; 5 cas sans assez d'essais |

Réparations : 6 essai(s) à réparer, 5 tenté(s) en 7 tentative(s), 3 avec une correction rejouable ; saine exécutable après : 2, conforme après : 2 ; coût des réparations : **0.594 $**.

- commande_persistance_serveur essai 1 : l'agent n'a rien réécrit
- commande_confirmation essai 2 : l'agent n'a rien réécrit
- commande_persistance_serveur essai 3 : plafond de coût : cumul 4.047 $ + essai le plus cher attendu 0.535 $ > plafond 4.500 $

## Coût

Total : **3.453 $** = 3.197 € (1 € = 1.08 $) pour 25 génération(s) ; par génération : 0.138 $ / 0.128 €.
Les jeux sur les variantes ne coûtent rien (aucun appel LLM) : tout le coût est celui des générations.

| Cas | Coût moyen par génération ($) |
|---|---|
| client_creation_nom_limite | 0.107 |
| client_creation_nom_requis | 0.089 |
| client_creation_valide | 0.087 |
| commande_confirmation | 0.112 |
| commande_persistance_serveur | 0.378 |
| connexion_refusee | 0.183 |
| connexion_valide | 0.107 |
| panier_remise_arrondi | 0.080 |
| panier_total_tva | 0.132 |
| produits_recherche | 0.066 |

## Intégrité : le MÊME test est joué partout

Jeux dont les empreintes sha256 des fichiers joués égalent celles de la génération : **46** ; divergentes : **0** ; non rapportées : 0.

## Écarts aux attendus (à instruire : le test généré, le défaut ou le verdict — jamais l'attendu)

| Cas | Variante | Essai | Attendu | Obtenu | Cause |
|---|---|---|---|---|---|
| commande_persistance_serveur | saine | 1 | conforme | technical_error | unknown |
| connexion_valide | saine | 1 | conforme | blocked | precondition_non_remplie |
| panier_total_tva | saine | 1 | conforme | technical_error | wrong_field_name |
| panier_total_tva | total_faux | 1 | non_conforme | technical_error | wrong_field_name |
| client_creation_nom_limite | saine | 2 | conforme | technical_error | wrong_field_name |
| client_creation_valide | saine | 2 | conforme | non_conforme | assertion_mismatch |
| commande_confirmation | saine | 2 | conforme | technical_error | wrong_field_name |
| commande_persistance_serveur | saine | 2 | conforme | technical_error | generation_echouee |
| commande_persistance_serveur | etat_non_enregistre | 2 | non_conforme | technical_error | generation_echouee |
| panier_total_tva | saine | 2 | conforme | technical_error | wrong_field_name |
| panier_total_tva | total_faux | 2 | non_conforme | technical_error | wrong_field_name |
| client_creation_nom_requis | saine | 3 | conforme | non_conforme | assertion_mismatch |
| commande_persistance_serveur | saine | 3 | conforme | technical_error | wrong_field_name |
| commande_persistance_serveur | etat_non_enregistre | 3 | non_conforme | technical_error | wrong_field_name |

## Génération par essai

| Cas | Essai | Généré | Coût ($) | Empreinte du test (sha256) |
|---|---|---|---|---|
| client_creation_nom_limite | 1 | oui | 0.162 | `3189dde196b6ea38` |
| client_creation_nom_requis | 1 | oui | 0.064 | `72ca1ed13e52d4e1` |
| client_creation_valide | 1 | oui | 0.088 | `ba6e01aeb6006180` |
| commande_confirmation | 1 | oui | 0.140 | `6b2fd1bd7791e658` |
| commande_persistance_serveur | 1 | oui | 0.325 | `fe7979d74fdd0450` |
| connexion_refusee | 1 | oui | 0.145 | `525758ba7253efcf` |
| connexion_valide | 1 | oui | 0.123 | `707da6b7c788ab0f` |
| panier_remise_arrondi | 1 | oui | 0.069 | `35671fb8de636618` |
| panier_total_tva | 1 | oui | 0.141 | `0fd39823bb2e21fa` |
| produits_recherche | 1 | oui | 0.065 | `fc50ae34987887d0` |
| client_creation_nom_limite | 2 | oui | 0.094 | `5c3183a1d64617f5` |
| client_creation_nom_requis | 2 | oui | 0.128 | `f7ead175c9e65ad5` |
| client_creation_valide | 2 | oui | 0.070 | `3b47278d28beb4b9` |
| commande_confirmation | 2 | oui | 0.092 | `9a7737f2055a74a5` |
| commande_persistance_serveur | 2 | NON : génération sans essai à blanc passé | 0.535 | `—` |
| connexion_refusee | 2 | oui | 0.222 | `b828e96dda85c704` |
| connexion_valide | 2 | oui | 0.091 | `154e216d62a2f85b` |
| panier_remise_arrondi | 2 | oui | 0.091 | `016d97ab8c93a798` |
| panier_total_tva | 2 | oui | 0.123 | `f7dbcd64a008254b` |
| produits_recherche | 2 | oui | 0.067 | `049aafd5e5610c17` |
| client_creation_nom_limite | 3 | oui | 0.063 | `a3966b38890b7552` |
| client_creation_nom_requis | 3 | oui | 0.076 | `65e8a9ffb542f8be` |
| client_creation_valide | 3 | oui | 0.104 | `eb953158d017b66e` |
| commande_confirmation | 3 | oui | 0.103 | `cceea9901573b881` |
| commande_persistance_serveur | 3 | oui | 0.273 | `cbe0e4f8da06ec0f` |
