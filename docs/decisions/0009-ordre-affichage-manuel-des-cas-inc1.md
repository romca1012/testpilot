# 0009 — Ordre d'affichage manuel des cas (glisser-déposer) — AMENDE 0006/§2.4

Date : 2026-07-16
Statut : **DÉCIDÉ et LIVRÉ** (plan validé par le porteur avant tout code).
Migration : **6** (`test_case.position`)

---

## En tête — cette note RÉVISE une décision actée

`0006`/§2.4 dit littéralement : **« Pas de colonne `position` »**. Cette note l'amende, sur
demande explicite du porteur. Sans cet amendement, les documents se contrediraient — exactement
le genre d'incohérence que ce projet traque.

**Ce que 0006 refusait**, et qui reste refusé : une position **décorative**. Celle de l'ancien
prototype (§2.6) existait en base et n'était **jamais alimentée** — le tri réel restait la date de
création. Elle promettait un ordre que rien n'honorait, et laissait croire qu'elle pilotait
l'exécution.

**Ce que 0009 introduit** : un ordre **réellement honoré** par le tri (`ORDER BY position, id`),
qui ne promet **rien** sur l'exécution. Les deux propriétés sont indissociables :
- s'il n'était pas honoré, ce serait le champ mort de 0006 ;
- s'il pilotait l'exécution, il retomberait dans le piège « affiché ≠ réel » (§4.6).

La distinction n'est donc pas un contournement de 0006 : c'est **la raison même** pour laquelle
0006 refusait l'autre.

## Décision

1. **`test_case.position INTEGER NOT NULL DEFAULT 0`** (migration 6), **backfill par le tri
   existant** (priorité puis titre) : à la migration, **rien ne bouge à l'écran**. Une position à
   0 partout aurait resorti la liste par `id` — un réordonnancement surprise que personne n'a
   demandé.
2. **Pas de `UNIQUE(module_id, position)`.** Un glissement décale N voisins ; l'unicité ferait
   échouer les états intermédiaires (positions négatives temporaires ou ordre d'`UPDATE` savant),
   pour aucun bénéfice. L'invariant qui compte est que l'**affichage soit déterministe** : il est
   tenu par `id` en second critère de tri, pas par une contrainte.
3. **`PUT /api/modules/{id}/cases/order`**, en **lot** et **transactionnel**. Un glissement change
   N positions : N `PATCH` seraient N allers-retours et un ordre incohérent si l'un échouait. La
   liste doit décrire **exactement** les cas du module (**409** sinon) — une liste partielle
   laisserait des cas à une position périmée, un id étranger déplacerait un cas hors de son module
   par un endpoint qui ne parle que d'ordre. Le serveur **recalcule** les positions (0, 1, 2…) :
   on ne fait pas confiance à des indices envoyés par le client.
4. **UI** : poignée de déplacement (drag HTML5 **natif**, sans dépendance — une liste, un niveau)
   dans la **liste du module uniquement**. Seule la **poignée** est `draggable`, pas la ligne :
   sinon on déclencherait un glissement en voulant déplier ou cliquer un cas. Retour visuel
   immédiat, puis **la réponse du serveur fait foi** (sinon l'écran pourrait diverger de la base) ;
   en cas de refus, **retour à l'état d'avant** + message.
5. **L'infobulle DIT que l'ordre ne pilote rien** : « Ordre de lecture […] Il n'ordonne PAS
   l'exécution — celle-ci suit l'ordre des scénarios dans le `.feature`. » Même patron que
   l'infobulle de la priorité (0006). Un tri manuel **muet** laisserait croire l'inverse.
6. **`priority` reste intacte et indépendante** : étiquette d'importance d'un côté, tri manuel
   libre de l'autre.

## Périmètre — ce qu'on ne fait PAS

- **Aucun câblage vers l'exécution.** `position` n'est lu que par l'affichage. Si l'**Exécution
  nommée transverse** (§7) veut un jour un ordre, ce sera **sa** décision, à ce moment-là — on ne
  préjuge pas qu'elle héritera de celui-ci. **Gardé par un test** qui échoue si `position`
  apparaît dans `execution/`, `verdict/`, `reporting/` ou `behave_runtime/`.
- **Pas de drag dans « Tous les cas »** (vue transverse : une position propre à chaque module n'y
  aurait pas de référent) **ni dans l'arbre** (colonne étroite, drag fragile). L'arbre **honore**
  l'ordre sans permettre de le changer.
- **Pas de déplacement entre modules par drag** : ça change `module_id` (le rangement **métier**),
  pas l'ordre. Chantier séparé — arbitré avec le porteur.

## Conséquence VISIBLE, assumée

**La priorité n'ordonne plus la liste.** Avant 0009, `list_all` triait par priorité puis titre :
changer une priorité réordonnait l'affichage. Ce n'est plus le cas — la priorité redevient une
pure étiquette, ce que 0006/§2.4 affirmait déjà (« étiquette de lecture assumée ») sans que le
tri le reflète. Le test `test_tri_par_priorite_puis_titre` figeait l'ancien contrat : il a été
**réécrit** (`test_tri_par_ordre_manuel_pas_par_priorite`), pas supprimé.

Sur les vues transverses, le tri reste **groupé par module** (`ORDER BY module_id, position, id`) :
sinon des positions propres à chaque module s'entremêleraient en un ordre qui ne veut rien dire.

## Suivi d'implémentation

- Migration 6 + backfill · `CaseRepo.reorder()` (validation stricte, transactionnel) ·
  `_next_position()` (un nouveau cas naît **en fin** de liste, sinon tous naîtraient à 0 et
  s'empileraient en tête) · `PUT …/cases/order` · poignée + drag dans `ModuleDetail` ·
  `CaseRow` passé de `<li>` à `<div>` (c'est la liste parente qui porte le `<li>`).
- **13 tests** : ordre honoré, nouveau cas en fin, déterminisme des ex æquo, priorité qui
  n'ordonne plus, liste partielle / id étranger / doublon refusés, transactionnalité, backfill de
  la migration, API (200/409/404), et la **garde anti-fuite vers l'exécution**.
