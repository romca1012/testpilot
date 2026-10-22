# Banc d'agents web — 2026-10-22 — etape5-apres

Échantillon : **11 cas × k = 2 essais** → 22/22 essais lancés, 42 jeux (couples cas/variante). Commit `3e20ca4` · modèle de génération `claude-sonnet-4-6` · testpilot `0.1.0` · behave `1.3.3` · playwright `1.62.0`.

## Indicateurs

| Indicateur | Valeur |
|---|---|
| **Faux verts** (défaut injecté, attendu non_conforme, obtenu conforme) | 0/16 (0,0 %, IC95 % 0,0–19,4 %) ; 4 non concluants |
| Faux rouges (saine, attendu conforme, obtenu non_conforme) | 1/17 (5,9 %, IC95 % 1,0–27,0 %) ; 5 non concluants |
| pass@1 — le test généré s'exécute sans erreur technique | 9/11 (81,8 %, IC95 % 52,3–94,9 %) |
| pass@2 — au moins un essai sur 2 | 10/11 (90,9 %, IC95 % 62,3–98,4 %) |
| pass^2 — tous les essais | 7/11 (63,6 %, IC95 % 35,4–84,8 %) |
| pass@1 — résultat juste partout (saine ET défauts) | 8/11 (72,7 %, IC95 % 43,4–90,3 %) |
| pass@2 — résultat juste partout | 10/11 (90,9 %, IC95 % 62,3–98,4 %) |
| pass^2 — résultat juste partout, à chaque essai | 6/11 (54,5 %, IC95 % 28,0–78,7 %) |

« non mesuré » signifie qu'aucun jeu concluant n'existe pour cet indicateur : ce n'est PAS 0 %. Un taux de faux verts faible obtenu avec beaucoup de non concluants ne prouve rien : lire la ligne suivante et les intervalles (Wilson 95 %).

## Résultats non concluants (comptés, jamais retirés)

| Verdict | Jeux |
|---|---|
| technical_error | 9 |

## Détection par défaut

| Défaut | Jeux | Concluants | Détectés (non_conforme) | dont fiables (saine du même essai conforme) | Faux verts | Non concluants |
|---|---|---|---|---|---|---|
| `etat_non_enregistre` | 4 | 3 | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 2/3 (66,7 %, IC95 % 20,8–93,9 %) | 0 | 1 |
| `filtre_ignore` | 2 | 1 | 1/1 (100,0 %, IC95 % 20,7–100,0 %) | 1/1 (100,0 %, IC95 % 20,7–100,0 %) | 0 | 1 |
| `limite_age_decalee` | 2 | 2 | 2/2 (100,0 %, IC95 % 34,2–100,0 %) | 2/2 (100,0 %, IC95 % 34,2–100,0 %) | 0 | 0 |
| `login_accepte_tout` | 2 | 2 | 2/2 (100,0 %, IC95 % 34,2–100,0 %) | 2/2 (100,0 %, IC95 % 34,2–100,0 %) | 0 | 0 |
| `message_erreur_absent` | 4 | 3 | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 2/3 (66,7 %, IC95 % 20,8–93,9 %) | 0 | 1 |
| `total_faux` | 4 | 3 | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 0 | 1 |
| `validation_absente` | 2 | 2 | 2/2 (100,0 %, IC95 % 34,2–100,0 %) | 2/2 (100,0 %, IC95 % 34,2–100,0 %) | 0 | 0 |

## Coût

Total : **3.399 $** = 3.148 € (1 € = 1.08 $) pour 22 génération(s) ; par génération : 0.155 $ / 0.143 €.
Les jeux sur les variantes ne coûtent rien (aucun appel LLM) : tout le coût est celui des générations.

| Cas | Coût moyen par génération ($) |
|---|---|
| acces_age_limite | 0.113 |
| client_creation_nom_limite | 0.103 |
| client_creation_nom_requis | 0.115 |
| client_creation_valide | 0.123 |
| commande_confirmation | 0.165 |
| commande_persistance_serveur | 0.328 |
| connexion_refusee | 0.089 |
| connexion_valide | 0.110 |
| panier_remise_arrondi | 0.150 |
| panier_total_tva | 0.275 |
| produits_recherche | 0.129 |

## Intégrité : le MÊME test est joué partout

Jeux dont les empreintes sha256 des fichiers joués égalent celles de la génération : **36** ; divergentes : **0** ; non rapportées : 0.

## Écarts aux attendus (à instruire : le test généré, le défaut ou le verdict — jamais l'attendu)

| Cas | Variante | Essai | Attendu | Obtenu | Cause |
|---|---|---|---|---|---|
| client_creation_nom_limite | saine | 1 | conforme | technical_error | generation_echouee |
| client_creation_nom_limite | message_erreur_absent | 1 | non_conforme | technical_error | generation_echouee |
| commande_persistance_serveur | saine | 1 | conforme | non_conforme | assertion_mismatch |
| panier_remise_arrondi | saine | 1 | conforme | technical_error | generation_echouee |
| panier_remise_arrondi | total_faux | 1 | non_conforme | technical_error | generation_echouee |
| client_creation_nom_limite | saine | 2 | conforme | technical_error | broken_test_code |
| client_creation_valide | saine | 2 | conforme | technical_error | wrong_field_name |
| client_creation_valide | etat_non_enregistre | 2 | non_conforme | technical_error | wrong_field_name |
| produits_recherche | saine | 2 | conforme | technical_error | generation_echouee |
| produits_recherche | filtre_ignore | 2 | non_conforme | technical_error | generation_echouee |

## Refus des gardes d'écriture pendant la génération (lot VH-04)

Chaque refus renvoie l'agent corriger dans la même génération : il coûte des tours, il ne casse rien.

| Code du refus | Nombre |
|---|---|
| `LITTERAL_NON_OBSERVE` | 4 |
| `CONSTAT_SANS_LECTURE` | 2 |
| `ECHAPPEMENT_LITTERAL` | 1 |
| `TRANSPORT_INTERDIT` | 1 |
| `PYTHON_INTERDIT` | 1 |

## Code libre (lot VH-06)

Tests générés sans AUCUN step écrit à la main : **16/19** ; steps définis par les tests : 6 au total (maximum 3 dans un test). Un step écrit à la main n'a ni test de falsifiabilité ni résolution éprouvée : la cible est zéro.

## Prêts à lancer (étape 3 du plan unique)

Tests que le produit livrerait **prêts à lancer** (aucun point de vigilance) : **17/22 (77,3 %, IC95 % 56,6–89,9 %)** des essais lancés ; générations échouées : 3 ; mesures impossibles : 0 ; faux verts parmi les prêts : **0**.

Contrôle de fin d'écriture **allumé** : la correction d'après-coup ne repasse pas sur les points déjà vus — mesure proche du produit, ses tours sont dans le coût.

| Raison du blocage | Tests |
|---|---|
| `champ_ui_non_verifie` | 2 |

Contrôle de fin d'écriture : 22 génération(s) ; tours 0 ×13, 1 ×9 ; générations où l'IA a reçu le point : `champ_ui_non_verifie` ×9.

## Génération par essai

| Cas | Essai | Généré | Coût ($) | Refus à l'écriture | Steps écrits à la main | Empreinte du test (sha256) |
|---|---|---|---|---|---|---|
| acces_age_limite | 1 | oui | 0.123 | — | 0 | `4b0ca0908c517d3a` |
| client_creation_nom_limite | 1 | NON : génération sans essai à blanc passé | 0.083 | — | — | `—` |
| client_creation_nom_requis | 1 | oui | 0.103 | — | 0 | `d9f824d6fe2bf73b` |
| client_creation_valide | 1 | oui | 0.145 | — | 0 | `5b53001734af5af3` |
| commande_confirmation | 1 | oui | 0.193 | ECHAPPEMENT_LITTERAL ×1 | 0 | `973df7f862752d04` |
| commande_persistance_serveur | 1 | oui | 0.298 | CONSTAT_SANS_LECTURE ×1, LITTERAL_NON_OBSERVE ×2, TRANSPORT_INTERDIT ×1 | 3 | `b0dd9f40ee3feaa3` |
| connexion_refusee | 1 | oui | 0.089 | — | 0 | `61c7edc49964343d` |
| connexion_valide | 1 | oui | 0.127 | — | 0 | `de10de62ecaa7786` |
| panier_remise_arrondi | 1 | NON : génération sans essai à blanc passé | 0.142 | — | — | `—` |
| panier_total_tva | 1 | oui | 0.250 | — | 2 | `282ec03eec287650` |
| produits_recherche | 1 | oui | 0.161 | LITTERAL_NON_OBSERVE ×1 | 1 | `669ebd7165285bd2` |
| acces_age_limite | 2 | oui | 0.103 | — | 0 | `41daf3e7bbad4d1a` |
| client_creation_nom_limite | 2 | oui | 0.122 | — | 0 | `37071989ffcf278b` |
| client_creation_nom_requis | 2 | oui | 0.127 | — | 0 | `34a0606f94f49e89` |
| client_creation_valide | 2 | oui | 0.100 | — | 0 | `d9ac6773eed23058` |
| commande_confirmation | 2 | oui | 0.137 | — | 0 | `a33468a5877b7a0b` |
| commande_persistance_serveur | 2 | oui | 0.358 | CONSTAT_SANS_LECTURE ×1, LITTERAL_NON_OBSERVE ×1, PYTHON_INTERDIT ×1 | 0 | `0b13ae40625d8c95` |
| connexion_refusee | 2 | oui | 0.090 | — | 0 | `2af5c542de4f087c` |
| connexion_valide | 2 | oui | 0.093 | — | 0 | `4a80458f29a1228b` |
| panier_remise_arrondi | 2 | oui | 0.159 | — | 0 | `b63c468de51d1be9` |
| panier_total_tva | 2 | oui | 0.300 | — | 0 | `cdbc17bf82588814` |
| produits_recherche | 2 | NON : génération sans essai à blanc passé | 0.097 | — | — | `—` |
