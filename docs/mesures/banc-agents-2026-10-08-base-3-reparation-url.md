# Banc d'agents web — 2026-10-08 — base-3-reparation-url

Échantillon : **10 cas × k = 3 essais** → 30/30 essais lancés, 57 jeux (couples cas/variante). Commit `1ab2695` · modèle de génération `claude-sonnet-4-6` · testpilot `0.1.0` · behave `1.3.3` · playwright `1.62.0`.

## Indicateurs

| Indicateur | Valeur |
|---|---|
| **Faux verts** (défaut injecté, attendu non_conforme, obtenu conforme) | 0/21 (0,0 %, IC95 % 0,0–15,5 %) ; 6 non concluants |
| Faux rouges (saine, attendu conforme, obtenu non_conforme) | 6/23 (26,1 %, IC95 % 12,5–46,5 %) ; 7 non concluants |
| pass@1 — le test généré s'exécute sans erreur technique | 9/10 (90,0 %, IC95 % 59,6–98,2 %) |
| pass@3 — au moins un essai sur 3 | 9/10 (90,0 %, IC95 % 59,6–98,2 %) |
| pass^3 — tous les essais | 6/10 (60,0 %, IC95 % 31,3–83,2 %) |
| pass@1 — résultat juste partout (saine ET défauts) | 7/10 (70,0 %, IC95 % 39,7–89,2 %) |
| pass@3 — résultat juste partout | 7/10 (70,0 %, IC95 % 39,7–89,2 %) |
| pass^3 — résultat juste partout, à chaque essai | 3/10 (30,0 %, IC95 % 10,8–60,3 %) |

« non mesuré » signifie qu'aucun jeu concluant n'existe pour cet indicateur : ce n'est PAS 0 %. Un taux de faux verts faible obtenu avec beaucoup de non concluants ne prouve rien : lire la ligne suivante et les intervalles (Wilson 95 %).

## Résultats non concluants (comptés, jamais retirés)

| Verdict | Jeux |
|---|---|
| technical_error | 13 |

## Détection par défaut

| Défaut | Jeux | Concluants | Détectés (non_conforme) | dont fiables (saine du même essai conforme) | Faux verts | Non concluants |
|---|---|---|---|---|---|---|
| `etat_non_enregistre` | 6 | 4 | 4/4 (100,0 %, IC95 % 51,0–100,0 %) | 0/4 (0,0 %, IC95 % 0,0–49,0 %) | 0 | 2 |
| `filtre_ignore` | 3 | 3 | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 0 | 0 |
| `login_accepte_tout` | 3 | 3 | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 0 | 0 |
| `message_erreur_absent` | 6 | 6 | 6/6 (100,0 %, IC95 % 61,0–100,0 %) | 4/6 (66,7 %, IC95 % 30,0–90,3 %) | 0 | 0 |
| `total_faux` | 6 | 2 | 2/2 (100,0 %, IC95 % 34,2–100,0 %) | 2/2 (100,0 %, IC95 % 34,2–100,0 %) | 0 | 4 |
| `validation_absente` | 3 | 3 | 3/3 (100,0 %, IC95 % 43,8–100,0 %) | 2/3 (66,7 %, IC95 % 20,8–93,9 %) | 0 | 0 |

## Après UNE réparation (D23)

Pour chaque essai dont le jeu sur l'application saine sort en `technical_error`, l'agent de réparation reçoit l'échec observé (jamais un diagnostic) et propose UNE correction ; la version réparée est rejouée sur toutes les variantes. Les autres essais restent tels quels. Ce n'est pas le circuit complet du produit (budget fixé à la relecture, plusieurs tentatives) : c'est une borne basse de ce que la réparation apporte.

| Indicateur | Avant réparation | Après une réparation |
|---|---|---|
| Faux verts | 0/21 (0,0 %, IC95 % 0,0–15,5 %) ; 6 non concluants | 0/22 (0,0 %, IC95 % 0,0–14,9 %) ; 5 non concluants |
| Faux rouges | 6/23 (26,1 %, IC95 % 12,5–46,5 %) ; 7 non concluants | 6/23 (26,1 %, IC95 % 12,5–46,5 %) ; 7 non concluants |
| pass@1 — s'exécute sans erreur technique | 9/10 (90,0 %, IC95 % 59,6–98,2 %) | 9/10 (90,0 %, IC95 % 59,6–98,2 %) |
| pass@1 — résultat juste partout | 7/10 (70,0 %, IC95 % 39,7–89,2 %) | 7/10 (70,0 %, IC95 % 39,7–89,2 %) |
| pass^k — résultat juste partout, à chaque essai | 3/10 (30,0 %, IC95 % 10,8–60,3 %) | 3/10 (30,0 %, IC95 % 10,8–60,3 %) |

Réparations : 5 à réparer, 5 tentées, 4 rejouables ; saine exécutable après : 0, conforme après : 0 ; coût des réparations : **0.061 $**.

- client_creation_nom_limite essai 3 : l'agent n'a rien réécrit

## Coût

Total : **0.000 $** = 0.000 € (1 € = 1.08 $) pour 30 génération(s) ; par génération : 0.000 $ / 0.000 €.
Les jeux sur les variantes ne coûtent rien (aucun appel LLM) : tout le coût est celui des générations.

| Cas | Coût moyen par génération ($) |
|---|---|
| client_creation_nom_limite | 0.000 |
| client_creation_nom_requis | 0.000 |
| client_creation_valide | 0.000 |
| commande_confirmation | 0.000 |
| commande_persistance_serveur | 0.000 |
| connexion_refusee | 0.000 |
| connexion_valide | 0.000 |
| panier_remise_arrondi | 0.000 |
| panier_total_tva | 0.000 |
| produits_recherche | 0.000 |

## Intégrité : le MÊME test est joué partout

Jeux dont les empreintes sha256 des fichiers joués égalent celles de la génération : **53** ; divergentes : **0** ; non rapportées : 0.

## Écarts aux attendus (à instruire : le test généré, le défaut ou le verdict — jamais l'attendu)

| Cas | Variante | Essai | Attendu | Obtenu | Cause |
|---|---|---|---|---|---|
| client_creation_valide | saine | 1 | conforme | non_conforme | assertion_mismatch |
| commande_persistance_serveur | saine | 1 | conforme | non_conforme | assertion_mismatch |
| panier_total_tva | saine | 1 | conforme | technical_error | wrong_field_name |
| panier_total_tva | total_faux | 1 | non_conforme | technical_error | wrong_field_name |
| client_creation_nom_requis | saine | 2 | conforme | non_conforme | assertion_mismatch |
| client_creation_valide | saine | 2 | conforme | non_conforme | assertion_mismatch |
| commande_persistance_serveur | saine | 2 | conforme | technical_error | wrong_field_name |
| commande_persistance_serveur | etat_non_enregistre | 2 | non_conforme | technical_error | wrong_field_name |
| connexion_valide | saine | 2 | conforme | non_conforme | assertion_mismatch |
| panier_remise_arrondi | saine | 2 | conforme | technical_error | generation_echouee |
| panier_remise_arrondi | total_faux | 2 | non_conforme | technical_error | generation_echouee |
| panier_total_tva | saine | 2 | conforme | technical_error | wrong_field_name |
| panier_total_tva | total_faux | 2 | non_conforme | technical_error | wrong_field_name |
| client_creation_nom_limite | saine | 3 | conforme | technical_error | wrong_field_name |
| client_creation_valide | saine | 3 | conforme | non_conforme | assertion_mismatch |
| commande_persistance_serveur | saine | 3 | conforme | technical_error | generation_echouee |
| commande_persistance_serveur | etat_non_enregistre | 3 | non_conforme | technical_error | generation_echouee |
| panier_total_tva | saine | 3 | conforme | technical_error | wrong_field_name |
| panier_total_tva | total_faux | 3 | non_conforme | technical_error | wrong_field_name |

## Génération par essai

| Cas | Essai | Généré | Coût ($) | Empreinte du test (sha256) |
|---|---|---|---|---|
| client_creation_nom_limite | 1 | oui | 0.000 | `e845982ffac2cccf` |
| client_creation_nom_requis | 1 | oui | 0.000 | `042dedc2b4b651d3` |
| client_creation_valide | 1 | oui | 0.000 | `eae8c3312479cfc8` |
| commande_confirmation | 1 | oui | 0.000 | `d21c2ab1efa22ebf` |
| commande_persistance_serveur | 1 | oui | 0.000 | `2899e79dd06fd073` |
| connexion_refusee | 1 | oui | 0.000 | `12f172bf893c4b35` |
| connexion_valide | 1 | oui | 0.000 | `3e02c536587cbe32` |
| panier_remise_arrondi | 1 | oui | 0.000 | `b52942d25df56a97` |
| panier_total_tva | 1 | oui | 0.000 | `3b2c18337f88f413` |
| produits_recherche | 1 | oui | 0.000 | `5d12990021f3a151` |
| client_creation_nom_limite | 2 | oui | 0.000 | `419c5cb4e74ca555` |
| client_creation_nom_requis | 2 | oui | 0.000 | `867df992cc38e8d1` |
| client_creation_valide | 2 | oui | 0.000 | `70c198ce3e4a5c7e` |
| commande_confirmation | 2 | oui | 0.000 | `4fde2eec0028c6e0` |
| commande_persistance_serveur | 2 | oui | 0.000 | `4ad8a211e92a17aa` |
| connexion_refusee | 2 | oui | 0.000 | `1c92758a4cf9bcbe` |
| connexion_valide | 2 | oui | 0.000 | `51987f19331620d4` |
| panier_remise_arrondi | 2 | NON : génération sans essai à blanc passé | 0.000 | `—` |
| panier_total_tva | 2 | oui | 0.000 | `f877c50e4e32a75f` |
| produits_recherche | 2 | oui | 0.000 | `d7afabb920add159` |
| client_creation_nom_limite | 3 | oui | 0.000 | `6622821a2ade28cc` |
| client_creation_nom_requis | 3 | oui | 0.000 | `4211f2ad55fe725c` |
| client_creation_valide | 3 | oui | 0.000 | `b2565cd771adaf58` |
| commande_confirmation | 3 | oui | 0.000 | `ad5641607477c2c3` |
| commande_persistance_serveur | 3 | NON : Connection error. | 0.000 | `—` |
| connexion_refusee | 3 | oui | 0.000 | `627e0ab1a66b5efe` |
| connexion_valide | 3 | oui | 0.000 | `213effdef15b86d7` |
| panier_remise_arrondi | 3 | oui | 0.000 | `e4eef583efff2565` |
| panier_total_tva | 3 | oui | 0.000 | `a34ab648cd8bcc98` |
| produits_recherche | 3 | oui | 0.000 | `46d2f2f31bedd49d` |
