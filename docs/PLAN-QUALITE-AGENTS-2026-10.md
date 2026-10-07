# Plan — Qualité des agents et des vérifications (Q1-Q5)

Date : 2026-10-07. Statut : **en cours — Q1 démarré**. Sources de vérité :
`docs/SOURCES-DE-REFERENCE-AGENTS.md` (documentation officielle et recherches), puis les documents
habituels (`docs/PRINCIPES.md`, `docs/CONTINUITE.md` §4, `docs/PLAN-FIABILITE-VERDICT-2026-09.md`
dont ce plan **prolonge** le registre des décisions : D16 et suivantes).
Exécution : un lot = une branche = des commits atomiques ; aucune fusion sans accord du porteur.

## 1. Objectif

Monter, **de façon mesurée**, la garantie qu'offre TestPilot : (1) un test généré s'exécute sans
erreur technique dès la première génération ; (2) un `conforme` prouve réellement ce qui était
demandé ; (3) une valeur calculée par l'application est comparée à une **référence indépendante** ;
(4) les agents s'améliorent par la mesure, pas par l'intuition. Les agents orchestrent des **outils
fiables** ; la garantie vient des outils (déterministes, testés, falsifiables).

## 2. Constat de départ (mesuré le 2026-10-07)

| Constat | Mesure | Où |
|---|---|---|
| Un scénario est `conforme` dès **un seul** constat réussi sous un `Alors` (D3) ; un `Alors` qui ne constate rien n'est vu que s'il n'y en a aucun dans tout le scénario | lu dans `verdict/status.py` l.188-197 | Q1 |
| Steps `@then`/`@step` de la bibliothèque partagée qui ne peuvent consigner aucun constat | **1 sur 35** : `j'attends la soumission du formulaire` (inventaire AST, `generic/_generic_steps.py`) | Q1 |
| `write_test_plan` compte ce step comme une assertion (`assertion |= effective == 'then'`) | lu dans `technical_plan.py` | Q1 |
| Aucun outil ni mode `strict`, aucun `input_examples` sur les outils de l'agent | grep `generation/tools/__init__.py` : 0 occurrence | Q3 |
| Clôture « ce dont je ne suis pas sûr » jamais produite : le dry-run vert met fin à la boucle | `react_loop.py` l.138-140 | Q3 |
| `Connector.rules()` n'est surchargée par aucun connecteur : le bloc `<regles_connecteur>` du prompt est vide | `grep "def rules" connectors/` | Q3 |
| Aucun calcul de référence indépendant de la valeur attendue | cartographie de la génération (2026-10-07) | Q4, Q5 |

## 3. Lots

| Lot | Objet | Décisions | Dépend de |
|---|---|---|---|
| **Q1** | Honnêteté du verdict : preuve par `Alors`, steps non assertifs, tolérances explicites | D16, D17, D19 | — |
| Q2 | Banc d'agents : défauts injectés, jeu équilibré, pass@1 / pass^k, faux verts | D18 | Q1 |
| Q3 | Durcissement des outils existants : mode strict, exemples, descriptions, boucle pilotée par transcripts ; hypothèses non vérifiées structurées ; règles du connecteur | D20 | Q2 |
| Q4 | Nouveaux outils de vérification : lecture normalisée, comparateur à tolérance déclarée, valeurs limites, couverture des exigences, agent critique de plan | D21 | Q2, Q3 |
| Q5 | Atelier de calcul : recherche sourcée, calculateur testé, contre-vérification, fiche signée ; calibrage sur la France | D22 | Q4 |

Règle commune (SOURCES §4) : **mesurer après avoir rendu le verdict honnête** — Q2 ne démarre pas
tant que Q1 n'est pas fusionné.

## 4. Registre des décisions (prolonge celui de `PLAN-FIABILITE-VERDICT-2026-09.md` §4)

| ID | Question | Proposition | Lot | Statut |
|---|---|---|---|---|
| D16 | Un scénario vert où **un `Alors` assertif ne consigne aucun constat réussi** (alors qu'un autre en a consigné) peut-il rester `conforme` ? | **Non** : `indetermine`, cause DÉDIÉE `alors_sans_constat` (libellé « Un résultat attendu n'a rien vérifié » ; `cause_category` est un texte en base, aucune migration) — la cause `aucun_constat` (« aucune vérification exécutée ») serait fausse quand un autre `Alors` a constaté (revue du 2026-10-07). Le compteur ne compte que les constats RÉUSSIS ; si le contrôle est impossible, une ligne `controle_impossible` est consignée et le verdict reste prudent. Prolonge D3 (« un vert sans constat n'est jamais conforme ») du scénario à chaque `Alors`. Un step déclaré **non assertif** (D17) est exempté | Q1 | ☐ à confirmer par le porteur — **instruction du 2026-10-07 : « commence par l'étape 1 »** après lecture des recommandations ; confirmation explicite requise avant fusion |
| D17 | Un step `@then` partagé qui ne peut constater (attente, navigation) compte-t-il comme assertion ? | **Non** : il est marqué `@non_assertif` ; `write_test_plan` ne le compte pas ; le runtime l'exempte de D16 **seulement s'il vient du socle** (jamais du fichier de steps généré, désigné au sous-processus par `TP_GENERATED_STEPS_FILE` : garantie structurelle) ; `write_steps_file` refuse en plus toute référence au mécanisme (`MECANISME_RESERVE`). Un test d'accord vérifie que l'ensemble des steps `@then` sans constat (AST) est EXACTEMENT l'ensemble des steps marqués | Q1 | ☐ à confirmer (idem D16) |
| D19 | Une tolérance numérique par défaut (repli de 0,01 sans devise) peut-elle rester implicite ? | **Non** : la tolérance appliquée et sa source (explicite / devise / repli) figurent dans le message du constat | Q1 | ☐ à confirmer — **à instruire d'abord** (voir §5) |
| D18-D22 | Banc, outils, atelier de calcul | à rédiger au démarrage de chaque lot | Q2-Q5 | ☐ |

## 5. Q1 — périmètre et critères d'acceptation

**Hors périmètre** (consigné, pas oublié) : exception dédiée aux constats (`ConstatEchoue`) et
reclassement d'un `AssertionError` non instrumenté — à instruire d'abord par mesure (combien de
`AssertionError` hors `constater` sous un `Alors` ?) ; relecture d'un champ après remplissage ;
tolérance numérique si l'instruction (D19) montre un risque réel.

Livrables :
1. `SharedStep.asserte` (calculé par AST, source unique de vérité : le code) et `@non_assertif`
   sur `j'attends la soumission du formulaire`.
2. `write_test_plan` : une `Alors` ne compte comme assertion que si le step partagé apparié est
   assertif ; refus au message clair sinon.
3. Runtime : compteur de constats par step ; un `Alors` assertif passé sans constat est consigné
   (`sans_constat`) ; le verdict le lit (D16).
4. Tests de falsifiabilité pour chacun, test d'accord AST ↔ marqueurs, suite complète sans nouvelle
   régression (les 5 échecs Windows antérieurs sont connus et listés).

Critères d'acceptation :
- [ ] un scénario avec 1 `Alors` assertif réussi + 1 `Alors` sans constat n'est plus `conforme`
- [ ] un scénario dont le seul `Alors` est « j'attends la soumission… » est refusé à l'écriture
- [ ] le step « j'attends… » après un `Alors` n'abaisse pas un verdict par ailleurs prouvé
- [ ] aucun changement de verdict sur le corpus de tests existant hors des cas visés (suite verte)
- [ ] revue `verdict-reviewer` faite, points bloquants traités

## 6. Suivi

| Lot | Statut | Date | Rapport |
|---|---|---|---|
| Q1 | en cours | 2026-10-07 | |
| Q2 (a, b, d) | statistiques (Q2-a), application locale à défauts (Q2-b) et orchestrateur `scripts/banc_agents.py` (Q2-d) livrés, **jamais lancés en réel** (coût LLM : accord du porteur requis) | 2026-10-07 | |
| Q3-Q5 | à faire | | |
