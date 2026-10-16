# Banc d'agents web — 2026-10-16 — m1c-donnees

Échantillon : **2 cas × k = 3 essais** → 6/6 essais lancés, 15 jeux (couples cas/variante). Commit `9fa0ef6` · modèle de génération `claude-sonnet-4-6` · testpilot `0.1.0` · behave `1.3.3` · playwright `1.62.0`.

## ⚠️ Sous-ensemble de cas (mise au point)

Ce rapport ne porte PAS sur le corpus entier : ne jamais le publier comme mesure du banc.

## Indicateurs

| Indicateur | Valeur |
|---|---|
| **Faux verts** (défaut injecté, attendu non_conforme, obtenu conforme) | 0/9 (0,0 %, IC95 % 0,0–29,9 %) |
| Faux rouges (saine, attendu conforme, obtenu non_conforme) | 0/6 (0,0 %, IC95 % 0,0–39,0 %) |
| pass@1 — le test généré s'exécute sans erreur technique | 2/2 (100,0 %, IC95 % 34,2–100,0 %) |
| pass@3 — au moins un essai sur 3 | 2/2 (100,0 %, IC95 % 34,2–100,0 %) |
| pass^3 — tous les essais | 2/2 (100,0 %, IC95 % 34,2–100,0 %) |
| pass@1 — résultat juste partout (saine ET défauts) | 2/2 (100,0 %, IC95 % 34,2–100,0 %) |
| pass@3 — résultat juste partout | 2/2 (100,0 %, IC95 % 34,2–100,0 %) |
| pass^3 — résultat juste partout, à chaque essai | 2/2 (100,0 %, IC95 % 34,2–100,0 %) |

« non mesuré » signifie qu'aucun jeu concluant n'existe pour cet indicateur : ce n'est PAS 0 %. Un taux de faux verts faible obtenu avec beaucoup de non concluants ne prouve rien : lire la ligne suivante et les intervalles (Wilson 95 %).

## Résultats non concluants (comptés, jamais retirés)

Aucun jeu non concluant.

## Détection par défaut

| Défaut | Jeux | Concluants | Détectés (non_conforme) | dont fiables (saine du même essai conforme) | Faux verts | Non concluants |
|---|---|---|---|---|---|---|
| `etat_non_enregistre` | 3 | 3 | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 0 | 0 |
| `message_erreur_absent` | 3 | 3 | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 0 | 0 |
| `validation_absente` | 3 | 3 | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 0 | 0 |

## Coût

Total : **0.468 $** = 0.433 € (1 € = 1.08 $) pour 6 génération(s) ; par génération : 0.078 $ / 0.072 €.
Les jeux sur les variantes ne coûtent rien (aucun appel LLM) : tout le coût est celui des générations.

| Cas | Coût moyen par génération ($) |
|---|---|
| client_creation_valide | 0.074 |
| client_creation_nom_requis | 0.082 |

## Intégrité : le MÊME test est joué partout

Jeux dont les empreintes sha256 des fichiers joués égalent celles de la génération : **15** ; divergentes : **0** ; non rapportées : 0.

## Refus des gardes d'écriture pendant la génération (lot VH-04)

Chaque refus renvoie l'agent corriger dans la même génération : il coûte des tours, il ne casse rien.

| Code du refus | Nombre |
|---|---|
| `ECHAPPEMENT_LITTERAL` | 1 |

## Code libre (lot VH-06)

Tests générés sans AUCUN step écrit à la main : **6/6** ; steps définis par les tests : 0 au total (maximum 0 dans un test). Un step écrit à la main n'a ni test de falsifiabilité ni résolution éprouvée : la cible est zéro.

## Données de test (lot PT-02d)

Tests générés qui écrivent au moins une variable : **6/6** ; variables écrites : `ville_client` ×6, `nom_client` ×3.

## Second jeu de données

Chaque test qui écrit une variable, et dont le jeu sur l'application SAINE est conforme à l'attendu, est rejoué sur la saine avec un second jeu (`nom_client` = « Martin Lefèvre SA », `ville_client` = « Paris »). Un test est compté PROUVÉ seulement si le jeu est conforme ET si l'état du serveur montre la valeur du second jeu de CHAQUE variable qu'il écrit, sans aucune valeur du premier ; un verdict conforme seul dit seulement que le test ne casse pas. « Prouvé » dit que les valeurs ont atteint le serveur, pas qu'un « Alors » les vérifie. Un cas qui ne crée rien (« aucune trace au serveur ») ne peut pas être prouvé ainsi. Compté à part : jamais dans pass@k ni dans les faux verts. Les versions réparées ne sont pas rejouées au second jeu.

Rejoués : **6** ; conformes à l'attendu : **6/6** ; variable prouvée par l'état du serveur : **3/6** ; valeur du premier jeu restée en dur : **0** ; preuve partielle : **0** ; aucune trace au serveur : 3. Intégrité : 6 vérifiées, 0 divergentes, 0 non rapportées.

| Cas | Essai | Attendu | Obtenu | État du serveur | Cause | Détail |
|---|---|---|---|---|---|---|
| client_creation_valide | 1 | conforme | conforme | valeurs du second jeu | — | — |
| client_creation_nom_requis | 1 | conforme | conforme | aucune des valeurs | — | — |
| client_creation_valide | 2 | conforme | conforme | valeurs du second jeu | — | — |
| client_creation_nom_requis | 2 | conforme | conforme | aucune des valeurs | — | — |
| client_creation_valide | 3 | conforme | conforme | valeurs du second jeu | — | — |
| client_creation_nom_requis | 3 | conforme | conforme | aucune des valeurs | — | — |

## Génération par essai

| Cas | Essai | Généré | Coût ($) | Refus à l'écriture | Steps écrits à la main | Empreinte du test (sha256) |
|---|---|---|---|---|---|---|
| client_creation_valide | 1 | oui | 0.080 | — | 0 | `8fd69941bd6e8ce7` |
| client_creation_nom_requis | 1 | oui | 0.084 | — | 0 | `3e16c7e87ee1ed5d` |
| client_creation_valide | 2 | oui | 0.073 | ECHAPPEMENT_LITTERAL ×1 | 0 | `310ade338861ef16` |
| client_creation_nom_requis | 2 | oui | 0.091 | — | 0 | `94c5d894b9da57df` |
| client_creation_valide | 3 | oui | 0.068 | — | 0 | `bd6b71f91aa7ebb9` |
| client_creation_nom_requis | 3 | oui | 0.072 | — | 0 | `e92a89ebed6e1e06` |
