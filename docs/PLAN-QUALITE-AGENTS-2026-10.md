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
| D17 | Un step `@then` partagé qui ne peut constater (attente, navigation) compte-t-il comme assertion ? | **Non** : il est marqué `@non_assertif` ; `write_test_plan` ne le compte pas ; le runtime l'exempte de D16 **seulement s'il vient du socle** (jamais du fichier de steps généré, désigné au sous-processus par `TP_GENERATED_STEPS_FILE` : garantie structurelle) ; `write_steps_file` refuse en plus toute référence au mécanisme (`MECANISME_RESERVE`). Un test d'accord vérifie que l'ensemble des steps `@then` sans constat (AST) est EXACTEMENT l'ensemble des steps marqués | Q1 | ☑ confirmée par le porteur le 2026-10-08 |
| D19 | Une tolérance numérique par défaut (repli de 0,01 sans devise) peut-elle rester implicite ? | **Non** : la tolérance appliquée et sa source (devise / repli sans devise / repli devise illisible) figurent dans le message du constat | Q1 | ☑ instruite et appliquée le 2026-10-07 (`_tolerance_avec_source`, Odoo seul : aucune autre tolérance implicite trouvée dans le runtime) ; confirmée par le porteur le 2026-10-08 |
| D20 | Faut-il ACTIVER le mode strict, les `input_examples`, les descriptions V2 et la phrase « hypothèses non vérifiées » ? Et que doit contenir `Connector.rules()` (aujourd'hui `""` pour tous les connecteurs) ? | **Q3-a livre les trois interrupteurs ÉTEINTS** (`TESTPILOT_TOOLS_STRICT`, `TESTPILOT_TOOLS_DESCRIPTIONS_V2`, `TESTPILOT_PROMPT_HYPOTHESES`, `generation/interrupteurs.py`) : on n'allume rien avant d'avoir mesuré (banc Q2) et vérifié par UN appel réel que l'API accepte les schémas stricts. Le contenu de `rules()` du connecteur `web` est ÉCRIT le 2026-10-07 (`generation/regles_connecteur.py`, interrupteur `TESTPILOT_REGLES_CONNECTEUR`, ÉTEINT) : compte « principal » annoncé dès le premier compte, interdiction des appels HTTP directs dans un step, regarder la page d'arrivée après un envoi — chaque règle vient d'un défaut mesuré (campagne `base-1`), aucune ne nomme un client. `odoo` : aucune règle (aucun défaut mesuré). Aucune activation avant mesure du banc | Q3 | ☐ à confirmer (activation) |
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
| Q3 (règles du connecteur) | mesuré : campagne `base-3` (règles du connecteur allumées + step de comptage de l'oracle), 0 faux vert sur 21 (IC95 0–15,5 %), faux rouges 6/23 (base-2 : 9/24), pass@1 exécution 9/10 (8/10), pass^3 résultat 3/10 (2/10), coût 3,01 $ ; **échantillon trop petit pour conclure** (intervalles qui se recouvrent) ; code de sortie 3 : 1 génération sans coût consigné (« Connection error », mise en veille du poste). Activation de `TESTPILOT_REGLES_CONNECTEUR` : **pas encore décidée** | 2026-10-08 | `docs/mesures/banc-agents-2026-10-08-base-3.md` |
| Q4 (outils 1 et 2) | lecteur de nombres affichés et comparateur à tolérance déclarée livrés et revus ; **pas encore reliés à un step** | 2026-10-07 | |
| Q3 (reste : boucle pilotée par transcripts), Q4 (3 à 5), Q5 | à faire | | |

## 7. Constat du 2026-10-08 — « l'état résiduel » est une hypothèse RÉFUTÉE

Hypothèse écrite le 2026-10-08 (bilan base-2) : `panier_total_tva` échouerait 3 fois sur 3 parce que l'essai à blanc de la
génération passerait grâce à un état résiduel de l'application (panier déjà rempli par un essai précédent).

**Mesure** (`.local-preview/qualification/banc-agents-panier_total_tva-t1/…/generation/dry-run.behave.json`) : l'« essai à
blanc » de la génération est `behave --dry-run` (`execution/behave_runner.py` l.188) — il vérifie seulement que chaque step a une
définition ; les 14 steps sortent `untested`, **rien n'est exécuté**, donc aucun état résiduel n'est possible.

**Vraie cause** : un test généré n'est JAMAIS exécuté avant la relecture humaine (le gate est souverain, §4.3 de la décision
0014). L'agent ne peut pas découvrir qu'après « Ajouter » l'application change de page : ses outils lisent des pages, ils ne
soumettent rien. L'échec apparaît à la première exécution réelle, en `technical_error` (honnête : jamais un faux verdict). La
boucle de réparation (`repair_service`) est faite pour cela ; le banc ne mesure aujourd'hui que la PREMIÈRE génération.

**Conséquence** : ne pas exécuter pendant la génération (cela contournerait le gate humain et écrirait des données chez le
client). Mesurer plutôt « réussite après réparation » (D23 à proposer), et améliorer ce que l'agent peut vérifier sans rien soumettre.

## 8. Mesure « après UNE réparation » (D23, 2026-10-08)

Protocole : les 30 tests générés de la campagne `base-3` sont REJOUÉS (aucune nouvelle génération). Pour chaque test dont le jeu sur la
saine sort en `technical_error`, l'agent de réparation du produit reçoit l'échec observé (jamais un diagnostic) et propose UNE
correction ; la version réparée est rejouée sur toutes les variantes. Interrupteur des règles du connecteur : éteint (produit actuel).

| | Haiku 4.5 (défaut du produit) | Sonnet 4.6 |
|---|---|---|
| Tests à réparer | 5 | 5 |
| Corrections rejouables | 4 | 5 |
| Saine exécutable après réparation | **0** | **1** (`client_creation_nom_limite` essai 3) |
| Faux verts après réparation | 0 sur 21 | 0 sur 22 |
| Coût des réparations | 0,09 $ | 0,29 $ |

Lecture : échantillon de 5 — aucune conclusion statistique. Constats : (1) la réparation ne produit PAS de faux vert (le risque central :
« réparer » en supprimant ce qui vérifiait) ; (2) elle répare rarement (0/5, 1/5) ; (3) elle coûte très peu, il y a donc de la marge
pour la rendre plus utile ; (4) `panier_total_tva` (3 essais) n'est réparé par aucun modèle : le message d'échec ne dit pas sur quelle
page le navigateur se trouvait, l'agent accuse le sélecteur alors que la page a changé. Piste suivante, mesurable sur ces mêmes tests :
fournir à l'agent l'adresse de la page au moment de l'échec (fait mesuré par le navigateur, pas un texte de l'agent).
Rapports : `docs/mesures/banc-agents-2026-10-08-base-3-reparation.md` et `…-sonnet.md`.

Corrections de produit trouvées en chemin : le tarif de l'alias `claude-haiku-4-5` manquait (les réparations étaient comptées au tarif
Sonnet, environ 3,75 fois trop cher) ; la réservation de budget de qualification ne couvrait pas le modèle de réparation.

### Suite du §8 (2026-10-08) — causes trouvées, Sonnet par défaut, plusieurs tentatives

**Causes des échecs de `panier_total_tva`** (trois défauts INDÉPENDANTS en chaîne, vérifiés sur la vraie page) : (1) le code écrit
`"Quantite"` sans accent alors que l'application affiche « Quantité » ; (2) un champ ciblé par `aria-label` alors que l'application
utilise un `<label for>` (le ciblage par rôle + nom le trouve) ; (3) page supposée inchangée après un ajout. Le snapshot de page
fusionnait en plus nom accessible et texte affiché (un bouton « Ajouter » d'`aria-label` « Ajouter Clavier… » était visé par
`:has-text('Ajouter Clavier…')`) : corrigé (`texte` ajouté quand il diffère du nom). Ajout de l'adresse de la page au moment de
l'échec (sidecar, sans secret) : ne suffit pas seule (Haiku 0/5 avec adresse, 0/5 avec texte affiché).

**Protocole corrigé** : le produit autorise `REPAIR_BUDGET_DEFAULT` = 2 tentatives ; une seule tentative ne peut pas régler des défauts
en chaîne. Le banc rejoue maintenant 2 tentatives, chacune partant de l'échec de la version précédente.

**Modèle** : `MODEL_REPAIR` passe à Sonnet 4.6 par défaut (partagé avec l'agent de correction). Mesure Sonnet + 2 tentatives sur les 5
tests à réparer de `base-3` (rapport `…-sonnet-2tentatives`, cas `client_creation_nom_limite` essai 3 relancé après une panne de
crédits, rapport `…-nom-limite-reparation-sonnet`) :

| | Avant | Après (Sonnet, 2 tentatives) |
|---|---|---|
| Faux verts | 0/21 | 0/23 |
| Faux rouges | 6/23 | 7/26 |
| pass@1 exécution / résultat | 9/10 / 7/10 | 10/10 / 8/10 |
| pass^3 exécution / résultat | — / 3/10 | 7/10 / 4/10 |
| Tests réparés (saine conforme) | 0/5 | 2/5 ; exécutables 3/5 |
| Coût des réparations | — | 0,45 $ (9 tentatives) |

Constat à retenir : une réparation peut transformer une erreur technique en **faux rouge** (`commande_persistance_serveur` essai 2 : le
test réparé compare mal une ligne qui existe bien). Le verdict accuse alors l'application ; la relecture humaine reste le filet.
Incident : les crédits API se sont épuisés pendant une réparation ; le banc la comptait comme un échec de l'agent — corrigé (la
campagne s'arrête, comme pour la génération).

