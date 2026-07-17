# 0016 — « Réparée » veut dire « passe au vert » : les deux axes fusionnés dans la boucle

Date : 2026-07-17
Statut : **À ARBITRER** — note d'abord, aucun code. Trouvé en mesurant le taux d'erreurs
techniques demandé par le porteur, pas en relisant le code.
Famille : `0014` (la boucle de réparation) × invariant **§4.1** (les deux axes ne fusionnent
jamais).

---

## Le fait, mesuré sur le cas 1

Rejeu réel du 2026-07-17 (exécutions 16 → 17) :

| | version | verdict | ce que ça veut dire |
|---|---|---|---|
| avant réparation | `v1` | `technical_error/indetermine` **0/3** | `HTTPError 404` sur `/web/dataset/call_kw` — le test utilisait `requests` au lieu d'`odoorpc`. **L'outil est aveugle : il ne juge rien.** |
| après réparation | `v9` | `success/non_conforme` **1/3** | Le test **tourne**. 2 scénarios échouent sur des assertions — **l'outil produit un constat sur l'application.** |

**L'agent a réussi exactement ce qu'on attend de lui** : il a supprimé `requests`, tout fait
passer par `context.odoo` (odoorpc) et `context.page` (Playwright), et transformé une cécité
technique en verdict fonctionnel.

**Et cette version a été jetée.**

`v9` n'a pas été adoptée, le disque a été rembobiné sur `v1` (vérifié : `import requests` est de
retour dans `behave_runtime/generated/demande_materiel_steps.py`), et `test_case.current_version_id`
vaut toujours `v1`. **Un nouveau run du cas 1 refera le `HTTPError 404`.**

## La cause : un seul mot

```python
session.resolved = (session.outcome == "resolved")   # ⇔ ZÉRO échec
...
reference = current_version_id if session.resolved else version_id   # sinon : rembobinage
```

`resolved` ne vaut que si le run est **entièrement vert**. Or :

- « le test **tourne** » est l'axe **exécution** ;
- « le test **passe** » est l'axe **fonctionnel**.

Le critère d'adoption les **fusionne** — c'est **§4.1**, l'invariant que tout le reste du projet
tient scrupuleusement, violé au cœur de `0014`. Et il l'est dans la direction la plus coûteuse :

> **Un test réparé qui détecte un vrai bug ne peut JAMAIS être adopté.**
> Plus l'application est défectueuse, moins l'outil sait garder ses propres réparations.

C'est le contraire du but affiché : *« l'outil répare/diagnostique l'application »*. Ici, l'outil a
diagnostiqué, puis a effacé sa réparation **parce que** le diagnostic était négatif.

Le §5 le dit déjà, ailleurs, exactement comme il faut — `validation_status_after_run` :

> *« Validé » = joué en entier sans interruption technique (exécution=success), **quel que soit le
> statut fonctionnel** : un test qui tourne et détecte un vrai bug reste un test validé.*

La boucle de réparation, elle, applique la règle inverse.

## L'incohérence visible qui en découle (§4.6)

Le cas 1 affiche aujourd'hui :

- `validation_status = validated` et `last_execution_status = success/non_conforme` — obtenus sur
  **`v9`** ;
- `current_version_id = v1` — la version **cassée**, seule à pouvoir être exécutée.

**L'écran promet un état que la version courante ne redonnera pas.** Le statut est vrai du run qui
l'a produit (§4.2 tient : il vient d'une exécution réelle), mais il est attaché à un cas dont la
référence a été rembobinée juste après. C'est « affiché ≠ réel » par un chemin nouveau : non pas un
statut inventé, mais un statut **orphelin de la version qui l'a produit**.

## Options

**A — `resolved` devient « le test tourne » (`execution_status == success`).** Aligné sur §4.1 et
sur `validation_status_after_run`. La version réparée est adoptée dès qu'elle rend le test
exécutable, et repasse `to_review` pour ratification humaine (le gate reste souverain, `0014`
option (i) inchangée). Conséquence : on adopterait `v9`, et le cas 1 dirait enfin « l'application
ne se comporte pas comme la spec l'exige » — un constat, ce pour quoi l'outil existe.

**B — Deux issues distinctes** : `resolved` (vert) et `rendu_executable` (tourne mais non
conforme), la seconde adoptée **et** signalée différemment à l'écran. Plus fin, plus de vocabulaire.

**C — Statu quo, et on assume.** À condition de le dire : la réparation ne sert alors que les cas
où l'application est **saine**. Sur une application défectueuse — le cas d'usage réel de l'outil —
elle ne garde rien.

## Recommandation (à valider — rien n'est tranché)

**A.** Le critère d'adoption doit lire l'axe **exécution**, jamais le fonctionnel — c'est
littéralement §4.1, et la règle est déjà écrite et éprouvée dans `validation_status_after_run`. Le
garde-fou contre l'adoption d'un test complaisant n'est pas « il doit être vert » : c'est le
**gate humain** (`to_review`, jamais approuvé d'office) et la règle anti-maquillage du prompt.

⚠️ **Le risque à ne pas se cacher** : un agent pourrait « réparer » un test en supprimant les
assertions gênantes — le test tournerait, donc serait adopté. Aujourd'hui l'obligation d'être vert
ne protège pas de ça non plus (un test vidé passe au vert *plus* facilement). Les protections
réelles restent le gate, le lint d'assertions infalsifiables (`0008` phase C) et la ratification.
À dire explicitement dans l'arbitrage plutôt qu'à découvrir après.

## Questions d'arbitrage

1. **A, B ou C ?**
2. Si A : le cas 1 doit-il être **rejoué** pour adopter `v9` (une réparation coûte un appel LLM),
   ou `v9` adoptée directement depuis l'historique (elle a déjà tourné : exec 17 en est la preuve) ?
3. L'incohérence « statut orphelin » (statut d'un cas produit par une version rembobinée) :
   corrigée par A (la version est adoptée), ou faut-il en plus **interdire** qu'un statut de cas
   survive au rembobinage de la version qui l'a produit ?

## Le motif

Ce n'est pas *« une donnée écrite par le composant jugé sert à le juger »* — c'est l'autre motif de
la semaine : **un critère binaire qui écrase une distinction que tout le reste du système
maintient**. La taxonomie (`0015`) confondait le texte et le signal ; ici la boucle confond
« tourne » et « passe ». Dans les deux cas, l'invariant existait, écrit noir sur blanc — il n'était
simplement pas appliqué là.
