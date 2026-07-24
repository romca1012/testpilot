# Brief Produit — Outil de Test Management piloté par IA (ERP / Odoo)

*Document de cadrage — référence pour l'implémentation. Aucune implémentation ne démarre sans validation de ce document.*

> **Ce document est la SEULE source de vérité du projet.** Toute note, tout principe, toute
> décision d'une session de travail qui le contredit est **caduc**. Une déviation proposée doit
> être **signalée comme telle et validée** avant implémentation — jamais actée en autonomie.

---

## Journal des amendements

*Le brief est la référence : il ne se modifie pas en silence. Tout amendement est tracé ici,
daté, avec sa raison.*

| date | § touchés | amendement | décidé par |
|---|---|---|---|
| 2026-07-17 | **§6, §9, §11.2** | **Le plafond « 50 €/mois » est retiré du périmètre produit.** Ce chiffre désignait le **budget de développement du porteur de projet**, pas une limite applicative à implémenter. Il avait été inscrit au brief par confusion entre les deux. **Le seul objectif de coût du produit est, et reste, celui du §9 : moins de 1 € par nouveau cas de test** (génération + exécution + rapport). | Porteur du projet |
| 2026-07-19 | **§4** | **Ajout d'une étape de confirmation de périmètre, en langage métier, avant toute génération.** L'agent ne doit plus enchaîner directement de la lecture de l'annuaire technique à la génération d'un cas de test. Une étape de confirmation explicite s'intercale, formulée en langage humain (pas un dump de schéma technique) — voir détail du principe au §4bis et au §8. | Porteur du projet |
| 2026-07-19 | **§6** | **Formalisation de l'étape de découverte (« annuaire »)** comme phase 1 du triptyque Découverte → Confirmation de périmètre → Génération. L'agent construit/consulte un annuaire structuré de l'application cible (routes, modèles, champs) avant de générer quoi que ce soit — ce n'était qu'une pratique implicite, elle devient une exigence du produit. | Porteur du projet |
| 2026-07-19 | **§6** | **Réutilisation obligatoire de la bibliothèque de steps partagée.** L'agent doit s'appuyer sur les steps existants de la bibliothèque (comptage, actions courantes, etc.) plutôt que d'inventer ses propres appels HTTP bruts pendant la génération — contrainte structurelle, pas une simple préférence de prompt. Constaté nécessaire après un premier e2e où l'agent avait réinventé un transport au lieu de réutiliser l'existant. | Porteur du projet |
| 2026-07-19 | **§5** | **Précision de la taxonomie de défauts** : distinguer explicitement *valeur d'option inexistante* (l'agent invente ou déforme une valeur de champ) de *champ introuvable* (le sélecteur/élément n'existe pas). Un timeout Playwright sur une valeur d'option absente ressemblait, avant cette précision, à un champ introuvable — ce qui orientait le diagnostic et la réparation vers la mauvaise cause et consommait du budget pour rien. | Porteur du projet |
| 2026-07-19 | **§6, §9** | **Calibrage réel du garde-fou de coût par cas.** Le plafond par tentative de réparation se réinitialise à chaque tentative : le coût plafond réel d'un cas n'est donc pas le plafond d'une seule tentative, mais ce plafond multiplié par le nombre de tentatives de réparation autorisées. Le mécanisme doit être revu pour plafonner le **coût cumulé par cas** (génération + toutes les réparations), pas seulement chaque tentative prise isolément — faute de quoi la cible du §9 (< 1 € par cas) n'est pas réellement garantie par le garde-fou existant. | Porteur du projet |
| 2026-07-19 | **§7** | **Principe de traçabilité non-destructive.** Aucune purge de données de test (cas, versions, exécutions) ne doit être une suppression sèche. Toute opération de nettoyage du référentiel est précédée d'une sauvegarde complète et récupérable. « Nettoyer » signifie *archiver puis repartir propre*, jamais *détruire*. | Porteur du projet |
| 2026-07-19 | **§2, §8** | **Rappel du public cible non-technique.** Les rôles QA / lead technique ne sont pas nécessairement des profils développeurs. Toute interaction visible par un utilisateur (confirmation de périmètre, rapports, choix de scénario de test) reste en langage métier — jamais un schéma de données brut, des noms de champs internes, ou une arborescence technique de l'annuaire. Le détail technique, s'il existe, est toujours secondaire et replié par défaut (mode dev, §5), jamais la première chose montrée. | Porteur du projet |
| 2026-07-21 | **§4.3, §5** | **La validation du MÉTIER à la création vaut relecture — plus de gate humain séparé sur le Gherkin.** Le §4.3 imposait une relecture humaine du test généré avant sa première exécution. Or le parcours en 2 passes fait déjà valider par l'humain le **métier** (intention) avant génération, et la saisie manuelle est elle-même une validation. Re-demander une approbation du Gherkin faisait doublon. Une version produite depuis un métier validé est donc **approuvée automatiquement** — mais **tracé** (reviewer `validation-metier`), jamais silencieux : on sait toujours d'où vient l'autorisation (même discipline que la provenance des coûts et des statuts). Le **smoke-check reste affiché** en points de vigilance (information), il ne disparaît pas — l'amendement retire le *geste d'approbation*, pas la *mise en garde technique*. Le budget de réparation quitte aussi le cas : il est géré au niveau du **Run** (un cas ne s'exécute pas seul). | Porteur du projet |
| 2026-07-24 | **§5, §11.4** | **Le garde-fou « un diagnostic *test à réparer* doit être confirmé par un humain » est RETIRÉ.** Il avait déjà quitté le produit (onglet Confirmations et décision `0013` supprimés) **sans passer par ce journal** — l'écart est régularisé ici, dans le sens du produit. Ce qui prend sa place traite la cause au lieu d'arbitrer une étiquette : la réparation automatique bornée par le gate (`0014`) et le 4ᵉ verdict `donnee_invalide`, qui empêche l'outil d'accuser l'application quand c'est la donnée du test qui était irrecevable. | Porteur du projet |
| 2026-07-24 | **§4.2** | **La spécification est un DOCUMENT, pas un formulaire structuré.** L'utilisateur colle un texte ou importe un fichier (`.txt`, `.md`, `.docx`). Le cadrage structuré n'a pas disparu, il s'est déplacé en aval : la **pause métier** fait valider titre / préconditions / étapes / résultat attendu avant génération. **Ajout au périmètre** : un **modèle (template) de spécification** proposé à l'utilisateur, pour qu'il sache quoi écrire et que la génération parte d'une matière régulière. | Porteur du projet |
| 2026-07-24 | **§4.5** | **Corps du texte aligné sur l'amendement du 2026-07-21.** Le §4 point 5 imposait encore une relecture humaine obligatoire avant première exécution, alors que le journal l'avait retirée : le brief se contredisait lui-même, et qui le lisait sans lire le journal appliquait l'ancienne règle. | Porteur du projet |
| 2026-07-24 | **§6, §11.2** | **Inversion intention / résolveur.** Le LLM produit une **intention** ; une couche **déterministe** la résout en actions en lisant l'annuaire mesuré. Sur le chemin nominal, l'agent **ne nomme plus** les champs ni leurs valeurs — il les nomme uniquement quand le champ visé **est le sujet du test** (scénario négatif) ou quand l'annuaire ne couvre pas le cas. La mitigation du §11.2 (« ne pas restreindre ce que l'agent a le droit d'écrire ») est **réécrite** : ce n'est plus une restriction de liberté, c'est l'interdiction de **deviner un fait déjà mesuré**. | Porteur du projet |
| 2026-07-24 | **§6** | **Ce que la découverte ne peut PAS voir, inscrit noir sur blanc.** Une règle de saisie appliquée en **JavaScript** est invisible à tout crawl statique (constaté en réel : un champ sans contrainte HTML refusé par le navigateur). Enrichir l'annuaire ne corrigera jamais ça — d'où la **détection à l'exécution**, nécessaire et non optionnelle. | Porteur du projet |
| 2026-07-24 | **§5, §9** | **Philosophie du verdict complétée** : 4ᵉ issue `donnee_invalide` ; doctrine du **refus silencieux** (l'outil n'accuse pas sans preuve) ; et objectif **« zéro verdict non concluant »**, avec ses six mécanismes et un indicateur mesuré au §9. | Porteur du projet |
| 2026-07-24 | **§7** | **Vocabulaire aligné sur le produit et sur TestRail** : l'« Exécution nommée » devient le **run** (campagne), contenu à terme dans un **plan**. Règle structurante inscrite : **un cas ne s'exécute pas seul** (l'exécution, et le budget de réparation, vivent dans le run). **Traçabilité étendue** : une exécution **conserve ses artefacts bruts** (sortie et journal du moteur), pour qu'un test qui passait reste consultable avec ce que la machine a réellement vu. | Porteur du projet |
| 2026-07-24 | **§8, §12** | **L'architecture multi-connecteurs se pose AU 2ᵉ connecteur, pas avant.** Avec une seule implémentation, toute interface serait une supposition ; le contrat de connecteur sortira de ce que le résolveur exige réellement. `connector_type` reste une étiquette jusque-là, et c'est assumé. | Porteur du projet |
| 2026-07-24 | **§2, §8, §12** | **Comptes, rôles et vue client externe sortent de la V1** (ils y étaient « essentiels »). La V1 est un outil **interne mono-utilisateur** — cohérent avec le §9, qui juge déjà l'adoption non pertinente à ce stade. Ils redeviennent **obligatoires avant tout déploiement client**, avec le chiffrement du secret de connexion. | Porteur du projet |
| 2026-07-24 | **§8, §12** | **Le périmètre élargi (gestion de projet type Jira, charge, sécurité, CI/CD) est repoussé en V2.** Le §8 signalait lui-même le risque de dilution de la promesse centrale ; il est tranché dans l'autre sens. La V1 se recentre sur : référentiel + génération + exécution + **verdict honnête**. Ce sont les **premiers non-goals V1** du projet. | Porteur du projet |
| 2026-07-24 | **§9** | **Les critères cessent d'être déclaratifs.** Coût : la **mesure réelle datée** est inscrite à côté de la cible. Temps : **instrumenté au banc** au lieu d'être supposé. Cas Odoo : le critère est rattaché au **tableau « modules à retester »**, sans lequel il n'est pas observable. Ajout : **taux de verdicts concluants**. | Porteur du projet |
| 2026-07-20 | **§1, §5** | **Un résultat peut être SAISI par un humain — à condition de dire qu'il l'est.** Les tests non automatisables (rendu visuel, mail reçu, comportement matériel) et la liaison d'un défaut exigent une saisie humaine. Un résultat porte donc une **provenance obligatoire** — *exécuté* ou *déclaré* — visuellement distincte, jamais confondues. Un cas dont le résultat est déclaré atteint l'état **« validé manuellement »**, distinct de « validé » (réservé à une exécution réelle). **Ce qui reste interdit** : qu'un statut déclaré soit indiscernable d'un statut exécuté. La promesse du §1 n'est pas « aucun humain ne saisit », c'est « **on sait toujours d'où vient un statut** » — même discipline que la provenance des coûts (`estimated` vs `anthropic_api`). | Porteur du projet |

---

## 1. Vision & promesse

**Vision.** Les équipes qui font évoluer des ERP (Odoo en premier lieu, modules natifs et custom) accumulent des tests fonctionnels écrits à la main dans TestRail. Le cycle de test complet pour valider les ajouts sur un ERP peut prendre plusieurs jours, et rien ne garantit qu'un test référencé a réellement été rejoué contre le code actuel. Cette faille a déjà eu un coût réel : un test connu, non rejoué faute de temps, a laissé passer un bug en production — coûtant un client. L'outil à construire supprime ce risque en rendant le coût de retest négligeable et en garantissant que le statut d'un test n'est jamais déclaratif.

**Promesse en une phrase.** *Un outil honnête qui dit ce qui est réellement couvert par les tests, et s'assure que rien ne casse après l'ajout d'une fonctionnalité — parce que le statut "testé" n'est jamais une case cochée, mais toujours la conséquence d'une exécution réelle, confirmée par l'IA.*

**Différenciation vs existant :**
- vs **TestRail** : pas de simple champ de statut modifiable par n'importe qui ; le statut est produit par l'exécution réelle et son interprétation par l'IA.
- vs **Playwright/Selenium** : ce n'est pas qu'un moteur d'exécution — c'est aussi un référentiel métier structuré, avec génération de tests à partir d'une spécification.
- vs **QA manuelle classique** : élimine le risque de faux-positif de couverture (un test "supposé bon" mais jamais rejoué).

---

## 2. Problème & utilisateurs

**Problème.** Plusieurs ERP/applications évoluent en continu (ajouts de fonctionnalités, amélioration de modules). Les tests sont écrits à la main, référencés dans TestRail, parfois transverses à plusieurs modules. Le cycle de test complet peut prendre plusieurs jours. Cas fondateur : sur Odoo, un test existait mais n'a pas été rejoué faute de temps → bug en production → perte d'un client.

**Pourquoi maintenant :** la croissance du périmètre (nombre d'ERP/modules à couvrir) dépasse la capacité humaine à tout retester manuellement à chaque changement, et les LLM sont désormais assez matures pour automatiser une partie significative de ce travail.

**Utilisateurs & rôles :**

| Rôle | Ce qu'il fait |
|---|---|
| QA / Consultant fonctionnel | Crée des tests (manuellement ou via génération IA à partir d'une spec), décide quoi tester à l'exécution (campagnes courantes) |
| Lead technique / Chef de projet | Décide quoi tester à l'exécution (orchestration de release), consulte le rapport, décide go/no-go |
| Admin | Accède en plus aux KPIs et coûts LLM (réservés à ce rôle) |
| Client externe (essentiel dès V1) | Vue finale simplifiée du rapport, compte dédié |
| Tous les rôles internes | Accès au rapport décisionnel (statuts exécution + fonctionnel) ; décision finale go/no-go ouverte à tous en interne |

> **⚠️ Amendement 2026-07-24 — ces rôles ne sont PAS de la V1.** La V1 est un outil **interne
> mono-utilisateur** : ni comptes, ni authentification, ni cloisonnement par rôle. Le tableau
> ci-dessus décrit la cible, pas la V1. **Ils redeviennent obligatoires avant le premier
> déploiement client**, en même temps que le chiffrement du secret de connexion — un outil sans
> comptes ne peut pas montrer un rapport à un client externe, ni réserver les coûts aux admins
> (§6), ni tester « un employé ne doit pas voir la page admin ».

> **⚠️ Amendement 2026-07-19 :** ces rôles (notamment QA / consultant fonctionnel) ne sont **pas
> présumés techniques**. Toute fonctionnalité qui leur est destinée (en particulier la
> confirmation de périmètre avant génération, §4bis) doit être conçue pour un utilisateur qui ne
> lit ni schéma de base de données, ni nom de route technique, ni structure d'annuaire brute.

---

## 3. Jobs to be done (priorisés)

### Essentiel

**JTBD 1 — Cycle standard de développement**
Dev ajoute une fonctionnalité sur branche dev → en staging, rejeu des tests du **module modifié + tests transverses** qui le concernent (pas l'ERP entier) → passage prod une fois la conformité confirmée → les retours clients terrain enrichissent la boucle a posteriori.

**JTBD 2 — Détection de régression transverse**
- *Détection automatique* : dès qu'une spec change ou qu'un nouveau cas de test est créé sur un module, celui-ci est marqué **« à retester »** sur un tableau de bord.
- *Décision de lancer manuelle* : QA ou lead technique choisit quand exécuter, en s'appuyant sur ce tableau de bord — élimine le risque d'oubli silencieux (cas Odoo).
- *(Évolution envisageable à terme : déclenchement 100 % automatique une fois l'outil mature — hors V1.)*

**JTBD 3 — Couverture rétroactive**
Formalisation de tests pour une fonctionnalité existante jamais testée, toujours à partir d'une **spécification complète** fournie par un humain (jamais d'exploration autonome sans cadrage documentaire pour ce cas précis).

### Souhaitable
- Déclenchement 100 % automatique des régressions transverses (V2+).

### Hors-scope
- ~~Aucun élément identifié comme totalement hors-scope à ce stade.~~ → **AMENDÉ le 2026-07-24 :
  la V1 a désormais des non-goals explicites — voir §8.** (Jira / charge / sécurité / CI-CD en V2 ;
  comptes et rôles hors V1 ; abstraction multi-connecteurs au 2ᵉ connecteur ; back-office de l'ERP
  hors périmètre du crawl.)

---

## 4. Parcours cible

1. **Connexion** avec identifiants → accès aux projets.
2. **Gestion des cas de tests** (onglet séparé de l'exécution) : l'utilisateur exprime un besoin via une **spécification** — un **document** qu'il colle ou importe (`.txt`, `.md`, `.docx`). La spec peut décrire une nouvelle fonctionnalité ou documenter une fonctionnalité déjà existante. *(Amendé le 2026-07-24 : ce point exigeait un « formulaire structuré, pas un champ libre ». Le document libre a été retenu — une spec existante s'importe, elle ne se ressaisit pas. **En contrepartie, l'outil fournit un modèle de spécification** que l'utilisateur remplit s'il part de zéro, et le cadrage structuré reste garanti en aval par la pause métier de l'étape 3.)*
3. **Découverte + confirmation de périmètre** *(nouvelle étape, voir §4bis)* : l'agent consulte l'annuaire technique de l'application, puis reformule en langage métier ce qu'il compte tester. L'utilisateur confirme ou corrige **avant** toute génération.
4. **Génération** : l'IA produit le cas de test (Gherkin + script), rangé dans le module concerné du référentiel.
5. **Relecture humaine** : **la validation du métier faite à l'étape 3 VAUT relecture** — le test généré depuis un métier validé est approuvé automatiquement, mais **tracé** (reviewer `validation-metier`), jamais en silence. Une relecture reste possible à tout moment, et les points de vigilance techniques (smoke-check) restent affichés. *(Amendé le 2026-07-24 : ce point imposait encore une relecture obligatoire avant première exécution, contredisant l'amendement du 2026-07-21 inscrit au journal — re-demander une approbation du Gherkin après avoir validé l'intention faisait doublon.)*
6. **Exécution** (onglet séparé) : sélection libre de cas de tests, mono ou multi-modules, regroupés dans un **run** (campagne) qui porte un nom et un but propres. **Un cas ne s'exécute pas seul** : l'exécution — et le budget de réparation — vivent dans le run.
7. **Rapport** :
   - exécution multi-modules → rapport attaché à **l'exécution nommée** ;
   - exécution mono-module → rapport attaché **au module**.

### 4bis. Le triptyque Découverte → Confirmation de périmètre → Génération *(ajouté 2026-07-19)*

Ce triptyque répond à un problème observé concrètement : sans lui, l'agent partait générer un cas de test sans qu'aucun humain n'ait confirmé le périmètre exact visé, produisant des cas qui ne correspondaient pas à l'intention réelle et consommaient du budget de réparation pour de mauvaises raisons.

1. **Découverte** — l'agent consulte l'annuaire structuré de l'application cible (routes, modèles, champs, contraintes) et la bibliothèque de steps partagée. Cette étape est **interne à l'agent**, jamais montrée telle quelle à l'utilisateur.
2. **Confirmation de périmètre** — avant d'écrire le moindre fichier de test, l'agent restitue en une ou deux phrases, **en langage métier**, ce qu'il compte tester (ex. *« Je vais tester : un employé remplit une demande de matériel et la soumet ; je vérifierai qu'elle apparaît dans la liste après validation. »*). L'utilisateur valide ou corrige. Pas de jargon technique, pas de nom de modèle Odoo brut, pas d'arborescence de l'annuaire affichée par défaut — un lien optionnel replié « voir le détail technique » peut exister pour qui veut creuser, jamais en premier plan.
3. **Génération** — seulement une fois l'étape 2 validée explicitement par l'utilisateur.

Cette étape concerne les rôles qui **créent** des cas de test (QA, consultant fonctionnel, lead technique) — pas le client externe, qui ne consulte que des rapports.

---

## 5. Invariants & philosophie du verdict

- **Deux statuts indépendants, toujours croisés dans le rapport :**
  - *Statut d'exécution* : le test a-t-il pu tourner techniquement (pas de crash / timeout / erreur d'environnement) ?
  - *Statut fonctionnel* : l'application s'est-elle comportée conformément au besoin documenté ?
- **QUATRE issues possibles, pas trois** *(ajouté le 2026-07-24)* :

  | Ce qui s'est passé | Issue |
  |---|---|
  | le test n'a pas pu tourner | **erreur technique** |
  | le test a tourné, l'application est conforme | **conforme** |
  | le test a tourné, l'application ne l'est pas | **non conforme** |
  | le test a tourné, ce sont **ses données** qui ont été refusées | **donnée du test invalide** |

  Sans la quatrième, une donnée mal formée fait dire à l'outil « votre application est cassée ».
  **C'est le pire mensonge possible pour un outil de test** — il détruit la confiance dans ses
  propres verdicts, y compris les justes. Mesuré en réel : un formulaire refusait silencieusement
  une valeur violant son motif, rien n'était créé, et l'outil concluait « non conforme » alors que
  l'application avait raison.
- **L'outil n'accuse jamais sans preuve** *(ajouté le 2026-07-24 — pendant de la ligne rouge)*.
  Un verdict « non conforme » n'est prononcé que si la soumission a **réellement eu lieu** et que la
  donnée a été **acceptée**. Quand l'application ne crée rien **et** n'affiche rien, l'outil nomme ce
  **refus silencieux** pour ce qu'il est — un trou d'observabilité de l'application, à instruire côté
  serveur — au lieu de le convertir en défaut. Un futur contributeur qui « améliorerait » ce verdict
  en le rendant affirmatif régresserait la promesse centrale du produit.
- **Validation d'un cas de test** = il a été joué en entier, sans interruption technique. Une fois validé, il n'est **plus régénéré**, sauf évolution de la fonctionnalité (dans ce cas, le Gherkin/script est **complété**, jamais reconstruit from scratch).
- **Diagnostic « test cassé » vs « vrai bug applicatif »** : effectué par l'IA via un prompt dédié, à partir des résultats constatés. ~~**Garde-fou asymétrique** : un diagnostic classant un échec comme *« test à réparer »* doit être **confirmé par un humain** avant classement définitif.~~
  > **⚠️ AMENDÉ le 2026-07-24 — ce garde-fou est RETIRÉ.** L'arbitrage humain des diagnostics
  > (écran de confirmations, décision `0013`) avait déjà quitté le produit sans amendement ; l'écart
  > est régularisé dans le sens du produit. **Ce qui le remplace traite la cause au lieu d'arbitrer
  > une étiquette** : la réparation automatique bornée par le gate (`0014`), et surtout le 4ᵉ verdict
  > ci-dessus, qui empêche le faux « non conforme » à la source. Un diagnostic « vrai bug » reste
  > remonté directement — l'asymétrie de risque, elle, n'a pas changé.
  > **⚠️ Amendement 2026-07-19 :** la taxonomie de défauts doit distinguer explicitement
  > *valeur d'option inexistante* (l'agent invente/déforme une valeur de champ, ex. un type de
  > demande qui n'existe pas dans les choix réels) de *champ introuvable* (le sélecteur/élément
  > n'existe pas dans la page). Ces deux causes produisaient auparavant la même signature
  > d'erreur (timeout Playwright), ce qui orientait la réparation vers la mauvaise cible et
  > consommait du budget sans traiter la vraie cause.
- **Ligne rouge absolue** : jamais de masquage d'un échec.
- **Deux modes d'affichage du même rapport** : mode *dev* (logs techniques, activité de l'IA en temps réel) et mode *utilisateur* (verdict textuel uniquement). *(⚠️ Non construit au 2026-07-24 : il n'existe qu'un seul affichage, qui montre du technique à un public que le §8 dit non technique. Rattaché à l'Incrément 2.)*

### 5bis. Objectif « zéro verdict non concluant » *(ajouté le 2026-07-24)*

**« Erreur technique » et « donnée du test invalide » sont des états TRANSITOIRES, pas des
verdicts.** Ils doivent déclencher une correction et un rejeu, et l'utilisateur ne doit lire, au
bout du compte, que *conforme* ou *non conforme* — ou, à défaut, un **« non concluant » explicité**,
jamais une accusation. Un verdict n'est prononcé que si sa **recevabilité est prouvée** : la
soumission est partie, la donnée a été acceptée, aucune erreur technique n'est survenue.

Les six mécanismes qui y mènent, dans l'ordre de rendement décroissant :

1. **Ce que l'application refuse devient une règle apprise.** Le refus est déjà capté (message du
   navigateur, champs en erreur renvoyés par le serveur) mais n'est pas réinjecté : chaque refus doit
   **enrichir l'annuaire du projet**, pour que le résolveur ne puisse plus jamais produire cette
   valeur. **C'est le seul moyen d'atteindre les règles écrites en JavaScript**, invisibles au crawl
   (§6). Conséquence : une même cause ne se reproduit pas, et le taux décroît à chaque exécution.
2. **Rejeu immédiat après correction**, dans le même run, borné par le budget de réparation existant.
   L'incident reste tracé, il cesse d'être le résultat.
3. **Préconditions montées par API/RPC, pas par l'interface.** L'interface ne pilote que le
   comportement réellement sous test. Un échec pendant la préparation n'est pas un résultat de test.
4. **Vérifier l'ÉTAT, jamais l'écran** : toute assertion de création/modification interroge
   l'enregistrement. Un libellé qui change ne doit pas produire un faux « non conforme ».
5. **Séparer l'instable du vrai défaut** : un échec isolé est rejoué ; s'il alterne, il est marqué
   instable et sort du verdict — pour une durée **bornée**, sinon on accumule des tests morts.
6. **Gate de recevabilité** : la règle générale dont le refus silencieux est le premier cas.

⚠️ **Zéro n'est pas promis** : les états dynamiques et les règles serveur non observables resteront.
Ce qui est promis : que chaque occurrence soit **expliquée**, **auto-corrigée à la fois suivante**, et
**jamais présentée comme un défaut de l'application**. La mesure associée est au §9.

---

## 6. Comportement de l'agent & maîtrise des coûts

- **Phase de découverte obligatoire avant génération** *(ajouté 2026-07-19)* : l'agent constitue ou consulte un **annuaire structuré** de l'application cible (routes, modèles de données, champs, valeurs possibles) avant toute génération de cas de test. Cet annuaire est construit une fois par connecteur/instance et réutilisé ensuite — il n'est pas reconstruit à chaque génération. Voir le triptyque complet au §4bis.
  > **⚠️ Ce que la découverte ne peut PAS voir *(ajouté le 2026-07-24)*.** L'annuaire relève ce que
  > la page **déclare** : rôles, libellés accessibles, noms techniques, types, options, contraintes
  > de saisie. Il ne verra **jamais** une règle appliquée en **JavaScript** — constaté en réel sur un
  > champ sans aucune contrainte HTML, que le navigateur refuse pourtant à l'exécution. **Aucun
  > enrichissement de l'annuaire ne corrigera ça** : c'est une limite de la méthode, pas de son
  > implémentation. Conséquence directe : *prévenir* ne peut pas être exhaustif, *détecter à
  > l'exécution* si — la détection au moment de l'exécution est donc **nécessaire, pas optionnelle**
  > (§5bis, mécanisme 1). Ne jamais promettre « l'agent connaît l'application » : il connaît ce
  > qu'elle a déclaré, à la date de la mesure.
- **Réutilisation obligatoire de la bibliothèque de steps partagée** *(ajouté 2026-07-19)* : l'agent s'appuie sur les steps existants (actions courantes, comptage, etc.) plutôt que d'inventer ses propres appels techniques bruts pendant la génération. C'est une contrainte structurelle imposée à l'agent, pas une simple recommandation de prompt.
- L'agent a le droit d'**explorer l'application par lui-même** (la spec est un cadre, pas une vérité absolue — des écarts existent, ex. casse des noms de champs, qui sont la cause racine des itérations de réparation constatées aujourd'hui).
- **Le LLM produit une INTENTION ; une couche DÉTERMINISTE la résout en actions** *(ajouté le
  2026-07-24)*. Sur le chemin nominal, l'agent n'écrit plus « je renseigne le champ X avec la valeur
  Y » : il écrit « je remplis le formulaire de *tel écran* avec des données valides », et le
  résolveur lit l'annuaire mesuré pour remplir **tous** les champs requis visibles avec des valeurs
  du bon type, conformes aux contraintes réelles, en choisissant de vraies options et en ignorant les
  champs cachés.
  - **Le LLM fournit le SENS, le déterministe garantit la FORME.**
  - L'agent **nomme** encore un champ dans deux cas, et deux seulement : quand ce champ **est le
    sujet du test** (scénario négatif : on lui donne délibérément une mauvaise valeur), et quand
    l'annuaire ne couvre pas la situation (état dynamique, assistant, modale).
  - **Pourquoi c'est structurel** : neuf causes d'échec successives relevaient du même motif —
    *l'annuaire savait, personne ne transmettait*. Chaque fait de l'application que le LLM ignorait
    devenait une panne, sur une surface **illimitée**. Après l'inversion, ce qui reste est « le
    modèle mesuré est incomplet ou périmé » : une surface **bornée, détectable, réparable**.
  - **Ce que ça a changé, mesuré** (banc du 2026-07-23) : le taux de réussite technique n'a **pas**
    bougé (88 %) — le gain est ailleurs, et il est décisif : **zéro fausse accusation par invention
    de champ**, et le 4ᵉ verdict qui se déclenche à la place.
- **Réparation automatique** des scripts en échec technique : invisible pour l'utilisateur, mais bornée par un **garde-fou combiné tentatives + budget** — le premier seuil atteint déclenche une escalade vers un humain avec un rapport de ce qui a été essayé (chiffres exacts à calibrer en implémentation).
  > **⚠️ Amendement 2026-07-19 — calibrage du garde-fou de coût.** Le plafond appliqué à chaque
  > tentative de réparation se réinitialise à chaque tentative : le coût plafond réel d'un cas de
  > test n'est donc pas ce plafond pris une fois, mais ce plafond **multiplié par le nombre de
  > tentatives de réparation autorisées**. Le garde-fou doit être revu pour plafonner le **coût
  > cumulé par cas** (génération + toutes les réparations confondues), afin de garantir
  > réellement la cible du §9 plutôt que de la mesurer après coup.
- **Suivi des coûts** : données réelles récupérées depuis le compte du fournisseur LLM (Anthropic) quand l'API l'expose ; calcul estimé en fallback sinon. Visible **uniquement par les admins**.
- ~~**Budget plafond global : 50 €/mois** pour l'ensemble de l'outil (génération + exécution + réparations cumulées).~~
  > **⚠️ AMENDÉ le 2026-07-17 — ce n'est PAS un garde-fou produit.**
  > **Le seul plafond de coût produit est le critère du §9 : moins de 1 € par nouveau cas de test.**
  > Le chiffre de 50 €/mois a pu apparaître dans des échanges de cadrage, mais il désigne le
  > **budget de développement du porteur de projet** — pas une limite applicative. Aucun code ne
  > l'implémente, et aucun ne doit l'implémenter : il n'y a **pas** de plafond mensuel produit à
  > brancher, à mesurer ou à faire respecter par l'outil.
  > *(Conséquence : `config.MONTHLY_BUDGET_EUR/_USD` existe mais n'est lu par personne. C'est
  > normal et voulu — non pertinent au produit. Ne pas construire dessus.)*

---

## 7. Modèle conceptuel des données (niveau métier)

**Hiérarchie du référentiel :** Projet → Module/Fonctionnalité → **Spécification** → Cas de test.
*(La Spécification — le document d'origine — a été intercalée le 2026-07-19 : une spec engendre
plusieurs cas, un par angle testé. Elle porte le document et son empreinte, ce qui permet de savoir
qu'un cas est né d'une spec depuis modifiée.)*

**Cas de test — socle commun :**
- Identifiant + titre
- Description / spec d'origine
- Module propriétaire (un seul, même si réutilisé ailleurs)
- Étapes attendues (Gherkin)
- Origine (généré IA / créé manuellement puis converti)
- Statut de validation (jamais exécuté / validé / à réviser)
- Dernier statut d'exécution + dernier statut fonctionnel
- Date de dernière exécution
- Auteur
- Version courante + lien vers l'historique

**Cas de test — champs spécifiques au connecteur (extensible) :**
- Type de connecteur/ERP ciblé
- Paramètres techniques d'environnement propres au connecteur

**Concept transverse — le RUN (campagne), anciennement « Exécution nommée » :** regroupement libre
de cas de tests issus de modules différents, indépendant de la hiérarchie de rangement ; il a un nom
et un but propres, se lance explicitement, et se clôture (lecture seule, réversible). À terme, un
**plan** regroupe plusieurs runs.

> **⚠️ Amendement 2026-07-24 — vocabulaire et règle d'exécution.** Le produit et la vision TestRail
> disent **run / plan** ; le brief disait « exécution nommée ». Un seul vocabulaire désormais, celui
> du produit. Et la règle qui va avec : **un cas ne s'exécute pas seul** — l'exécution vit dans un
> run, le budget de réparation aussi. Un cas isolé n'a ni but, ni périmètre, ni budget.

**Traçabilité :** double logique d'**historisation** (delta lisible entre versions de cas de test et des fichiers d'exécution correspondants) et d'**archivage** (gestion du stockage long terme, réutilisation possible).

> **⚠️ Amendement 2026-07-24 — une exécution conserve ses artefacts bruts.** Un test qui passait
> doit rester **consultable** des mois plus tard, **associé aux fichiers de son exécution** : non
> seulement le Gherkin et le script de la version exactement jouée (déjà versionnés), mais la
> **sortie brute du moteur d'exécution** (journal, résultat structuré, captures si disponibles),
> conservée sur disque et référencée en base. Sans elle, on ne peut relire que ce que la base a bien
> voulu résumer — pas ce que la machine a réellement vu.

> **⚠️ Amendement 2026-07-19 — principe de traçabilité non-destructive.** Aucune purge de
> données de test (cas, versions, exécutions) ne doit être une suppression sèche. Toute opération
> de nettoyage du référentiel — y compris un « repartir propre » légitime — est précédée d'une
> **sauvegarde complète et récupérable** de ce qui est retiré. « Nettoyer » signifie *archiver
> puis repartir propre*, jamais *détruire sans filet*. Ce principe s'applique aussi bien aux
> opérations manuelles du porteur de projet qu'à tout mécanisme automatique futur.

---

## 8. Périmètre & non-goals

**V1 — inclus :**
- Connecteur **Odoo** (modules natifs + custom). ~~avec une architecture multi-connecteurs posée dès le départ~~ → **AMENDÉ le 2026-07-24 : l'architecture multi-connecteurs se pose AU 2ᵉ connecteur, pas avant.** Avec une seule implémentation réelle, toute interface serait une supposition ; le contrat de connecteur doit sortir de ce que le résolveur **exige** face à un deuxième ERP, pas d'une prévision. Jusque-là, le type de connecteur reste une **étiquette** et l'implémentation Odoo est câblée — c'est assumé, et documenté pour qu'on ne le prenne pas pour un oubli.
- Référentiel de cas de tests + génération IA + exécution automatisée + statuts croisés + garde-fous de coût.
- ~~Compte client externe (vue simplifiée) — essentiel dès la V1, pas repoussé.~~ → **AMENDÉ le 2026-07-24 : hors V1.** Comptes, rôles et vue client externe sortent du périmètre V1 (voir §2). La V1 est un outil **interne mono-utilisateur**. **Ils redeviennent obligatoires avant le premier déploiement client**, avec le chiffrement du secret de connexion.
- Séparation stricte, y compris visuelle et UX, entre l'onglet **Gestion des cas de tests** et l'onglet **Exécution**.
- Interface **responsive, pensée par un UI/UX designer**, qui sort du générique « app générée par IA ».
- ~~**Éléments additionnels validés pour la V1** : 1. Gestion de projet type Jira · 2. Tests de charge/performance · 3. Tests de sécurité · 4. Intégration CI/CD~~
  > **⚠️ AMENDÉ le 2026-07-24 — ces quatre chantiers sont REPOUSSÉS EN V2.** Le risque de dilution
  > que ce paragraphe signalait lui-même est tranché dans l'autre sens : **la V1 se recentre sur la
  > promesse centrale** — référentiel + génération + exécution + **verdict honnête**. L'ordre de
  > priorité est conservé pour la V2 (Jira, charge, sécurité, CI/CD).

> **⚠️ Amendement 2026-07-19 — public non-technique.** L'interface (et en particulier l'étape de
> confirmation de périmètre du §4bis) doit être conçue pour un utilisateur qui n'est pas
> nécessairement développeur. Concrètement : jamais de schéma de données brut, de nom de route
> technique, ou d'arborescence d'annuaire affichés en premier plan. Le détail technique reste
> disponible pour qui le cherche (mode dev, §5) mais n'est jamais la première chose montrée.

~~**⚠️ Risque assumé et documenté** : ce périmètre V1 élargi augmente fortement la complexité et le délai, et dilue potentiellement la promesse centrale.~~ → **Le 2026-07-24, ce risque a été résolu plutôt qu'assumé** : le périmètre élargi est sorti de la V1.

**Non-goals explicites de la V1** *(les premiers du projet, arrêtés le 2026-07-24 — le cadrage
d'origine n'en déclarait aucun)* :

- gestion de projet type Jira, tests de charge, tests de sécurité, intégration CI/CD → **V2** ;
- comptes, rôles et vue client externe → **hors V1**, obligatoires avant tout déploiement client ;
- abstraction multi-connecteurs → **au 2ᵉ connecteur** ;
- back-office de l'ERP (`/web`, `/odoo` chez Odoo) → **hors périmètre du crawl** : l'y étendre serait
  un autre produit.

---

## 9. Critères de succès mesurables

| Critère | Cible |
|---|---|
| Temps — nouveau cas de test (spec → Gherkin/script validé → exécution → rapport) | < 5 minutes — **à instrumenter au banc** *(2026-07-24 : ce critère n'a jamais été mesuré ; un critère de succès jamais mesuré est exactement le « statut déclaratif » que ce produit combat chez les autres. Le banc chronomètre déjà chaque étape sans le restituer.)* |
| Temps — cas de test déjà existant et validé | seule l'exécution compte, temps encore inférieur |
| **Coût — nouveau cas de test (génération + exécution + rapport)** | **< 1 €** — ⚠️ **l'UNIQUE cible de coût du produit**, sans exception. C'est elle qu'on mesure et qu'on calibre. Elle couvre **les réparations cumulées** du cas. Voir amendement §6 sur le calibrage réel du garde-fou nécessaire pour la garantir.<br>📏 **Dernière mesure réelle : ~0,08 à 0,11 $ par cas** (banc du 2026-07-23, modèle Sonnet 4.6) — soit un facteur 10 de marge. La cible reste à 1 € : c'est un **plafond**, pas une prévision. *(Un essai de bascule vers Sonnet 5 a été mesuré puis **annulé** : coût ×2 et qualité en baisse sur notre prompt. Changer de modèle suppose de re-mesurer, jamais de supposer.)* |
| ~~Budget global mensuel~~ | ~~≤ 50 €/mois, tous usages confondus~~ → **AMENDÉ le 2026-07-17 : retiré.** Budget de **développement du porteur**, pas un critère produit. Voir §6 et le journal des amendements. |
| **Verdicts concluants** (conforme + non conforme) rapportés à l'ensemble des cas d'une campagne | **à faire tendre vers 100 %** — *ajouté le 2026-07-24, §5bis.* Mesure le contraire des erreurs techniques et des données invalides : la capacité de l'outil à **trancher**. À afficher au banc à côté du taux technique et du coût. |
| Fiabilité — cas « Odoo » (module à retester non traité avant mise en prod) | zéro occurrence sur une période donnée — ⚠️ **non observable tant que le tableau de bord « modules à retester » (§3, JTBD 2) n'existe pas.** Le constat se fait en production, pas dans l'outil : le critère mesurable côté outil est *« aucun module marqué à retester au moment du go prod »*. |
| Fiabilité — faux-négatifs découverts a posteriori (test classé « à réparer » mais vrai bug) | tendre vers zéro |
| Adoption | non pertinent à ce stade (outil interne, phase de dev) |

---

## 10. Contraintes & actifs réutilisables

- **Actif existant** : prototype de génération Gherkin + script Python (behave) piloté par IA — organisation actuelle jugée insuffisante (architecture de fichiers trop complexe, nommage peu clair). À trancher précisément (quoi garder / reconstruire) une fois ce brief validé.
- **Exigence de qualité technique** : nommage clair, regroupement logique des fichiers, respect d'un coding style, facilité de compréhension et d'usage.
- **LLM retenu** : Claude/Anthropic (choix déjà éprouvé).
- **Environnement de test** : instance Odoo locale neutralisée (copie de la prod), lancée via docker-compose.
- **Délai** : pas de délai réaliste identifié pour le périmètre complet. Un **premier incrément « preuve de concept » en 2 jours** est visé : un seul module Odoo, un cas de test généré de bout en bout (spec → Gherkin/script → exécution → rapport), sans les briques élargies (PM, charge, sécurité, CI/CD).

---

## 11. Risques & questions ouvertes

1. **Périmètre V1 très large** (cœur + gestion de projet + charge + sécurité + CI/CD) → risque de dilution de la promesse centrale et d'allongement du délai, malgré la volonté d'aller vite. *Risque assumé.*
2. **Coût de génération multi-connecteur** : itérations de réparation dues aux écarts spec/réalité (ex. casse des champs) → **risque de dépasser la cible de moins de 1 € par cas (§9)** si le garde-fou tentatives + budget par cas n'est pas bien calibré. *(Amendé le 2026-07-17 : ce risque visait « le budget de 50 €/mois » — chiffre retiré du périmètre produit, cf. §6. Le risque lui-même est **inchangé et intact**, seule sa cible est renommée : c'est le §9 qu'une réparation mal bornée fait sauter.)* *(Précisé le 2026-07-19 : le mécanisme actuel de plafond par tentative, qui se réinitialise à chaque tentative, ne garantit pas cette cible — voir amendement §6.)*
   **Mitigation, réécrite le 2026-07-24** : *bien calibrer le garde-fou tentatives + budget au niveau
   du coût cumulé par cas* — **et empêcher l'agent de DEVINER un fait déjà mesuré** (§6, inversion
   intention/résolveur). ~~Pas restreindre ce que l'agent a le droit d'écrire.~~ L'ancienne rédaction
   interdisait précisément ce qui s'est avéré être le correctif : neuf causes d'échec successives
   venaient toutes de champs et de valeurs **inventés** par le LLM alors que l'annuaire les
   connaissait. Ce n'est pas une restriction de son exploration — elle reste entière — c'est le
   retrait d'une charge qu'il n'a aucun moyen d'assumer sans risque.
3. **Dépendance à l'API de coûts réels d'Anthropic** : si elle n'est pas assez granulaire, le suivi budgétaire retombe sur une estimation moins fiable.
4. ~~**Garde-fou anti faux-négatif** (validation humaine obligatoire sur les diagnostics « test à réparer ») repose sur la discipline humaine à valider réellement.~~
   > **⚠️ CADUC le 2026-07-24** — le garde-fou lui-même est retiré (§5). **Le risque, lui, subsiste
   > sous une autre forme** : un échec classé « test à réparer » à tort masque un vrai défaut, et plus
   > personne ne relit. Ce qui le contient désormais : le 4ᵉ verdict (qui distingue *notre donnée est
   > mauvaise* de *l'application est en faute*), la doctrine « jamais d'accusation sans preuve », et
   > l'objectif de verdicts concluants du §5bis — des mécanismes vérifiables, là où la relecture
   > humaine reposait sur une discipline.
5. **Confusion possible entre l'annuaire technique et l'interface utilisateur** *(ajouté 2026-07-19)* : le risque existe que l'étape de confirmation de périmètre (§4bis) glisse vers un affichage technique par facilité d'implémentation. Point de vigilance explicite pour la relecture de toute maquette de cette étape.

*Aucune question ouverte supplémentaire identifiée par le porteur du projet à la clôture de ce cadrage.*

---

## 12. Découpage suggéré en incréments livrables

**Incrément 0 — Preuve de concept (visé : ~2 jours)**
Un seul module Odoo. Cas de test unique généré de bout en bout : spec → Gherkin/script (IA) → relecture humaine obligatoire → exécution → rapport (statuts exécution + fonctionnel). Pas de gestion de projet, pas de charge/sécurité/CI-CD, pas de multi-rôles avancés.

**Incrément 1 — Cœur du référentiel & exécution**
Structure complète Projet → Module → **Spécification** → Cas de test (socle commun + champs connecteur). Séparation UX Gestion/Exécution. **Runs** transverses multi-modules. Historisation + archivage, **artefacts bruts d'exécution conservés**. ~~Rôles et permissions (QA, lead technique, admin, client externe).~~ → **déplacés hors V1 le 2026-07-24** (§2, §8) : à traiter dans un incrément « Ouverture aux utilisateurs », **prérequis à tout déploiement client**, avec le chiffrement du secret de connexion.

**Incrément 2 — Fiabilisation & gouvernance du verdict**
~~Garde-fou de validation humaine sur les diagnostics « à réparer »~~ *(retiré le 2026-07-24, §5)* → à la place : les **six mécanismes du « zéro verdict non concluant »** (§5bis). Mode dev/utilisateur. **Provenance d'un résultat — exécuté vs déclaré — et statut « validé manuellement »** (amendement du 2026-07-20, écrit mais jamais construit). Tableau de bord des modules « à retester » (détection automatique). Garde-fous tentatives + budget par cas de test (recalibrés au coût cumulé, §6). Suivi des coûts réels (Anthropic) + fallback estimation, visible admins uniquement. **Triptyque Découverte → Confirmation de périmètre → Génération** (§4bis) et réutilisation de la bibliothèque de steps partagée (§6).

**Incrément 3 — Élargissement du périmètre validé — ⚠️ REPORTÉ EN V2 le 2026-07-24**
Dans l'ordre de priorité fixé, conservé : (1) gestion de projet type Jira, (2) tests de charge/performance, (3) tests de sécurité, (4) intégration CI/CD. **Ne fait plus partie de la V1** (§8).

**Incrément 4 — Extension multi-connecteurs**
Ouverture de l'architecture à un second ERP. ~~en s'appuyant sur les fondations posées dès la V1~~ →
**c'est ici que l'abstraction se conçoit** (§8, amendement du 2026-07-24), pas avant : le contrat de
connecteur s'extrait de ce que le résolveur exige face à un ERP réellement différent. Prévoir aussi,
à ce moment-là, la **construction de l'annuaire du nouveau connecteur** et l'adaptation de
l'explorateur — c'est le seul travail non gratuit, fait une fois par connecteur.