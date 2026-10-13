# Paramètres de test — mesures de référence avant travaux (lot PT-00)

Date : 2026-10-13. Code mesuré : `master` = `846ef04`, sur une copie de travail intacte, poste Windows du porteur.

## Suite de contrôles du serveur

Commande : `python -m pytest -q` (suite par défaut, tests à navigateur réel exclus).

| Résultat | Nombre |
|---|---|
| Réussis | 4 206 |
| En échec | 5 |
| Ignorés | 17 |
| Durée | 28 min 22 s |

Les 5 échecs existent **avant** tout changement du chantier ; ils tiennent au poste, pas au code :

| Test | Cause |
|---|---|
| `test_bibliotheque_par_connecteur::test_assemble_copie_les_deux_volets_du_profil_sapian_sous_un_nom_canonique` | compare un chemin écrit avec des `/` à un chemin Windows |
| `test_migration_lot06_profil_instance` (4 tests) | lancent un script dans un sous-processus ; ils échouent dans une copie de travail secondaire qui partage l'environnement virtuel de la copie principale. Cause exacte non instruite. |

Conséquence pour les lots suivants : ces 5 échecs ne sont pas des régressions. Tout autre échec en est une.

## Contrôles de l'interface

Commande : `npm --prefix frontend test -- --run`, puis `npm --prefix frontend run type-check`.

| Mesure | Avant le chantier | Après PT-00 | Après PT-01a | Après PT-01b et la revue |
|---|---|---|---|---|
| Fichiers de tests | 61 | 61 | 63 | 64 |
| Tests réussis | 401 | 403 | 426 | 442 |
| Vérification des types | propre | propre | propre | propre |

Un test d'interface instable, antérieur au chantier : `ProjectsList.premierAdmin.spec.ts` (« propose de créer directement
ici… ») échoue de temps en temps quand le poste est chargé (1 fois sur 3 passages complets pendant la revue, 3 réussites
sur 3 lancé seul). Cause non instruite ; il n'est pas compté comme une régression.

## Banc d'agents

Référence inchangée : campagne `base-7` (`banc-agents-2026-10-11-base-7.md`) — 0 faux vert sur 25, 0 faux rouge sur 23,
7 cas sur 10 justes au premier essai, 0,166 $ par génération. PT-00 et PT-01 ne changent rien de ce que l'agent reçoit :
aucune campagne n'est nécessaire pour eux.
