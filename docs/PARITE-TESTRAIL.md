# Carte de parité TestRail → TestPilot

> **À quoi sert ce document.** Il recense **le fonctionnement réel de TestRail**, relevé dans sa
> documentation officielle (support.testrail.com, parcourue le 2026-08-04), et le confronte à l'état
> de TestPilot. Objectif : ne plus découvrir en cours de route qu'un comportement existait déjà chez
> TestRail et qu'on ne l'avait pas copié.
>
> Le cap est la **parité**, avec l'exécution automatique en plus. Toute divergence doit donc être un
> **choix assumé et écrit**, jamais un oubli.
>
> Légende : ✅ conforme · ⚠️ divergence · ❌ absent · ➕ TestPilot va au-delà

---

## 1. Structure d'un projet

| TestRail | TestPilot | État |
|---|---|---|
| **Projet** — unité principale ; tout (runs, résultats, jalons) lui est rattaché | `project` | ✅ |
| **3 types de projet** : Dépôt unique · Dépôt unique avec *baselines* · Suites multiples. Le type se change après coup (procédure de migration documentée) | un seul modèle implicite | ⚠️ |
| **Test Suite** — n'existe que sur 2 des 3 types. ⚠️ *On ne peut pas mélanger des cas de plusieurs suites dans un même run* | `module` en tient lieu | ⚠️ |
| **Section / Sous-section** — arborescence **libre et imbriquée sans limite**, réordonnable par glisser-déposer, pliable/dépliable individuellement + « Tout déplier / Tout replier ». **Supprimer une section supprime ses sous-sections et ses cas — irréversible** | `case_group`, **2 niveaux fixes** (Module → Spécification), pas d'imbrication libre, pas de réordonnancement | ⚠️ |
| **Jalon (Milestone)** — nom, références, **parent** (jalons enfants), description, dates début/fin ; états *Ouvert* / *À venir* ; les runs et plans s'y rattachent | — | ❌ |

---

## 2. Le cas de test

### Champs système (Admin > Customizations réordonne / ajoute / modifie)

| Champ | Obligatoire | Détail TestRail | TestPilot |
|---|---|---|---|
| **Title** | oui | — | ✅ |
| **Section** | oui | — | ✅ (`group_id`) |
| **Template** | **oui** | 5 modèles : *Test Case (Text)*, *Test Case (Steps)*, *Exploratory Session*, *BDD*, *AI Evaluation* | ❌ un seul modèle implicite (équivalent *Text*) |
| **Type** | oui | liste ouverte, `is_default` (« Other » par défaut dans l'API) | ⚠️ Fonctionnel / Non fonctionnel — simplification **assumée** |
| **Priority** | oui | **4 valeurs : Critical · High · Medium · Low** | ⚠️ **3 valeurs** (haute/moyenne/basse) — *Critical manque* |
| **Status** *(Enterprise)* | oui | cycle de vie — voir §3 | ⚠️ voir §3 |
| **Assigned To** *(Enterprise)* | non | **qui conçoit/relit le cas** — distinct de l'assignation d'exécution | ❌ |
| **Estimate** | non | format `10s` / `1m` / `10m` / `1h` | ✅ (`estimate`) |
| **References** | non | **liste séparée par des virgules** ; hyperlien automatique si `View Reference URL` configuré (Admin > Integration) ; sélecteur d'issues intégré depuis 10.0 (Jira Cloud) | ⚠️ texte simple, pas de liste ni de lien |

### Autres capacités sur le cas

| TestRail | TestPilot |
|---|---|
| **Commentaires** sur un cas (fil de discussion, notification e-mail à l'assigné) | ❌ |
| **Labels** (étiquettes) | ❌ |
| **Versionnage du cas** *(Enterprise)* + restauration partielle d'une version | ➕ déjà présent, et **hors Enterprise** |
| **Shared steps** — bibliothèque d'étapes réutilisables, importables dans un cas | ➕ existe côté technique (`steps_library`), pas côté métier |
| **Déplacer / copier** cas et sections par glisser-déposer (`Ctrl`=déplacer, `Maj`=copier), entre suites et entre projets | ❌ |
| **Suppression / restauration** de cas | ✅ (suppression douce + corbeille) |
| **Filtrer** (AI Status, Section, Priority, Status, Assigned To, Created By, Created On…) avec **« Correspondre à TOUS » / « Correspondre à AU MOINS UN »** | ⚠️ filtres simples, pas de combinateur ET/OU |
| **Trier** par n'importe quel champ, ascendant/descendant | ⚠️ partiel |
| **Import** CSV/Excel/XML · **Export** | ❌ import · ⚠️ export CSV seulement |
| **Édition en lot** (statut, assignation, priorité…) | ⚠️ partiel (priorité, suppression) |

---

## 3. ⚠️ Le cycle de vie du cas — divergence à arbitrer

**Ce que fait TestRail** (*Test case review & approvals*, Enterprise, activable **par projet**) :

- 3 statuts par défaut, **entièrement personnalisables** (Admin > Customizations > Case Statuses) :
  **Design** (défaut) → **Review** → **Ready (Approved)**.
- Deux drapeaux obligatoires sur la liste : exactement un statut `is_default`, exactement un
  `is_approved`.
- **Toute modification d'un cas le fait retomber au statut par défaut.** C'est explicite :
  *« Each time a change is done in a test case, its status will be reverted to default status. »*
- **Le statut approuvé conditionne les runs** : un run « Tous les cas » n'inclut **que** les cas
  approuvés. Pour inclure des cas en Design/Review, il faut les choisir à la main ou poser un filtre.
- Un cas s'assigne à un relecteur, qui **approuve ou rejette** et commente la version.
- Une permission de rôle dédiée (*Test Case Approval*) et un onglet **TODO > TEST CASES** listant les
  cas non approuvés.
- Si les approbations ne sont **pas** activées sur le projet, le champ Status **n'apparaît pas**.

**Ce qui a été implémenté dans TestPilot** : l'État (Nouveau/Conception/Prêt/Obsolète) est un champ
**libre, sans aucun automatisme** — décision prise le 2026-08-04 sur ma recommandation.

**La divergence** : cette recommandation s'appuyait sur l'idée que le retour automatique appartenait
à une fonctionnalité *séparée*. C'est inexact — le champ *State* de la capture d'écran **est** ce
champ, avec une liste personnalisée. Chez TestRail, il est bien remis à zéro à chaque édition, et il
**garde la porte des runs**.

→ **À arbitrer** (§ « Décisions en attente », plus bas).

---

## 4. Campagnes, plans, exécution

| TestRail | TestPilot | État |
|---|---|---|
| **Test Run** — nom, description, références, jalon, **Assigned To**, **dates début/fin** (optionnelles, éditables tant que le run est actif, héritées du jalon, avertissement si dépassement — sans blocage) | `test_run` sans jalon, sans assignation globale, sans dates | ⚠️ |
| **Sélection des cas** : *tous* · *sélection manuelle* · **filtre dynamique** (les nouveaux cas correspondants entrent automatiquement, ceux qui cessent de correspondre sortent ; icône d'entonnoir sur les tests entrés ainsi) | `all` / `frozen` — **filtre dynamique absent** | ⚠️ |
| **Test Plan** — conteneur de runs ; nom, référence, jalon, description, dates ; « Rerun Test Plan » | — | ❌ |
| **Configurations** — matrice (navigateur × OS…) : *un même cas, un résultat par configuration*, historique unifié | — | ❌ |
| **Clôture** — archive les résultats, gèle le run. ⚠️ **Irréversible** (*« closing a test run cannot be undone »*) | archivage **réversible** (rouvrir) | ⚠️ |
| **Rerun** — clone d'un run/plan **sans les résultats**, filtré par statut des résultats précédents (rejouer les *Failed*, les *Blocked*…), avec option **« Copier les assignations »** | — | ❌ |
| **Assignation** — 5 chemins : à la création du run · à l'édition du run · sur un test · **dans la fenêtre Add Result** · **en lot** (+ « Assigner tout le filtre ») | prévu (étape 9) | ❌ |
| **TODO** — liste par utilisateur et par projet, vue d'équipe pour les responsables, sous-onglet TEST CASES | — | ❌ |
| **Notifications e-mail** + abonnement à un test ou à un run | — | ❌ |

---

## 5. Les résultats

### Statuts de résultat (API `get_statuses`)

| ID | Nom | Drapeaux |
|---|---|---|
| 1 | Passed | `is_system`, `is_final` |
| 2 | Blocked | `is_system` |
| 3 | **Untested** | `is_system`, `is_untested` |
| 4 | Retest | `is_system` |
| 5 | Failed | `is_system`, `is_final` |

Statuts **personnalisés** possibles (`custom_status1`…). Chaque statut porte **3 couleurs** (claire,
moyenne, sombre). ⚠️ **Règle dure** : *« Once a test result has been added to a test, it can never
receive the Untested status again. »* → ✅ TestPilot est naturellement conforme (une ligne de
registre existe désormais).

### La fenêtre « Add Result »

| Champ | TestRail | TestPilot |
|---|---|---|
| **Status** | seul champ obligatoire | ✅ |
| **Comment** | — | ✅ |
| **Attachments** | tout type, **jusqu'à 256 Mo** | ⏳ étape 8 (plafond prévu : 10 Mo) |
| **Assign To** | réassigner depuis la fenêtre | ❌ |
| **Version** | version/build de l'application testée | ❌ |
| **Elapsed** | saisie (`2m 10s`) **ou chronomètre Start/Stop** | ❌ (écarté V1) |
| **Defects** | liste d'IDs + **Push** vers l'outil externe | ❌ (écarté V1) |
| **Résultats par étape** | si le cas utilise le modèle *Steps* : statut **et résultat réel** par étape | ❌ (écarté V1) |
| **Champs personnalisés de résultat** | oui | ❌ |

### Les 5 façons de saisir un résultat — ⚠️ TestPilot n'en a qu'une

1. **Menu déroulant de statut directement dans la liste** du run ;
2. bouton **Add Result** dans la **vue 3 panneaux** ;
3. **« Pass & Next »** — passe le cas au vert et enchaîne au suivant (avec une flèche pour choisir un
   autre statut) ;
4. **saisie en lot** — sélectionner N cas, un seul statut pour tous ;
5. depuis la **page du test**.

TestPilot : une fenêtre, un cas à la fois.

### Les 3 vues de suivi d'un test

**Results & comments** (chronologique) · **History & Context** (courbe des résultats dans le temps +
dernier résultat par run) · **Defects**.

---

## 6. Administration

| TestRail | TestPilot |
|---|---|
| **Champs personnalisés** — jusqu'à **150**, sur les **cas** et les **résultats**, **13 types** (Checkbox, Date, Dropdown, Integer, Milestone, Multi-select, Steps, Step Results, String, Text, URL, User, Rating). Nom système immuable, **affectation par projet avec options différentes par projet** | ❌ |
| **Templates** de cas (créer/modifier) | ❌ |
| **Case Types / Priorities / Case Statuses / Result Statuses** — tous personnalisables | ❌ (valeurs figées, mais champs en texte libre → extensible sans migration) |
| **Utilisateurs, rôles et permissions** (dont *Test Case Approval*, *ToDo Workload for Other Users*), SSO, MFA | ❌ (pas de comptes) |
| **Intégrations** — références et défauts : `View/Add Reference URL`, `Defect View/Add URL`, plugins (survol = aperçu du ticket, push de défaut) | ❌ (base posée : champ `refs`) |
| **Thème clair / sombre** configurable | ⚠️ sombre uniquement |
| **Audit log**, sauvegardes, sécurité d'instance | ❌ |
| **UI scripts** (personnalisation de l'interface) | ❌ |

---

## 7. Rapports et tableaux de bord

**Tableau de bord** : projets, activité récente, to-dos.
**Vues d'un run/jalon** : *Status* / *Activity* / *Progress*.

**Rapports** (une quinzaine) : Activity Summary (Cases) · **Coverage for References (Cases)** ·
Property Distribution (Cases / Results) · Status Tops · Summary (Defects) · Summary for Cases /
References (Defects) · Comparison for Cases / References (Results) · Milestone / Plan / Project /
Runs (Summary) · Projects (Test Execution) Summary · **User (Test Execution) Workload**.
Plus : graphiques personnalisables, tableaux de bord, impression, rapports planifiés.

TestPilot : un tableau de bord qualité, un rapport d'exécution. ❌ pour le reste.

> ⚠️ **Coverage for References** est le rapport qui répond à « quels cas couvrent cette user
> story ? » et « quelle exigence n'est couverte par aucun cas ? ». C'est le débouché naturel du
> remplissage automatique de `refs` prévu à l'étape 9.

---

## 8. Ce que TestPilot fait que TestRail ne fait pas

À préserver — c'est la raison d'être du produit :

- **exécution réellement automatique** contre l'application (Behave + Playwright + RPC) ;
- **verdict à deux axes** (technique / fonctionnel) et le 4ᵉ verdict « donnée du test invalide » ;
- **provenance stockée** `executed` / `declared`, garantie par un `CHECK` en base ;
- **génération de cas par IA depuis une spécification** (TestRail a l'équivalent depuis 9.5, mais
  sans exécution) ;
- **réparation automatique bornée** et mémoire des règles apprises ;
- **suivi du coût LLM** au cas près ;
- **versionnage des cas hors Enterprise**.

---

## 9. Arbitrages du porteur (2026-08-04)

| Sujet | Décision | Motif |
|---|---|---|
| **État** | **inchangé** — reste libre, sans automatisme | c'est ce que montre l'onglet d'exécution de TestRail : un test archivé y garde `State: New` |
| **Priorité** | **3 niveaux**, pas de « Critique » | l'implémentation actuelle est correcte |
| **Type** | validé tel quel | — |
| **Clôture irréversible** | **reportée** au déploiement en production | sans effet tant qu'on n'est pas en prod |
| **Références (liste, hyperlien)** | **hors V1** | — |
| **Modèles de cas** | **sans objet** — TestPilot applique déjà le modèle *Text*, qui correspond au « un seul verdict global » déjà tranché | — |
| **Sections imbriquées** | à faire, **rattaché au chantier génération de cas** (étape 9) | les deux touchent la même arborescence |
| **Pièce jointe / capture** | **confirmée nécessaire** : elle atteste que le test a réellement été fait (étape 8) | — |
| **Façons de saisir un résultat** | à revoir plus tard | confort de saisie, pas une fonctionnalité |

### Le chantier en cours : la parité de l'écran d'exécution

Priorité donnée à **l'exécution manuelle, non terminée**, et à l'interface qui l'entoure — à copier
sur TestRail à l'identique.

Reste absent (voir §4 et §5) : Jalons · Plans · Configurations · Rerun · TODO · champs
personnalisés · rôles · import · rapports.
