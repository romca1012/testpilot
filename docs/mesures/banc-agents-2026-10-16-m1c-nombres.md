# Banc d'agents web — 2026-10-16 — m1c-nombres

Échantillon : **2 cas × k = 3 essais** → 6/6 essais lancés, 12 jeux (couples cas/variante). Commit `9fa0ef6` · modèle de génération `claude-sonnet-4-6` · testpilot `0.1.0` · behave `1.3.3` · playwright `1.62.0`.

## ⚠️ Sous-ensemble de cas (mise au point)

Ce rapport ne porte PAS sur le corpus entier : ne jamais le publier comme mesure du banc.

## Indicateurs

| Indicateur | Valeur |
|---|---|
| **Faux verts** (défaut injecté, attendu non_conforme, obtenu conforme) | non mesuré (6 non concluants) |
| Faux rouges (saine, attendu conforme, obtenu non_conforme) | non mesuré (6 non concluants) |
| pass@1 — le test généré s'exécute sans erreur technique | 0/2 (0,0 %, IC95 % 0,0–65,8 %) |
| pass@3 — au moins un essai sur 3 | 0/2 (0,0 %, IC95 % 0,0–65,8 %) |
| pass^3 — tous les essais | 0/2 (0,0 %, IC95 % 0,0–65,8 %) |
| pass@1 — résultat juste partout (saine ET défauts) | 0/2 (0,0 %, IC95 % 0,0–65,8 %) |
| pass@3 — résultat juste partout | 0/2 (0,0 %, IC95 % 0,0–65,8 %) |
| pass^3 — résultat juste partout, à chaque essai | 0/2 (0,0 %, IC95 % 0,0–65,8 %) |

« non mesuré » signifie qu'aucun jeu concluant n'existe pour cet indicateur : ce n'est PAS 0 %. Un taux de faux verts faible obtenu avec beaucoup de non concluants ne prouve rien : lire la ligne suivante et les intervalles (Wilson 95 %).

## Résultats non concluants (comptés, jamais retirés)

| Verdict | Jeux |
|---|---|
| technical_error | 12 |

## Détection par défaut

| Défaut | Jeux | Concluants | Détectés (non_conforme) | dont fiables (saine du même essai conforme) | Faux verts | Non concluants |
|---|---|---|---|---|---|---|
| `total_faux` | 6 | 0 | non mesuré | non mesuré | 0 | 6 |

## Coût

Total : **0.849 $** = 0.786 € (1 € = 1.08 $) pour 6 génération(s) ; par génération : 0.141 $ / 0.131 €.
Les jeux sur les variantes ne coûtent rien (aucun appel LLM) : tout le coût est celui des générations.

| Cas | Coût moyen par génération ($) |
|---|---|
| panier_total_tva | 0.172 |
| panier_remise_arrondi | 0.111 |

## Intégrité : le MÊME test est joué partout

Jeux dont les empreintes sha256 des fichiers joués égalent celles de la génération : **6** ; divergentes : **0** ; non rapportées : 0.

## Écarts aux attendus (à instruire : le test généré, le défaut ou le verdict — jamais l'attendu)

| Cas | Variante | Essai | Attendu | Obtenu | Cause |
|---|---|---|---|---|---|
| panier_total_tva | saine | 1 | conforme | technical_error | wrong_field_name |
| panier_total_tva | total_faux | 1 | non_conforme | technical_error | wrong_field_name |
| panier_remise_arrondi | saine | 1 | conforme | technical_error | generation_echouee |
| panier_remise_arrondi | total_faux | 1 | non_conforme | technical_error | generation_echouee |
| panier_total_tva | saine | 2 | conforme | technical_error | wrong_field_name |
| panier_total_tva | total_faux | 2 | non_conforme | technical_error | wrong_field_name |
| panier_remise_arrondi | saine | 2 | conforme | technical_error | generation_echouee |
| panier_remise_arrondi | total_faux | 2 | non_conforme | technical_error | generation_echouee |
| panier_total_tva | saine | 3 | conforme | technical_error | wrong_field_name |
| panier_total_tva | total_faux | 3 | non_conforme | technical_error | wrong_field_name |
| panier_remise_arrondi | saine | 3 | conforme | technical_error | generation_echouee |
| panier_remise_arrondi | total_faux | 3 | non_conforme | technical_error | generation_echouee |

## Code libre (lot VH-06)

Tests générés sans AUCUN step écrit à la main : **1/3** ; steps définis par les tests : 6 au total (maximum 4 dans un test). Un step écrit à la main n'a ni test de falsifiabilité ni résolution éprouvée : la cible est zéro.

## Second jeu de données

Chaque test qui écrit une variable, et dont le jeu sur l'application SAINE est conforme à l'attendu, est rejoué sur la saine avec un second jeu (`nom_client` = « Martin Lefèvre SA », `ville_client` = « Paris »). Un test est compté PROUVÉ seulement si le jeu est conforme ET si l'état du serveur montre la valeur du second jeu de CHAQUE variable qu'il écrit, sans aucune valeur du premier ; un verdict conforme seul dit seulement que le test ne casse pas. « Prouvé » dit que les valeurs ont atteint le serveur, pas qu'un « Alors » les vérifie. Un cas qui ne crée rien (« aucune trace au serveur ») ne peut pas être prouvé ainsi. Compté à part : jamais dans pass@k ni dans les faux verts. Les versions réparées ne sont pas rejouées au second jeu.

Aucun test rejouable (aucun test n'écrit de variable, ou leur saine est déjà en écart) : non mesuré.

## Génération par essai

| Cas | Essai | Généré | Coût ($) | Refus à l'écriture | Steps écrits à la main | Empreinte du test (sha256) |
|---|---|---|---|---|---|---|
| panier_total_tva | 1 | oui | 0.217 | — | 2 | `f9500bd19e38e837` |
| panier_remise_arrondi | 1 | NON : génération sans essai à blanc passé | 0.148 | — | — | `—` |
| panier_total_tva | 2 | oui | 0.169 | — | 4 | `4c3c98e9280ce9d2` |
| panier_remise_arrondi | 2 | NON : génération sans essai à blanc passé | 0.095 | — | — | `—` |
| panier_total_tva | 3 | oui | 0.131 | — | 0 | `e0be2196ff1dd7c0` |
| panier_remise_arrondi | 3 | NON : génération sans essai à blanc passé | 0.089 | — | — | `—` |
