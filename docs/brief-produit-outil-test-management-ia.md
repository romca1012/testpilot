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
- Aucun élément identifié comme totalement hors-scope à ce stade (voir §7 sur le périmètre élargi assumé).

---

## 4. Parcours cible

1. **Connexion** avec identifiants → accès aux projets.
2. **Gestion des cas de tests** (onglet séparé de l'exécution) : l'utilisateur exprime un besoin via une **spécification guidée** (formulaire structuré, pas un champ libre) — la spec peut décrire une nouvelle fonctionnalité ou documenter une fonctionnalité déjà existante.
3. **Découverte + confirmation de périmètre** *(nouvelle étape, voir §4bis)* : l'agent consulte l'annuaire technique de l'application, puis reformule en langage métier ce qu'il compte tester. L'utilisateur confirme ou corrige **avant** toute génération.
4. **Génération** : l'IA produit le cas de test (Gherkin + script), rangé dans le module concerné du référentiel.
5. **Relecture humaine** : **obligatoire avant la toute première exécution** d'un test généré par l'IA (garde-fou qualité) ; facultative ensuite, à tout moment.
6. **Exécution** (onglet séparé) : sélection libre de cas de tests, mono ou multi-modules, regroupement en une exécution nommée avec un but propre.
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
- **Validation d'un cas de test** = il a été joué en entier, sans interruption technique. Une fois validé, il n'est **plus régénéré**, sauf évolution de la fonctionnalité (dans ce cas, le Gherkin/script est **complété**, jamais reconstruit from scratch).
- **Diagnostic « test cassé » vs « vrai bug applicatif »** : effectué par l'IA via un prompt dédié, à partir des résultats constatés. **Garde-fou asymétrique** : un diagnostic classant un échec comme *« test à réparer »* (non-bloquant) doit être **confirmé par un humain** avant classement définitif ; un diagnostic classant un échec comme *« vrai bug »* peut être remonté directement (le risque d'un faux positif est acceptable, celui d'un faux négatif ne l'est pas).
  > **⚠️ Amendement 2026-07-19 :** la taxonomie de défauts doit distinguer explicitement
  > *valeur d'option inexistante* (l'agent invente/déforme une valeur de champ, ex. un type de
  > demande qui n'existe pas dans les choix réels) de *champ introuvable* (le sélecteur/élément
  > n'existe pas dans la page). Ces deux causes produisaient auparavant la même signature
  > d'erreur (timeout Playwright), ce qui orientait la réparation vers la mauvaise cible et
  > consommait du budget sans traiter la vraie cause.
- **Ligne rouge absolue** : jamais de masquage d'un échec.
- **Deux modes d'affichage du même rapport** : mode *dev* (logs techniques, activité de l'IA en temps réel) et mode *utilisateur* (verdict textuel uniquement).

---

## 6. Comportement de l'agent & maîtrise des coûts

- **Phase de découverte obligatoire avant génération** *(ajouté 2026-07-19)* : l'agent constitue ou consulte un **annuaire structuré** de l'application cible (routes, modèles de données, champs, valeurs possibles) avant toute génération de cas de test. Cet annuaire est construit une fois par connecteur/instance et réutilisé ensuite — il n'est pas reconstruit à chaque génération. Voir le triptyque complet au §4bis.
- **Réutilisation obligatoire de la bibliothèque de steps partagée** *(ajouté 2026-07-19)* : l'agent s'appuie sur les steps existants (actions courantes, comptage, etc.) plutôt que d'inventer ses propres appels techniques bruts pendant la génération. C'est une contrainte structurelle imposée à l'agent, pas une simple recommandation de prompt.
- L'agent a le droit d'**explorer l'application par lui-même** (la spec est un cadre, pas une vérité absolue — des écarts existent, ex. casse des noms de champs, qui sont la cause racine des itérations de réparation constatées aujourd'hui).
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

**Hiérarchie du référentiel :** Projet → Module/Fonctionnalité → Cas de test.

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

**Concept transverse — Exécution nommée (« Test Suite » ad hoc) :** regroupement libre de cas de tests issus de modules différents, indépendant de la hiérarchie de rangement ; a un nom et un but propres.

**Traçabilité :** double logique d'**historisation** (delta lisible entre versions de cas de test et des fichiers d'exécution correspondants) et d'**archivage** (gestion du stockage long terme, réutilisation possible).

> **⚠️ Amendement 2026-07-19 — principe de traçabilité non-destructive.** Aucune purge de
> données de test (cas, versions, exécutions) ne doit être une suppression sèche. Toute opération
> de nettoyage du référentiel — y compris un « repartir propre » légitime — est précédée d'une
> **sauvegarde complète et récupérable** de ce qui est retiré. « Nettoyer » signifie *archiver
> puis repartir propre*, jamais *détruire sans filet*. Ce principe s'applique aussi bien aux
> opérations manuelles du porteur de projet qu'à tout mécanisme automatique futur.

---

## 8. Périmètre & non-goals

**V1 — inclus :**
- Connecteur **Odoo** (modules natifs + custom), avec une **architecture multi-connecteurs** posée dès le départ.
- Référentiel de cas de tests + génération IA + exécution automatisée + statuts croisés + garde-fous de coût.
- Compte client externe (vue simplifiée) — essentiel dès la V1, pas repoussé.
- Séparation stricte, y compris visuelle et UX, entre l'onglet **Gestion des cas de tests** et l'onglet **Exécution**.
- Interface **responsive, pensée par un UI/UX designer**, qui sort du générique « app générée par IA ».
- **Éléments additionnels validés pour la V1**, par ordre de priorité de livraison au sein des incréments suivants (voir §11) :
  1. Gestion de projet type Jira
  2. Tests de charge/performance
  3. Tests de sécurité
  4. Intégration CI/CD

> **⚠️ Amendement 2026-07-19 — public non-technique.** L'interface (et en particulier l'étape de
> confirmation de périmètre du §4bis) doit être conçue pour un utilisateur qui n'est pas
> nécessairement développeur. Concrètement : jamais de schéma de données brut, de nom de route
> technique, ou d'arborescence d'annuaire affichés en premier plan. Le détail technique reste
> disponible pour qui le cherche (mode dev, §5) mais n'est jamais la première chose montrée.

**⚠️ Risque assumé et documenté** : ce périmètre V1 élargi (au-delà du cœur référentiel + exécution + IA) augmente fortement la complexité et le délai, et dilue potentiellement la promesse centrale au milieu de fonctionnalités sans lien direct avec elle. Décision prise et assumée par le porteur du projet.

**Non-goals explicites :** aucun à ce stade — tous les éléments évoqués pendant le cadrage ont été inclus au périmètre, avec priorisation de livraison (voir découpage en incréments).

---

## 9. Critères de succès mesurables

| Critère | Cible |
|---|---|
| Temps — nouveau cas de test (spec → Gherkin/script validé → exécution → rapport) | < 5 minutes |
| Temps — cas de test déjà existant et validé | seule l'exécution compte, temps encore inférieur |
| **Coût — nouveau cas de test (génération + exécution + rapport)** | **< 1 €** — ⚠️ **l'UNIQUE cible de coût du produit**, sans exception. C'est elle qu'on mesure et qu'on calibre. Elle couvre **les réparations cumulées** du cas. Voir amendement §6 sur le calibrage réel du garde-fou nécessaire pour la garantir. |
| ~~Budget global mensuel~~ | ~~≤ 50 €/mois, tous usages confondus~~ → **AMENDÉ le 2026-07-17 : retiré.** Budget de **développement du porteur**, pas un critère produit. Voir §6 et le journal des amendements. |
| Fiabilité — cas « Odoo » (module à retester non traité avant mise en prod) | zéro occurrence sur une période donnée |
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
   **La mitigation reste celle-ci et pas une autre** : *bien calibrer le garde-fou tentatives + budget, désormais au niveau du coût cumulé par cas*. **Pas** restreindre ce que l'agent a le droit d'écrire — le §6 lui accorde l'exploration, c'est une décision prise.
3. **Dépendance à l'API de coûts réels d'Anthropic** : si elle n'est pas assez granulaire, le suivi budgétaire retombe sur une estimation moins fiable.
4. **Garde-fou anti faux-négatif** (validation humaine obligatoire sur les diagnostics « test à réparer ») repose sur la discipline humaine à valider réellement — un humain qui valide sans vérifier recrée le risque qu'on veut éliminer.
5. **Confusion possible entre l'annuaire technique et l'interface utilisateur** *(ajouté 2026-07-19)* : le risque existe que l'étape de confirmation de périmètre (§4bis) glisse vers un affichage technique par facilité d'implémentation. Point de vigilance explicite pour la relecture de toute maquette de cette étape.

*Aucune question ouverte supplémentaire identifiée par le porteur du projet à la clôture de ce cadrage.*

---

## 12. Découpage suggéré en incréments livrables

**Incrément 0 — Preuve de concept (visé : ~2 jours)**
Un seul module Odoo. Cas de test unique généré de bout en bout : spec → Gherkin/script (IA) → relecture humaine obligatoire → exécution → rapport (statuts exécution + fonctionnel). Pas de gestion de projet, pas de charge/sécurité/CI-CD, pas de multi-rôles avancés.

**Incrément 1 — Cœur du référentiel & exécution**
Structure complète Projet → Module → Cas de test (socle commun + champs connecteur). Séparation UX Gestion/Exécution. Exécutions nommées transverses multi-modules. Historisation + archivage. Rôles et permissions (QA, lead technique, admin, client externe).

**Incrément 2 — Fiabilisation & gouvernance du verdict**
Garde-fou de validation humaine sur les diagnostics « à réparer ». Mode dev/utilisateur. Tableau de bord des modules « à retester » (détection automatique). Garde-fous tentatives + budget par cas de test (recalibrés au coût cumulé, §6). Suivi des coûts réels (Anthropic) + fallback estimation, visible admins uniquement. **Triptyque Découverte → Confirmation de périmètre → Génération** (§4bis) et réutilisation de la bibliothèque de steps partagée (§6).

**Incrément 3 — Élargissement du périmètre validé**
Dans l'ordre de priorité fixé : (1) gestion de projet type Jira, (2) tests de charge/performance, (3) tests de sécurité, (4) intégration CI/CD.

**Incrément 4 — Extension multi-connecteurs**
Ouverture de l'architecture à un second ERP, en s'appuyant sur les fondations posées dès la V1.