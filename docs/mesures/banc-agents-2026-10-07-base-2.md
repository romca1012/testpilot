# Banc d'agents web — 2026-10-07 — base-2

Échantillon : **10 cas × k = 3 essais** → 30/30 essais lancés, 57 jeux (couples cas/variante). Commit `0c60317` · modèle de génération `claude-sonnet-4-6` · testpilot `0.1.0` · behave `1.3.3` · playwright `1.62.0`.

## Indicateurs

| Indicateur | Valeur |
|---|---|
| **Faux verts** (défaut injecté, attendu non_conforme, obtenu conforme) | 0/22 (0,0 %, IC95 % 0,0–14,9 %) ; 5 non concluants |
| Faux rouges (saine, attendu conforme, obtenu non_conforme) | 9/24 (37,5 %, IC95 % 21,2–57,3 %) ; 6 non concluants |
| pass@1 — le test généré s'exécute sans erreur technique | 8/10 (80,0 %, IC95 % 49,0–94,3 %) |
| pass@3 — au moins un essai sur 3 | 9/10 (90,0 %, IC95 % 59,6–98,2 %) |
| pass^3 — tous les essais | 6/10 (60,0 %, IC95 % 31,3–83,2 %) |
| pass@1 — résultat juste partout (saine ET défauts) | 5/10 (50,0 %, IC95 % 23,7–76,3 %) |
| pass@3 — résultat juste partout | 7/10 (70,0 %, IC95 % 39,7–89,2 %) |
| pass^3 — résultat juste partout, à chaque essai | 2/10 (20,0 %, IC95 % 5,7–51,0 %) |

« non mesuré » signifie qu'aucun jeu concluant n'existe pour cet indicateur : ce n'est PAS 0 %. Un taux de faux verts faible obtenu avec beaucoup de non concluants ne prouve rien : lire la ligne suivante et les intervalles (Wilson 95 %).

## Résultats non concluants (comptés, jamais retirés)

| Verdict | Jeux |
|---|---|
| technical_error | 11 |

## Détection par défaut

| Défaut | Jeux | Concluants | Détectés (non_conforme) | Faux verts | Non concluants |
|---|---|---|---|---|---|
| `etat_non_enregistre` | 6 | 5 | 5/5 (100,0 %, IC95 % 56,6–100,0 %) | 0 | 1 |
| `filtre_ignore` | 3 | 3 | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 0 | 0 |
| `login_accepte_tout` | 3 | 3 | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 0 | 0 |
| `message_erreur_absent` | 6 | 6 | 6/6 (100,0 %, IC95 % 61,0–100,0 %) | 0 | 0 |
| `total_faux` | 6 | 2 | 2/2 (100,0 %, IC95 % 34,2–100,0 %) | 0 | 4 |
| `validation_absente` | 3 | 3 | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 0 | 0 |

## Coût

Total : **3.279 $** = 3.036 € (1 € = 1.08 $) pour 30 génération(s) ; par génération : 0.109 $ / 0.101 €.
Les jeux sur les variantes ne coûtent rien (aucun appel LLM) : tout le coût est celui des générations.

| Cas | Coût moyen par génération ($) |
|---|---|
| client_creation_nom_limite | 0.104 |
| client_creation_nom_requis | 0.117 |
| client_creation_valide | 0.083 |
| commande_confirmation | 0.108 |
| commande_persistance_serveur | 0.176 |
| connexion_refusee | 0.089 |
| connexion_valide | 0.109 |
| panier_remise_arrondi | 0.084 |
| panier_total_tva | 0.130 |
| produits_recherche | 0.092 |

## Intégrité : le MÊME test est joué partout

Jeux dont les empreintes sha256 des fichiers joués égalent celles de la génération : **54** ; divergentes : **0** ; non rapportées : 0.

## Écarts aux attendus (à instruire : le test généré, le défaut ou le verdict — jamais l'attendu)

| Cas | Variante | Essai | Attendu | Obtenu | Cause |
|---|---|---|---|---|---|
| client_creation_nom_limite | saine | 1 | conforme | non_conforme | assertion_mismatch |
| client_creation_valide | saine | 1 | conforme | non_conforme | assertion_mismatch |
| commande_confirmation | saine | 1 | conforme | technical_error | generation_echouee |
| commande_persistance_serveur | saine | 1 | conforme | non_conforme | assertion_mismatch |
| panier_total_tva | saine | 1 | conforme | technical_error | wrong_field_name |
| panier_total_tva | total_faux | 1 | non_conforme | technical_error | wrong_field_name |
| client_creation_nom_limite | saine | 2 | conforme | non_conforme | assertion_mismatch |
| client_creation_nom_requis | saine | 2 | conforme | non_conforme | assertion_mismatch |
| commande_persistance_serveur | saine | 2 | conforme | non_conforme | assertion_mismatch |
| connexion_valide | saine | 2 | conforme | non_conforme | assertion_mismatch |
| panier_remise_arrondi | saine | 2 | conforme | technical_error | generation_echouee |
| panier_remise_arrondi | total_faux | 2 | non_conforme | technical_error | generation_echouee |
| panier_total_tva | saine | 2 | conforme | technical_error | wrong_field_name |
| panier_total_tva | total_faux | 2 | non_conforme | technical_error | wrong_field_name |
| client_creation_nom_limite | saine | 3 | conforme | non_conforme | assertion_mismatch |
| client_creation_nom_requis | saine | 3 | conforme | non_conforme | assertion_mismatch |
| commande_persistance_serveur | saine | 3 | conforme | technical_error | unknown |
| commande_persistance_serveur | etat_non_enregistre | 3 | non_conforme | technical_error | unknown |
| panier_total_tva | saine | 3 | conforme | technical_error | wrong_field_name |
| panier_total_tva | total_faux | 3 | non_conforme | technical_error | wrong_field_name |

## Génération par essai

| Cas | Essai | Généré | Coût ($) | Empreinte du test (sha256) |
|---|---|---|---|---|
| client_creation_nom_limite | 1 | oui | 0.130 | `c50f3a9e34164f7d` |
| client_creation_nom_requis | 1 | oui | 0.150 | `9260cd82b25537c5` |
| client_creation_valide | 1 | oui | 0.093 | `33320586fc53662b` |
| commande_confirmation | 1 | NON : génération sans essai à blanc passé | 0.105 | `—` |
| commande_persistance_serveur | 1 | oui | 0.198 | `c3d4c07bab8c36e6` |
| connexion_refusee | 1 | oui | 0.090 | `6c4140aefc8ddb09` |
| connexion_valide | 1 | oui | 0.108 | `2b60720f813e6c7a` |
| panier_remise_arrondi | 1 | oui | 0.086 | `57b6993d808458c7` |
| panier_total_tva | 1 | oui | 0.136 | `95d86171d8764300` |
| produits_recherche | 1 | oui | 0.064 | `f3ffcab95f929ba1` |
| client_creation_nom_limite | 2 | oui | 0.066 | `6559e33f244f32bb` |
| client_creation_nom_requis | 2 | oui | 0.107 | `e2889842646b9674` |
| client_creation_valide | 2 | oui | 0.090 | `162c89d6a1f0c9ad` |
| commande_confirmation | 2 | oui | 0.123 | `007293cf76c501df` |
| commande_persistance_serveur | 2 | oui | 0.182 | `db17a37921816723` |
| connexion_refusee | 2 | oui | 0.074 | `96b6f31b918da30a` |
| connexion_valide | 2 | oui | 0.120 | `03c1d928121183b3` |
| panier_remise_arrondi | 2 | NON : génération sans essai à blanc passé | 0.085 | `—` |
| panier_total_tva | 2 | oui | 0.129 | `2a345cc7027de71e` |
| produits_recherche | 2 | oui | 0.147 | `a66a8cd7fae0e258` |
| client_creation_nom_limite | 3 | oui | 0.118 | `b50697f063a9d463` |
| client_creation_nom_requis | 3 | oui | 0.094 | `db15ff5c142d5c91` |
| client_creation_valide | 3 | oui | 0.067 | `e9c0609dde4dae3f` |
| commande_confirmation | 3 | oui | 0.095 | `fa5ffcde8b8ed7fb` |
| commande_persistance_serveur | 3 | oui | 0.149 | `6aa86cef597a5182` |
| connexion_refusee | 3 | oui | 0.105 | `9b8474b540c5ed69` |
| connexion_valide | 3 | oui | 0.100 | `18abccb1cd9bf405` |
| panier_remise_arrondi | 3 | oui | 0.081 | `358cc37262f326ec` |
| panier_total_tva | 3 | oui | 0.124 | `a917d14131abf391` |
| produits_recherche | 3 | oui | 0.064 | `15a50d4434205d0d` |
