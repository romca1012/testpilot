# Rapport de continuité — TestPilot

> Document de reprise. À lire en premier après un `/clear`. Il fige **ce qui est décidé**
> (à ne pas re-débattre), **ce qui est vrai du code aujourd'hui**, et **ce qui reste ouvert**.
> Date : 2026-07-15.

---

## 1. Vue d'ensemble

| Incrément | État |
|---|---|
| **Incrément 0 — PoC** | ✅ **Terminé.** Pipeline complet `spec → analyse → génération → gate → exécution → verdict 2 axes → rapport`, prouvé de bout en bout sur un cas réel (`demande_materiel`) contre une instance Odoo neutralisée. |
| **Incrément 1.1 — Interface** | 🟡 **En cours, largement avancé.** API FastAPI + SPA Vite/Vue livrées et fonctionnelles ; hiérarchie Projet→Module→Cas en place ; 4 pages designées ; page détail module livrée. |
| **Incrément 1 (reste)** | Backlog documenté (§7). |
| **Incrément 2** | Sécurité (mot de passe en clair) — bloquant avant tout déploiement client. |

**Tests : 165 Python · 15 vitest · build front OK.** Tout est vert au moment de ce rapport.

**Stack** : Python 3.10, FastAPI + SQLite (portable PostgreSQL), Behave + Playwright + odoorpc,
Anthropic (Claude), frontend Vite + Vue 3 + Tailwind (dark, esprit « Linear »).

**Lancer** : `python -m uvicorn testpilot.api.app:app --port 8011` (⚠️ le port 8000 est occupé
par un autre serveur, hors projet). CLI : `testpilot run specs/demande_materiel.md --yes`.

---

## 2. Décisions structurantes tranchées (NE PAS re-débattre)

Chaque décision a sa note détaillée dans `docs/decisions/`.

### 2.1 Hiérarchie Projet → Module → Cas (§7) — `0004`
- Le socle Inc. 0 n'avait qu'un **champ texte `module`** sur `test_case`. Trou de conception.
- **Découverte clé** : ce champ avait un **double rôle conflaté** — métier (module affiché) ET
  technique (`case["module"]` servait à trouver le fichier `{module}.feature`).
- **Décision** : séparer. `module_id` (FK métier) **et** `feature_slug` (nom du `.feature`,
  technique, propre au cas). La colonne texte `module` a été **supprimée** (pas laissée inerte).
- Migration versionnée par `PRAGMA user_version` dans `store/db.py`, idempotente, gardée par
  introspection. Appliquée à la vraie base (backups `data/testpilot.db.pre*.bak`, gitignorés).

### 2.2 Le connecteur vit sur le PROJET, pas sur le cas — `0005`
- **Projet = l'application/ERP sous test** (ex. « Portail Sapian »). **Pas de niveau Client
  au-dessus** : « client externe » est un **rôle utilisateur** (§2), pas une entité.
- « Odoo » est une **valeur de connecteur**, **jamais** un nom de projet (l'erreur de la
  migration 1, corrigée : projet renommé « Odoo » → « Portail Sapian »).
- `project` porte `connector_type` + `base_url`/`database`/`username`/`password`.
  `test_case.connector_type` supprimé.
- **Runtime câblé dessus** (fait) : `connectors/runtime_env.py` traduit le projet en variables
  d'env, injectées dans le sous-processus behave ; `OdooConnector.from_project`. Sinon
  l'interface promettait un multi-projet que tout run trahissait en tapant la config globale.
- Le mot de passe est **write-only côté API** (jamais renvoyé). Stockage en clair = dette
  documentée → Incrément 2.

### 2.3 Un cas = un fichier `.feature` (PAS un scénario) — `0006`
- La granularité fine existe déjà **là où elle compte** : `scenario_result`, 2 statuts par
  scénario. La page détail module **déplie** les scénarios du dernier run à l'intérieur du cas.
- Migrer vers une granularité scénario impliquerait versioning/gate au niveau scénario :
  refonte lourde **non justifiée**. À revisiter seulement si ça devient réellement limitant.

### 2.4 Priorité de lecture, JAMAIS de `position` décorative — `0006`
- `test_case.priority` (`low|medium|high`) = **étiquette de lecture** assumée.
- **Pas de colonne `position`.** Pour un cas automatisé, l'ordre d'exécution réel est celui des
  scénarios **dans le `.feature`** : un ordre en base promettrait ce que l'exécution n'honore
  pas (même piège « affiché ≠ réel » que le runtime). L'ancien prototype avait un `position`…
  **jamais alimenté** (tri réel = date de création).
- L'infobulle de la priorité **dit explicitement** qu'elle n'ordonne pas l'exécution.
- Un ordre **réel** viendra avec l'**Exécution nommée transverse** (§7), où il aura un référent.

### 2.5 « Ajouter un cas » = fournir une SPEC — `0006`
- **Jamais de coquille manuelle inerte.** `POST /api/modules/{id}/cases` accepte
  `spec_content` (ou `spec_path`) et enchaîne **spec → analyse → génération → gate**, en
  imposant le `module_id`. Tâche de fond (202 + polling du job), comme les exécutions.
- Raison : un cas sans version ni Gherkin afficherait un cas qui ne teste rien (§3) — c'était
  précisément le « cas fantôme » de l'ancien prototype.
- Après génération, on emmène vers le détail du cas : la version existe mais **n'est pas
  relue** — le gate reste souverain.

### 2.6 Ancien prototype (`../testpilot-agent`) = inspiration ponctuelle, jamais un modèle
- Il a été conçu **avant** les invariants actuels. Limites identifiées : référentiel **scindé**
  (cas automatisé = pas de ligne en base, identité `auto:{suite}:{nom_scénario}` parsée du
  fichier → régénération = identité perdue), **statut mono-axe**, **pas de gate**.
- Repris : la **palette** (`main.css`), quelques primitives UI, la moitié RPC du connecteur
  Odoo, le harnais Behave (`environment.py` + bibliothèque de steps).
- Rejeté : son organisation de pages/navigation, son modèle de statut.

### 2.7 Autres décisions actées
- **Navigation** : le projet est un **contexte porté par l'URL** (`/projects/:pid/...`), au-dessus
  des deux onglets **Gestion des cas / Exécution** (séparation §8 **structurelle**). Aucune vue
  ne mélange deux projets (filtres API + `pid` systématique côté front).
- **Vocabulaire** : **aucune valeur d'enum brute à l'écran**. Tout passe par
  `frontend/src/lib/status.ts`. Libellés courts + **infobulle « i »** pour les explications.
- **Shim `features.*`** dans `behave_runtime/environment.py` : le prompt impose
  `from features.environment import register_created` alors que le runner assemble un layout
  **plat**. Le shim (alias `sys.modules`) fait le pont — **ce n'est pas un oubli**, c'est
  documenté dans le fichier. Ne pas le supprimer.

---

## 3. Modèle de données actuel (`user_version = 3`)

```
project        id, name, description, created_at,
               connector_type, base_url, database, username, password   ← connecteur (0005)
   └─ module   id, project_id, name, description, created_at
        └─ test_case  id, title, description, origin, validation_status,
                      module_id,          ← rangement MÉTIER (0004)
                      feature_slug,       ← nom du .feature, TECHNIQUE (0004)
                      priority,           ← étiquette de lecture (0006, migration 3)
                      current_version_id, last_execution_status,
                      last_functional_status, last_executed_at,
                      author, created_at, updated_at
             ├─ test_case_version  id, test_case_id, version_number, spec_content, spec_hash,
             │                     feature_content, steps_content, feature_path, steps_path,
             │                     change_summary, created_at, created_by
             ├─ review_decision    id, test_case_id, version_id, decision, reviewer,
             │                     comment, decided_at
             └─ execution          id, test_case_id, version_id,
                                   execution_status, functional_status,   ← LES 2 AXES
                                   scenarios_total/passed/failed, cost_usd, iterations,
                                   duration_seconds, report_json_path, report_html_path,
                                   trigger, started_at
                   ├─ scenario_result  id, execution_id, scenario_name,
                   │                   execution_status, functional_status,  ← 2 axes/scénario
                   │                   failure_type, cause_category, error_summary
                   └─ repair_attempt   id, execution_id, attempt_number, failure_signature,
                                       cause_category, defect_origin, confirmation_status,
                                       confirmed_by, confirmed_at, what_was_tried, created_at
cost_ledger    id, period_month, execution_id, phase, model, cost_usd, source, created_at
```

**Migrations** (`store/db.py`, `PRAGMA user_version`) : 1 = project/module + feature_slug ;
2 = connecteur sur projet + `Odoo`→`Portail Sapian` ; 3 = `priority`.
Non implémenté du §7 : l'**Exécution nommée transverse**.

---

## 4. Invariants à NE JAMAIS régresser

1. **Les deux axes ne fusionnent jamais** (§5). `execution_status` (le test a-t-il pu tourner ?)
   et `functional_status` (l'app est-elle conforme ?) sont deux jugements distincts, partout :
   base, API, rapport, UI (`StatusPair`). Jamais un badge unique « OK/KO ».
2. **Un statut n'est jamais déclaratif** : il est toujours la conséquence d'une exécution réelle.
3. **Le gate de relecture humaine est obligatoire avant la première exécution** d'une version
   générée par IA (§4). Il dépend de l'approbation de la **version**, jamais du module/projet.
4. **Asymétrie du défaut** (§5) : un `vrai_bug` se remonte **directement** ; un
   `test_a_reparer` ou un `indetermine` exige une **confirmation humaine** (faux-négatif
   inacceptable, faux-positif acceptable).
5. **Un échec technique ne vaut jamais « conforme »** : en cas de plantage, le run est clos en
   `technical_error / indetermine` — jamais un faux succès.
6. **Jamais « affiché ≠ réel »** : ce que l'UI promet, le runtime doit le tenir (leçon du
   câblage connexion-projet ; raison du refus d'un `position` décoratif).
7. **Aucune valeur d'enum brute à l'écran** ; aucun libellé qui se contredit (ex. « Jamais
   lancé » sur un cas qui a un verdict → corrigé en « Non validé »).
8. **Séparation Gestion des cas / Exécution** visible et structurelle (§8), sous le contexte
   Projet. **Aucun mélange inter-projets**.
9. **Garde-fou anti-production** : `ODOO_ENV=prod` fait échouer le harnais. Un projet ne peut
   **jamais** produire cette variable.
10. **Coûts** : cap par-run (`COST_LIMIT_PER_RUN_USD = 2`) + provenance honnête du coût
    (`estimated` vs `anthropic_api` — le label `anthropic_api` **uniquement** si un chiffre réel
    a été mesuré). ⚠️ Le « budget 50 €/mois » du brief est le **budget de dev du porteur**, pas
    un garde-fou produit — ne pas le ré-implémenter (malentendu déjà tranché).

---

## 5. Historique des commits

```
b0235b8  Page détail module (0006) : priorité de lecture, ajout par spec, dépliage scénarios
14e0e41  Réutilisation des steps partagés (0003, A+B) : catalogue montré, AST, transport refusé
24b8ee6  Parser des steps errored (0002) : formatter maison, error_text(), http_error
70f8792  Runtime branché sur la connexion du projet (fin de l'incohérence affiché/réel)
769561c  Redesign CaseDetail (dernier résultat, relecture/exécution, onglets code, historique)
39da584  Fix vocabulaire validation ('Jamais lancé' → 'Non validé')
20851d5  Passe design ExecutionsList + ReportView
7b7b24a  Backlog centralisé
629d365  Connecteur au niveau Projet (0005) + migration 2
e280182  Gestion projets (création/suppression cascade/renommage)
a2b5599  Nav projet (URL, sélecteur, fil d'Ariane)
f5fd54f  Hiérarchie Projet→Module→Cas (0004) + migration 1
7f8c1b0  Passe UX (vocabulaire, arborescence, alignements)
3ee5465  Frontend fonctionnel (SPA, 2 axes, gate)
f5b48ad  Backend API
--- Incrément 0 ---
23c0af1  e2e demande_materiel + correctifs connecteur/CLI
0a38095  Harnais Behave · cbc03a2 Connecteur Odoo · 14eeca1 Reporting+CLI
8ddf9ae  Guardrails · 46cbef9 + 02f74f5 Verdict · 4373458 Execution
e6aab00  Generation · 73294b6 Analysis · b0b5c01 Socle
```

---

## 6. Run e2e réel — TERMINÉ, concluant, **+ 1 nouvel écart trouvé**

**But** : valider **en un passage** (a) le flux 0006 « ajouter un cas par spec » et (b) l'effet
réel de 0003 « l'agent réutilise-t-il les steps partagés ? ».

**Dispositif** : `scripts/run_reel_0003_0006.py` — passe par la **vraie route HTTP**
(`POST /api/modules/1/cases`) via `TestClient` (qui exécute la tâche de fond de façon
synchrone), sur la **vraie base**. Spec : `specs/validation_champ_requis.md` (variante réelle
de `demande_materiel`, ciblée sur la validation d'un champ requis — un besoin qui **exige** le
comptage de tickets, donc le step partagé). Base sauvegardée :
`data/testpilot.db.pre-run-reel.bak`. **Rejouable** :
`PYTHONUTF8=1 python scripts/run_reel_0003_0006.py`.

### (a) Flux 0006 — ✅ **validé de bout en bout**
```
POST /api/modules/1/cases        → HTTP 202
job                              → done, case_id = 2
projet / module                  → Portail Sapian / Demande materiel   (module imposé ✓)
validation_status                → never_executed
gate.allowed                     → False   ← généré mais NON RELU (invariant §4 tenu ✓)
versions                         → 1
```
Aucune coquille : le cas naît **avec** sa version, son Gherkin et ses steps.

### (b) Mesure 0003 — ✅ **validé en conditions réelles**
| Mesure | Résultat |
|---|---|
| Steps partagés réutilisés | **16 / 37 libellés uniques** |
| **Step de comptage partagé réutilisé** | ✅ **OUI** — les trois : `…est enregistré pour comparaison`, `…augmente de 1`, `…n'a pas augmenté` |
| Steps custom écrits | **4**, tous légitimement spécifiques (chaîne de 300 car., chemin de redirection, `team_id`, cohérence chaîne longue) |
| Transport brut (`requests`/`urllib`/`/web/dataset`) | ✅ **Aucun** |

Avant 0003 : l'agent inventait `_count_tickets` avec `requests` → 404, tuant les 3 scénarios.
Après : il réutilise la bibliothèque et n'écrit du custom que là où c'est justifié.

### ⚠️ NOUVEL ÉCART TROUVÉ (non corrigé, à traiter à la reprise)

**L'agent réutilise le bon step, mais lui passe le mauvais argument.** Le Gherkin généré dit :
```gherkin
Et je renseigne le champ "Raison de la demande" avec la valeur "..."
Et je laisse le champ "Raison de la demande" vide
```
Or le helper derrière ce step partagé sélectionne par **attribut HTML `name`** :
```python
def fill_field(page, name, value):
    page.wait_for_selector(f'[name="{name}"]', ...)
```
L'agent a passé le **libellé humain** (« Raison de la demande ») là où le step attend le **nom
technique du champ** (`name`). `[name="Raison de la demande"]` n'existe pas → `TimeoutError` à
l'exécution réelle.

**Incohérence interne révélatrice** : dans le *même* fichier, pour les vérifications RPC, il
utilise correctement le nom technique (`un enregistrement avec le champ "name" égal à …`).
Il confond donc les deux registres **uniquement sur les steps UI**.

**Cause probable** : le catalogue de 0003 expose les **libellés** des steps, mais **rien sur la
sémantique des placeholders** — `{field}` est-il un libellé humain ou un attribut HTML ? On lui
a montré *quoi* réutiliser, pas *comment* le paramétrer.

**Statut de la preuve** : **non prouvé par une exécution**. Le dry-run passe (les steps se
résolvent — il ne vérifie pas la sémantique des arguments) ; le gate bloque l'exécution tant
que la version n'est pas relue (correctement). L'analyse repose sur la lecture du helper
`_base_helpers.fill_field`. **À confirmer** en approuvant le cas 2 et en le lançant.

**Note positive** : si ce diagnostic est juste, la chaîne §5 le classera **correctement** —
`TimeoutError` → `ui_timeout` → `wrong_field_name` → « Champ/sélecteur introuvable » →
`test_a_reparer`. Ce serait une validation de bout en bout de la taxonomie (0002).

**Piste (à valider avant de coder)** : enrichir le catalogue avec la **sémantique des
paramètres** (ex. annoter `{field}` = « nom technique du champ HTML, pas son libellé »). C'est
le prolongement naturel de 0003 — même racine : on montre, mais pas assez.

### Suite à donner (à la reprise)
1. **Confirmer l'écart** : approuver le cas 2 (gate) et le lancer ; vérifier que l'échec est
   bien un `ui_timeout` sur `[name="Raison de la demande"]`.
2. Si confirmé : **ouvrir une décision `0007`** et proposer un plan (sémantique des paramètres
   dans le catalogue) **avant** de coder.
3. Le cas 2 est un **vrai cas** du référentiel (base restaurable via
   `data/testpilot.db.pre-run-reel.bak` si on veut l'effacer).

### Nuance de mesure à connaître
`steps_library.catalogue()` renvoie **43 déclarations** pour **37 libellés uniques** : certaines
fonctions portent deux décorateurs (`@when` **et** `@then` sur le même libellé). Les deux
chiffres sont corrects, ils ne mesurent pas la même chose.

---

## 7. Backlog ouvert (voir `docs/BACKLOG.md`)

| Priorité | Item |
|---|---|
| **1 — recommandée** | **Sémantique des paramètres de steps** (nouvel écart du §6) : l'agent réutilise le bon step mais lui passe un libellé humain là où il faut le nom technique du champ → `TimeoutError`. **D'abord confirmer par une exécution réelle**, puis décision `0007` + plan avant de coder. C'est la suite directe de 0003 (même racine : on montre *quoi*, pas *comment le paramétrer*). |
| **2** | **Exécution nommée transverse** (§7, JTBD essentiel §3) : regroupement de cas de modules différents, rapport attaché à l'exécution. L'UI laisse déjà la porte ouverte (badge « Cas unique / Suite transverse », champ `suite_name` réservé côté API). C'est **le dernier gros manque du §7**. |
| **3** | **Confirmations `pending_human`** (`0001`) : écran de traitement de la file des origines de défaut. |
| **4** | **Édition de la connexion d'un projet** : `PATCH /api/projects/{id}` ne gère que nom/description. |
| **5** | `testpilot run --project` : lever l'implicite (la CLI prend le **premier** projet). Sans effet observable tant qu'il n'y a qu'un projet réel. |
| **6 — observation** | Quasi-doublons sémantiques (volet C de `0003`) : écarté, à reconsidérer avec des exemples concrets après plusieurs runs. |
| **Inc. 2 — bloquant client** | **Mot de passe de connexion en clair** dans SQLite. Atténué (write-only côté API) mais à chiffrer / passer en gestionnaire de secrets **avant tout déploiement client**. |

---

## 8. Méthode de travail à maintenir

1. **Proposer un plan avant de coder.** Pour tout chantier non trivial : arborescence, endpoints,
   composants, schéma — puis **attendre la validation**.
2. **S'arrêter aux décisions structurantes.** Modèle de données, sémantique produit, ce qu'un
   mot veut dire à l'écran : ce sont des choix du porteur, pas des détails d'implémentation.
3. **Ne jamais enchaîner plusieurs choix engageants sans validation explicite.**
4. **Signaler les écarts plutôt que de les arrondir** — même mineurs, même quand ça oblige à
   corriger sa propre analyse antérieure (cf. la note `0002`, dont le diagnostic initial était
   faux et a été corrigé au dossier plutôt que laissé tel quel).
5. **Mesurer plutôt que supposer.** Lire la source (celle de Behave a livré la vraie cause de
   `0002`), compter, prouver — les trois plus gros bugs de ce projet ont été trouvés en
   vérifiant une hypothèse, pas en la croyant.
6. **Auditer l'ancien prototype comme source d'inspiration ponctuelle**, jamais comme modèle.
7. **Tests avant commit**, commits atomiques par brique logique, **sans attribution Claude**
   dans les messages.
8. **Vérifier en conditions réelles** quand c'est possible (capture d'écran, run réel) — un test
   vert ne prouve pas qu'un utilisateur voit la bonne chose.
