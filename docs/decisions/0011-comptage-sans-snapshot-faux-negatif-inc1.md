# 0011 — Un comptage sans point de comparaison passait en silence (chaîne de faux-négatif)

Date : 2026-07-16
Statut : **DÉCIDÉ et LIVRÉ**
Famille : **suite immédiate de `0010`** (vérification creuse dans la **bibliothèque partagée**),
mais **décision propre** — voir ci-dessous.

---

## Pourquoi une décision propre et non une suite de `0010`

Le porteur a posé la question. Le projet a déjà tranché ce type de cas : `0007` est une décision
**propre** bien qu'étant « de famille commune avec `0008`/`0003` », **parce que le remède
différait**. Même situation ici :

| | `0010` | `0011` |
|---|---|---|
| Mécanisme | `pass` **inconditionnel** | `warn` + `return` **conditionnel** |
| Le step | ne vérifiait **jamais** rien | vérifie **sauf** si un prérequis manque |
| Remède | **suppression** (promesse intenable) | **échec explicite** (la vérification est légitime) |

`0010` était clos et livré : y greffer un correctif au mécanisme et au remède différents aurait
brouillé la trace.

## Le défaut — une chaîne muette AUX DEUX BOUTS

Trouvé par le garde de `0010` (`test_chaque_then_partage_assertit_ou_delegue_explicitement`),
qui a signalé trois `@then` de plus. Vérification : ils **délèguent** bien une vraie assertion —
mais leurs helpers avaient ceci :

```python
def memorize_record_count(context, model):        # ← LE POSEUR
    try:
        setattr(context, attr, context.odoo.env[model].search_count([]))
    except Exception as exc:
        warnings.warn(f"Impossible de mémoriser le count : {exc}")   # avale l'échec

def check_count_not_increased(context, model):    # ← LE VÉRIFICATEUR
    if not hasattr(context, attr):
        warnings.warn(f"Aucun snapshot initial pour '{model}'.")
        return                                     # sort SANS asserter
    ...
```

**La chaîne complète du faux-négatif** :
1. le poseur échoue → **avale** son exception, aucun snapshot ;
2. le vérificateur ne trouve pas le snapshot → **`warn` + `return`**, aucune assertion ;
3. le `@then` passe → **scénario VERT qui n'a rien vérifié**.

`warnings.warn` **n'échoue pas un test**. Le verdict devenait donc **déclaratif** (§4.2) et
produisait exactement le **faux-négatif** que §4.4 déclare **inacceptable**. C'est aussi le motif
de `0007` : **un repli ne doit jamais être silencieux**.

**Aggravant** : ce sont les helpers les **plus réutilisés** de la bibliothèque. La mesure de
`0003` (run #1) montrait que l'agent réutilise **les trois** steps de comptage — c'est le succès
de `0003` qui donnait sa portée à ce défaut. Et le piège est réaliste : un `@then` « le nombre
augmente de 1 » **sans** le `@given` de snapshot passe **toujours**. Rien n'obligeait l'agent à
générer les deux ensemble.

## Décision — ÉCHOUER, avec un message actionnable

Un comptage sans point de comparaison est un **test incomplet**, pas un test qui passe.

- `memorize_record_count` **lève** au lieu d'avaler : échouer **là où la cause est visible**
  plutôt que laisser le scénario finir au vert sans rien avoir prouvé. La cause d'origine est
  conservée (`from exc`).
- `_require_snapshot()` (extrait, point unique) **lève** en **nommant le step manquant** — un
  message qui dit seulement « ça a raté » n'aide personne. Le libellé cité est **vérifié comme
  existant au catalogue** par un test : nommer un step inexistant enverrait le lecteur dans le mur.
- Le comportement utile est **intact** : avec snapshot, les comparaisons passent et échouent comme
  avant.

## Portée du changement — assumée

Un scénario qui comptait **sans** snapshot passait au vert et **échouera désormais**. C'est le
but : il ne prouvait rien. Aucun cas actuel n'est concerné (les deux du référentiel posent leur
snapshot dans le `Contexte`), mais un futur cas mal généré échouera — **bruyamment**, ce qui est
précisément l'intention.

## Tests — le motif, pas seulement les cas trouvés

9 tests, sans Odoo (faux `context`) : échec sans snapshot pour les deux vérificateurs, message
actionnable, **libellé cité présent au catalogue**, comportement intact avec snapshot (passe et
échoue quand il faut), et le poseur qui n'avale plus.

Le garde central est `test_aucun_warn_puis_return_dans_les_helpers` : il détecte **`warn` suivi de
`return`** par AST **dans tout le fichier**, pas dans les trois fonctions corrigées — un échec
déguisé en succès. **Vérifié qu'il échoue sur l'ancien code et passe sur le nouveau** : c'est un
garde-fou réel, pas un test complaisant.

## Lien avec le reste

- `0010` — même bibliothèque, même famille (vérification creuse), remède différent.
- `0008` — même conséquence (faux « conforme »), mais dans le code **généré**.
- `0007` — même principe : **un repli silencieux est un mensonge**.
- ⚠️ **L'angle mort du lint reste ouvert** (cf. `0010`, § *Suite*) : il ne regarde que le code
  généré, jamais la bibliothèque. Ces deux défauts ont été trouvés **à la main**, à l'occasion
  d'un audit d'import — pas par l'outillage.
