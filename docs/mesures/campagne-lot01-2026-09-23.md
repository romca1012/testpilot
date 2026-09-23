# Campagne de validation du lot 01 — 2026-09-23

Deux campagnes réelles (génération LLM indépendante + exécution physique unique par essai,
`TESTPILOT_QUALIFICATION=1`, isolation des mémoires apprises entre essais, vérification
indépendante par requête RPC hors des assertions du Gherkin généré), lancées avec
`scripts/qualify_campaign_pilot.py` (généralisé le 23/09 pour accepter `--project-id`/`--cases`/
`--iterations` au lieu des 2 cas du projet 12 codés en dur à l'origine).

- **Projet 12** (staging cloud Sapian) : cas 127 et 128, 3 itérations chacun (rejeu du pilote
  connu, mêmes conditions qui avaient révélé 3 bugs corrigés avant ce lot).
- **Projet 1** (Odoo local, confirmé base de développement — pas une donnée réelle sensible) :
  8 cas distincts, 1 itération chacune (13, 95, 97, 99, 100, 101, 103, 126 — mélange de cas
  nominaux et négatifs, choisis pour exercer les deux branches du comptage cloisonné).

## Résultat pour le lot 01

**Validé en non-régression réelle.** Sur les 14 essais, aucun verdict faux imputable au
comptage cloisonné n'a été observé — chaque `conforme`/`non_conforme`/`donnee_invalide`/
`technical_error` a une cause identifiée, indépendante du mécanisme corrigé par le lot 01.
Le cas le plus direct (projet 12, cas 127, itération 2) montre le marqueur de tentative
(`step_fill_unique`) isoler exactement une création en 0,3 s, sans ambiguïté, sur une instance
partagée où la vérification indépendante (fenêtre `write_date`, non affinée par domaine) a
elle-même plafonné à 50 enregistrements touchés — confirmant que le comptage interne cloisonné
(`id > max_id`) reste correct même quand une mesure externe plus grossière ne l'est pas.

**Ce que cette campagne NE prouve PAS** : l'élimination du faux PASSED d'origine (F1 — un tiers
crée un enregistrement pendant qu'un scénario échoue réellement) exige qu'une création
concurrente survienne PENDANT un échec réel du scénario — un événement qui ne se produit
quasiment jamais spontanément dans une campagne de cette taille. Cette preuve reste apportée par
le test unitaire du lot (`tests/test_comptage_cloisonne.py::test_GARDE_…`), et le sera à nouveau,
en conditions réelles, par un scénario de création concurrente injectée à ajouter au corpus du
lot 04 (banc de mesure).

## Décompte (méthodologie I4 : `technical_error` compté à part des verdicts exploitables)

| | Essais | Exploitables (`execution_status=success`) | `technical_error` |
|---|---|---|---|
| Projet 12 (6 essais) | 6 | 3 (50 %) | 3 (50 %) — cas 128 ×3 |
| Projet 1 (8 essais) | 8 | 7 (87,5 %) | 1 (12,5 %) — cas 13 |
| **Total** | **14** | **10 (71,4 %)** | **4 (28,6 %)** |

Parmi les 10 essais exploitables : 3 `conforme`, 3 `non_conforme`, 4 `donnee_invalide`.

## Coût

14 essais, 1,54 $ au total (0,72 $ projet 12 + 0,83 $ projet 1), soit **≈ 0,11 $/essai** —
confortable au regard du plafond §9 (< 1 €/nouveau cas, génération + exécution + réparations).

## Cinq constats (1 déjà connu, 4 nouveaux) — jamais liés au lot 01

| # | Cas | Nature réelle | Effet sur le statut | Référence plan |
|---|---|---|---|---|
| 1 (connu) | 128 ×3 | Timeout de clic menu (`navigate_menu`) — cause : `discover_menus` capture le libellé anglais alors que la session tourne en français | `retest`/`technical_error` | Rattaché aux lots 07c (contexte navigateur figé, locale) et 08a (détection de version) — pas de nouveau lot |
| 2 (nouveau) | 13 | Produit halluciné (« PC Portable HP ») absent du catalogue réel | `technical_error` | C10 |
| 3 (nouveau) | 95 | `verifier_soumission_non_bloquee` se déclenche sur un clic de **navigation intermédiaire**, pas seulement sur une vraie soumission | Faux `donnee_invalide` : accuse le jeu de données à tort | F7 → lot 11 |
| 4 (nouveau) | 99, 101, 126 (3 essais sur 8, ~38 % du projet 1) | Masque de saisie sur `numero_facture1` transformant une valeur inventée par l'agent (« FAC-TEST-001 » → « 001 », « 1234567 7654321 » → « 1234567/7654321 ») | `donnee_invalide` répété, même cause racine que #2 (valeur non observée) | C10 → lot 12 |
| 5 (nouveau) | 97 | Assertion figée sur un texte de message deviné, différent du message réel affiché (refus bien réel) | Faux `failed`/`non_conforme` : l'application a bien refusé, c'est le test qui se trompe | F8 → lot 11 |

Les défauts #3 et #5 produisent des **statuts faux** (le principe le plus grave du chantier) et
passent donc avant le #4 malgré sa fréquence plus élevée — traités ensemble dans le lot 11. Les
défauts #2 et #4 partagent la même cause racine (une valeur écrite sans avoir été observée) et
sont traités ensemble dans le lot 12, sur le modèle du correctif many2one déjà fait.

Détail des essais et artefacts : `.local-preview/qualification/pilote-lot01-projet12-20260923/`
et `.local-preview/qualification/pilote-lot01-projet1-20260923/` (non versionnés).
