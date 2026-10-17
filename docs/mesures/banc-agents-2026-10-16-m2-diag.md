# Banc d'agents web — 2026-10-16 — m2-diag

Échantillon : **2 cas × k = 1 essais** → 2/2 essais lancés, 4 jeux (couples cas/variante). Commit `6f8e34b` · modèle de génération `claude-sonnet-4-6` · testpilot `0.1.0` · behave `1.3.3` · playwright `1.62.0`.

## ⚠️ Sous-ensemble de cas (mise au point)

Ce rapport ne porte PAS sur le corpus entier : ne jamais le publier comme mesure du banc.

## Indicateurs

| Indicateur | Valeur |
|---|---|
| **Faux verts** (défaut injecté, attendu non_conforme, obtenu conforme) | 0/2 (0,0 %, IC95 % 0,0–65,8 %) |
| Faux rouges (saine, attendu conforme, obtenu non_conforme) | 0/2 (0,0 %, IC95 % 0,0–65,8 %) |
| pass@1 — le test généré s'exécute sans erreur technique | 2/2 (100,0 %, IC95 % 34,2–100,0 %) |
| pass@1 — au moins un essai sur 1 | 2/2 (100,0 %, IC95 % 34,2–100,0 %) |
| pass^1 — tous les essais | 2/2 (100,0 %, IC95 % 34,2–100,0 %) |
| pass@1 — résultat juste partout (saine ET défauts) | 2/2 (100,0 %, IC95 % 34,2–100,0 %) |
| pass@1 — résultat juste partout | 2/2 (100,0 %, IC95 % 34,2–100,0 %) |
| pass^1 — résultat juste partout, à chaque essai | 2/2 (100,0 %, IC95 % 34,2–100,0 %) |

« non mesuré » signifie qu'aucun jeu concluant n'existe pour cet indicateur : ce n'est PAS 0 %. Un taux de faux verts faible obtenu avec beaucoup de non concluants ne prouve rien : lire la ligne suivante et les intervalles (Wilson 95 %).

## Résultats non concluants (comptés, jamais retirés)

Aucun jeu non concluant.

## Détection par défaut

| Défaut | Jeux | Concluants | Détectés (non_conforme) | dont fiables (saine du même essai conforme) | Faux verts | Non concluants |
|---|---|---|---|---|---|---|
| `login_accepte_tout` | 1 | 1 | 1/1 (100,0 %, IC95 % 20,7–100,0 %) | 1/1 (100,0 %, IC95 % 20,7–100,0 %) | 0 | 0 |
| `total_faux` | 1 | 1 | 1/1 (100,0 %, IC95 % 20,7–100,0 %) | 1/1 (100,0 %, IC95 % 20,7–100,0 %) | 0 | 0 |

## Coût

Total : **0.371 $** = 0.344 € (1 € = 1.08 $) pour 2 génération(s) ; par génération : 0.186 $ / 0.172 €.
Les jeux sur les variantes ne coûtent rien (aucun appel LLM) : tout le coût est celui des générations.

| Cas | Coût moyen par génération ($) |
|---|---|
| connexion_refusee | 0.156 |
| panier_total_tva | 0.215 |

## Intégrité : le MÊME test est joué partout

Jeux dont les empreintes sha256 des fichiers joués égalent celles de la génération : **4** ; divergentes : **0** ; non rapportées : 0.

## Code libre (lot VH-06)

Tests générés sans AUCUN step écrit à la main : **1/2** ; steps définis par les tests : 4 au total (maximum 4 dans un test). Un step écrit à la main n'a ni test de falsifiabilité ni résolution éprouvée : la cible est zéro.

## Second jeu de données

Chaque test qui écrit une variable, et dont le jeu sur l'application SAINE est conforme à l'attendu, est rejoué sur la saine avec un second jeu (`nom_client` = « Martin Lefèvre SA », `ville_client` = « Paris »). Un test est compté PROUVÉ seulement si le jeu est conforme ET si l'état du serveur montre la valeur du second jeu de CHAQUE variable qu'il écrit, sans aucune valeur du premier ; un verdict conforme seul dit seulement que le test ne casse pas. « Prouvé » dit que les valeurs ont atteint le serveur, pas qu'un « Alors » les vérifie. Un cas qui ne crée rien (« aucune trace au serveur ») ne peut pas être prouvé ainsi. Compté à part : jamais dans pass@k ni dans les faux verts. Les versions réparées ne sont pas rejouées au second jeu.

Aucun test rejouable (aucun test n'écrit de variable, ou leur saine est déjà en écart) : non mesuré.

## Génération par essai

| Cas | Essai | Généré | Coût ($) | Refus à l'écriture | Steps écrits à la main | Empreinte du test (sha256) |
|---|---|---|---|---|---|---|
| connexion_refusee | 1 | oui | 0.156 | — | 0 | `430837f35b3141fc` |
| panier_total_tva | 1 | oui | 0.215 | — | 4 | `c3a34f72e942bb7b` |
