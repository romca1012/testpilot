---
description: Lot 02 — Cause selon le type de step, prérequis → blocked (défauts F2 et F5)
---

# Lot 02 — Classer selon le type de step ; prérequis et pannes → `blocked`

Lis `CLAUDE.md`, puis F2 et F5 du plan. Décisions requises : **D1 et D2** (registre §4 du plan).
Si elles ne sont pas cochées, arrête-toi et présente la proposition en 10 lignes maximum.
Branche : `lot-02-causes-preconditions`.

## Pourquoi

Aujourd'hui tout `AssertionError` devient `ASSERTION_MISMATCH` → `non_conforme` → `failed`.
Or les steps de Contexte affirment des **prérequis** (« module non installé », « utilisateur non
authentifié ») et `hasattr(context, "last_record_ids")` trahit un **bug du test**. Et aucune panne
d'environnement ne produit `blocked` : tout finit en `retest`.

## À lire d'abord

- `src/testpilot/verdict/defect_taxonomy.py` (en entier, décision 0015 en tête).
- `src/testpilot/verdict/status.py` (en entier), `src/testpilot/verdict/explication.py`.
- `src/testpilot/execution/behave_result.py` : `BehaveFailure`, parsing des steps (~l.350-400).
- `behave_runtime/tp_json_formatter.py`, `behave_runtime/environment.py` (`before_scenario`,
  fixtures `odoo_session`, `playwright_browser`).
- `behave_runtime/steps_library/odoo/_odoo_background_steps.py`, `odoo/_odoo_steps.py`.
- `frontend/src/lib/status.ts`, `frontend/src/components/StatusPair.vue`.
- Schéma : `store/schema_sa.py` (CHECK sur `execution_status`), `store/db.py` (dernière migration).

## Étape 0 — mesurer avant de coder

Vérifie dans la source de Behave installée **et** sur un JSON réel produit par le harnais (dry-run
suffit) que chaque step porte `step_type` ∈ {given, when, then} et qu'un `Et`/`Mais` hérite du type
du step précédent. Colle l'extrait dans le rapport. Si ce n'est pas le cas, calcule le type
effectif dans le parser (héritage du dernier type explicite) et teste-le.

## Travail

1. `BehaveFailure` reçoit `step_type: str = ""`, rempli par le parser depuis le JSON. Les erreurs
   de hook (`hook_error`, `before_scenario`) reçoivent `step_type = "hook"`.
2. Nouvelle exception `PreconditionNonRemplieError` dans un module importable par tous les steps
   (à côté de `NavigationImpossibleError`). Nouvelle cause `PRECONDITION_NON_REMPLIE` dans la
   taxonomie, libellé « Prérequis non rempli (environnement) », mappée depuis le type d'exception.
3. `classify_failure` : après le calcul actuel (inchangé),
   - `ASSERTION_MISMATCH` + `step_type == "given"` → `PRECONDITION_NON_REMPLIE` ;
   - `ASSERTION_MISMATCH` + `step_type == "when"` → `BROKEN_TEST_CODE` ;
   - `step_type == "hook"` → `PRECONDITION_NON_REMPLIE` quel que soit le type d'exception.
   Ne lis **jamais** `step_text`.
4. Remplace par `raise PreconditionNonRemplieError(...)` les `assert` de prérequis des steps de
   Contexte (session RPC, uid, module installé, « aucun enregistrement ne commence par … » en
   `@given`). Remplace les `assert hasattr(context, ...)` par `RuntimeError` (bug du test).
5. `status.py` (selon D1) : nouvelle valeur d'axe exécution `EXEC_BLOCKED = "blocked"`.
   `scenario_verdict` : cause `PRECONDITION_NON_REMPLIE` → (`blocked`, `indetermine`).
   `derive_verdict` : échec de connexion / crash de fixture avant tout step → `blocked`.
   `aggregate` : priorité `technical_error` > `blocked` > `success` sur l'axe exécution ;
   un `non_conforme` surface toujours (inchangé).
   `statut_de_test` et `sql_statut` : `execution == blocked` → `STATUT_BLOCKED`, **avant** la
   règle `indetermine → retest`. Mets à jour le test qui compare la fonction et le SQL sur toutes
   les combinaisons.
6. Schéma : ajoute `blocked` aux CHECK de l'axe exécution (quatre étapes de `CLAUDE.md` §6).
7. `explication.py` + frontend : libellé et explication de `blocked` et de la nouvelle cause ;
   aucune valeur brute à l'écran.
8. `repair_circuit` / `defect_origin` : un `blocked` n'est **jamais** envoyé en réparation
   automatique (l'environnement n'est pas le test). Vérifie et teste.

## Tests exigés

- Taxonomie : `AssertionError` en given/when/then/hook → 4 causes attendues ; même texte d'erreur,
  libellés de step différents → même cause (non-régression décision 0015).
- Verdict : module non installé → `blocked` / lecture `blocked` ; login RPC impossible → `blocked` ;
  assertion en `Alors` → `failed` (inchangé) ; `TimeoutError` en `Quand` → `retest` (inchangé).
- Parser : `Et` après `Soit` → `given`.
- Migration SQLite + Alembic + portabilité du schéma.
- Frontend : `status.spec.ts` couvre `blocked` automatique.

## Critères d'acceptation

- [ ] Aucun prérequis de la bibliothèque ne lève `AssertionError`.
- [ ] Un `failed` ne peut plus provenir que d'un step `then`.
- [ ] `blocked` est produit automatiquement et jamais réparé automatiquement.
- [ ] Suites Python et frontend vertes.

Rapport au format `CLAUDE.md` §10 ; lance `verdict-reviewer`.
