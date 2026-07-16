# 0015 — La taxonomie classe sur du texte écrit par l'agent qu'elle juge

Date : 2026-07-16
Statut : **À ARBITRER** — note d'abord, aucun code. Priorité fixée par le porteur : **avant**
l'exécution groupée.
Famille : suite de `0007` (même fragilité), rendue **urgente** par `0014`.

---

## Pourquoi maintenant, et pas au backlog

Jusqu'à hier, une classification fausse coûtait un **libellé faux** à l'écran et une fausse piste
d'enquête. On l'a vu deux fois — `0007` (« timeout » → `wrong_field_name`, juste **par chance**)
et `0012` (« Rôle manquant » venait du mot « role » dans un message **écrit par l'agent**, la vraie
cause n'avait rien à voir : deux fausses pistes suivies).

**`0014` a changé la nature du risque.** La classification décide désormais de **ce qui est
réparable** : `defect_origin` pilote `repair_circuit.evaluate()`. Une erreur de classement ne fait
plus afficher un mauvais mot — elle **autorise ou refuse une boucle de réparation**.

Et le risque n'est **pas symétrique** :

- `test_a_reparer` classé `vrai_bug` → on sur-arrête → **sans danger** (§4.4 tolère le faux
  positif, et `0013` permet désormais de l'infirmer) ;
- **`vrai_bug` classé `test_a_reparer` → la boucle répare un test CORRECT contre une application
  cassée.** C'est la direction du **faux négatif**, que §4.4 déclare **inacceptable**.

Ce qui protège aujourd'hui de ce second cas : la règle anti-maquillage du prompt et le plafond de
budget. **L'obéissance d'un LLM et un compteur** — pas un garde-fou déterministe.

## Le défaut, mesuré

`defect_taxonomy.classify_failure()` classe sur `step_text + traceback_summary + raw`, par
mots-clés testés **dans un ordre de priorité**. Or `step_text` est le **libellé Gherkin écrit par
l'agent**, et le message qui suit `AssertionError:` aussi.

**Le même échec — le `TypeError` réel du cas 2 — classé quatre fois différemment, selon le seul
nom du step :**

| `step_text` | cause | origine |
|---|---|---|
| `…le champ "team_id" pointant vers…` *(le vrai step du cas 2)* | `missing_server_context` | **test_a_reparer** |
| `Alors le ticket est créé` *(neutre)* | `unknown` | **indetermine** → le circuit s'arrête |
| `Alors la route "/tickets" répond` | `wrong_navigation` | **test_a_reparer** |
| `Alors le timeout est respecté` | `wrong_field_name` | **test_a_reparer** |

**Le cas dangereux, reproduit** — un **vrai bug applicatif** avec un nom de step malheureux :

```
AssertionError: le ticket devrait être en état 'validé', obtenu 'brouillon'
  step « Alors le ticket est validé »                    → vrai_bug        ✔ correct
  step « Alors le champ "team_id" du ticket est correct » → test_a_reparer  ✘ RÉPARABLE À TORT
```

C'est **exactement** le scénario que le porteur avait anticipé.

⚠️ **Trois aggravants relevés au passage :**

1. **`step_text` n'est pas persisté.** `scenario_result` stocke `scenario_name`, pas le step. La
   classification est donc **inauditable a posteriori** — on ne peut pas savoir ce qui l'a décidée.
   (Ma première sonde s'est trompée pour cette raison : elle mesurait `scenario_name`.)
2. **`team_id` est un mot-clé en dur** dans une taxonomie déclarée « connector-agnostic ». C'est un
   champ d'un module Odoo précis, figé dans un module générique.
3. **Le pire classement est le plus juste des trois.** Un `TypeError` **nu** tombe en `unknown` →
   `indetermine` → le circuit **s'arrête**. Or un `TypeError` dans le code d'un step est **la chose
   la plus réparable qui soit** : c'est un bug dans du code que *nous* avons écrit, l'application
   n'y est pour rien. La taxonomie refuse de réparer précisément ce qu'elle devrait réparer.

## Le signal existe, et il est déterministe

Le **type d'exception** est produit par Python/Playwright — **jamais par l'agent**. Mesuré sur nos
échecs réels : `TimeoutError` ×3, `TypeError` ×1.

```
TimeoutError    → l'élément n'est pas là            → test à réparer
TypeError,
AttributeError,
KeyError…       → bug DANS LE CODE du step          → test à réparer (l'app n'y est pour rien)
AssertionError  → le test attendait autre chose     → jugement humain
AccessError/403 → droit manquant                    → environnement
HTTPError 4xx   → parcours faux                     → test à réparer
```

Le **`Call log`** de Playwright (le sélecteur attendu) et le **statut HTTP** sont également
déterministes. Ce qui ne l'est pas : le `step_text` et le **message** après `AssertionError:`.

## Options

**A — Classer sur le TYPE d'exception d'abord, le texte en dernier recours.** Le type décide ;
les mots-clés ne servent qu'à affiner *à l'intérieur* d'un type, jamais à le contredire.
`step_text` sort du texte classé.

**B — Retirer seulement `step_text`.** Minimal. **Insuffisant** : le message d'`AssertionError`
est aussi écrit par l'agent — c'est lui qui a produit le faux « Rôle manquant » de `0012`.

**C — Deux couches : signal (déterministe) + indice (texte), le signal gagnant toujours.**
Équivalent à A avec une traçabilité explicite de ce qui a décidé.

## Recommandation (à valider — rien n'est tranché)

**A, avec une nouvelle catégorie.** Le type d'exception prime ; `step_text` n'est plus lu ; le
message ne sert qu'à affiner. Et surtout : **`broken_test_code`** (`TypeError`, `AttributeError`,
`KeyError`, `NameError`, `ImportError`…) → **`test_a_reparer` déterministe**. Un `TypeError` dans
notre code n'est *jamais* un bug de l'application — aujourd'hui il tombe en `indetermine` et
bloque la réparation.

Effet attendu, non symétrique et voulu : on **répare mieux** (le `TypeError` du cas 2 devient
réparable **par son type**, plus par la chance d'un nom de step) et on **sur-arrête moins** — tout
en fermant la porte au faux négatif, puisqu'un `AssertionError` restera `vrai_bug` quoi qu'écrive
l'agent dans son message.

**Persister `step_text`** (migration) : sans lui, aucune classification n'est auditable. À
trancher — c'est un ajout de schéma pour une raison de traçabilité, pas de fonctionnalité.

**`team_id` en dur** : à sortir de la taxonomie générique. Sa place est dans les règles du
**connecteur**, si elle est quelque part.

## Questions d'arbitrage

1. **A, B ou C ?**
2. **`broken_test_code`** : nouvelle catégorie, ou repli sur `wrong_field_name` (moins juste, zéro
   migration de vocabulaire) ?
3. **Persister `step_text`** pour rendre la classification auditable ?
4. **`team_id`** : le sortir maintenant, ou avec l'audit complet des mots-clés ?

## Le motif, une cinquième fois

Ce défaut est une variante de celui de la journée : **une donnée écrite par le composant jugé sert
à le juger**. `0012` l'avait nommé (« un diagnostic qui se cite lui-même ») ; `0014` lui a donné
du pouvoir. À surveiller partout ailleurs : la seule protection durable est de ne juger que sur
des signaux que le composant jugé **ne produit pas**.
