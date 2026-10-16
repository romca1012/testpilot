# Banc d'agents web — 2026-10-16 — m1-allume

Échantillon : **10 cas × k = 2 essais** → 20/20 essais lancés, 38 jeux (couples cas/variante). Commit `9fa0ef6` · modèle de génération `claude-sonnet-4-6` · testpilot `0.1.0` · behave `1.3.3` · playwright `1.62.0`.

## Indicateurs

| Indicateur | Valeur |
|---|---|
| **Faux verts** (défaut injecté, attendu non_conforme, obtenu conforme) | 0/13 (0,0 %, IC95 % 0,0–22,8 %) ; 5 non concluants |
| Faux rouges (saine, attendu conforme, obtenu non_conforme) | 1/13 (7,7 %, IC95 % 1,4–33,3 %) ; 7 non concluants |
| pass@1 — le test généré s'exécute sans erreur technique | 5/10 (50,0 %, IC95 % 23,7–76,3 %) |
| pass@2 — au moins un essai sur 2 | 8/10 (80,0 %, IC95 % 49,0–94,3 %) |
| pass^2 — tous les essais | 5/10 (50,0 %, IC95 % 23,7–76,3 %) |
| pass@1 — résultat juste partout (saine ET défauts) | 4/10 (40,0 %, IC95 % 16,8–68,7 %) |
| pass@2 — résultat juste partout | 8/10 (80,0 %, IC95 % 49,0–94,3 %) |
| pass^2 — résultat juste partout, à chaque essai | 4/10 (40,0 %, IC95 % 16,8–68,7 %) |

« non mesuré » signifie qu'aucun jeu concluant n'existe pour cet indicateur : ce n'est PAS 0 %. Un taux de faux verts faible obtenu avec beaucoup de non concluants ne prouve rien : lire la ligne suivante et les intervalles (Wilson 95 %).

## Résultats non concluants (comptés, jamais retirés)

| Verdict | Jeux |
|---|---|
| technical_error | 12 |

## Détection par défaut

| Défaut | Jeux | Concluants | Détectés (non_conforme) | dont fiables (saine du même essai conforme) | Faux verts | Non concluants |
|---|---|---|---|---|---|---|
| `etat_non_enregistre` | 4 | 4 | 4/4 (100,0 %, IC95 % 51,0–100,0 %) | 2/4 (50,0 %, IC95 % 15,0–85,0 %) | 0 | 0 |
| `filtre_ignore` | 2 | 2 | 2/2 (100,0 %, IC95 % 34,2–100,0 %) | 1/2 (50,0 %, IC95 % 9,5–90,5 %) | 0 | 0 |
| `login_accepte_tout` | 2 | 2 | 2/2 (100,0 %, IC95 % 34,2–100,0 %) | 2/2 (100,0 %, IC95 % 34,2–100,0 %) | 0 | 0 |
| `message_erreur_absent` | 4 | 3 | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 0 | 1 |
| `total_faux` | 4 | 1 | 1/1 (100,0 %, IC95 % 20,7–100,0 %) | 1/1 (100,0 %, IC95 % 20,7–100,0 %) | 0 | 3 |
| `validation_absente` | 2 | 1 | 1/1 (100,0 %, IC95 % 20,7–100,0 %) | 1/1 (100,0 %, IC95 % 20,7–100,0 %) | 0 | 1 |

## Coût

Total : **2.571 $** = 2.381 € (1 € = 1.08 $) pour 20 génération(s) ; par génération : 0.129 $ / 0.119 €.
Les jeux sur les variantes ne coûtent rien (aucun appel LLM) : tout le coût est celui des générations.

| Cas | Coût moyen par génération ($) |
|---|---|
| client_creation_nom_limite | 0.137 |
| client_creation_nom_requis | 0.080 |
| client_creation_valide | 0.083 |
| commande_confirmation | 0.090 |
| commande_persistance_serveur | 0.333 |
| connexion_refusee | 0.165 |
| connexion_valide | 0.115 |
| panier_remise_arrondi | 0.120 |
| panier_total_tva | 0.105 |
| produits_recherche | 0.058 |

## Intégrité : le MÊME test est joué partout

Jeux dont les empreintes sha256 des fichiers joués égalent celles de la génération : **36** ; divergentes : **0** ; non rapportées : 0.

## Écarts aux attendus (à instruire : le test généré, le défaut ou le verdict — jamais l'attendu)

| Cas | Variante | Essai | Attendu | Obtenu | Cause |
|---|---|---|---|---|---|
| client_creation_nom_requis | saine | 1 | conforme | technical_error | wrong_field_name |
| client_creation_nom_requis | validation_absente | 1 | non_conforme | technical_error | wrong_field_name |
| client_creation_nom_requis | message_erreur_absent | 1 | non_conforme | technical_error | wrong_field_name |
| commande_confirmation | saine | 1 | conforme | technical_error | wrong_field_name |
| commande_persistance_serveur | saine | 1 | conforme | technical_error | wrong_field_name |
| panier_remise_arrondi | saine | 1 | conforme | technical_error | wrong_field_name |
| panier_remise_arrondi | total_faux | 1 | non_conforme | technical_error | wrong_field_name |
| panier_total_tva | saine | 1 | conforme | technical_error | generation_echouee |
| panier_total_tva | total_faux | 1 | non_conforme | technical_error | generation_echouee |
| produits_recherche | saine | 1 | conforme | non_conforme | assertion_mismatch |
| commande_persistance_serveur | saine | 2 | conforme | technical_error | broken_test_code |
| panier_total_tva | saine | 2 | conforme | technical_error | wrong_field_name |
| panier_total_tva | total_faux | 2 | non_conforme | technical_error | wrong_field_name |

## Refus des gardes d'écriture pendant la génération (lot VH-04)

Chaque refus renvoie l'agent corriger dans la même génération : il coûte des tours, il ne casse rien.

| Code du refus | Nombre |
|---|---|
| `LITTERAL_NON_OBSERVE` | 4 |
| `ECHAPPEMENT_LITTERAL` | 1 |

## Code libre (lot VH-06)

Tests générés sans AUCUN step écrit à la main : **17/19** ; steps définis par les tests : 2 au total (maximum 1 dans un test). Un step écrit à la main n'a ni test de falsifiabilité ni résolution éprouvée : la cible est zéro.

## Données de test (lot PT-02d)

Tests générés qui écrivent au moins une variable : **4/19** ; variables écrites : `ville_client` ×4, `nom_client` ×2.

## Second jeu de données

Chaque test qui écrit une variable, et dont le jeu sur l'application SAINE est conforme à l'attendu, est rejoué sur la saine avec un second jeu (`nom_client` = « Martin Lefèvre SA », `ville_client` = « Paris »). Un test est compté PROUVÉ seulement si le jeu est conforme ET si l'état du serveur montre la valeur du second jeu de CHAQUE variable qu'il écrit, sans aucune valeur du premier ; un verdict conforme seul dit seulement que le test ne casse pas. « Prouvé » dit que les valeurs ont atteint le serveur, pas qu'un « Alors » les vérifie. Un cas qui ne crée rien (« aucune trace au serveur ») ne peut pas être prouvé ainsi. Compté à part : jamais dans pass@k ni dans les faux verts. Les versions réparées ne sont pas rejouées au second jeu.

Rejoués : **3** ; conformes à l'attendu : **3/3** ; variable prouvée par l'état du serveur : **2/3** ; valeur du premier jeu restée en dur : **0** ; preuve partielle : **0** ; aucune trace au serveur : 1. Intégrité : 3 vérifiées, 0 divergentes, 0 non rapportées.

| Cas | Essai | Attendu | Obtenu | État du serveur | Cause | Détail |
|---|---|---|---|---|---|---|
| client_creation_valide | 1 | conforme | conforme | valeurs du second jeu | — | — |
| client_creation_nom_requis | 2 | conforme | conforme | aucune des valeurs | — | — |
| client_creation_valide | 2 | conforme | conforme | valeurs du second jeu | — | — |

Non rejoués, leur saine étant déjà en écart : client_creation_nom_requis essai 1 (saine : technical_error).

## Génération par essai

| Cas | Essai | Généré | Coût ($) | Refus à l'écriture | Steps écrits à la main | Empreinte du test (sha256) |
|---|---|---|---|---|---|---|
| client_creation_nom_limite | 1 | oui | 0.149 | — | 0 | `fa0e36b50816878e` |
| client_creation_nom_requis | 1 | oui | 0.059 | — | 0 | `e98941719c78d5ed` |
| client_creation_valide | 1 | oui | 0.085 | ECHAPPEMENT_LITTERAL ×1 | 0 | `d51b4fc85de8f2b6` |
| commande_confirmation | 1 | oui | 0.096 | — | 0 | `e96780f989603765` |
| commande_persistance_serveur | 1 | oui | 0.359 | LITTERAL_NON_OBSERVE ×1 | 0 | `74e698294a24742c` |
| connexion_refusee | 1 | oui | 0.179 | LITTERAL_NON_OBSERVE ×1 | 1 | `ead37dbcbb1602ae` |
| connexion_valide | 1 | oui | 0.105 | — | 0 | `9d11018b7d32e4f7` |
| panier_remise_arrondi | 1 | oui | 0.077 | — | 0 | `1d79c94f5c096dad` |
| panier_total_tva | 1 | NON : génération sans essai à blanc passé | 0.105 | — | — | `—` |
| produits_recherche | 1 | oui | 0.059 | — | 0 | `1252c6167578aeaa` |
| client_creation_nom_limite | 2 | oui | 0.125 | — | 0 | `403151f807723d02` |
| client_creation_nom_requis | 2 | oui | 0.101 | — | 0 | `3306be72ce866f4a` |
| client_creation_valide | 2 | oui | 0.080 | — | 0 | `191ccc2bd4ef0e16` |
| commande_confirmation | 2 | oui | 0.084 | — | 0 | `14d1beaaf70e72e1` |
| commande_persistance_serveur | 2 | oui | 0.307 | LITTERAL_NON_OBSERVE ×1 | 0 | `69afd473c7606c32` |
| connexion_refusee | 2 | oui | 0.150 | LITTERAL_NON_OBSERVE ×1 | 1 | `43b600ac24411831` |
| connexion_valide | 2 | oui | 0.125 | — | 0 | `a4825d67f6354413` |
| panier_remise_arrondi | 2 | oui | 0.163 | — | 0 | `3990da18f08dcf63` |
| panier_total_tva | 2 | oui | 0.105 | — | 0 | `5422986fa0a9ffd3` |
| produits_recherche | 2 | oui | 0.056 | — | 0 | `4832a91a942e9f08` |
