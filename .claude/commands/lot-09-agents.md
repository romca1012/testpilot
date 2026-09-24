---
description: Lot 09 — Mieux équiper les agents TestPilot : perception, prompts, garde de réparation des assertions (C9)
---

# Lot 09 — Agents de génération et de réparation

Lis `CLAUDE.md` (§3 et §8 surtout), C9 du plan. Décision requise : **D4**. Dépend des lots 07a, 07b-e et
08 (le vocabulaire à exposer doit exister). Branche : `lot-09-agents`.

## Pourquoi

L'agent ne perçoit aujourd'hui que des formulaires (`inspect_page_form`) et un schéma RPC
(`inspect_schema`). Pour un flux ERP il ne voit ni les boutons de la vue, ni les états possibles,
ni les sous-champs d'une ligne de commande ; pour une page web quelconque il n'a pas l'arbre
d'accessibilité. Il devine, et le run réel le corrige à prix fort. Objectif : moins de devinettes,
donc plus d'exécutions réussies au premier passage (I3) **dans le budget §9** (I6).

## À lire d'abord

- `src/testpilot/generation/tools/inspect.py`, `tools/write.py`, `tools/__init__.py`
  (enregistrement des outils, `ToolOutcome`, `verified_fields`).
- `src/testpilot/generation/react_loop.py`, `agent.py`, `prompt.py`, `steps_library.py`
  (`catalogue`), `smoke_check.py`, `provenance.py`, `repair_agent.py`, `repair_diff.py`.
- `src/testpilot/generation/prompts/system_prompt.md`, `repair_prompt.md`,
  `correction_prompt.md`.
- `src/testpilot/connectors/base.py`, `odoo.py`, `generic_web.py`.
- `behave_runtime/steps_library/_adaptive_resolution.py` (`_JS_CANDIDATS` : réutilisable).

## Étape 0 — ligne de base

Sur le banc (lot 04, mode génération), mesure I3, I4, I6 et la taille du prompt système avant
toute modification. Sans cette mesure, le lot n'est pas livrable.

## Travail

1. **Outil `inspect_odoo_view(model, view_type="form")`** (connecteur odoo) : par RPC
   (`get_views` ≥ 16, sinon `fields_view_get`), rend de façon compacte : boutons (`name`,
   libellé, type, conditions de visibilité), champ de barre d'état et ses valeurs, champs x2many
   et leurs sous-champs éditables, champs requis. Déterministe, sans navigateur, résultat mis en
   cache par (projet, modèle, type de vue, version). Alimente `verified_fields` pour que le
   smoke-check sache que ces noms ont été **observés**.
2. **Outil `inspect_page_snapshot(url)`** (connecteurs web et odoo) : liste des éléments
   interactifs visibles (rôle, nom accessible, type), même JS que `_JS_CANDIDATS`, plafonnée
   (≤ 120 éléments) et tronquée proprement, avec la session et le contexte du lot 07.
3. **Catalogue exposé à l'agent** : `catalogue(connector_type, profil)` renvoie `generic/` +
   connecteur + profil ; le prompt n'injecte que ces steps, groupés par intention (connexion,
   navigation, saisie, action, constat UI, constat serveur). Mesure la taille avant/après.
4. **Prompt système** : règles courtes et exemples pour
   - « `Soit` = prérequis, `Quand` = action, `Alors` = constat ; `constater` uniquement en
     `Alors` » (D4, cohérent avec les refus de `write_steps_file` du lot 03) ;
   - « toute création se prouve par un step serveur (lot 08c ou oracle 07e) quand le connecteur
     le permet, pas seulement par un message à l'écran » ;
   - « observe avant de nommer » : appeler `inspect_odoo_view` / `inspect_page_snapshot` avant
     d'utiliser un nom de bouton, de champ ou de menu non présent dans l'annuaire ;
   - « préférer un step de la bibliothèque à du Python » (déjà présent : vérifie qu'il est
     cohérent avec le nouveau catalogue).
   Retire du prompt ce que les gardes déterministes rendent redondant, pour tenir I6.
5. **Garde de réparation des assertions** : `repair_diff` signale au gate, **en bandeau
   distinct**, toute réparation qui modifie un step `@then`, un appel `constater*`, une valeur
   attendue du `.feature` ou supprime un scénario. Le prompt de réparation interdit ces
   modifications ; si l'agent estime l'attendu faux, il doit le dire dans sa réponse, pas le
   changer. Une réparation qui touche un attendu ne peut pas être auto-approuvée
   (`test_auto_approbation_si_propre.py` à étendre).
6. **Réparation guidée par la cause** : le `repair_prompt` reçoit la cause (lot 02), la
   confiance (lot 05) et les paliers de résolution, pas seulement le traceback ; `blocked` et
   `aucun_constat` n'entrent jamais dans la boucle de réparation automatique (vérifie
   `repair_circuit`).

## Tests exigés

- Outils : rendu de `inspect_odoo_view` sur une vue réelle du banc (16/17/18) et sur des
  doublures ; plafond et troncature de `inspect_page_snapshot`.
- `repair_diff` : modification d'un `@then` → bandeau ; auto-approbation refusée.
- Prompt : test de non-régression sur la taille maximale du prompt système (seuil explicite).

## Critères d'acceptation

- [ ] Banc, mode génération : I3 et I4 en hausse par rapport à l'étape 0, I1 = 0, I6 < 1 €.
      Publier les deux mesures avec l'échantillon.
- [ ] Aucune règle nouvelle ne s'appuie sur le texte produit par l'agent pour décider.

Rapport au format `CLAUDE.md` §10 ; lance `verdict-reviewer`.
