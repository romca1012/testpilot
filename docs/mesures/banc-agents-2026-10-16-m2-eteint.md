# Banc d'agents web — 2026-10-16 — m2-eteint

Échantillon : **10 cas × k = 2 essais** → 18/20 essais lancés, 34 jeux (couples cas/variante). Commit `178054f` · modèle de génération `claude-sonnet-4-6` · testpilot `0.1.0` · behave `1.3.3` · playwright `1.62.0`.

## ⚠️ Campagne INCOMPLÈTE : plafond de coût : cumul 3.049 $ + essai le plus cher attendu 0.515 $ > plafond 3.500 $ (avant panier_total_tva, essai 2)

Les indicateurs portent sur les essais lancés seulement, jamais sur le corpus entier.

## Indicateurs

| Indicateur | Valeur |
|---|---|
| **Faux verts** (défaut injecté, attendu non_conforme, obtenu conforme) | 0/12 (0,0 %, IC95 % 0,0–24,3 %) ; 4 non concluants |
| Faux rouges (saine, attendu conforme, obtenu non_conforme) | 0/14 (0,0 %, IC95 % 0,0–21,5 %) ; 4 non concluants |
| pass@1 — le test généré s'exécute sans erreur technique | 8/10 (80,0 %, IC95 % 49,0–94,3 %) |
| pass@2 — au moins un essai sur 2 | 7/8 (87,5 %, IC95 % 52,9–97,8 %) ; 2 cas sans assez d'essais |
| pass^2 — tous les essais | 5/8 (62,5 %, IC95 % 30,6–86,3 %) ; 2 cas sans assez d'essais |
| pass@1 — résultat juste partout (saine ET défauts) | 8/10 (80,0 %, IC95 % 49,0–94,3 %) |
| pass@2 — résultat juste partout | 7/8 (87,5 %, IC95 % 52,9–97,8 %) ; 2 cas sans assez d'essais |
| pass^2 — résultat juste partout, à chaque essai | 4/8 (50,0 %, IC95 % 21,5–78,5 %) ; 2 cas sans assez d'essais |

« non mesuré » signifie qu'aucun jeu concluant n'existe pour cet indicateur : ce n'est PAS 0 %. Un taux de faux verts faible obtenu avec beaucoup de non concluants ne prouve rien : lire la ligne suivante et les intervalles (Wilson 95 %).

## Résultats non concluants (comptés, jamais retirés)

| Verdict | Jeux |
|---|---|
| technical_error | 8 |

## Détection par défaut

| Défaut | Jeux | Concluants | Détectés (non_conforme) | dont fiables (saine du même essai conforme) | Faux verts | Non concluants |
|---|---|---|---|---|---|---|
| `etat_non_enregistre` | 4 | 1 | 1/1 (100,0 %, IC95 % 20,7–100,0 %) | 1/1 (100,0 %, IC95 % 20,7–100,0 %) | 0 | 3 |
| `filtre_ignore` | 1 | 1 | 1/1 (100,0 %, IC95 % 20,7–100,0 %) | 1/1 (100,0 %, IC95 % 20,7–100,0 %) | 0 | 0 |
| `login_accepte_tout` | 2 | 2 | 2/2 (100,0 %, IC95 % 34,2–100,0 %) | 2/2 (100,0 %, IC95 % 34,2–100,0 %) | 0 | 0 |
| `message_erreur_absent` | 4 | 4 | 4/4 (100,0 %, IC95 % 51,0–100,0 %) | 4/4 (100,0 %, IC95 % 51,0–100,0 %) | 0 | 0 |
| `total_faux` | 3 | 2 | 2/2 (100,0 %, IC95 % 34,2–100,0 %) | 2/2 (100,0 %, IC95 % 34,2–100,0 %) | 0 | 1 |
| `validation_absente` | 2 | 2 | 2/2 (100,0 %, IC95 % 34,2–100,0 %) | 2/2 (100,0 %, IC95 % 34,2–100,0 %) | 0 | 0 |

## Coût

Total : **3.049 $** = 2.824 € (1 € = 1.08 $) pour 18 génération(s) ; par génération : 0.169 $ / 0.157 €.
Les jeux sur les variantes ne coûtent rien (aucun appel LLM) : tout le coût est celui des générations.

| Cas | Coût moyen par génération ($) |
|---|---|
| client_creation_nom_limite | 0.136 |
| client_creation_nom_requis | 0.115 |
| client_creation_valide | 0.110 |
| commande_confirmation | 0.146 |
| commande_persistance_serveur | 0.511 |
| connexion_refusee | 0.118 |
| connexion_valide | 0.127 |
| panier_remise_arrondi | 0.138 |
| panier_total_tva | 0.162 |
| produits_recherche | 0.086 |

## Intégrité : le MÊME test est joué partout

Jeux dont les empreintes sha256 des fichiers joués égalent celles de la génération : **28** ; divergentes : **0** ; non rapportées : 0.

## Écarts aux attendus (à instruire : le test généré, le défaut ou le verdict — jamais l'attendu)

| Cas | Variante | Essai | Attendu | Obtenu | Cause |
|---|---|---|---|---|---|
| commande_persistance_serveur | saine | 1 | conforme | technical_error | generation_echouee |
| commande_persistance_serveur | etat_non_enregistre | 1 | non_conforme | technical_error | generation_echouee |
| panier_remise_arrondi | saine | 1 | conforme | technical_error | generation_echouee |
| panier_remise_arrondi | total_faux | 1 | non_conforme | technical_error | generation_echouee |
| client_creation_valide | etat_non_enregistre | 2 | non_conforme | technical_error | wrong_field_name |
| commande_confirmation | saine | 2 | conforme | technical_error | broken_test_code |
| commande_persistance_serveur | saine | 2 | conforme | technical_error | generation_echouee |
| commande_persistance_serveur | etat_non_enregistre | 2 | non_conforme | technical_error | generation_echouee |

## Refus des gardes d'écriture pendant la génération (lot VH-04)

Chaque refus renvoie l'agent corriger dans la même génération : il coûte des tours, il ne casse rien.

| Code du refus | Nombre |
|---|---|
| `LITTERAL_NON_OBSERVE` | 3 |
| `ASSERTION_MAL_PLACEE` | 2 |
| `TRANSPORT_INTERDIT` | 1 |
| `ECHAPPEMENT_LITTERAL` | 1 |

## Code libre (lot VH-06)

Tests générés sans AUCUN step écrit à la main : **14/15** ; steps définis par les tests : 2 au total (maximum 2 dans un test). Un step écrit à la main n'a ni test de falsifiabilité ni résolution éprouvée : la cible est zéro.

## Données de test (lot PT-02d)

Tests générés qui écrivent au moins une variable : **4/15** ; variables écrites : `ville_client` ×4, `nom_client` ×2.

## Second jeu de données

Chaque test qui écrit une variable, et dont le jeu sur l'application SAINE est conforme à l'attendu, est rejoué sur la saine avec un second jeu (`nom_client` = « Martin Lefèvre SA », `ville_client` = « Paris »). Un test est compté PROUVÉ seulement si le jeu est conforme ET si l'état du serveur montre la valeur du second jeu de CHAQUE variable qu'il écrit, sans aucune valeur du premier ; un verdict conforme seul dit seulement que le test ne casse pas. « Prouvé » dit que les valeurs ont atteint le serveur, pas qu'un « Alors » les vérifie. Un cas qui ne crée rien (« aucune trace au serveur ») ne peut pas être prouvé ainsi. Compté à part : jamais dans pass@k ni dans les faux verts. Les versions réparées ne sont pas rejouées au second jeu.

Rejoués : **4** ; conformes à l'attendu : **4/4** ; variable prouvée par l'état du serveur : **2/4** ; valeur du premier jeu restée en dur : **0** ; preuve partielle : **0** ; aucune trace au serveur : 2. Intégrité : 4 vérifiées, 0 divergentes, 0 non rapportées.

| Cas | Essai | Attendu | Obtenu | État du serveur | Cause | Détail |
|---|---|---|---|---|---|---|
| client_creation_nom_requis | 1 | conforme | conforme | aucune des valeurs | — | — |
| client_creation_valide | 1 | conforme | conforme | valeurs du second jeu | — | — |
| client_creation_nom_requis | 2 | conforme | conforme | aucune des valeurs | — | — |
| client_creation_valide | 2 | conforme | conforme | valeurs du second jeu | — | — |

## Génération par essai

| Cas | Essai | Généré | Coût ($) | Refus à l'écriture | Steps écrits à la main | Empreinte du test (sha256) |
|---|---|---|---|---|---|---|
| client_creation_nom_limite | 1 | oui | 0.136 | — | 0 | `c577985a1b870a13` |
| client_creation_nom_requis | 1 | oui | 0.125 | — | 0 | `d23c21c7b1e8b29b` |
| client_creation_valide | 1 | oui | 0.115 | — | 0 | `2ebb5c5bc8abe035` |
| commande_confirmation | 1 | oui | 0.136 | — | 0 | `37b4bf9097eab984` |
| commande_persistance_serveur | 1 | NON : génération sans essai à blanc passé | 0.506 | ASSERTION_MAL_PLACEE ×2, LITTERAL_NON_OBSERVE ×2, TRANSPORT_INTERDIT ×1 | — | `—` |
| connexion_refusee | 1 | oui | 0.122 | LITTERAL_NON_OBSERVE ×1 | 0 | `fc866a7d9845d0d2` |
| connexion_valide | 1 | oui | 0.133 | — | 0 | `6d02bce27ea5d971` |
| panier_remise_arrondi | 1 | NON : génération sans essai à blanc passé | 0.135 | — | — | `—` |
| panier_total_tva | 1 | oui | 0.162 | — | 0 | `9e8f84aec24219a0` |
| produits_recherche | 1 | oui | 0.086 | — | 0 | `7a2a77df53fe2567` |
| client_creation_nom_limite | 2 | oui | 0.136 | — | 0 | `63af2e2a4e3baf3e` |
| client_creation_nom_requis | 2 | oui | 0.106 | — | 0 | `5d8c9fced197fbf0` |
| client_creation_valide | 2 | oui | 0.105 | — | 2 | `a8a1b9579ac2b7bf` |
| commande_confirmation | 2 | oui | 0.157 | — | 0 | `e58a6b131cb45265` |
| commande_persistance_serveur | 2 | NON : génération sans essai à blanc passé | 0.515 | ECHAPPEMENT_LITTERAL ×1 | — | `—` |
| connexion_refusee | 2 | oui | 0.114 | — | 0 | `3b14a98e09414a35` |
| connexion_valide | 2 | oui | 0.121 | — | 0 | `b95ce9d73a1b0ade` |
| panier_remise_arrondi | 2 | oui | 0.140 | — | 0 | `53db4c1b2a6d4052` |
