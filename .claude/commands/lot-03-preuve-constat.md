---
description: Lot 03 — Preuve runtime qu'une assertion a été exécutée ; gardes d'écriture (défaut F4)
---

# Lot 03 — Pas de `conforme` sans constat exécuté

Lis `CLAUDE.md`, F4 du plan. Décisions requises : **D3 et D4**. Dépend du lot 02.
Branche : `lot-03-preuve-constat`.

## Pourquoi

Un scénario vert devient `conforme` même si aucune assertion ne s'est exécutée (assertion dans
une branche non prise, `Alors` qui ne fait qu'attendre). `assertion_lint` est statique et non
bloquant : il ne voit pas l'exécution.

## À lire d'abord

- `behave_runtime/steps_library/_base_helpers.py` : tous les `assert`, `raise AssertionError`,
  `expect(` ; le motif sidecar `_record_field_fallback` / `FIELD_FALLBACK_FILE_ENV`.
- `src/testpilot/execution/behave_runner.py` (constantes sidecar, lecture des fichiers),
  `behave_result.py` (champs sidecar de `BehaveResult`).
- `src/testpilot/verdict/status.py`, `src/testpilot/generation/assertion_lint.py`,
  `src/testpilot/generation/tools/write.py`, `src/testpilot/generation/prompts/system_prompt.md`
  (Règle 4).

## Travail

1. Dans `_base_helpers.py` : `constater(condition, message)` (lève `AssertionError(message)` si
   faux) et `constater_visible(locator, ...)`, `constater_texte(locator, attendu, ...)` qui
   enveloppent `expect(...)`. Chaque appel **réussi ou échoué** écrit une ligne dans un sidecar
   `TP_CONSTATS_FILE` : `{"scenario": <nom>, "step_type": ..., "ok": bool}`. Le nom du scénario
   courant est posé par `before_scenario` (même mécanisme que `_tp_intention_step`).
2. Convertis **toutes** les assertions des steps `@then` de `generic/` et `odoo/` et des helpers
   qu'ils appellent vers ces fonctions. Aucune assertion nue ne doit subsister dans un chemin
   `Alors`.
3. Runner : constante `CONSTATS_FILE_ENV/FILENAME`, lecture du sidecar, `BehaveResult.constats`
   (liste) ; le parser rattache le nombre de constats réussis à chaque `BehaveScenario`.
4. Verdict (D3) : `scenario.status == "passed"` et `constats_reussis == 0` →
   (`success`, `indetermine`), cause `AUCUN_CONSTAT`, libellé « Aucune vérification exécutée ».
   Ne concerne que les scénarios exécutés en run réel (pas le dry-run).
5. `write_steps_file` (D4, bloquant) refuse, avec un message qui dit quoi faire :
   - un `assert`, `raise AssertionError` ou `expect(` dans une fonction décorée `@given`/`@when` ;
   - une fonction `@then` qui n'appelle ni `constater*` ni un helper de la bibliothèque ;
   - un `except` nu ou `except Exception` dont le corps ne relève pas (`pass`, `return`, log) dans
     une fonction `@then` (avale l'échec).
   Garde `assertion_lint` pour les tautologies (détectif, inchangé).
6. `system_prompt.md` Règle 4 : les assertions s'écrivent `constater(...)` uniquement dans un
   `Alors` ; exemple correct / exemple refusé. Garde le texte court (coût §9).

## Tests exigés

- Sidecar : un `Alors` qui appelle `constater` 2 fois → 2 lignes ; échec → ligne `ok: false`.
- Verdict : scénario vert + 0 constat → `indetermine` / `retest` ; vert + ≥ 1 constat → `conforme`.
- Falsifiabilité : chaque helper `constater_*` échoue sur une page doublure qui ne satisfait pas
  la condition.
- `write_steps_file` : 3 refus attendus (assert en `@when`, `@then` sans constat, `except` qui
  avale) ; un fichier correct accepté.
- Conformité (`-m conformance`) toujours verte sur SauceDemo / the-internet.

## Critères d'acceptation

- [ ] Un scénario ne peut être `conforme` que si au moins un constat réussi a été consigné.
- [ ] Aucune assertion nue dans les chemins `Alors` de la bibliothèque (grep dans le rapport).
- [ ] Coût de génération mesuré avant/après le changement de prompt (ou justification si non
      mesurable sans LLM, avec la taille du prompt en caractères).

Rapport au format `CLAUDE.md` §10 ; lance `verdict-reviewer`.
