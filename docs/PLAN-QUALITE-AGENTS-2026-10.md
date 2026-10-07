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
| D19 | Une tolérance numérique par défaut (repli de 0,01 sans devise) peut-elle rester implicite ? | **Non** : la tolérance appliquée et sa source (devise / repli sans devise / repli devise illisible) figurent dans le message du constat | Q1 | ☑ instruite et appliquée le 2026-10-07 (`_tolerance_avec_source`, Odoo seul : aucune autre tolérance implicite trouvée dans le runtime) ; **à confirmer par le porteur** |
| D20 | Faut-il ACTIVER le mode strict, les `input_examples`, les descriptions V2 et la phrase « hypothèses non vérifiées » ? Et que doit contenir `Connector.rules()` (aujourd'hui `""` pour tous les connecteurs) ? | **Q3-a livre les trois interrupteurs ÉTEINTS** (`TESTPILOT_TOOLS_STRICT`, `TESTPILOT_TOOLS_DESCRIPTIONS_V2`, `TESTPILOT_PROMPT_HYPOTHESES`, `generation/interrupteurs.py`) : on n'allume rien avant d'avoir mesuré (banc Q2) et vérifié par UN appel réel que l'API accepte les schémas stricts. Le contenu de `rules()` n'est PAS écrit : inventaire dans le rapport Q3-a, décision du porteur | Q3 | ☐ à confirmer |
| D18 | Le banc a-t-il des attendus écrits par un humain AVANT le run, jamais modifiés après ? | **Oui** : `specs/banc_local/attendus.yaml`, relu par le porteur le 2026-10-07 ; l'orchestrateur refuse les clés YAML dupliquées | Q2 | ☑ confirmée le 2026-10-07 |
| D21 | Quels outils de vérification ajouter, et à quel niveau ? | **Proposition** (à mesurer avant d'activer) : (1) *lecture normalisée* d'une valeur affichée (« 1 234,50 € » → nombre + devise), pure et testée ; (2) *comparateur à tolérance déclarée* : la tolérance et sa source figurent dans le constat (D19), jamais un repli muet ; (3) *valeurs limites* générées de façon déterministe depuis les bornes de la spec (40/41 caractères…) ; (4) *couverture des exigences* : chaque critère de la spec doit être relié à ≥ 1 `Alors` assertif, sinon le plan est refusé ; (5) *agent critique de plan* en lecture seule, qui ne peut QUE refuser un plan avec motif (il n'écrit jamais un verdict). Chaque outil derrière un interrupteur éteint, mesuré par le banc (faux verts, pass^k, coût) avant activation | Q4 | ☐ à confirmer — **le porteur a demandé de suivre les recommandations (2026-10-07)** : démarrage par (1)+(2) car purs et sans appel LLM |
| D22 | Atelier de calcul (valeurs de référence indépendantes) : quel périmètre ? | **Proposition** : une *fiche de calcul* signée (sources citées, formule, jeux d'essai, date de validité) produite par une recherche sourcée puis relue par un humain avant tout usage ; un *calculateur* testé (jamais un calcul écrit par l'agent au vol) ; une *contre-vérification* par un second calcul indépendant ; calibrage d'abord sur la France (Publicodes / mon-entreprise, API URSSAF), jamais sur un pays dont l'oracle est « expérimental » (OpenFisca-Sénégal). Aucune valeur calculée par un LLM n'est une attendue sans fiche signée | Q5 | ☐ à confirmer |

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
| Q1 | code et tests terminés, revue indépendante faite et ses points corrigés ; suite complète verte (2026-10-07) ; D16 confirmée par le porteur le 2026-10-07 (**D17/D19 à confirmer**) | 2026-10-07 | |
| Q2 (a, b, d) | statistiques, application locale à défauts, orchestrateur livrés ; D18 : `attendus.yaml` relu par le porteur le 2026-10-07 ; campagne `base-1` faite (22 résultats sur 57 non concluants, cause principale : oracle non déclaré par le banc, corrigé) ; campagne `base-2` en cours | 2026-10-07 | `docs/mesures/banc-agents-2026-10-07-base-1.md` |
| Q3-a | outils existants durcis, **tout derrière des interrupteurs éteints** (strict + `input_examples`, descriptions V2, champ `hypotheses_non_verifiees` + phrase du PILIER 4) ; défaut octet pour octet identique (témoin figé) ; **rien d'activé, aucun appel réel fait** : l'API accepte-t-elle ces schémas en strict ? à confirmer par un appel réel peu coûteux (accord du porteur : oui, 2026-10-07) ; `rules()` des connecteurs : inventaire seul, décision D20 | 2026-10-07 | rapport Q3-a (conversation) |
| Q3 (reste : boucle pilotée par transcripts, règles du connecteur), Q4, Q5 | à faire | | |
