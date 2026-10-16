# Banc d'agents web — 2026-10-16 — m2-allume

Échantillon : **10 cas × k = 2 essais** → 19/20 essais lancés, 36 jeux (couples cas/variante). Commit `178054f` · modèle de génération `claude-sonnet-4-6` · testpilot `0.1.0` · behave `1.3.3` · playwright `1.62.0`.

## ⚠️ Campagne INCOMPLÈTE : plafond de coût : cumul 3.134 $ + essai le plus cher attendu 0.503 $ > plafond 3.500 $ (avant produits_recherche, essai 2)

Les indicateurs portent sur les essais lancés seulement, jamais sur le corpus entier.

## Indicateurs

| Indicateur | Valeur |
|---|---|
| **Faux verts** (défaut injecté, attendu non_conforme, obtenu conforme) | 0/11 (0,0 %, IC95 % 0,0–25,9 %) ; 6 non concluants |
| Faux rouges (saine, attendu conforme, obtenu non_conforme) | 0/12 (0,0 %, IC95 % 0,0–24,3 %) ; 7 non concluants |
| pass@1 — le test généré s'exécute sans erreur technique | 6/10 (60,0 %, IC95 % 31,3–83,2 %) |
| pass@2 — au moins un essai sur 2 | 7/9 (77,8 %, IC95 % 45,3–93,7 %) ; 1 cas sans assez d'essais |
| pass^2 — tous les essais | 4/9 (44,4 %, IC95 % 18,9–73,3 %) ; 1 cas sans assez d'essais |
| pass@1 — résultat juste partout (saine ET défauts) | 6/10 (60,0 %, IC95 % 31,3–83,2 %) |
| pass@2 — résultat juste partout | 7/9 (77,8 %, IC95 % 45,3–93,7 %) ; 1 cas sans assez d'essais |
| pass^2 — résultat juste partout, à chaque essai | 4/9 (44,4 %, IC95 % 18,9–73,3 %) ; 1 cas sans assez d'essais |

« non mesuré » signifie qu'aucun jeu concluant n'existe pour cet indicateur : ce n'est PAS 0 %. Un taux de faux verts faible obtenu avec beaucoup de non concluants ne prouve rien : lire la ligne suivante et les intervalles (Wilson 95 %).

## Résultats non concluants (comptés, jamais retirés)

| Verdict | Jeux |
|---|---|
| technical_error | 13 |

## Détection par défaut

| Défaut | Jeux | Concluants | Détectés (non_conforme) | dont fiables (saine du même essai conforme) | Faux verts | Non concluants |
|---|---|---|---|---|---|---|
| `etat_non_enregistre` | 4 | 3 | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 0 | 1 |
| `filtre_ignore` | 1 | 1 | 1/1 (100,0 %, IC95 % 20,7–100,0 %) | 1/1 (100,0 %, IC95 % 20,7–100,0 %) | 0 | 0 |
| `login_accepte_tout` | 2 | 0 | non mesuré | non mesuré | 0 | 2 |
| `message_erreur_absent` | 4 | 4 | 4/4 (100,0 %, IC95 % 51,0–100,0 %) | 4/4 (100,0 %, IC95 % 51,0–100,0 %) | 0 | 0 |
| `total_faux` | 4 | 1 | 1/1 (100,0 %, IC95 % 20,7–100,0 %) | 1/1 (100,0 %, IC95 % 20,7–100,0 %) | 0 | 3 |
| `validation_absente` | 2 | 2 | 2/2 (100,0 %, IC95 % 34,2–100,0 %) | 2/2 (100,0 %, IC95 % 34,2–100,0 %) | 0 | 0 |

## Coût

Total : **3.134 $** = 2.902 € (1 € = 1.08 $) pour 19 génération(s) ; par génération : 0.165 $ / 0.153 €.
Les jeux sur les variantes ne coûtent rien (aucun appel LLM) : tout le coût est celui des générations.

| Cas | Coût moyen par génération ($) |
|---|---|
| client_creation_nom_limite | 0.091 |
| client_creation_nom_requis | 0.135 |
| client_creation_valide | 0.115 |
| commande_confirmation | 0.174 |
| commande_persistance_serveur | 0.447 |
| connexion_refusee | 0.120 |
| connexion_valide | 0.133 |
| panier_remise_arrondi | 0.132 |
| panier_total_tva | 0.172 |
| produits_recherche | 0.096 |

## Intégrité : le MÊME test est joué partout

Jeux dont les empreintes sha256 des fichiers joués égalent celles de la génération : **23** ; divergentes : **0** ; non rapportées : 0.

## Écarts aux attendus (à instruire : le test généré, le défaut ou le verdict — jamais l'attendu)

| Cas | Variante | Essai | Attendu | Obtenu | Cause |
|---|---|---|---|---|---|
| commande_confirmation | saine | 1 | conforme | technical_error | generation_echouee |
| commande_persistance_serveur | saine | 1 | conforme | technical_error | generation_echouee |
| commande_persistance_serveur | etat_non_enregistre | 1 | non_conforme | technical_error | generation_echouee |
| connexion_refusee | saine | 1 | conforme | technical_error | generation_echouee |
| connexion_refusee | login_accepte_tout | 1 | non_conforme | technical_error | generation_echouee |
| panier_total_tva | saine | 1 | conforme | technical_error | generation_echouee |
| panier_total_tva | total_faux | 1 | non_conforme | technical_error | generation_echouee |
| connexion_refusee | saine | 2 | conforme | technical_error | generation_echouee |
| connexion_refusee | login_accepte_tout | 2 | non_conforme | technical_error | generation_echouee |
| panier_remise_arrondi | saine | 2 | conforme | technical_error | generation_echouee |
| panier_remise_arrondi | total_faux | 2 | non_conforme | technical_error | generation_echouee |
| panier_total_tva | saine | 2 | conforme | technical_error | generation_echouee |
| panier_total_tva | total_faux | 2 | non_conforme | technical_error | generation_echouee |

## Refus des gardes d'écriture pendant la génération (lot VH-04)

Chaque refus renvoie l'agent corriger dans la même génération : il coûte des tours, il ne casse rien.

| Code du refus | Nombre |
|---|---|
| `LITTERAL_NON_OBSERVE` | 6 |
| `ECHAPPEMENT_LITTERAL` | 2 |

## Code libre (lot VH-06)

Tests générés sans AUCUN step écrit à la main : **11/12** ; steps définis par les tests : 1 au total (maximum 1 dans un test). Un step écrit à la main n'a ni test de falsifiabilité ni résolution éprouvée : la cible est zéro.

## Données de test (lot PT-02d)

Tests générés qui écrivent au moins une variable : **4/12** ; variables écrites : `ville_client` ×4, `nom_client` ×2.

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
| client_creation_nom_limite | 1 | oui | 0.086 | — | 0 | `746de64f1d54454a` |
| client_creation_nom_requis | 1 | oui | 0.179 | LITTERAL_NON_OBSERVE ×1 | 1 | `b1e408aacf6ee0a9` |
| client_creation_valide | 1 | oui | 0.112 | ECHAPPEMENT_LITTERAL ×1 | 0 | `16e05981df875bc9` |
| commande_confirmation | 1 | NON : génération sans essai à blanc passé | 0.205 | — | — | `—` |
| commande_persistance_serveur | 1 | NON : génération sans essai à blanc passé | 0.503 | LITTERAL_NON_OBSERVE ×3 | — | `—` |
| connexion_refusee | 1 | NON : génération sans essai à blanc passé | 0.127 | — | — | `—` |
| connexion_valide | 1 | oui | 0.156 | — | 0 | `d1d925cf187554bd` |
| panier_remise_arrondi | 1 | oui | 0.137 | — | 0 | `ca5bdd0ec9577493` |
| panier_total_tva | 1 | NON : génération sans essai à blanc passé | 0.189 | — | — | `—` |
| produits_recherche | 1 | oui | 0.096 | — | 0 | `cb9bab9bb4bdaa94` |
| client_creation_nom_limite | 2 | oui | 0.097 | — | 0 | `f12d51ae13de3ca7` |
| client_creation_nom_requis | 2 | oui | 0.090 | — | 0 | `50d6c8c7ede3cdf2` |
| client_creation_valide | 2 | oui | 0.117 | ECHAPPEMENT_LITTERAL ×1 | 0 | `d3b3c9b492ff0617` |
| commande_confirmation | 2 | oui | 0.144 | — | 0 | `174d26b918293fd3` |
| commande_persistance_serveur | 2 | oui | 0.390 | LITTERAL_NON_OBSERVE ×2 | 0 | `a23567cf4d0e3489` |
| connexion_refusee | 2 | NON : génération sans essai à blanc passé | 0.114 | — | — | `—` |
| connexion_valide | 2 | oui | 0.110 | — | 0 | `e441297a34a801db` |
| panier_remise_arrondi | 2 | NON : génération sans essai à blanc passé | 0.128 | — | — | `—` |
| panier_total_tva | 2 | NON : génération sans essai à blanc passé | 0.155 | — | — | `—` |
