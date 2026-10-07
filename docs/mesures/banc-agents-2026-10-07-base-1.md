# Banc d'agents web — 2026-10-07 — base-1

Échantillon : **10 cas × k = 3 essais** → 30/30 essais lancés, 57 jeux (couples cas/variante). Commit `9ede14b` · modèle de génération `claude-sonnet-4-6` · testpilot `0.1.0` · behave `1.3.3` · playwright `1.62.0`.

## Indicateurs

| Indicateur | Valeur |
|---|---|
| **Faux verts** (défaut injecté, attendu non_conforme, obtenu conforme) | 0/19 (0,0 %, IC95 % 0,0–16,8 %) ; 8 non concluants |
| Faux rouges (saine, attendu conforme, obtenu non_conforme) | 1/16 (6,2 %, IC95 % 1,1–28,3 %) ; 14 non concluants |
| pass@1 — le test généré s'exécute sans erreur technique | 6/10 (60,0 %, IC95 % 31,3–83,2 %) |
| pass@3 — au moins un essai sur 3 | 6/10 (60,0 %, IC95 % 31,3–83,2 %) |
| pass^3 — tous les essais | 4/10 (40,0 %, IC95 % 16,8–68,7 %) |
| pass@1 — résultat juste partout (saine ET défauts) | 6/10 (60,0 %, IC95 % 31,3–83,2 %) |
| pass@3 — résultat juste partout | 6/10 (60,0 %, IC95 % 31,3–83,2 %) |
| pass^3 — résultat juste partout, à chaque essai | 3/10 (30,0 %, IC95 % 10,8–60,3 %) |

« non mesuré » signifie qu'aucun jeu concluant n'existe pour cet indicateur : ce n'est PAS 0 %. Un taux de faux verts faible obtenu avec beaucoup de non concluants ne prouve rien : lire la ligne suivante et les intervalles (Wilson 95 %).

## Résultats non concluants (comptés, jamais retirés)

| Verdict | Jeux |
|---|---|
| blocked | 5 |
| technical_error | 17 |

## Détection par défaut

| Défaut | Jeux | Concluants | Détectés (non_conforme) | Faux verts | Non concluants |
|---|---|---|---|---|---|
| `etat_non_enregistre` | 6 | 3 | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 0 | 3 |
| `filtre_ignore` | 3 | 3 | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 0 | 0 |
| `login_accepte_tout` | 3 | 3 | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 0 | 0 |
| `message_erreur_absent` | 6 | 5 | 5/5 (100,0 %, IC95 % 56,6–100,0 %) | 0 | 1 |
| `total_faux` | 6 | 2 | 2/2 (100,0 %, IC95 % 34,2–100,0 %) | 0 | 4 |
| `validation_absente` | 3 | 3 | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 0 | 0 |

## Coût

Total : **3.466 $** = 3.210 € (1 € = 1.08 $) pour 30 génération(s) ; par génération : 0.116 $ / 0.107 €.
Les jeux sur les variantes ne coûtent rien (aucun appel LLM) : tout le coût est celui des générations.

| Cas | Coût moyen par génération ($) |
|---|---|
| client_creation_nom_limite | 0.113 |
| client_creation_nom_requis | 0.113 |
| client_creation_valide | 0.086 |
| commande_confirmation | 0.111 |
| commande_persistance_serveur | 0.233 |
| connexion_refusee | 0.087 |
| connexion_valide | 0.130 |
| panier_remise_arrondi | 0.096 |
| panier_total_tva | 0.117 |
| produits_recherche | 0.069 |

## Intégrité : le MÊME test est joué partout

Jeux dont les empreintes sha256 des fichiers joués égalent celles de la génération : **55** ; divergentes : **0** ; non rapportées : 0.

## Écarts aux attendus (à instruire : le test généré, le défaut ou le verdict — jamais l'attendu)

| Cas | Variante | Essai | Attendu | Obtenu | Cause |
|---|---|---|---|---|---|
| client_creation_nom_limite | saine | 1 | conforme | blocked | precondition_non_remplie |
| client_creation_nom_requis | saine | 1 | conforme | blocked | precondition_non_remplie |
| commande_persistance_serveur | saine | 1 | conforme | technical_error | broken_test_code |
| commande_persistance_serveur | etat_non_enregistre | 1 | non_conforme | technical_error | broken_test_code |
| panier_total_tva | saine | 1 | conforme | technical_error | wrong_field_name |
| panier_total_tva | total_faux | 1 | non_conforme | technical_error | wrong_field_name |
| client_creation_nom_limite | saine | 2 | conforme | blocked | precondition_non_remplie |
| client_creation_nom_requis | saine | 2 | conforme | blocked | precondition_non_remplie |
| commande_confirmation | saine | 2 | conforme | technical_error | wrong_field_name |
| commande_persistance_serveur | saine | 2 | conforme | technical_error | broken_test_code |
| commande_persistance_serveur | etat_non_enregistre | 2 | non_conforme | technical_error | broken_test_code |
| panier_total_tva | saine | 2 | conforme | technical_error | wrong_field_name |
| panier_total_tva | total_faux | 2 | non_conforme | technical_error | wrong_field_name |
| client_creation_nom_limite | saine | 3 | conforme | technical_error | wrong_field_name |
| client_creation_nom_limite | message_erreur_absent | 3 | non_conforme | technical_error | wrong_field_name |
| client_creation_nom_requis | saine | 3 | conforme | blocked | precondition_non_remplie |
| commande_persistance_serveur | saine | 3 | conforme | technical_error | broken_test_code |
| commande_persistance_serveur | etat_non_enregistre | 3 | non_conforme | technical_error | broken_test_code |
| connexion_valide | saine | 3 | conforme | non_conforme | assertion_mismatch |
| panier_remise_arrondi | saine | 3 | conforme | technical_error | generation_echouee |
| panier_remise_arrondi | total_faux | 3 | non_conforme | technical_error | generation_echouee |
| panier_total_tva | saine | 3 | conforme | technical_error | wrong_field_name |
| panier_total_tva | total_faux | 3 | non_conforme | technical_error | wrong_field_name |

## Génération par essai

| Cas | Essai | Généré | Coût ($) | Empreinte du test (sha256) |
|---|---|---|---|---|
| client_creation_nom_limite | 1 | oui | 0.124 | `29d0629edc445cae` |
| client_creation_nom_requis | 1 | oui | 0.089 | `9bab2cbcbc42d0d2` |
| client_creation_valide | 1 | oui | 0.085 | `e446f0737000ddc7` |
| commande_confirmation | 1 | oui | 0.121 | `3e099931d222e82d` |
| commande_persistance_serveur | 1 | oui | 0.257 | `2d3adcf8875ae76c` |
| connexion_refusee | 1 | oui | 0.077 | `d98996d83bcca7f8` |
| connexion_valide | 1 | oui | 0.127 | `f4e80f8f40132457` |
| panier_remise_arrondi | 1 | oui | 0.106 | `efb1938c91a3a245` |
| panier_total_tva | 1 | oui | 0.117 | `7218119d9b104fa5` |
| produits_recherche | 1 | oui | 0.075 | `36a10121068c17b4` |
| client_creation_nom_limite | 2 | oui | 0.120 | `f052f09adc4bcbfc` |
| client_creation_nom_requis | 2 | oui | 0.116 | `3c07a5eb37636cab` |
| client_creation_valide | 2 | oui | 0.088 | `e657e12fa4884b6d` |
| commande_confirmation | 2 | oui | 0.102 | `4f9be12f048d348c` |
| commande_persistance_serveur | 2 | oui | 0.243 | `1167c140999df9ab` |
| connexion_refusee | 2 | oui | 0.091 | `aec4829b7a9d78c9` |
| connexion_valide | 2 | oui | 0.149 | `fe9a40e26464b60a` |
| panier_remise_arrondi | 2 | oui | 0.092 | `10cfd293bdccc014` |
| panier_total_tva | 2 | oui | 0.085 | `d111c0e4b57a9081` |
| produits_recherche | 2 | oui | 0.079 | `a9265fe70792d700` |
| client_creation_nom_limite | 3 | oui | 0.095 | `7bc805496785816c` |
| client_creation_nom_requis | 3 | oui | 0.135 | `a5c8c1a563d567c7` |
| client_creation_valide | 3 | oui | 0.086 | `216480e319da5015` |
| commande_confirmation | 3 | oui | 0.111 | `7bac6064c1f453f9` |
| commande_persistance_serveur | 3 | oui | 0.197 | `90ac5f5e443a64ff` |
| connexion_refusee | 3 | oui | 0.094 | `c8af6fdfcce8b245` |
| connexion_valide | 3 | oui | 0.115 | `cb95461d90cbb571` |
| panier_remise_arrondi | 3 | NON : génération sans essai à blanc passé | 0.090 | `—` |
| panier_total_tva | 3 | oui | 0.149 | `2fbbb57d4ffc2dd1` |
| produits_recherche | 3 | oui | 0.054 | `5916683954a4afe6` |
