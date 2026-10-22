# Banc d'agents web — 2026-10-22 — etape5-avant

Échantillon : **11 cas × k = 2 essais** → 22/22 essais lancés, 42 jeux (couples cas/variante). Commit `3e20ca4` · modèle de génération `claude-sonnet-4-6` · testpilot `0.1.0` · behave `1.3.3` · playwright `1.62.0`.

## Indicateurs

| Indicateur | Valeur |
|---|---|
| **Faux verts** (défaut injecté, attendu non_conforme, obtenu conforme) | 0/12 (0,0 %, IC95 % 0,0–24,3 %) ; 8 non concluants |
| Faux rouges (saine, attendu conforme, obtenu non_conforme) | 0/13 (0,0 %, IC95 % 0,0–22,8 %) ; 9 non concluants |
| pass@1 — le test généré s'exécute sans erreur technique | 6/11 (54,5 %, IC95 % 28,0–78,7 %) |
| pass@2 — au moins un essai sur 2 | 9/11 (81,8 %, IC95 % 52,3–94,9 %) |
| pass^2 — tous les essais | 4/11 (36,4 %, IC95 % 15,2–64,6 %) |
| pass@1 — résultat juste partout (saine ET défauts) | 6/11 (54,5 %, IC95 % 28,0–78,7 %) |
| pass@2 — résultat juste partout | 9/11 (81,8 %, IC95 % 52,3–94,9 %) |
| pass^2 — résultat juste partout, à chaque essai | 4/11 (36,4 %, IC95 % 15,2–64,6 %) |

« non mesuré » signifie qu'aucun jeu concluant n'existe pour cet indicateur : ce n'est PAS 0 %. Un taux de faux verts faible obtenu avec beaucoup de non concluants ne prouve rien : lire la ligne suivante et les intervalles (Wilson 95 %).

## Résultats non concluants (comptés, jamais retirés)

| Verdict | Jeux |
|---|---|
| blocked | 4 |
| technical_error | 13 |

## Détection par défaut

| Défaut | Jeux | Concluants | Détectés (non_conforme) | dont fiables (saine du même essai conforme) | Faux verts | Non concluants |
|---|---|---|---|---|---|---|
| `etat_non_enregistre` | 4 | 3 | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 2/3 (66,7 %, IC95 % 20,8–93,9 %) | 0 | 1 |
| `filtre_ignore` | 2 | 2 | 2/2 (100,0 %, IC95 % 34,2–100,0 %) | 2/2 (100,0 %, IC95 % 34,2–100,0 %) | 0 | 0 |
| `limite_age_decalee` | 2 | 0 | non mesuré | non mesuré | 0 | 2 |
| `login_accepte_tout` | 2 | 2 | 2/2 (100,0 %, IC95 % 34,2–100,0 %) | 2/2 (100,0 %, IC95 % 34,2–100,0 %) | 0 | 0 |
| `message_erreur_absent` | 4 | 3 | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 0 | 1 |
| `total_faux` | 4 | 1 | 1/1 (100,0 %, IC95 % 20,7–100,0 %) | 1/1 (100,0 %, IC95 % 20,7–100,0 %) | 0 | 3 |
| `validation_absente` | 2 | 1 | 1/1 (100,0 %, IC95 % 20,7–100,0 %) | 1/1 (100,0 %, IC95 % 20,7–100,0 %) | 0 | 1 |

## Coût

Total : **2.954 $** = 2.735 € (1 € = 1.08 $) pour 22 génération(s) ; par génération : 0.134 $ / 0.124 €.
Les jeux sur les variantes ne coûtent rien (aucun appel LLM) : tout le coût est celui des générations.

| Cas | Coût moyen par génération ($) |
|---|---|
| acces_age_limite | 0.098 |
| client_creation_nom_limite | 0.094 |
| client_creation_nom_requis | 0.097 |
| client_creation_valide | 0.107 |
| commande_confirmation | 0.096 |
| commande_persistance_serveur | 0.415 |
| connexion_refusee | 0.134 |
| connexion_valide | 0.106 |
| panier_remise_arrondi | 0.107 |
| panier_total_tva | 0.159 |
| produits_recherche | 0.064 |

## Intégrité : le MÊME test est joué partout

Jeux dont les empreintes sha256 des fichiers joués égalent celles de la génération : **42** ; divergentes : **0** ; non rapportées : 0.

## Écarts aux attendus (à instruire : le test généré, le défaut ou le verdict — jamais l'attendu)

| Cas | Variante | Essai | Attendu | Obtenu | Cause |
|---|---|---|---|---|---|
| acces_age_limite | saine | 1 | conforme | technical_error | wrong_field_name |
| acces_age_limite | limite_age_decalee | 1 | non_conforme | technical_error | wrong_field_name |
| client_creation_nom_requis | saine | 1 | conforme | technical_error | wrong_field_name |
| client_creation_nom_requis | validation_absente | 1 | non_conforme | technical_error | wrong_field_name |
| client_creation_nom_requis | message_erreur_absent | 1 | non_conforme | technical_error | wrong_field_name |
| commande_persistance_serveur | saine | 1 | conforme | technical_error | broken_test_code |
| panier_remise_arrondi | saine | 1 | conforme | blocked | precondition_non_remplie |
| panier_remise_arrondi | total_faux | 1 | non_conforme | blocked | precondition_non_remplie |
| panier_total_tva | saine | 1 | conforme | technical_error | wrong_field_name |
| panier_total_tva | total_faux | 1 | non_conforme | technical_error | wrong_field_name |
| acces_age_limite | saine | 2 | conforme | technical_error | wrong_field_name |
| acces_age_limite | limite_age_decalee | 2 | non_conforme | technical_error | wrong_field_name |
| client_creation_valide | saine | 2 | conforme | blocked | precondition_non_remplie |
| client_creation_valide | etat_non_enregistre | 2 | non_conforme | blocked | precondition_non_remplie |
| commande_confirmation | saine | 2 | conforme | technical_error | broken_test_code |
| panier_total_tva | saine | 2 | conforme | technical_error | wrong_field_name |
| panier_total_tva | total_faux | 2 | non_conforme | technical_error | wrong_field_name |

## Refus des gardes d'écriture pendant la génération (lot VH-04)

Chaque refus renvoie l'agent corriger dans la même génération : il coûte des tours, il ne casse rien.

| Code du refus | Nombre |
|---|---|
| `LITTERAL_NON_OBSERVE` | 5 |
| `TRANSPORT_INTERDIT` | 1 |
| `PYTHON_INTERDIT` | 1 |

## Code libre (lot VH-06)

Tests générés sans AUCUN step écrit à la main : **21/22** ; steps définis par les tests : 3 au total (maximum 3 dans un test). Un step écrit à la main n'a ni test de falsifiabilité ni résolution éprouvée : la cible est zéro.

## Prêts à lancer (étape 3 du plan unique)

Tests que le produit livrerait **prêts à lancer** (aucun point de vigilance) : **20/22 (90,9 %, IC95 % 72,2–97,5 %)** des essais lancés ; générations échouées : 0 ; mesures impossibles : 0 ; faux verts parmi les prêts : **0**.

Contrôle de fin d'écriture **éteint** : borne BASSE — le produit tenterait une correction automatique sur ces points, non jouée et non coûtée ici. Ne pas comparer au bras allumé sans le dire.

| Raison du blocage | Tests |
|---|---|
| `champ_ui_non_verifie` | 2 |

## Génération par essai

| Cas | Essai | Généré | Coût ($) | Refus à l'écriture | Steps écrits à la main | Empreinte du test (sha256) |
|---|---|---|---|---|---|---|
| acces_age_limite | 1 | oui | 0.099 | — | 0 | `c736f8d7ccca43b3` |
| client_creation_nom_limite | 1 | oui | 0.092 | — | 0 | `44ee7ad1f43fe658` |
| client_creation_nom_requis | 1 | oui | 0.083 | — | 0 | `706e53fe6f35196c` |
| client_creation_valide | 1 | oui | 0.109 | — | 0 | `dbc54af43541fcfc` |
| commande_confirmation | 1 | oui | 0.109 | — | 0 | `de0caac5355b5485` |
| commande_persistance_serveur | 1 | oui | 0.363 | LITTERAL_NON_OBSERVE ×2, TRANSPORT_INTERDIT ×1 | 0 | `19e3b30ddea05ddc` |
| connexion_refusee | 1 | oui | 0.161 | — | 0 | `0ca5016cd3a31cfe` |
| connexion_valide | 1 | oui | 0.091 | — | 0 | `3e90478230d757ee` |
| panier_remise_arrondi | 1 | oui | 0.127 | — | 0 | `be0b82c1cff913da` |
| panier_total_tva | 1 | oui | 0.166 | — | 0 | `e6d79899549d4bca` |
| produits_recherche | 1 | oui | 0.068 | — | 0 | `600fd31436c61cab` |
| acces_age_limite | 2 | oui | 0.098 | — | 0 | `ff3055c48c3b1688` |
| client_creation_nom_limite | 2 | oui | 0.097 | — | 0 | `cea1ce323ce752b0` |
| client_creation_nom_requis | 2 | oui | 0.112 | — | 0 | `8f64a5d06140fc5b` |
| client_creation_valide | 2 | oui | 0.106 | — | 0 | `5350dcc31a5e17bf` |
| commande_confirmation | 2 | oui | 0.082 | — | 0 | `f627971c8b37348f` |
| commande_persistance_serveur | 2 | oui | 0.467 | LITTERAL_NON_OBSERVE ×3, PYTHON_INTERDIT ×1 | 3 | `522cf3102899cfff` |
| connexion_refusee | 2 | oui | 0.107 | — | 0 | `1e2d955938668a2a` |
| connexion_valide | 2 | oui | 0.121 | — | 0 | `488d137848a923f3` |
| panier_remise_arrondi | 2 | oui | 0.087 | — | 0 | `251ad93ca03a188e` |
| panier_total_tva | 2 | oui | 0.151 | — | 0 | `08076af164a96a1e` |
| produits_recherche | 2 | oui | 0.059 | — | 0 | `9a5675298c90a0b4` |
