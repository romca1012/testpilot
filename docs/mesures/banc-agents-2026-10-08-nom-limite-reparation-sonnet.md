# Banc d'agents web — 2026-10-08 — nom-limite-reparation-sonnet

Échantillon : **1 cas × k = 3 essais** → 3/3 essais lancés, 6 jeux (couples cas/variante). Commit `1dfe199` · modèle de génération `claude-sonnet-4-6` · testpilot `0.1.0` · behave `1.3.3` · playwright `1.62.0`.

## ⚠️ Sous-ensemble de cas (mise au point)

Ce rapport ne porte PAS sur le corpus entier : ne jamais le publier comme mesure du banc.

## Indicateurs

| Indicateur | Valeur |
|---|---|
| **Faux verts** (défaut injecté, attendu non_conforme, obtenu conforme) | 0/3 (0,0 %, IC95 % 0,0–56,2 %) |
| Faux rouges (saine, attendu conforme, obtenu non_conforme) | 0/2 (0,0 %, IC95 % 0,0–65,8 %) ; 1 non concluant |
| pass@1 — le test généré s'exécute sans erreur technique | 1/1 (100,0 %, IC95 % 20,7–100,0 %) |
| pass@3 — au moins un essai sur 3 | 1/1 (100,0 %, IC95 % 20,7–100,0 %) |
| pass^3 — tous les essais | 0/1 (0,0 %, IC95 % 0,0–79,3 %) |
| pass@1 — résultat juste partout (saine ET défauts) | 1/1 (100,0 %, IC95 % 20,7–100,0 %) |
| pass@3 — résultat juste partout | 1/1 (100,0 %, IC95 % 20,7–100,0 %) |
| pass^3 — résultat juste partout, à chaque essai | 0/1 (0,0 %, IC95 % 0,0–79,3 %) |

« non mesuré » signifie qu'aucun jeu concluant n'existe pour cet indicateur : ce n'est PAS 0 %. Un taux de faux verts faible obtenu avec beaucoup de non concluants ne prouve rien : lire la ligne suivante et les intervalles (Wilson 95 %).

## Résultats non concluants (comptés, jamais retirés)

| Verdict | Jeux |
|---|---|
| technical_error | 1 |

## Détection par défaut

| Défaut | Jeux | Concluants | Détectés (non_conforme) | dont fiables (saine du même essai conforme) | Faux verts | Non concluants |
|---|---|---|---|---|---|---|
| `message_erreur_absent` | 3 | 3 | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 2/3 (66,7 %, IC95 % 20,8–93,9 %) | 0 | 0 |

## Après UNE réparation (D23)

Pour chaque essai dont le jeu sur l'application saine sort en `technical_error`, l'agent de réparation reçoit l'échec observé (jamais un diagnostic) et propose UNE correction ; la version réparée est rejouée sur toutes les variantes. Les autres essais restent tels quels. Le nombre de tentatives par essai est celui du budget de réparation du produit (`--tentatives-reparation`) ; le circuit complet (arrêt sur régression, couverture perdue) n'est pas rejoué ici.

| Indicateur | Avant réparation | Après une réparation |
|---|---|---|
| Faux verts | 0/3 (0,0 %, IC95 % 0,0–56,2 %) | 0/3 (0,0 %, IC95 % 0,0–56,2 %) |
| Faux rouges | 0/2 (0,0 %, IC95 % 0,0–65,8 %) ; 1 non concluant | 0/3 (0,0 %, IC95 % 0,0–56,2 %) |
| pass@1 — s'exécute sans erreur technique | 1/1 (100,0 %, IC95 % 20,7–100,0 %) | 1/1 (100,0 %, IC95 % 20,7–100,0 %) |
| pass@1 — résultat juste partout | 1/1 (100,0 %, IC95 % 20,7–100,0 %) | 1/1 (100,0 %, IC95 % 20,7–100,0 %) |
| pass^k — résultat juste partout, à chaque essai | 0/1 (0,0 %, IC95 % 0,0–79,3 %) | 1/1 (100,0 %, IC95 % 20,7–100,0 %) |

Réparations : 1 essai(s) à réparer, 1 tenté(s) en 1 tentative(s), 1 avec une correction rejouable ; saine exécutable après : 1, conforme après : 1 ; coût des réparations : **0.034 $**.

## Coût

Total : **0.000 $** = 0.000 € (1 € = 1.08 $) pour 3 génération(s) ; par génération : 0.000 $ / 0.000 €.
Les jeux sur les variantes ne coûtent rien (aucun appel LLM) : tout le coût est celui des générations.

| Cas | Coût moyen par génération ($) |
|---|---|
| client_creation_nom_limite | 0.000 |

## Intégrité : le MÊME test est joué partout

Jeux dont les empreintes sha256 des fichiers joués égalent celles de la génération : **6** ; divergentes : **0** ; non rapportées : 0.

## Écarts aux attendus (à instruire : le test généré, le défaut ou le verdict — jamais l'attendu)

| Cas | Variante | Essai | Attendu | Obtenu | Cause |
|---|---|---|---|---|---|
| client_creation_nom_limite | saine | 3 | conforme | technical_error | wrong_field_name |

## Génération par essai

| Cas | Essai | Généré | Coût ($) | Empreinte du test (sha256) |
|---|---|---|---|---|
| client_creation_nom_limite | 1 | oui | 0.000 | `e845982ffac2cccf` |
| client_creation_nom_limite | 2 | oui | 0.000 | `419c5cb4e74ca555` |
| client_creation_nom_limite | 3 | oui | 0.000 | `6622821a2ade28cc` |
