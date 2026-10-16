# Banc d'agents web — 2026-10-16 — m1c-eteint

Échantillon : **4 cas × k = 3 essais** → 12/12 essais lancés, 27 jeux (couples cas/variante). Commit `9fa0ef6` · modèle de génération `claude-sonnet-4-6` · testpilot `0.1.0` · behave `1.3.3` · playwright `1.62.0`.

## ⚠️ Sous-ensemble de cas (mise au point)

Ce rapport ne porte PAS sur le corpus entier : ne jamais le publier comme mesure du banc.

## Indicateurs

| Indicateur | Valeur |
|---|---|
| **Faux verts** (défaut injecté, attendu non_conforme, obtenu conforme) | 0/8 (0,0 %, IC95 % 0,0–32,4 %) ; 7 non concluants |
| Faux rouges (saine, attendu conforme, obtenu non_conforme) | 0/5 (0,0 %, IC95 % 0,0–43,4 %) ; 7 non concluants |
| pass@1 — le test généré s'exécute sans erreur technique | 1/4 (25,0 %, IC95 % 4,6–69,9 %) |
| pass@3 — au moins un essai sur 3 | 3/4 (75,0 %, IC95 % 30,1–95,4 %) |
| pass^3 — tous les essais | 1/4 (25,0 %, IC95 % 4,6–69,9 %) |
| pass@1 — résultat juste partout (saine ET défauts) | 1/4 (25,0 %, IC95 % 4,6–69,9 %) |
| pass@3 — résultat juste partout | 3/4 (75,0 %, IC95 % 30,1–95,4 %) |
| pass^3 — résultat juste partout, à chaque essai | 1/4 (25,0 %, IC95 % 4,6–69,9 %) |

« non mesuré » signifie qu'aucun jeu concluant n'existe pour cet indicateur : ce n'est PAS 0 %. Un taux de faux verts faible obtenu avec beaucoup de non concluants ne prouve rien : lire la ligne suivante et les intervalles (Wilson 95 %).

## Résultats non concluants (comptés, jamais retirés)

| Verdict | Jeux |
|---|---|
| technical_error | 14 |

## Détection par défaut

| Défaut | Jeux | Concluants | Détectés (non_conforme) | dont fiables (saine du même essai conforme) | Faux verts | Non concluants |
|---|---|---|---|---|---|---|
| `etat_non_enregistre` | 3 | 1 | 1/1 (100,0 %, IC95 % 20,7–100,0 %) | 1/1 (100,0 %, IC95 % 20,7–100,0 %) | 0 | 2 |
| `message_erreur_absent` | 3 | 3 | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 0 | 0 |
| `total_faux` | 6 | 1 | 1/1 (100,0 %, IC95 % 20,7–100,0 %) | 1/1 (100,0 %, IC95 % 20,7–100,0 %) | 0 | 5 |
| `validation_absente` | 3 | 3 | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 0 | 0 |

## Coût

Total : **1.408 $** = 1.303 € (1 € = 1.08 $) pour 12 génération(s) ; par génération : 0.117 $ / 0.109 €.
Les jeux sur les variantes ne coûtent rien (aucun appel LLM) : tout le coût est celui des générations.

| Cas | Coût moyen par génération ($) |
|---|---|
| client_creation_valide | 0.110 |
| client_creation_nom_requis | 0.106 |
| panier_total_tva | 0.126 |
| panier_remise_arrondi | 0.127 |

## Intégrité : le MÊME test est joué partout

Jeux dont les empreintes sha256 des fichiers joués égalent celles de la génération : **21** ; divergentes : **0** ; non rapportées : 0.

## Écarts aux attendus (à instruire : le test généré, le défaut ou le verdict — jamais l'attendu)

| Cas | Variante | Essai | Attendu | Obtenu | Cause |
|---|---|---|---|---|---|
| client_creation_valide | saine | 1 | conforme | technical_error | wrong_field_name |
| client_creation_valide | etat_non_enregistre | 1 | non_conforme | technical_error | wrong_field_name |
| panier_total_tva | saine | 1 | conforme | technical_error | generation_echouee |
| panier_total_tva | total_faux | 1 | non_conforme | technical_error | generation_echouee |
| panier_remise_arrondi | saine | 1 | conforme | technical_error | generation_echouee |
| panier_remise_arrondi | total_faux | 1 | non_conforme | technical_error | generation_echouee |
| client_creation_valide | saine | 2 | conforme | technical_error | wrong_field_name |
| client_creation_valide | etat_non_enregistre | 2 | non_conforme | technical_error | wrong_field_name |
| panier_total_tva | saine | 2 | conforme | technical_error | wrong_field_name |
| panier_total_tva | total_faux | 2 | non_conforme | technical_error | wrong_field_name |
| panier_remise_arrondi | saine | 2 | conforme | technical_error | generation_echouee |
| panier_remise_arrondi | total_faux | 2 | non_conforme | technical_error | generation_echouee |
| panier_total_tva | saine | 3 | conforme | technical_error | wrong_field_name |
| panier_total_tva | total_faux | 3 | non_conforme | technical_error | wrong_field_name |

## Code libre (lot VH-06)

Tests générés sans AUCUN step écrit à la main : **8/9** ; steps définis par les tests : 4 au total (maximum 4 dans un test). Un step écrit à la main n'a ni test de falsifiabilité ni résolution éprouvée : la cible est zéro.

## Second jeu de données

Chaque test qui écrit une variable, et dont le jeu sur l'application SAINE est conforme à l'attendu, est rejoué sur la saine avec un second jeu (`nom_client` = « Martin Lefèvre SA », `ville_client` = « Paris »). Un test est compté PROUVÉ seulement si le jeu est conforme ET si l'état du serveur montre la valeur du second jeu de CHAQUE variable qu'il écrit, sans aucune valeur du premier ; un verdict conforme seul dit seulement que le test ne casse pas. « Prouvé » dit que les valeurs ont atteint le serveur, pas qu'un « Alors » les vérifie. Un cas qui ne crée rien (« aucune trace au serveur ») ne peut pas être prouvé ainsi. Compté à part : jamais dans pass@k ni dans les faux verts. Les versions réparées ne sont pas rejouées au second jeu.

Aucun test rejouable (aucun test n'écrit de variable, ou leur saine est déjà en écart) : non mesuré.

## Génération par essai

| Cas | Essai | Généré | Coût ($) | Refus à l'écriture | Steps écrits à la main | Empreinte du test (sha256) |
|---|---|---|---|---|---|---|
| client_creation_valide | 1 | oui | 0.141 | — | 0 | `0088922e32cd26eb` |
| client_creation_nom_requis | 1 | oui | 0.092 | — | 0 | `a005c9e6d9f96a0d` |
| panier_total_tva | 1 | NON : génération sans essai à blanc passé | 0.125 | — | — | `—` |
| panier_remise_arrondi | 1 | NON : génération sans essai à blanc passé | 0.089 | — | — | `—` |
| client_creation_valide | 2 | oui | 0.090 | — | 0 | `ca0e17342a45469b` |
| client_creation_nom_requis | 2 | oui | 0.128 | — | 0 | `d9b5c34de324fd0c` |
| panier_total_tva | 2 | oui | 0.131 | — | 4 | `ee77c69dd3cacfa1` |
| panier_remise_arrondi | 2 | NON : génération sans essai à blanc passé | 0.124 | — | — | `—` |
| client_creation_valide | 3 | oui | 0.098 | — | 0 | `d5705f7b63778390` |
| client_creation_nom_requis | 3 | oui | 0.098 | — | 0 | `d49895b1506b5dc0` |
| panier_total_tva | 3 | oui | 0.124 | — | 0 | `2320fd8af81647c4` |
| panier_remise_arrondi | 3 | oui | 0.169 | — | 0 | `dd8749c476cff3da` |
