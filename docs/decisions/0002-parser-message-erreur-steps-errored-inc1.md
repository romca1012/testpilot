# 0002 — Parser d'exécution : capturer le message des steps « errored » (Inc. 1)

Date : 2026-07-15
Statut : **implémenté** (Inc. 1) — voir « Implémentation » ci-dessous
Priorité : **HAUTE**

## Contexte

Découvert lors du premier e2e complet sur `demande_materiel`. Les 3 scénarios ont
« erroré » (statut behave `error`, pas `failed`) sur un step de contexte. Le rapport à
deux axes a correctement conclu `execution_status=technical_error`,
`functional_status=indetermine`, mais avec `cause_category=unknown` et un message vide.

Le message d'erreur réel EXISTE — visible via le formatter `plain` :

```
requests.exceptions.HTTPError: 404 Client Error: NOT FOUND for url:
    http://localhost:10017/web/dataset/call_kw
```

Mais `execution/behave_runner.py` lance behave en `-f json`, et le message n'y figure pas.
Résultat : `traceback_summary` et `raw` restent vides → `defect_taxonomy` ne peut classer
que `unknown`.

> **Correction de l'analyse initiale (au moment de l'implémentation).** Cette note supposait
> que `parse_behave_json` « ne récupérait pas » le message : c'était faux — le parser lisait
> bien `error_message` pour `failed` **et** `error`. La donnée n'était simplement **jamais
> écrite**. Cause réelle, vérifiée dans la source de behave 1.3.3 :
> ```python
> # behave/formatter/json.py
> if step.error_message and step.status == Status.failed:   # ← 'error' exclu
> ```
> behave ≥1.3 a scindé `Status.failed` (assertion) et `Status.error` (exception). Le message
> existe pourtant côté modèle (`Step._process_error` fait `self.error_message = …`) : seule
> la sérialisation le jetait.

## Décision

Corriger en **Incrément 1** (hors périmètre PoC). La PoC a atteint son but : prouver le
pipeline bout-en-bout et un verdict à deux axes honnête.

## Pourquoi priorité HAUTE

Sans ce correctif, **tout** futur échec technique restera `technical_error / unknown` —
opaque. On perd la valeur du diagnostic causal (§5) exactement quand on en a besoin :
distinguer « test à réparer » d'un vrai problème, orienter la réparation, alimenter le
disjoncteur (`repair_circuit`) avec une vraie cause plutôt qu'`indetermine`.

## Implémentation (faite) — 4 volets

L'investigation a révélé **deux défauts supplémentaires**, dont un plus grave que le bug
d'origine. Les quatre ont été traités ensemble :

**B. `error_message` en LISTE → crash (le plus critique).** Le formatter natif a
`split_text_into_lines = True` : dès que le message est multi-ligne (erreur Playwright
« Call log: … », assertion détaillée), il écrit une **liste**. `parse_behave_json` supposait
une chaîne → `TypeError` → l'exception était rattrapée par `run_execution` → run clos en
`technical_error`. **Une assertion en échec (= `vrai_bug`) était donc rétrogradée en erreur
technique** : le faux-négatif §5 que le produit doit rendre impossible. Corrigé par
`error_text()` (liste/None/str → chaîne), appliqué à tous les points d'entrée.

**A. Message des steps « errored ».** Formatter maison
`behave_runtime/tp_json_formatter.py` : sous-classe du `JSONFormatter` natif qui ajoute le
seul cas manquant (`error`/`hook_error`), assemblé dans le run_dir et référencé par
`-f tp_json_formatter:FullJSONFormatter`. Repli automatique sur `-f json` s'il est absent.
Écarté : ajouter `-f plain` et corréler par regex — fragile et contraire au principe « le
JSON est la source fiable, zéro regex ».

**C. Taxonomie — sinon on troque « opaque » contre « faux avec assurance ».** Une fois le
message récupéré, `404 … NOT FOUND for url: …` tombait en `wrong_field_name`
(« Champ/sélecteur introuvable ») car `normalize_error` remplace l'URL par `<url>` et
« not found » matche ce mot-clé. Ajout d'un symptôme `http_error` et de motifs
(`httperror`, `client error`, `server error`, `not found for url`) sur `WRONG_NAVIGATION`,
qui précède `WRONG_FIELD_NAME` : une erreur HTTP sur une route est un problème de
**parcours**. Un `403` reste un problème de **droit** (priorité préservée, testée).

**D. Statuts Behave ≥1.3.** `error` / `hook_error` / `cleanup_error` traités explicitement
comme des échecs (ils ne l'étaient que par accident) : une fixture en échec (Odoo
injoignable) reste un échec honnête, jamais un `passed`.

## Conséquence pour la PoC

Aucune régression : le verdict reste correct (technical_error), seule la finesse de la
cause est temporairement dégradée à `unknown`. Voir [[0003-agent-reutiliser-steps-partages-inc1]].
