# 0015 — La taxonomie classe sur du texte écrit par l'agent qu'elle juge

Date : 2026-07-16 · **DÉCIDÉ et LIVRÉ le 2026-07-17**
Statut : **LIVRÉ** — arbitré point par point par le porteur, puis implémenté, mesuré sur données
réelles et prouvé (`scripts/prove_0015_signal_vs_texte.py`).
Famille : suite de `0007` (même fragilité), rendue **urgente** par `0014`.

---

## Arbitrage du porteur (2026-07-16) et ce qui a été livré

| # | Question | Verdict | Livré |
|---|---|---|---|
| 1 | A, B ou C ? | **A** — le type d'exception prime, le texte en dernier recours | `classify_failure` : SIGNAL → SYMPTÔME → INDICE ; `step_text` n'est plus lu |
| 2 | `broken_test_code` ? | **Nouvelle catégorie** | `BROKEN_TEST_CODE` → `test_a_reparer` déterministe |
| 3 | Persister `step_text` ? | **Oui** (migration 10), *« on ne pourrait sinon jamais auditer si 0015 a vraiment amélioré les choses »* | Migration 10 + remontée parser → verdict → base → API |
| 4 | Mots-clés de domaine | **Maintenant**. `missing_server_context` : *« voie dégradée, pas de suppression — la cause est réelle et documentée, mais ne doit jamais décider seule de la réparabilité, seulement informer en dernier recours »* | `team_id`/`many2one`/`accesserror`/`group_` retirés ; `MISSING_SERVER_CONTEXT` → `indetermine` |

## ⚠️ Ce que la note ignorait — et qui l'aurait vidée de son effet

La note affirmait : *« un `AssertionError` restera `vrai_bug` quoi qu'écrive l'agent »*. **C'était
faux en run réel.** Vérifié dans la source de Behave 1.3.3 (`model.py:1888`) :

```python
schema = u"ERROR: {e_classname}: {e}"
if isinstance(exception, AssertionError):
    schema = u"ASSERT FAILED: {e}"        # ← le nom de la classe DISPARAÎT
...
if use_traceback:                          # use_traceback = config.verbose
    schema += u"\n{traceback}"             # ← pas de traceback hors mode verbose
```

**Behave n'écrit jamais « AssertionError ».** Conséquences mesurées sur les données réelles :

- les **5** assertions en base portent `ASSERT FAILED:` — aucune ne porte `AssertionError` ;
- la clé `AssertionError` de la carte des signaux était donc **du code mort en run réel** ;
- `_ASSERT_RE` du parser (`AssertionError:`) était mort aussi → `failure_type = unknown` pour
  **toutes** les assertions réelles ;
- signal et symptôme étant aveugles **ensemble**, les assertions retombaient sur les **mots-clés** —
  exactement la couche que cette décision rétrograde. **La porte du faux négatif restait ouverte
  là où 0015 prétendait l'avoir fermée** : un `ASSERT FAILED: … permission denied …` écrit par
  l'agent serait devenu `missing_role` → `test_a_reparer`.

Mon premier test de garde ne l'a pas vu : il testait `AssertionError: …`, une forme que Behave
n'émet **jamais**. Il passait en validant un monde qui n'existe pas — **la même erreur que
l'épisode B+ de `0007`**, où le test de garde omettait `environment.py`.

**Correctif.** `ASSERT FAILED:` et le statut de step `failed` sont produits par **Behave**, pas par
l'agent : ce sont des signaux au même titre qu'un type d'exception. Ils sont désormais reconnus, et
testés **en premier** — dans la taxonomie comme dans le parser — parce que « c'est une assertion »
est acquis avant que le message de l'agent ne commence. Les gardes partent maintenant des messages
**réellement en base** (`tests/test_taxonomy_signal.py`).

## Mesuré sur les données réelles (20 scénarios en échec)

| | Avant | Après |
|---|---|---|
| Le même `TypeError`, 4 noms de step | **4 causes** différentes | **1** (`broken_test_code`) |
| Vrai bug + step `…"team_id"…` | `test_a_reparer` ⚠️ | `vrai_bug` ✔ |
| Décidé par un signal (Behave/Python) | — | **14/20** |
| Reclassés | — | **9/20** |

**Le témoin du cas 6 est corrigé** (`scenario_result` #40) : le faux `missing_role` de `0012` —
qui venait du mot `group_expert_metier` dans un message **écrit par l'agent**, et qui a envoyé
l'enquête deux fois sur une fausse piste — devient `assertion_mismatch` → `vrai_bug`, le régime
honnête pour une assertion. La cause réelle (spec périmée) reste à trancher par un humain : c'est
la limite de `defect_origin`, que seule la file de confirmation (`0001` élargi) lèvera.

**Le coût, assumé et non caché.** Une assertion « sémantique » (l'agent écrit « le champ caché est
resté vide ») tombait en `test_a_reparer` par mots-clés ; elle devient `vrai_bug` → le circuit
s'arrête. **On sur-arrête donc plus sur cette voie** — la note promettait « on sur-arrête moins »,
ce qui n'est vrai que du chemin `TypeError`. Sur-arrêter est la direction sûre (§4.4 tolère le faux
positif, `0013` permet de l'infirmer) ; réparer un test correct contre une application cassée ne
l'est pas.

**Ce qui reste au repli par mots-clés : 6/20.** Trois sont des échecs sans aucune erreur stockée ;
deux (#4, #5) sont des lignes **héritées**, écrites avant le correctif de l'écart 3 — leur
`error_summary` a été tronqué **par la tête** et la ligne d'exception n'y a jamais été stockée. Ce
n'est pas une régression : la re-mesure ne peut pas voir un signal absent de la base.

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

## Recommandation (état AVANT arbitrage — conservée telle quelle)

> ⚠️ Deux affirmations de cette section ont été **démenties par la mesure**, et sont corrigées en
> tête de note : (1) *« un `AssertionError` restera `vrai_bug` quoi qu'écrive l'agent »* — faux en
> run réel, Behave n'écrit jamais « AssertionError » ; (2) *« on sur-arrête moins »* — vrai du seul
> chemin `TypeError` ; sur les assertions sémantiques, on sur-arrête **plus**.

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

## Questions d'arbitrage — **toutes tranchées** (verdicts en tête de note)

1. ~~**A, B ou C ?**~~ → **A**
2. ~~**`broken_test_code`** : nouvelle catégorie, ou repli sur `wrong_field_name` ?~~ → **nouvelle catégorie**
3. ~~**Persister `step_text`** pour rendre la classification auditable ?~~ → **oui, migration 10**
4. ~~**`team_id`** : maintenant, ou avec l'audit complet ?~~ → **maintenant** ; `missing_server_context` en **voie dégradée**

## Ce qui reste ouvert après 0015

- **6/20 échecs restent classés au repli** (dont 3 sans erreur stockée). Le repli n'est plus
  décisif, mais il n'est pas vide.
- **`defect_origin` reste une déduction** : un `assertion_mismatch` → `vrai_bug` peut être une spec
  périmée (cas 6). Sans la file de confirmation (`0001` élargi), un `not_required` est définitif et
  irrévocable. **0015 rend le classement honnête ; il ne le rend pas juste.**
- **Le statut de step de Behave** (`failed` = assertion, `error` = exception) est un signal encore
  plus sûr que son rendu textuel, et il n'est pas exploité : le parser met tous les statuts
  d'échec dans le même sac. À reprendre si le rendu textuel montre une autre faille.

## Le motif, une cinquième fois

Ce défaut est une variante de celui de la journée : **une donnée écrite par le composant jugé sert
à le juger**. `0012` l'avait nommé (« un diagnostic qui se cite lui-même ») ; `0014` lui a donné
du pouvoir. À surveiller partout ailleurs : la seule protection durable est de ne juger que sur
des signaux que le composant jugé **ne produit pas**.

**Et son corollaire, appris ici à mes dépens** : un garde-fou qui prétend ne lire que des signaux
doit être vérifié **contre la sortie réelle du producteur de signaux**, pas contre l'idée qu'on
s'en fait. `AssertionError:` n'a jamais existé dans nos runs ; deux couches de classement étaient
mortes sans que rien ne le signale — encore *« l'absence de signal prise pour un signal
positif »*, cette fois dans le code censé la corriger. C'est la source de Behave qui a tranché,
pas mon intuition.
