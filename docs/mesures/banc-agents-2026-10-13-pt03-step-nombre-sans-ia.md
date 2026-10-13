# Banc d'agents web — 2026-10-13 — pt03-step-nombre-sans-ia

Échantillon : **2 cas × k = 2 essais** → 4/4 essais lancés, 8 jeux (couples cas/variante). Commit `677ce43` · modèle de génération `claude-sonnet-4-6` · testpilot `0.1.0` · behave `1.3.3` · playwright `1.62.0`.

## ⚠️ Sous-ensemble de cas (mise au point)

Ce rapport ne porte PAS sur le corpus entier : ne jamais le publier comme mesure du banc.

## Indicateurs

| Indicateur | Valeur |
|---|---|
| **Faux verts** (défaut injecté, attendu non_conforme, obtenu conforme) | 0/4 (0,0 %, IC95 % 0,0–49,0 %) |
| Faux rouges (saine, attendu conforme, obtenu non_conforme) | 0/4 (0,0 %, IC95 % 0,0–49,0 %) |
| pass@1 — le test généré s'exécute sans erreur technique | 2/2 (100,0 %, IC95 % 34,2–100,0 %) |
| pass@2 — au moins un essai sur 2 | 2/2 (100,0 %, IC95 % 34,2–100,0 %) |
| pass^2 — tous les essais | 2/2 (100,0 %, IC95 % 34,2–100,0 %) |
| pass@1 — résultat juste partout (saine ET défauts) | 2/2 (100,0 %, IC95 % 34,2–100,0 %) |
| pass@2 — résultat juste partout | 2/2 (100,0 %, IC95 % 34,2–100,0 %) |
| pass^2 — résultat juste partout, à chaque essai | 2/2 (100,0 %, IC95 % 34,2–100,0 %) |

« non mesuré » signifie qu'aucun jeu concluant n'existe pour cet indicateur : ce n'est PAS 0 %. Un taux de faux verts faible obtenu avec beaucoup de non concluants ne prouve rien : lire la ligne suivante et les intervalles (Wilson 95 %).

## Résultats non concluants (comptés, jamais retirés)

Aucun jeu non concluant.

## Détection par défaut

| Défaut | Jeux | Concluants | Détectés (non_conforme) | dont fiables (saine du même essai conforme) | Faux verts | Non concluants |
|---|---|---|---|---|---|---|
| `total_faux` | 4 | 4 | 4/4 (100,0 %, IC95 % 51,0–100,0 %) | 4/4 (100,0 %, IC95 % 51,0–100,0 %) | 0 | 0 |

## Coût

Total : **0.000 $** = 0.000 € (1 € = 1.08 $) pour 4 génération(s) ; par génération : 0.000 $ / 0.000 €.
Les jeux sur les variantes ne coûtent rien (aucun appel LLM) : tout le coût est celui des générations.

| Cas | Coût moyen par génération ($) |
|---|---|
| panier_total_tva | 0.000 |
| panier_remise_arrondi | 0.000 |

## Intégrité : le MÊME test est joué partout

Jeux dont les empreintes sha256 des fichiers joués égalent celles de la génération : **8** ; divergentes : **0** ; non rapportées : 0.

## Code libre (lot VH-06)

Tests générés sans AUCUN step écrit à la main : **2/4** ; steps définis par les tests : 2 au total (maximum 1 dans un test). Un step écrit à la main n'a ni test de falsifiabilité ni résolution éprouvée : la cible est zéro.

## Génération par essai

| Cas | Essai | Généré | Coût ($) | Refus à l'écriture | Steps écrits à la main | Empreinte du test (sha256) |
|---|---|---|---|---|---|---|
| panier_total_tva | 1 | oui | 0.000 | — | 1 | `755109a976c60048` |
| panier_remise_arrondi | 1 | oui | 0.000 | — | 0 | `4ae9c8e0b61e4912` |
| panier_total_tva | 2 | oui | 0.000 | — | 1 | `7daa0eb2068490b0` |
| panier_remise_arrondi | 2 | oui | 0.000 | — | 0 | `cabce81bd4307d6b` |
