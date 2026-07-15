# 0002 — Parser d'exécution : capturer le message des steps « errored » (Inc. 1)

Date : 2026-07-15
Statut : acté — reporté à l'Incrément 1
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

Mais `execution/behave_runner.py` lance behave en `-f json`, et
`execution/behave_result.py::parse_behave_json` ne récupère pas le `error_message` pour
les steps au statut `error` (il le fait pour `failed`). Résultat : `traceback_summary` et
`raw` restent vides → `defect_taxonomy` ne peut classer que `unknown`.

## Décision

Corriger en **Incrément 1** (hors périmètre PoC). La PoC a atteint son but : prouver le
pipeline bout-en-bout et un verdict à deux axes honnête.

## Pourquoi priorité HAUTE

Sans ce correctif, **tout** futur échec technique restera `technical_error / unknown` —
opaque. On perd la valeur du diagnostic causal (§5) exactement quand on en a besoin :
distinguer « test à réparer » d'un vrai problème, orienter la réparation, alimenter le
disjoncteur (`repair_circuit`) avec une vraie cause plutôt qu'`indetermine`.

## Piste de correction

Dans `parse_behave_json` : pour un step de statut `error` comme `failed`, lire
`result.error_message` (behave le peuple aussi pour `error`) ; gérer le cas où c'est une
liste de lignes (le joindre) avant de le passer à `classify_failure`. Ajouter un test de
non-régression sur une sortie JSON behave contenant un step `error`.

## Conséquence pour la PoC

Aucune régression : le verdict reste correct (technical_error), seule la finesse de la
cause est temporairement dégradée à `unknown`. Voir [[0003-agent-reutiliser-steps-partages-inc1]].
