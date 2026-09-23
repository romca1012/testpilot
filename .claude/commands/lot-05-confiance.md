---
description: Lot 05 — Confiance du verdict (résolution adaptative, retry) et campagne stricte (F3)
---

# Lot 05 — Un vert obtenu par repli n'est pas un vert nominal

Lis `CLAUDE.md`, F3 du plan. Décision requise : **D5**. Dépend des lots 02 et 04.
Branche : `lot-05-confiance`.

## Pourquoi

Quand la cascade déterministe de `locate_field` / `navigate_menu` / `click_first_actionable`
échoue, un LLM choisit un élément réel de la page (`_adaptive_resolution.py`). C'est utile pour
exécuter, mais un champ renommé retrouvé ainsi est exactement une **régression d'UI** qu'une
campagne doit signaler. De même, un vert obtenu au second essai après `ui_timeout`
(`executor.py`) masque une instabilité. Aujourd'hui ces signaux sont tracés
(`selector_tiers`, `menus_appris`, `retried`) mais n'atteignent jamais le verdict.

## À lire d'abord

- `behave_runtime/steps_library/_adaptive_resolution.py`, et dans `_base_helpers.py` :
  `locate_field`, `navigate_menu`, `click_first_actionable`, les écritures de `selector_tiers` et
  `menus_appris`.
- `src/testpilot/execution/executor.py`, `behave_result.py`, `behave_runner.py`.
- `src/testpilot/verdict/status.py`, `explication.py`, `api/services/run_service.py`,
  `campaign_service.py`, le schéma de `execution` / `execution_attempt`.
- Frontend : `StatusPair.vue`, `RunTestDetail.vue`, `AddTestRunForm.vue`.

## Travail

1. Chaque résolution adaptative **réussie** écrit, dans le sidecar des paliers, `palier =
   "adaptatif"` avec le scénario courant (vérifie que c'est déjà le cas ; sinon ajoute-le).
2. `CaseVerdict` et `ScenarioVerdict` reçoivent `confiance` :
   `apres_retry` si l'outcome a été rejoué, sinon `auto_resolue` si au moins une résolution
   adaptative a eu lieu dans le scénario, sinon `nominale`. Calcul **pur**, dans `status.py`.
3. Persistance : colonne `confiance` sur l'exécution (quatre étapes de `CLAUDE.md` §6),
   défaut `nominale` pour l'historique (documente que l'historique n'a pas été mesuré).
4. Lecture : un `passed` non nominal s'affiche « Réussi — à confirmer » avec l'explication
   (quel champ ou menu a été résolu par repli, ou « réussi au second essai »). La valeur de
   `statut_de_test` reste `passed` (les deux axes ne changent pas) ; c'est une qualification.
5. Campagne stricte : option `strict` sur la campagne / le run. Transmise au sous-processus par
   variable d'environnement `TP_MODE_STRICT=1`. En mode strict : pas d'appel à
   `_adaptive_resolution` (l'échec de la cascade lève `ElementIntrouvableError`), pas de retry.
6. Tableau de bord qualité : compteur « verts à confirmer » par campagne.

## Tests exigés

- `status.py` : les trois valeurs de confiance selon sidecar et `retried`.
- Mode strict : un champ introuvable par la cascade → `retest` sans appel LLM (doublure qui
  échoue si appelée).
- Migration + portabilité.
- Frontend : libellé « Réussi — à confirmer » et explication.
- Banc (lot 04) : renommer un libellé de champ sur l'instance de référence → mode normal
  `passed` + `auto_resolue` ; mode strict `retest`. Résultat dans le rapport.

## Critères d'acceptation

- [ ] Aucun vert obtenu par repli ou par retry n'est présenté comme nominal.
- [ ] Le mode strict n'émet aucun appel LLM pendant l'exécution (coût d'exécution = 0 $).

Rapport au format `CLAUDE.md` §10 ; lance `verdict-reviewer`.
