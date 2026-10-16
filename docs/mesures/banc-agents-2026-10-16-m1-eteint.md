# Banc d'agents web — 2026-10-16 — m1-eteint

Échantillon : **10 cas × k = 2 essais** → 20/20 essais lancés, 38 jeux (couples cas/variante). Commit `b218dd4` · modèle de génération `claude-sonnet-4-6` · testpilot `0.1.0` · behave `1.3.3` · playwright `1.62.0`.

## Indicateurs

| Indicateur | Valeur |
|---|---|
| **Faux verts** (défaut injecté, attendu non_conforme, obtenu conforme) | 0/14 (0,0 %, IC95 % 0,0–21,5 %) ; 4 non concluants |
| Faux rouges (saine, attendu conforme, obtenu non_conforme) | 0/14 (0,0 %, IC95 % 0,0–21,5 %) ; 6 non concluants |
| pass@1 — le test généré s'exécute sans erreur technique | 5/10 (50,0 %, IC95 % 23,7–76,3 %) |
| pass@2 — au moins un essai sur 2 | 9/10 (90,0 %, IC95 % 59,6–98,2 %) |
| pass^2 — tous les essais | 5/10 (50,0 %, IC95 % 23,7–76,3 %) |
| pass@1 — résultat juste partout (saine ET défauts) | 5/10 (50,0 %, IC95 % 23,7–76,3 %) |
| pass@2 — résultat juste partout | 9/10 (90,0 %, IC95 % 59,6–98,2 %) |
| pass^2 — résultat juste partout, à chaque essai | 5/10 (50,0 %, IC95 % 23,7–76,3 %) |

« non mesuré » signifie qu'aucun jeu concluant n'existe pour cet indicateur : ce n'est PAS 0 %. Un taux de faux verts faible obtenu avec beaucoup de non concluants ne prouve rien : lire la ligne suivante et les intervalles (Wilson 95 %).

## Résultats non concluants (comptés, jamais retirés)

| Verdict | Jeux |
|---|---|
| blocked | 2 |
| technical_error | 8 |

## Détection par défaut

| Défaut | Jeux | Concluants | Détectés (non_conforme) | dont fiables (saine du même essai conforme) | Faux verts | Non concluants |
|---|---|---|---|---|---|---|
| `etat_non_enregistre` | 4 | 3 | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 0 | 1 |
| `filtre_ignore` | 2 | 2 | 2/2 (100,0 %, IC95 % 34,2–100,0 %) | 2/2 (100,0 %, IC95 % 34,2–100,0 %) | 0 | 0 |
| `login_accepte_tout` | 2 | 2 | 2/2 (100,0 %, IC95 % 34,2–100,0 %) | 2/2 (100,0 %, IC95 % 34,2–100,0 %) | 0 | 0 |
| `message_erreur_absent` | 4 | 3 | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 2/3 (66,7 %, IC95 % 20,8–93,9 %) | 0 | 1 |
| `total_faux` | 4 | 2 | 2/2 (100,0 %, IC95 % 34,2–100,0 %) | 2/2 (100,0 %, IC95 % 34,2–100,0 %) | 0 | 2 |
| `validation_absente` | 2 | 2 | 2/2 (100,0 %, IC95 % 34,2–100,0 %) | 1/2 (50,0 %, IC95 % 9,5–90,5 %) | 0 | 0 |

## Coût

Total : **2.606 $** = 2.413 € (1 € = 1.08 $) pour 20 génération(s) ; par génération : 0.130 $ / 0.121 €.
Les jeux sur les variantes ne coûtent rien (aucun appel LLM) : tout le coût est celui des générations.

| Cas | Coût moyen par génération ($) |
|---|---|
| client_creation_nom_limite | 0.123 |
| client_creation_nom_requis | 0.094 |
| client_creation_valide | 0.098 |
| commande_confirmation | 0.113 |
| commande_persistance_serveur | 0.292 |
| connexion_refusee | 0.151 |
| connexion_valide | 0.126 |
| panier_remise_arrondi | 0.116 |
| panier_total_tva | 0.120 |
| produits_recherche | 0.070 |

## Intégrité : le MÊME test est joué partout

Jeux dont les empreintes sha256 des fichiers joués égalent celles de la génération : **38** ; divergentes : **0** ; non rapportées : 0.

## Écarts aux attendus (à instruire : le test généré, le défaut ou le verdict — jamais l'attendu)

| Cas | Variante | Essai | Attendu | Obtenu | Cause |
|---|---|---|---|---|---|
| client_creation_nom_limite | saine | 1 | conforme | blocked | precondition_non_remplie |
| client_creation_nom_limite | message_erreur_absent | 1 | non_conforme | blocked | precondition_non_remplie |
| client_creation_nom_requis | saine | 1 | conforme | technical_error | broken_test_code |
| commande_confirmation | saine | 1 | conforme | technical_error | wrong_field_name |
| commande_persistance_serveur | saine | 1 | conforme | technical_error | broken_test_code |
| commande_persistance_serveur | etat_non_enregistre | 1 | non_conforme | technical_error | broken_test_code |
| panier_total_tva | saine | 1 | conforme | technical_error | wrong_field_name |
| panier_total_tva | total_faux | 1 | non_conforme | technical_error | wrong_field_name |
| panier_total_tva | saine | 2 | conforme | technical_error | wrong_field_name |
| panier_total_tva | total_faux | 2 | non_conforme | technical_error | wrong_field_name |

## Refus des gardes d'écriture pendant la génération (lot VH-04)

Chaque refus renvoie l'agent corriger dans la même génération : il coûte des tours, il ne casse rien.

| Code du refus | Nombre |
|---|---|
| `LITTERAL_NON_OBSERVE` | 7 |
| `CONSTAT_SANS_LECTURE` | 4 |

## Code libre (lot VH-06)

Tests générés sans AUCUN step écrit à la main : **18/20** ; steps définis par les tests : 3 au total (maximum 2 dans un test). Un step écrit à la main n'a ni test de falsifiabilité ni résolution éprouvée : la cible est zéro.

## Second jeu de données

Chaque test qui écrit une variable, et dont le jeu sur l'application SAINE est conforme à l'attendu, est rejoué sur la saine avec un second jeu (`nom_client` = « Martin Lefèvre SA », `ville_client` = « Paris »). Un test est compté PROUVÉ seulement si le jeu est conforme ET si l'état du serveur montre la valeur du second jeu de CHAQUE variable qu'il écrit, sans aucune valeur du premier ; un verdict conforme seul dit seulement que le test ne casse pas. « Prouvé » dit que les valeurs ont atteint le serveur, pas qu'un « Alors » les vérifie. Un cas qui ne crée rien (« aucune trace au serveur ») ne peut pas être prouvé ainsi. Compté à part : jamais dans pass@k ni dans les faux verts. Les versions réparées ne sont pas rejouées au second jeu.

Aucun test rejouable (aucun test n'écrit de variable, ou leur saine est déjà en écart) : non mesuré.

## Génération par essai

| Cas | Essai | Généré | Coût ($) | Refus à l'écriture | Steps écrits à la main | Empreinte du test (sha256) |
|---|---|---|---|---|---|---|
| client_creation_nom_limite | 1 | oui | 0.136 | — | 0 | `8a2fa4d9f9d253dc` |
| client_creation_nom_requis | 1 | oui | 0.081 | — | 0 | `1ead488d4ae40480` |
| client_creation_valide | 1 | oui | 0.090 | — | 0 | `543379ff7823124d` |
| commande_confirmation | 1 | oui | 0.119 | — | 0 | `7a10f74fe9e3070d` |
| commande_persistance_serveur | 1 | oui | 0.350 | CONSTAT_SANS_LECTURE ×4, LITTERAL_NON_OBSERVE ×2 | 0 | `7bfe1ea8123e1851` |
| connexion_refusee | 1 | oui | 0.173 | LITTERAL_NON_OBSERVE ×1 | 1 | `aa45d69db29d6f63` |
| connexion_valide | 1 | oui | 0.134 | — | 0 | `2110bfa4a57d4434` |
| panier_remise_arrondi | 1 | oui | 0.143 | — | 0 | `03c38f6e2d38afe3` |
| panier_total_tva | 1 | oui | 0.132 | LITTERAL_NON_OBSERVE ×1 | 0 | `0ffb8e6dcc285374` |
| produits_recherche | 1 | oui | 0.069 | — | 0 | `e837255edb92d31f` |
| client_creation_nom_limite | 2 | oui | 0.109 | — | 0 | `2e4eebf4b7545fde` |
| client_creation_nom_requis | 2 | oui | 0.107 | — | 0 | `4a81c8262e4286ab` |
| client_creation_valide | 2 | oui | 0.105 | — | 0 | `3d05d22fff00f27e` |
| commande_confirmation | 2 | oui | 0.107 | — | 0 | `0874f026ea3f9c00` |
| commande_persistance_serveur | 2 | oui | 0.234 | LITTERAL_NON_OBSERVE ×2 | 2 | `c580a386e66b84d3` |
| connexion_refusee | 2 | oui | 0.129 | LITTERAL_NON_OBSERVE ×1 | 0 | `a97ccbfffb6566dc` |
| connexion_valide | 2 | oui | 0.119 | — | 0 | `ff3aa5e9e2655cec` |
| panier_remise_arrondi | 2 | oui | 0.090 | — | 0 | `8bf30ad43590715c` |
| panier_total_tva | 2 | oui | 0.109 | — | 0 | `a56e1b228f8752ba` |
| produits_recherche | 2 | oui | 0.072 | — | 0 | `d610735066d940e3` |
