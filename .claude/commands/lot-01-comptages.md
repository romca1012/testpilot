---
description: Lot 01 — Comptages cloisonnés au scénario (défaut F1, faux PASSED/FAILED)
---

# Lot 01 — Comptages cloisonnés au scénario

Lis `CLAUDE.md` puis la section F1 de `docs/PLAN-FIABILITE-VERDICT-2026-09.md`.
Décision requise : aucune. Branche : `lot-01-comptages`.

## Pourquoi

Les assertions « augmente de 1 » / « n'a pas augmenté » comparent `search_count([])` sur **tout**
le modèle. Sur une instance partagée, une création par un tiers pendant que le test échoue donne
un **faux PASSED** ; deux créations donnent un faux `non_conforme`. C'est le défaut le plus grave
du dépôt : il peut rendre vert un test d'une fonctionnalité cassée.

## À lire d'abord

- `behave_runtime/steps_library/_base_helpers.py` : `record_count_not_increased` (~l.278),
  `memorize_record_count` (~l.1704), `check_count_not_increased` (~l.1772),
  `check_count_increased_by_one` (~l.1987), `_poll_until`, `_capturer_dernier_enregistrement`,
  et tout usage de `context.tentative_token`.
- `behave_runtime/steps_library/odoo/_odoo_steps.py` : steps qui appellent ces helpers.
- `behave_runtime/environment.py` : `register_created`, `after_scenario`.
- `tests/test_comptage_falsifiable.py` et ses doublures de `context.odoo`.

## Travail

1. `memorize_record_count` relève, en plus du compte actuel (gardé pour le diagnostic), le **plus
   grand id** du modèle : `search([], order="id desc", limit=1)` avec `active_test=False`.
2. Nouveau helper `_crees_par_ce_scenario(context, model) -> list[int]` :
   domaine `[("id", ">", max_id)]`, `active_test=False`, affiné par le marqueur de tentative
   **si et seulement si** un step de ce scénario a saisi une valeur « rendue unique pour cette
   tentative » (retrouve comment cette valeur est mémorisée ; si elle ne l'est pas, mémorise-la
   sur `context` dans ce step). N'affine **pas** par `create_uid` : les formulaires publics créent
   avec l'utilisateur public (à documenter dans la docstring).
3. `check_count_increased_by_one` : attend (via `_poll_until`) qu'au moins un id apparaisse, puis
   exige **exactement un** id. Conserve intégralement la chaîne de diagnostic existante (refus
   navigateur → `donnee_invalide`, refus serveur nommé/générique) avant l'`AssertionError` finale.
   Pose `last_record_ids` / `last_record_model` avec l'id trouvé et l'ajoute au registre
   `context.created` (utile au lot 06).
4. `check_count_not_increased` et `record_count_not_increased` : échouent si
   `_crees_par_ce_scenario` renvoie au moins un id, avec un message qui liste les ids.
5. Si `memorize_record_count` n'a pas été appelé avant un contrôle, lève une erreur de **code de
   test** (`RuntimeError` explicite), jamais un `AssertionError`.
6. Le message d'échec cite le domaine utilisé et le compte global (diagnostic), pas seulement le
   compte cloisonné.

## Tests exigés (`tests/test_comptage_cloisonne.py`)

- Tiers crée 1 enregistrement, le scénario 0 → `check_count_increased_by_one` **échoue**.
  Écris ce test en premier et montre qu'il **passe à tort** sur le code actuel (faux PASSED).
- Scénario crée 1, tiers crée 1 → **passe** et `last_record_ids` = l'id du scénario quand le
  marqueur est disponible ; sans marqueur, échoue avec un message qui dit « 2 créations ».
- `not_increased` : tiers crée 1 sans marqueur → échec avec ids listés (comportement documenté) ;
  avec marqueur et tiers non marqué → passe.
- Enregistrement archivé créé par le scénario → compté.
- Contrôle sans relevé préalable → `RuntimeError`, pas `AssertionError`.
- Les tests existants de `test_comptage_falsifiable.py` restent verts sans modification de leurs
  assertions (adapte seulement les doublures si leur interface change, et dis-le).

## Critères d'acceptation

- [ ] Plus aucun `search_count([])` servant de preuve de création/non-création dans les helpers.
- [ ] Le test « tiers crée pendant que le scénario échoue » passe à tort sur l'ancien code et
      échoue correctement sur le nouveau (preuve dans le rapport : commande + sortie avant/après).
- [ ] `python -m pytest -q` et ruff critique verts.

## Interdits

- Toucher à `defect_taxonomy.py` ou `status.py` (lot 02).
- Changer le libellé d'un step existant : les `.feature` déjà générés doivent continuer à matcher.

Termine par le rapport au format de `CLAUDE.md` §10 et lance le sous-agent `verdict-reviewer`.
