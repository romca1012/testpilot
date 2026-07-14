# Brief Produit — Outil de Test Management piloté par IA (ERP / Odoo)

*Document de cadrage — référence pour l'implémentation. Aucune implémentation ne démarre sans validation de ce document.*

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
3. **Génération** : l'IA produit le cas de test (Gherkin + script), rangé dans le module concerné du référentiel.
4. **Relecture humaine** : **obligatoire avant la toute première exécution** d'un test généré par l'IA (garde-fou qualité) ; facultative ensuite, à tout moment.
5. **Exécution** (onglet séparé) : sélection libre de cas de tests, mono ou multi-modules, regroupement en une exécution nommée avec un but propre.
6. **Rapport** :
   - exécution multi-modules → rapport attaché à **l'exécution nommée** ;
   - exécution mono-module → rapport attaché **au module**.

---

## 5. Invariants & philosophie du verdict

- **Deux statuts indépendants, toujours croisés dans le rapport :**
  - *Statut d'exécution* : le test a-t-il pu tourner techniquement (pas de crash / timeout / erreur d'environnement) ?
  - *Statut fonctionnel* : l'application s'est-elle comportée conformément au besoin documenté ?
- **Validation d'un cas de test** = il a été joué en entier, sans interruption technique. Une fois validé, il n'est **plus régénéré**, sauf évolution de la fonctionnalité (dans ce cas, le Gherkin/script est **complété**, jamais reconstruit from scratch).
- **Diagnostic « test cassé » vs « vrai bug applicatif »** : effectué par l'IA via un prompt dédié, à partir des résultats constatés. **Garde-fou asymétrique** : un diagnostic classant un échec comme *« test à réparer »* (non-bloquant) doit être **confirmé par un humain** avant classement définitif ; un diagnostic classant un échec comme *« vrai bug »* peut être remonté directement (le risque d'un faux positif est acceptable, celui d'un faux négatif ne l'est pas).
- **Ligne rouge absolue** : jamais de masquage d'un échec.
- **Deux modes d'affichage du même rapport** : mode *dev* (logs techniques, activité de l'IA en temps réel) et mode *utilisateur* (verdict textuel uniquement).

---

## 6. Comportement de l'agent & maîtrise des coûts

- L'agent a le droit d'**explorer l'application par lui-même** (la spec est un cadre, pas une vérité absolue — des écarts existent, ex. casse des noms de champs, qui sont la cause racine des itérations de réparation constatées aujourd'hui).
- **Réparation automatique** des scripts en échec technique : invisible pour l'utilisateur, mais bornée par un **garde-fou combiné tentatives + budget** — le premier seuil atteint déclenche une escalade vers un humain avec un rapport de ce qui a été essayé (chiffres exacts à calibrer en implémentation).
- **Suivi des coûts** : données réelles récupérées depuis le compte du fournisseur LLM (Anthropic) quand l'API l'expose ; calcul estimé en fallback sinon. Visible **uniquement par les admins**.
- **Budget plafond global : 50 €/mois** pour l'ensemble de l'outil (génération + exécution + réparations cumulées).

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

**⚠️ Risque assumé et documenté** : ce périmètre V1 élargi (au-delà du cœur référentiel + exécution + IA) augmente fortement la complexité et le délai, et dilue potentiellement la promesse centrale au milieu de fonctionnalités sans lien direct avec elle. Décision prise et assumée par le porteur du projet.

**Non-goals explicites :** aucun à ce stade — tous les éléments évoqués pendant le cadrage ont été inclus au périmètre, avec priorisation de livraison (voir découpage en incréments).

---

## 9. Critères de succès mesurables

| Critère | Cible |
|---|---|
| Temps — nouveau cas de test (spec → Gherkin/script validé → exécution → rapport) | < 5 minutes |
| Temps — cas de test déjà existant et validé | seule l'exécution compte, temps encore inférieur |
| Coût — nouveau cas de test (génération + exécution + rapport) | < 1 € |
| Budget global mensuel | ≤ 50 €/mois, tous usages confondus |
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
2. **Coût de génération multi-connecteur** : itérations de réparation dues aux écarts spec/réalité (ex. casse des champs) → risque de dépasser le budget de 50 €/mois si le garde-fou tentatives + budget par cas n'est pas bien calibré.
3. **Dépendance à l'API de coûts réels d'Anthropic** : si elle n'est pas assez granulaire, le suivi budgétaire retombe sur une estimation moins fiable.
4. **Garde-fou anti faux-négatif** (validation humaine obligatoire sur les diagnostics « test à réparer ») repose sur la discipline humaine à valider réellement — un humain qui valide sans vérifier recrée le risque qu'on veut éliminer.

*Aucune question ouverte supplémentaire identifiée par le porteur du projet à la clôture de ce cadrage.*

---

## 12. Découpage suggéré en incréments livrables

**Incrément 0 — Preuve de concept (visé : ~2 jours)**
Un seul module Odoo. Cas de test unique généré de bout en bout : spec → Gherkin/script (IA) → relecture humaine obligatoire → exécution → rapport (statuts exécution + fonctionnel). Pas de gestion de projet, pas de charge/sécurité/CI-CD, pas de multi-rôles avancés.

**Incrément 1 — Cœur du référentiel & exécution**
Structure complète Projet → Module → Cas de test (socle commun + champs connecteur). Séparation UX Gestion/Exécution. Exécutions nommées transverses multi-modules. Historisation + archivage. Rôles et permissions (QA, lead technique, admin, client externe).

**Incrément 2 — Fiabilisation & gouvernance du verdict**
Garde-fou de validation humaine sur les diagnostics « à réparer ». Mode dev/utilisateur. Tableau de bord des modules « à retester » (détection automatique). Garde-fous tentatives + budget par cas de test. Suivi des coûts réels (Anthropic) + fallback estimation, visible admins uniquement.

**Incrément 3 — Élargissement du périmètre validé**
Dans l'ordre de priorité fixé : (1) gestion de projet type Jira, (2) tests de charge/performance, (3) tests de sécurité, (4) intégration CI/CD.

**Incrément 4 — Extension multi-connecteurs**
Ouverture de l'architecture à un second ERP, en s'appuyant sur les fondations posées dès la V1.
