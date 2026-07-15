# 0006 — Page détail module : priorité de lecture, et « ajouter un cas » = fournir une spec

Date : 2026-07-15
Statut : **implémenté** (Inc. 1.1)

## Contexte

Besoin : gérer les cas de test à l'intérieur d'un module (lister, ajouter, ordonner).
Audit préalable de l'ancien prototype (`testpilot-agent`) pour savoir quoi éviter.

### Ce que l'audit a montré

- **Référentiel scindé** : un cas automatisé n'avait **aucune ligne en base** — son identité
  était `f"auto:{suite_id}:{nom_du_scénario}"`, dérivée du nom **parsé dans le `.feature`** à
  chaque lecture. Une régénération qui renomme un scénario ⇒ identité perdue (historique,
  section, calibration). Le cas manuel, lui, avait un vrai ID mais `executable: False`.
  « Ajouter un cas » et « avoir un cas exécutable » étaient **deux chemins déconnectés**.
- **Statut mono-axe** : `last_status` + `status_provenance` — nos deux axes (§5) y sont
  inexprimables (une erreur technique et une non-conformité s'écrasent en `failed`).
- **Pas de gate** (§4) : un cas automatisé n'avait pas de version ⇒ rien à approuver.
- **Ordre vestigial** : `position` (int) existait sur les cas et `ORDER BY position ASC` était
  appliqué… mais **rien ne l'alimentait jamais** (le seul `position=pos` du CRUD concernait les
  `StepResult`). Aucun endpoint de réordonnancement, aucun drag & drop ⇒ tri réel = date de
  création. `PRODUCT_LOGIC.md` ne mentionne jamais l'ordre : ce n'était pas un concept produit,
  mais un vestige de mimétisme TestRail. `priority` (low|medium|high|critical) était une
  **étiquette**, pas un ordre.

## Décisions

1. **Granularité : un cas = un fichier `.feature`** (inchangé). Le scénario n'est pas une entité
   de premier rang : il existe déjà là où il compte (`scenario_result`, 2 statuts par scénario).
   La page déplie les scénarios **du dernier run** à l'intérieur de la ligne du cas. À revisiter
   seulement si ça devient réellement limitant.
2. **« Ordonner » = priorité de LECTURE** (`low|medium|high`), étiquette assumée. **Pas de
   `position`** : pour un cas automatisé, l'ordre d'exécution réel est celui des scénarios dans
   le `.feature`. Un ordre en base promettrait ce que l'exécution n'honore pas — le décalage
   « affiché ≠ réel » que le produit doit supprimer (même leçon que le câblage runtime, 0005).
   L'infobulle de l'étiquette dit explicitement qu'elle n'ordonne pas l'exécution.
   Un ordre **réel** viendra avec l'**Exécution nommée transverse** (§7), où il pilotera une
   campagne — là il aura un référent.
3. **« Ajouter un cas » = fournir une SPÉCIFICATION**, jamais une coquille vide. `POST
   /api/modules/{id}/cases` accepte `spec_content` (ou `spec_path`) et enchaîne le flux existant
   **spec → analyse → génération → gate**, en imposant le `module_id` d'accueil. Un cas sans
   version ni Gherkin afficherait un cas qui ne teste rien (§3) et polluerait le référentiel —
   exactement le « cas fantôme » de l'ancien modèle. La génération étant longue et coûteuse, elle
   tourne en tâche de fond (202 + polling du job), comme les exécutions.

## Implémentation

- **Migration 3** : `test_case.priority` (`low|medium|high`, défaut `medium`), idempotente.
- **Tri** : `CaseRepo.list_all` ordonne par priorité (high→low) puis titre — tri de lecture.
- **API** : `GET /api/modules/{id}` (fil d'Ariane), `PATCH /api/cases/{id}` (priorité),
  `GET /api/cases/{id}/scenarios` (dernier run), `POST /api/modules/{id}/cases` (spec →
  génération), `GET /api/modules/jobs/{job_id}` (suivi).
- **Front** : `ModuleDetail.vue`, `PriorityBadge.vue` (éditable), `CaseRow.vue` (repliable).
  Le module devient cliquable depuis la liste des cas. Après génération réussie, on emmène vers
  le **détail du cas** : la version est générée mais **pas encore relue** — le gate reste souverain.

## Point traité au passage : unicité du `feature_slug`

Un slug = un fichier `.feature` sur disque ⇒ il doit être unique **globalement**. Deux cas d'un
même module dérivés du même titre se seraient écrasés l'un l'autre. `unique_feature_slug()`
suffixe (`retour_materiel_2`) ; le slug est dérivé du titre (`slugify`), plus du nom du module.

## Reste ouvert

- L'ajout d'un cas via l'UI n'a pas encore été exercé sur une **génération réelle** (coût LLM) :
  testé avec un agent simulé. À observer au prochain run réel.
- Génération = un seul job en mémoire (serveur mono-processus), comme les exécutions.
