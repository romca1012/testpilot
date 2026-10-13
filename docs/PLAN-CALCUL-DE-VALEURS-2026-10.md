# Plan — Calcul des valeurs attendues (CV-01 à CV-07)

Date : 2026-10-13. Statut : **remplacé** le 2026-10-13 par `PLAN-PARAMETRES-DE-TEST-2026-10.md` (CV-01 y devient PT-03, le
calcul des valeurs PT-06). Conservé pour l'historique : la vision de départ, et au §6.1 la première revue du lot.
Prolonge `PLAN-QUALITE-AGENTS-2026-10.md` (Q4, Q5) et le lot 8 de `PLAN-VERDICT-HONNETE-ZERO-ERREUR-2026-10.md`.
Les restes des autres chantiers sont consignés dans `SUITE-2026-10-12-RESTES-ET-CALCUL-DE-VALEURS.md`.

## 1. Le problème

Aujourd'hui la valeur attendue d'un test vient de la spécification : elle y est écrite, ou l'agent la calcule lui-même à
partir de la règle écrite. Dans ce second cas rien ne vérifie son calcul, et **aucune mesure n'existe** : dans les deux cas
de montants du banc, le résultat (129,51 € ; 10,56 €) est écrit dans la spec.

## 2. La vision (porteur, 2026-10-12)

Un système **générique**, réglable **par projet**, qui ne se fie plus à la spécification pour la valeur attendue :

1. **Valeurs de départ** : des jeux de valeurs nommés, dans les paramètres de test du projet.
2. **Règles de calcul** : nommées, déclarées par le projet (taux, tranches, plafonds, arrondis), validées par une personne.
3. **Avant le test**, un programme applique les règles aux valeurs de départ : valeurs attendues et détail ligne par ligne.
4. **Pendant le test**, l'outil saisit les mêmes valeurs de départ et lit ce que l'application affiche.
5. **À la fin**, il compare chaque valeur obtenue à la valeur calculée, devise comprise, et montre l'écart.

Valeurs utilisées ET valeurs attendues sont connues avant l'exécution. Rien n'est propre à un projet.

### 2.1 Correction du porteur (2026-10-13) : GLOBAL, pas « par projet »

Une première maquette présentait des paramètres de test rangés dans un projet et illustrés par la paie. Refusée : « c'est
propre à ce projet, et c'est exactement ce que j'essaye d'éviter ». Les paramètres de test sont une **bibliothèque commune à
tout TestPilot** (règles de calcul, jeux de valeurs, unités), que n'importe quel projet utilise. Un projet n'apporte que le
**branchement** : sa monnaie et son écriture des nombres, les règles qu'il choisit, et l'endroit où chaque valeur se trouve
sur ses écrans. Une règle ne cite jamais un projet ni un écran. Maquette de référence :
`reports/parametres-de-test-maquette-2026-10-13.pdf` (8 pages). **Partout ci-dessous, « paramètres de test du projet » se lit
à travers ce découpage** ; D39 et le lot CV-03 sont à réécrire en conséquence quand le porteur aura validé la maquette.
Ne jamais illustrer ce chantier par un client ou un métier unique.

### 2.2 Élargissement demandé (2026-10-13) : les paramètres de test ne sont pas que des valeurs calculées

Le porteur, sur la maquette refaite : « tu caricatures toujours ces paramètres en prenant en compte l'idée des valeurs
calculées ; essaye de voir plus loin ». Recherche faite sur des outils comparables (TestRail, Xray, Azure Test Plans, Qase,
qTest, Katalon, Tosca, mabl, testRigor, Postman, Playwright). Constats communs : la logique du test est séparée de ses
données ; les réglages s'héritent par niveaux et le plus proche l'emporte ; l'environnement est distinct des données ; les
identifiants sont une catégorie à part, chiffrée ; un jeu de données se joue ligne par ligne ; les paramètres partagés entre
projets existent (Qase, Azure). **Cadre proposé, NON validé** — six familles : où (environnements), qui (comptes et rôles),
avec quoi (variables, jeux de données, données générées), dans quel état (état de départ), ce qu'on attend (valeur écrite,
calculée par règle, lue côté serveur ; unités), comment (réglages d'exécution) ; quatre niveaux : bibliothèque commune →
projet → campagne → test. Le calcul d'une valeur attendue (le reste de ce plan) n'est qu'une des façons de fournir « ce
qu'on attend ». Ce plan est à renommer et à restructurer si le porteur valide ce cadre.

## 3. Garanties

- L'agent n'écrit **jamais** le chiffre attendu : il désigne un résultat par son nom (même garantie que les comptes, D8, et
  les requêtes d'oracle nommées, D7).
- Une règle n'est **jamais** déduite de ce que l'application affiche.
- Une règle doit **retrouver des cas de référence** fournis par le projet avant d'être utilisable.
- Le calcul est un programme pur, en `Decimal`, sans LLM : coût nul par cas (§9 du brief).
- Une marge d'écart ne vient jamais du texte du test : seulement d'une règle déclarée par le projet.

## 4. Registre des décisions (prolonge D16-D38)

| ID | Question | Décision | Lot | Statut |
|---|---|---|---|---|
| D21 (points 1, 2) | Lecture normalisée d'un montant affiché et comparateur | Branchés sur un step, derrière un interrupteur éteint | CV-01 | ☑ validée par le porteur le 2026-10-13 |
| D39 | D'où vient la valeur attendue d'un calcul ? | Des **paramètres de test du projet** (valeurs de départ + règles), calculée par un programme avant le test ; plus de la spécification | CV-02 à CV-04 | ☑ validée le 2026-10-13 |
| D40 | Forme d'une règle | Une **suite d'étapes simples**, lisible et corrigeable par quelqu'un qui n'est pas développeur (pourcentage, arrondi, plafond, barème par tranches, condition) ; pas un programme écrit par l'agent | CV-02 | ☑ validée le 2026-10-13 |
| D41 | Moment du calcul | **À chaque exécution**, avec la règle validée en vigueur : un taux corrigé à un seul endroit vaut pour tous les tests | CV-04 | ☑ validée le 2026-10-13 |
| D42 | Règle pas encore validée par une personne | **Aucun verdict** : les deux montants sont affichés avec « à vérifier » ; ni `conforme` ni `non_conforme` | CV-03, CV-04 | ☑ validée le 2026-10-13 |
| D43 | Devise (demande du porteur, 2026-10-13 : « elle varie d'un pays à un autre ; comprendre la valeur trouvée et dans quel contexte ») | Un montant se compare **avec sa devise**. Devise différente : défaut. Devise attendue mais **non affichée à côté de la valeur** : ni succès ni défaut (`indetermine`). Notation partagée (« $ », « F CFA ») : compatible avec chacune de ses monnaies, et le message le dit. Le projet déclarera sa devise et son écriture des nombres (CV-03) pour lever ces ambiguïtés | CV-01, CV-03 | ☐ appliquée dans CV-01, **à confirmer** |
| D44 | Vérification des taux (demande du porteur, 2026-10-13 : « confirmer que c'est le bon et qu'il est à jour ») | **Proposition** : chaque taux porte sa source, sa date d'effet et sa date de dernière vérification ; un taux périmé ou jamais vérifié est signalé avant l'exécution ; une vérification assistée compare le taux à sa source officielle et **signale** un écart, sans jamais modifier le taux elle-même | CV-03 | ☐ à confirmer (modalités à présenter avant CV-03) |

## 5. Lots

| Lot | Objet | Dépend de | LLM |
|---|---|---|---|
| **CV-01** | Step « le montant affiché pour … vaut … » : lecture en nombre, devise, comparaison exacte | D21 | non |
| CV-02 | Moteur de calcul pur (étapes simples, détail ligne par ligne), testé sur les règles de la boutique du banc | D40 | non |
| CV-03 | Paramètres de test du projet : jeux de valeurs, règles, cas de référence, validation, devise et écriture des nombres, suivi des taux (schéma : les quatre pièces de CLAUDE.md §6 ; écran) | D42, D43, D44 | non |
| CV-04 | Steps « utiliser un jeu de valeurs » et « comparer au résultat calculé » ; refus à l'écriture d'un nom inconnu | CV-01 à CV-03 | non |
| CV-05 | Mesure sur le banc : specs sans résultat écrit, défauts injectés, comparaison avec base-7 | CV-04 | oui (budget à annoncer) |
| CV-06 | Détail du calcul montré à la relecture et dans le résultat | CV-03 | non |
| CV-07 | Premier pays d'un projet réel : règles et cas de référence fournis par le projet | entrées du projet | oui |

Plus tard : plusieurs jeux de valeurs pour un même test, import des règles depuis Excel, aide de l'agent à la rédaction d'une
règle (jamais à sa validation), tolérance déclarée par la règle (arrondi de la devise).

Mis de côté (la vision rend ces points inutiles tant que les règles viennent du projet) : recherche de la législation par
l'agent, calibrage sur la France, second calcul indépendant. Hors sujet ici, restent dans les restes de génération :
couverture des exigences, agent critique de plan (D21 points 4 et 5).

## 6. CV-01 — périmètre et critères d'acceptation

Livrables : lecteur de devises élargi (codes ISO 4217 en circulation, symboles, notations partagées) ; comparaison à trois
issues (`egal`, `different`, `unite_non_verifiable`) ; step générique `Alors le montant affiché pour "<libellé>" vaut
"<montant>"` ; interrupteur `TESTPILOT_STEP_MONTANT` (éteint : le prompt de l'agent est inchangé).

- [ ] le même montant écrit autrement (« 129.51 EUR » pour « 129,51 € ») est reconnu
- [ ] un centime d'écart, une autre devise, un taux à la place d'un montant : `non_conforme`
- [ ] la devise attendue non affichée à côté de la valeur : `indetermine`, jamais `conforme`
- [ ] un montant attendu illisible : erreur du test, jamais un vert ni un défaut
- [ ] interrupteur éteint : ce que l'agent reçoit est identique à avant le lot
- [ ] suite complète sans nouvelle régression ; revue `verdict-reviewer` faite, points bloquants traités

Hors périmètre de CV-01 : une tolérance (elle viendra d'une règle, CV-02/CV-03) ; l'écriture ambiguë « 1,234 » (elle se
lèvera avec l'écriture des nombres déclarée par le projet, CV-03) ; la devise affichée ailleurs que près de la valeur
(en-tête de colonne) ; l'activation de l'interrupteur (après mesure sur le banc).

### 6.1 État au 2026-10-13 — lot SUSPENDU à la demande du porteur

Le porteur présente d'abord la vision à son manager (`reports/parametres-de-test-maquette-2026-10-13.pdf`). Rien n'est
commité. À reprendre dans cet ordre :

1. **Généralisation demandée le 2026-10-13** : une valeur n'est pas toujours une somme d'argent. Le step devient
   « le nombre affiché pour "<libellé>" vaut "<valeur>" » ; chaque valeur lue porte un nombre, une unité et une NATURE
   (monnaie, pourcentage, masse, durée, longueur, surface, volume, énergie, vitesse… ou unité inconnue gardée telle quelle) ;
   conversion seulement quand un rapport exact existe (1,5 kg = 1500 g ; jamais entre monnaies, ni mois/années, ni °C/°F).
   Prototype essayé hors dépôt (24 comparaisons conformes à l'attendu), **pas encore intégré**. Le projet déclarera ses
   propres unités (CV-03). Non traités : dates, durées en plusieurs morceaux (« 1 h 30 »), intervalles.
2. **Première revue `verdict-reviewer` (2026-10-13) : aucun bloquant, six points à corriger** avant d'allumer l'interrupteur :
   - D43 appliquée sans être validée, et muette sur « attendu sans unité, écran avec unité » ;
   - ce cas passe aujourd'hui (« 129,51 $ » à l'écran contre un attendu « 129,51 ») sans aucune trace : à trancher par le
     porteur — (a) ne pas conclure, ou (b) réussir avec un signal de confiance réduite consigné par sidecar ;
   - une devise ou un « % » AU MILIEU des chiffres est remplacé par une espace lue comme séparateur de milliers
     (« 5€300 » lu 5300 €) : n'accepter l'unité qu'à une extrémité ;
   - « (20 %) » lu −20 % : la convention comptable ne vaut pas pour un taux ;
   - `NombreLu` construit à la main peut être incohérent (`devise` sans `devises`) ;
   - registre fermé des steps derrière un interrupteur, pour que le décor adapté de `tests/test_steps_reuse.py` ne laisse
     pas un step disparaître du prompt sans qu'un test rougisse.
   Remarques à mesurer sur le banc : un suffixe (« HT », « /mois ») rend le constat non concluant ; table des notations
   partagées incomplète (« FC » : CDF seul) ; codes ISO qui sont aussi des mots (« TOP 10 ») ; le message d'un succès
   n'est consigné nulle part ; `scripts/preflight.py` ne liste pas `_lecture_nombre.py`.
3. **Suite complète du 2026-10-13 sur l'état non commité : 20 échecs, 4 236 réussis.** 1 échec connu du poste Windows
   (`test_bibliotheque_par_connecteur`, profil Sapian) ; **19 régressions causées par ce lot**, une seule cause :
   `ModuleNotFoundError: No module named '_lecture_nombre'`. `_base_helpers.py` est importé de deux façons — à plat dans le
   sous-processus Behave, et comme module du paquet `behave_runtime.steps_library` par des tests, des scripts et les steps
   de garde (`test_transport_*`, `test_field_resolution`, `test_migration_lot06_profil_instance`). Le nouvel import à plat
   `from _lecture_nombre import …` casse la seconde. À corriger en premier à la reprise (import valable dans les deux cas),
   puis relancer la suite complète. Non corrigé tant que le lot est suspendu.
4. Deuxième revue après corrections et généralisation, suite complète, puis mesure sur le banc (budget à annoncer).

## 7. Suivi

| Lot | Statut | Date | Rapport |
|---|---|---|---|
| CV-01 | écrit, non commité, **suspendu** (présentation de la vision au manager) ; première revue faite, six points à corriger, généralisation aux unités à intégrer — voir §6.1 | 2026-10-13 | |
| CV-02 à CV-07 | à faire | | |
