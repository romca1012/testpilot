# Banc d'agents web — 2026-10-09 — base-4-complement

Échantillon : **5 cas × k = 1 essais** → 5/5 essais lancés, 9 jeux (couples cas/variante). Commit `b325077` · modèle de génération `claude-sonnet-4-6` · testpilot `0.1.0` · behave `1.3.3` · playwright `1.62.0`.

## ⚠️ Sous-ensemble de cas (mise au point)

Ce rapport ne porte PAS sur le corpus entier : ne jamais le publier comme mesure du banc.

## Indicateurs

| Indicateur | Valeur |
|---|---|
| **Faux verts** (défaut injecté, attendu non_conforme, obtenu conforme) | 0/2 (0,0 %, IC95 % 0,0–65,8 %) ; 2 non concluants |
| Faux rouges (saine, attendu conforme, obtenu non_conforme) | 0/2 (0,0 %, IC95 % 0,0–65,8 %) ; 3 non concluants |
| pass@1 — le test généré s'exécute sans erreur technique | 2/5 (40,0 %, IC95 % 11,8–76,9 %) |
| pass@1 — au moins un essai sur 1 | 2/5 (40,0 %, IC95 % 11,8–76,9 %) |
| pass^1 — tous les essais | 2/5 (40,0 %, IC95 % 11,8–76,9 %) |
| pass@1 — résultat juste partout (saine ET défauts) | 2/5 (40,0 %, IC95 % 11,8–76,9 %) |
| pass@1 — résultat juste partout | 2/5 (40,0 %, IC95 % 11,8–76,9 %) |
| pass^1 — résultat juste partout, à chaque essai | 2/5 (40,0 %, IC95 % 11,8–76,9 %) |

« non mesuré » signifie qu'aucun jeu concluant n'existe pour cet indicateur : ce n'est PAS 0 %. Un taux de faux verts faible obtenu avec beaucoup de non concluants ne prouve rien : lire la ligne suivante et les intervalles (Wilson 95 %).

## Résultats non concluants (comptés, jamais retirés)

| Verdict | Jeux |
|---|---|
| blocked | 1 |
| technical_error | 4 |

## Détection par défaut

| Défaut | Jeux | Concluants | Détectés (non_conforme) | dont fiables (saine du même essai conforme) | Faux verts | Non concluants |
|---|---|---|---|---|---|---|
| `filtre_ignore` | 1 | 1 | 1/1 (100,0 %, IC95 % 20,7–100,0 %) | 1/1 (100,0 %, IC95 % 20,7–100,0 %) | 0 | 0 |
| `login_accepte_tout` | 1 | 1 | 1/1 (100,0 %, IC95 % 20,7–100,0 %) | 1/1 (100,0 %, IC95 % 20,7–100,0 %) | 0 | 0 |
| `total_faux` | 2 | 0 | non mesuré | non mesuré | 0 | 2 |

## Après UNE réparation (D23)

Pour chaque essai dont le jeu sur l'application saine sort en `technical_error`, l'agent de réparation reçoit l'échec observé (jamais un diagnostic) et propose UNE correction ; la version réparée est rejouée sur toutes les variantes. Les autres essais restent tels quels. Le nombre de tentatives par essai est celui du budget de réparation du produit (`--tentatives-reparation`) ; le circuit complet (arrêt sur régression, couverture perdue) n'est pas rejoué ici.

| Indicateur | Avant réparation | Après une réparation |
|---|---|---|
| Faux verts | 0/2 (0,0 %, IC95 % 0,0–65,8 %) ; 2 non concluants | 0/2 (0,0 %, IC95 % 0,0–65,8 %) ; 2 non concluants |
| Faux rouges | 0/2 (0,0 %, IC95 % 0,0–65,8 %) ; 3 non concluants | 0/3 (0,0 %, IC95 % 0,0–56,2 %) ; 2 non concluants |
| pass@1 — s'exécute sans erreur technique | 2/5 (40,0 %, IC95 % 11,8–76,9 %) | 3/5 (60,0 %, IC95 % 23,1–88,2 %) |
| pass@1 — résultat juste partout | 2/5 (40,0 %, IC95 % 11,8–76,9 %) | 2/5 (40,0 %, IC95 % 11,8–76,9 %) |
| pass^k — résultat juste partout, à chaque essai | 2/5 (40,0 %, IC95 % 11,8–76,9 %) | 2/5 (40,0 %, IC95 % 11,8–76,9 %) |

Réparations : 1 essai(s) à réparer, 1 tenté(s) en 1 tentative(s), 1 avec une correction rejouable ; saine exécutable après : 1, conforme après : 1 ; coût des réparations : **0.102 $**.

## Coût

Total : **0.511 $** = 0.473 € (1 € = 1.08 $) pour 5 génération(s) ; par génération : 0.102 $ / 0.095 €.
Les jeux sur les variantes ne coûtent rien (aucun appel LLM) : tout le coût est celui des générations.

| Cas | Coût moyen par génération ($) |
|---|---|
| connexion_refusee | 0.104 |
| connexion_valide | 0.126 |
| panier_remise_arrondi | 0.085 |
| panier_total_tva | 0.129 |
| produits_recherche | 0.066 |

## Intégrité : le MÊME test est joué partout

Jeux dont les empreintes sha256 des fichiers joués égalent celles de la génération : **7** ; divergentes : **0** ; non rapportées : 0.

## Écarts aux attendus (à instruire : le test généré, le défaut ou le verdict — jamais l'attendu)

| Cas | Variante | Essai | Attendu | Obtenu | Cause |
|---|---|---|---|---|---|
| connexion_valide | saine | 1 | conforme | blocked | precondition_non_remplie |
| panier_remise_arrondi | saine | 1 | conforme | technical_error | generation_echouee |
| panier_remise_arrondi | total_faux | 1 | non_conforme | technical_error | generation_echouee |
| panier_total_tva | saine | 1 | conforme | technical_error | wrong_field_name |
| panier_total_tva | total_faux | 1 | non_conforme | technical_error | wrong_field_name |

## Génération par essai

| Cas | Essai | Généré | Coût ($) | Empreinte du test (sha256) |
|---|---|---|---|---|
| connexion_refusee | 1 | oui | 0.104 | `26d62ef3ce689264` |
| connexion_valide | 1 | oui | 0.126 | `90cfb98fabc86e75` |
| panier_remise_arrondi | 1 | NON : génération sans essai à blanc passé | 0.085 | `—` |
| panier_total_tva | 1 | oui | 0.129 | `cd7ea9313644af90` |
| produits_recherche | 1 | oui | 0.066 | `5446289dc5fcdef5` |
