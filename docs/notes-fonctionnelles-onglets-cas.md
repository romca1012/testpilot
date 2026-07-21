# Notes fonctionnelles — à conserver pour la conception backend

Ce document liste, pour chaque élément visuel repéré sur les 3 onglets, à quoi il sert
concrètement dans TestRail et ce que ça implique comme donnée/logique côté backend.
Rien n'est à implémenter maintenant — c'est une réserve de contexte pour plus tard.

---

## Onglet "Tests & Résultats"

| Élément UI | Utilité fonctionnelle | Implication backend (plus tard) |
|---|---|---|
| Graphique en courbe (30 derniers jours) | Visualise l'évolution du nombre de résultats par statut dans le temps, pour repérer une dégradation de stabilité du cas de test | Nécessite un agrégat quotidien des résultats (`test_results`) par statut, filtré sur le `case_id`, fenêtre glissante 30 jours |
| Panneau stats "Passed/Blocked/Retest/Failed" | Résumé chiffré + % sur la période, donne un statut de santé rapide du cas | Somme des résultats par statut / total sur la période ; recalcul à chaque nouveau résultat ou en cache invalidé |
| Icônes export image / CSV | Permet de sortir les données pour reporting externe (audit, comité, etc.) | Génération d'image du graphique (canvas→PNG) et export CSV des points de données |
| Sous-onglet "Exécutions" | Historique de **dans quelles exécutions de test** ce cas a été inclus et testé, avec le run d'origine | Jointure `test_case` ↔ `test_instance` (résultat d'un cas dans un run donné) ↔ `test_run` |
| Sous-onglet "Résultats et commentaires" | Vue centrée sur le **contenu** des résultats (commentaires, pièces jointes) plutôt que sur le run | Table `test_results` avec `comment`, `attachments[]`, `author_id`, `created_at` |
| Statut "(archivé)" sur un run | Indique que le run est clos (les données de résultat sont figées, cf. la fonctionnalité TestRail "Close Run") — le cas de test a pu évoluer depuis, mais le run archivé garde une photo des détails du cas au moment du test | Nécessite un mécanisme de **snapshot/versioning** du cas de test au moment de la clôture du run, pour ne jamais afficher des données incohérentes sur un run archivé |
| Lien vers le nom du run / plan/projet | Navigation croisée entre le cas et l'exécution/le plan qui l'a testé | Simple relation FK, mais attention aux permissions (le user voit-il ce run/plan ?) |
| "Testé par [Nom]" | Traçabilité de qui a produit le résultat | `author_id` sur `test_results`, résolu en nom affiché |
| "Afficher tout" | Pagination — la vue par défaut ne montre qu'un extrait (2 mois dans l'exemple) | Endpoint paginé, tri par date desc, groupé par mois côté frontend ou backend |

---

## Onglet "Défauts"

| Élément UI | Utilité fonctionnelle | Implication backend (plus tard) |
|---|---|---|
| Gros chiffre "0 Défauts" | KPI immédiat : combien de défauts sont actuellement liés à ce cas de test | `COUNT(defects) WHERE case_id = X` |
| Graphique barres Défauts/Résultats/Tests | Met en perspective le volume de défauts par rapport au volume de tests/résultats — un cas avec beaucoup de résultats mais 0 défaut = cas stable | 3 agrégats distincts : nb de tests (instances), nb de résultats, nb de défauts liés |
| Stats "X tests commencés" | Nombre d'exécutions où ce cas a été inclus et a reçu au moins un résultat (≠ untested) | Compter les `test_instance` avec au moins un `test_result` non-untested |
| Stats "X résultats ajoutés" | Volume total de résultats historiques sur ce cas, tous runs confondus | `COUNT(test_results) WHERE case_id = X` |
| Stats "X défauts enregistrés" | Nombre de défauts distincts liés (un même défaut peut être lié à plusieurs résultats) | Table de liaison `result_defects` (many-to-many), `COUNT(DISTINCT defect_id)` |
| Liste des défauts (état vide ou peuplé) | Accès direct aux tickets de bug liés à ce cas | Selon intégration : soit défauts internes à l'outil, soit lien vers Jira/GitHub Issues (référence externe stockée, pas de duplication de données) |
| Texte explicatif "liés depuis Ajouter un résultat" | Indique le **point d'entrée fonctionnel** : on ne lie pas un défaut depuis cette page, mais depuis la saisie d'un résultat dans une exécution | Confirme que la relation défaut↔cas passe toujours par un résultat (`result_id` → `defect_ref`), jamais un lien direct cas↔défaut |

---

## Onglet "Historique"

| Élément UI | Utilité fonctionnelle | Implication backend (plus tard) |
|---|---|---|
| Timeline groupée par date | Audit trail complet du cas de test : qui a changé quoi et quand | Nécessite un **event log / audit log** par cas de test, horodaté |
| Badge "Création" / "Mise à jour" | Type d'événement | Champ `action_type` sur l'entrée d'historique (`created`, `updated`, à terme `deleted`/`restored`) |
| "Version : N" | Numéro de version incrémental du cas de test — chaque modification crée une nouvelle version | Implique un **versioning du cas de test** (snapshot complet ou diff stocké à chaque sauvegarde) |
| Auteur + date/heure | Traçabilité | `author_id`, `created_at` sur chaque entrée d'historique |
| Tableau de diff (champ, ancienne→nouvelle valeur) | Permet de voir précisément ce qui a changé sans comparer deux versions entières | Stocker le diff au moment de la sauvegarde (avant/après par champ modifié), plutôt que de le recalculer à la volée — plus fiable et plus rapide à afficher |
| Entrée de création | Point de départ de la timeline, toujours présente | Première entrée du log, version = 1, pas de diff associé |
| Bandeau "Comparer côte à côte (Enterprise)" | Fonctionnalité premium TestRail : diff visuel côte-à-côte entre deux versions | **Non retenu pour notre implémentation actuelle** — noté ici seulement comme feature possible en V2 si on veut un jour un vrai comparateur de versions |
| Lien "Ready" souligné dans un diff (ex: State New → Ready) | Les valeurs de champs à choix (statut, type...) sont cliquables/traçables vers leur définition | Suggère que les diffs de champs à liste de valeurs affichent un lien vers la valeur (utile si les valeurs de référence sont éditables/configurable par projet) |

---

## Module "Exécutions et résultats de test"

### Distinction fondamentale Run vs Plan (à ne jamais confondre dans le modèle de données)

| Concept | Définition | Implication backend |
|---|---|---|
| **Exécution de test (Test Run)** | Une liste concrète de cas de test à exécuter en une fois, sur un périmètre/version donnée | Une entité `test_run` liée à un `suite_id`/projet, avec une sélection de cas figée (ou dynamique) au moment de sa création |
| **Plan de test (Test Plan)** | Un **conteneur** regroupant plusieurs exécutions de test (ex : une par navigateur/config) | Une entité `test_plan` qui ne contient **aucun cas de test directement** — elle référence une liste de `test_run` ; chaque run garde sa propre sélection de cas |
| **Configuration** | Un attribut de test (navigateur, OS...) permettant de dupliquer automatiquement un run pour chaque combinaison | Nécessite un modèle `configurations` + `configuration_groups`, et une logique de génération combinatoire de runs à la création d'un plan (cf. doc API TestRail : chaque combinaison valide génère un run distinct) |

### Écran "Aperçu" (liste)

| Élément UI | Utilité fonctionnelle | Implication backend |
|---|---|---|
| Groupement "Archivé" / statut | Sépare les runs actifs des runs clos, pour ne pas polluer la vue de travail avec l'historique | Champ `is_archived` / `is_completed` sur `test_run`, filtre par défaut sur les runs actifs |
| % de complétion par ligne | Donne un aperçu instantané de l'avancement sans ouvrir le run | Calcul `(résultats non-untested / total cas du run) * 100`, à cacher/recalculer à chaque nouveau résultat |
| "Grouper par" / "Trier par" | Personnalisation de l'organisation de la liste (par jalon, par date, par assigné...) | Nécessite des index sur les champs de tri/groupement les plus utilisés (`milestone_id`, `created_at`, `assignedto_id`) côté requête |
| Bouton "Afficher les données de test" (icône cadenas) | Fonctionnalité vraisemblablement liée à un plan payant/role restreint chez TestRail (à clarifier — peut être lié à l'affichage détaillé des runs archivés ou à un rôle spécifique) | **À clarifier avec le métier avant d'implémenter une vraie restriction** — ne pas supposer une logique de permission sans confirmation |
| Item non cliquable dans la liste (`9.0.10.47176 COLPRDNEW`) | Suggère un run sans accès pour l'utilisateur courant, ou un format d'affichage différent (run sans lien direct, ex. run supprimé mais visible dans l'historique) | Prévoir un champ `is_accessible`/`deleted_at` pour distinguer ces cas côté API |

### Écran "Détail d'un run"

| Élément UI | Utilité fonctionnelle | Implication backend |
|---|---|---|
| Bandeau "exécution archivée" | Empêche toute modification une fois le run clos — garantit l'intégrité historique des résultats | Toute route de modification (ajout résultat, édition sélection de cas) doit vérifier `is_archived = false` côté API, pas seulement côté front |
| Bouton "Relancer" | Crée un nouveau run en reprenant la même config/sélection de cas que celui-ci (utile pour une re-campagne de test) | Endpoint de duplication : copie `case_selection`, `milestone_id`, structure — sans copier les résultats |
| "Select Schedule" | Planification récurrente d'exécutions (ex : tous les lundis) — fonctionnalité avancée | Nécessiterait un scheduler/cron + génération automatique de runs à date fixe — **hors périmètre V1**, à ne considérer qu'en V2/V3 |
| Donut + résumé % réussite | Vue synthétique de la santé du run | Agrégats par statut sur les `test_instance` du run (≠ historique global du cas, ici c'est borné à CE run) |
| "X / Y non testés" | Indique le reste à faire dans la campagne | `COUNT(test_instance) WHERE status = 'untested' AND run_id = X` |
| Groupement par section + mini barre de progression | Permet de visualiser l'avancement section par section (utile sur un run avec beaucoup de cas) | Agrégat par `section_id` au sein du run |
| "Appartient au jalon [X]" | Rattache le run à un objectif de release/sprint pour le reporting par jalon | FK `milestone_id` sur `test_run`, utilisé aussi dans les rapports (Runs Summary report) |

### Formulaires "Ajouter une exécution" / "Ajouter un plan"

| Élément UI | Utilité fonctionnelle | Implication backend |
|---|---|---|
| Champ "Références" | Lie le run/plan à des tickets externes (Jira, etc.) pour la traçabilité release ↔ tests | Champ texte libre `refs`, potentiellement parsé pour extraire des IDs et créer des liens cliquables si un connecteur externe est configuré |
| Champ "Jalon" (arbo parent/enfant) | Classement hiérarchique des jalons (release → patch) | Nécessite un modèle `milestones` auto-référencé (`parent_id`), pas juste une liste plate |
| "Inclure tous les cas de test" | Sélection **vivante** : les nouveaux cas créés après coup rejoignent automatiquement le run | `test_run.include_all = true` → la liste de cas du run doit être recalculée dynamiquement (vue/requête), pas figée à la création |
| "Sélectionner des cas spécifiques" | Sélection **figée** à la création, aucun ajout automatique ensuite | Table de liaison `test_run_cases` remplie une fois, jamais recalculée automatiquement |
| "Filtrage dynamique" | Sélection **conditionnelle** : un cas rejoint/quitte le run automatiquement selon des critères, sauf si le run est terminé | Stocker la définition du filtre (`dynamic_filters` JSON) + un job qui réévalue les cas à chaque création/modification de cas — s'arrête dès que `is_completed = true` |
| Bloc "Ajouter des exécutions depuis la barre latérale" (formulaire Plan) | Confirme qu'un plan est créé quasiment vide, puis peuplé itérativement de runs | Le `test_plan` doit pouvoir être sauvegardé sans aucun `run` associé au départ (draft), puis des `plan_entries` sont ajoutées, chacune générant un ou plusieurs `test_run` selon les configurations |

---

## Pages restantes — Activité/Progression/Défauts (run), Jalons, Rapports, Aperçu projet, Tâche à faire

### Sous-onglets d'un run

| Élément UI | Utilité fonctionnelle | Implication backend |
|---|---|---|
| Activité (run) | Flux chronologique de tous les résultats saisis sur ce run, tous cas confondus | Requête inverse de celle du cas de test : `WHERE run_id = X`, triée par date desc, groupée par jour |
| Progression / burndown | Aide un chef de projet à savoir si la campagne de test sera terminée à temps | Nécessite : (1) un historique quotidien du nombre de tests untested restants, (2) des estimations de durée par cas (champ `estimate` optionnel), (3) un algorithme de forecast basé sur la vitesse réelle d'avancement — **fonctionnalité avancée, coûteuse à fiabiliser** ; TestRail distingue 3 niveaux de précision de prévision selon la quantité de données disponibles |
| "Prévision non disponible" | Garde-fou quand il n'y a pas assez de données d'estimation | Le backend doit renvoyer explicitement un statut "insufficient_data" plutôt qu'un `null`/`0` ambigu, pour que le front sache afficher le bon message |
| Défauts (run) | Vue des défauts liés à l'échelle du run entier (vs à l'échelle d'un seul cas) | Même modèle de liaison défauts que pour le cas de test, mais agrégé par `run_id` au lieu de `case_id` |

### Page Jalons

| Élément UI | Utilité fonctionnelle | Implication backend |
|---|---|---|
| Sous-jalons ("A N sous-étapes") | Découper un jalon large (release) en étapes plus fines (sprints, phases) | Modèle `milestones` avec `parent_id` auto-référencé — **une seule profondeur de nesting dans TestRail** (un sous-jalon n'a pas lui-même de sous-jalon) ; les stats du parent agrègent celles de ses enfants |
| % de progression du jalon | Avancement de tous les runs rattachés au jalon (et ses sous-jalons) | Agrégat multi-niveaux : `SUM(tests passés)/SUM(tests totaux)` sur tous les runs liés au jalon + ses enfants |
| "Dû le [date]" / statut Ouvert-Terminé | Suivi d'échéance et clôture manuelle | Champs `due_date`, `is_completed`, `completed_on` ; clôture forçable même si tous les tests ne sont pas finis (décision métier, pas automatique) |
| Bouton suppression rapide (croix rouge) | Suppression directe depuis la liste | Cascade : un run/plan lié à un jalon supprimé → probablement `milestone_id = null`, pas de suppression en cascade des runs |

### Page Rapports

| Élément UI | Utilité fonctionnelle | Implication backend |
|---|---|---|
| Modèles catégorisés (Cas, Runs, Jalons, Projets…) | Chaque modèle = un besoin de reporting différent | Chaque type a sa logique d'agrégation ; système de "report templates" avec paramètres par type plutôt qu'un modèle générique unique |
| Rapports "Partagés" groupés par mois | Bibliothèque de rapports générés/planifiés, réutilisables | Table `reports` avec `created_by`, `created_at`, `is_shared`, `config` (JSON), potentiellement `is_scheduled` + fréquence |
| Actions dupliquer / supprimer / exporter | Réutilisation rapide d'une config existante | Dupliquer = copie du `config` JSON ; export = génération PDF/CSV à la demande, non stockée |

### Page Aperçu (dashboard projet)

| Élément UI | Utilité fonctionnelle | Implication backend |
|---|---|---|
| Graphique + état "Aucune donnée trouvée" | Vue globale de l'activité de test du projet, garde-fou si aucune donnée sur la période | Agrégat d'activité à l'échelle du **projet entier** (tous runs) — index efficace sur `project_id + date` |
| Bouton "Affiner" | Filtrage période + statuts | Paramètres API : `date_from`, `date_to`, `statuses[]` |
| Sections Jalons / Exécutions en aperçu | Point d'entrée rapide vers les 2 entités les plus utilisées | Requête limitée (ex 5 éléments), sans pagination |
| Sidebar "Actions" (Ajouter/Générer/Voir tout) | Accès rapide aux actions fréquentes | Pas d'implication backend — confirme que Jalons/Runs/Cas sont les 3 piliers de navigation |

### Page Tâche à faire (To-Do)

| Élément UI | Utilité fonctionnelle | Implication backend |
|---|---|---|
| Liste des tests assignés non traités | Vue personnelle "ce qu'il me reste à faire", tous runs confondus | `test_instance WHERE assignedto_id = current_user AND status = 'untested'`, groupée par run/section |
| Fil d'ariane projet → run → section | Contexte complet de chaque tâche | Résoudre la hiérarchie (projet/run/section) par instance — `JOIN` optimisé ou vue dénormalisée si la liste est longue |
| Grouper par / Filtre | Organisation personnelle | Mutualiser dans un service de filtrage générique backend plutôt que le refaire par module |
| État vide "réinitialiser le filtre" | Distinguer "vraiment aucune tâche" de "filtre trop restrictif" | Renvoyer le total NON filtré en plus du total filtré, pour choisir le bon message |

---

## Décisions à prendre plus tard (backend), à ne pas oublier
1. **Versioning des cas de test** : snapshot complet à chaque sauvegarde vs. stockage de diffs uniquement — impacte le coût de stockage et la vitesse d'affichage de l'historique.
2. **Gestion des runs archivés/clos** : faut-il figer une copie du cas de test au moment de la clôture d'un run (comme TestRail) pour garantir la cohérence historique des résultats ?
3. **Modèle de liaison défauts** : défauts internes à l'outil, ou uniquement des références vers un tracker externe (Jira, GitHub Issues, Linear...) ? Ça change complètement le modèle de données (table interne vs. simple champ `external_ref` + `external_url`).
4. **Permissions** : qui peut voir l'historique complet (avec auteurs) ? Qui peut voir les défauts liés si le tracker externe a ses propres restrictions d'accès ?
5. **Fréquence de rafraîchissement des stats/graphiques** : calcul à la volée (temps réel) vs. valeurs pré-agrégées/cache invalidé à chaque nouveau résultat.
6. **Modèle Run vs Plan vs Configuration** : confirmer si on implémente les configurations (navigateur/OS) dès la V1 backend, ou si on se limite à Run simple + Plan (regroupement) sans génération combinatoire automatique dans un premier temps.
7. **Filtrage dynamique** : décider si on implémente la réévaluation automatique des cas dans un run (job/trigger) dès la V1, ou si on limite la V1 à "tous les cas" et "sélection figée" uniquement, en repoussant le filtrage dynamique en V2.
8. **Sens du bouton "Afficher les données de test" (cadenas)** : à clarifier avec le métier avant d'implémenter — permission de rôle ? feature payante originale de TestRail à volontairement ignorer ?
9. **Profondeur de nesting des jalons** : TestRail limite volontairement à un seul niveau de sous-jalon (pas de sous-sous-jalon). À confirmer si on garde la même limite ou si on autorise plus de profondeur — impact direct sur le modèle `parent_id` et les requêtes d'agrégation de stats.
10. **Fiabilité du burndown/forecast** : décider si cette fonctionnalité est prioritaire pour une V1 backend (calcul complexe, nécessite un historique quotidien + des estimations de temps par cas) ou si on la reporte, en gardant "Prévision non disponible" comme état permanent en attendant.
11. **Rapports planifiés/récurrents** : à trancher si on implémente la génération automatique à fréquence fixe dès la V1, ou si les rapports restent uniquement générés à la demande dans un premier temps.

---

## Correspondance avec notre modèle actuel (repères pour la conception)

*Ajouté le 2026-07-20 — ce que le vocabulaire TestRail ci-dessus recouvre déjà chez nous, pour
ne pas réinventer l'existant lors de la conception backend.*

| Terme TestRail (note) | Notre équivalent actuel | État |
|---|---|---|
| `test_run` / plan de test | **Exécution nommée transverse** (§7 du brief) | ⚠️ **non construit** — dernier gros manque du §7 |
| `test_instance` (cas dans un run) | `execution` (une ligne par run d'une version d'un cas) | ✅ existe (`execution.test_case_id`, `version_id`, `suite_name`) |
| `test_results` | `scenario_result` (2 axes par scénario) + verdict de l'`execution` | ✅ existe |
| Versioning du cas | `test_case_version` (une version par changement, `change_summary`, `created_by`) | ✅ existe — l'onglet Historique s'appuie dessus |
| Défauts liés | `defect_origin` / `repair_attempt` / confirmations (`0013`) — PAS de table `defect` dédiée | ⚠️ à décider (interne vs. réf. externe Jira/GitHub — cf. décision 3) |
| Run archivé/clos + snapshot | Pas de mécanisme de clôture ni de snapshot au run | ⚠️ à concevoir (cf. décision 2) |
| Audit log par cas | Partiellement couvert par `test_case_version` ; pas d'`action_type` ni de diff par champ stocké | ⚠️ à étendre (cf. décision 1) |

**Rappel de discipline projet** : ces éléments ne s'implémentent pas en autonomie. Le brief reste
la source de vérité ; toute extension du modèle (défauts, snapshots, audit log) est une décision
du porteur, à tracer dans `docs/decisions/` au moment de la construire.
