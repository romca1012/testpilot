# 0013 — Un humain peut confirmer OU INFIRMER un diagnostic (remplace `0001`)

Date : 2026-07-16
Statut : **DÉCIDÉ et LIVRÉ** (plan validé avant tout code)
Migration : **8** (`repair_attempt.human_verdict` / `human_origin` / `human_comment`)
Remplace : **`0001`** (« Confirmations `pending_human` ») — intitulé trop étroit, voir ci-dessous.
Décale : la **réparation** devient `0014`.

---

## Pourquoi `0001` ne suffisait pas

`0001` parlait de traiter la file des `pending_human`. La mesure a montré que le trou est plus
large : **un `not_required` faux est irrévocable**. Il ne fallait donc pas une file d'attente,
mais une **surface d'arbitrage** — un humain doit pouvoir juger un diagnostic **quel que soit son
régime**.

## Le constat, mesuré

**Aucun diagnostic n'était jamais tranché.** Les 8 produits à ce jour avaient tous
`confirmed_by = NULL` : il n'existait **aucun endpoint, aucun écran** pour confirmer. L'UI
affichait pourtant « En attente de validation humaine » — une promesse que rien ne tenait (§4.6).

- un `pending_human` attendait une confirmation **qui ne pouvait pas arriver** (7 en file) ;
- un `not_required` était **définitif**, même faux (1).

**§4.4 dit « faux-positif acceptable », pas « faux-positif irréversible ».** Il est acceptable
*parce qu'*un humain le corrige. Sans exutoire, l'asymétrie perd sa justification.

**Cas réel qui l'a révélé** : le cas 6 est classé `vrai_bug` / `not_required`. Or la sonde prouve
que l'application **fonctionne** — elle refuse correctement un formulaire incomplet ; c'est la
spec importée qui est périmée (le test ne remplit que 4 des 8 champs requis). Un faux « bug
applicatif » qu'on ne pouvait pas infirmer.

## Décision — l'humain JUGE, il ne corrige pas

**Le point de conception qui commande tout le reste.** La décision humaine est une **couche
distincte**, jamais une réécriture :

```
defect_origin        ← ce que la MACHINE a déduit  — JAMAIS modifié
human_verdict        ← confirmed | overturned      — ce que l'HUMAIN a jugé
human_origin         ← sa correction, si infirmé
human_comment        ← POURQUOI — la seule chose qui vaudra encore dans six mois
confirmed_by / _at   ← existaient déjà, jamais alimentés
```

Si l'humain **écrasait** `defect_origin`, on perdrait ce que la machine avait déduit — donc toute
possibilité de mesurer si la taxonomie s'améliore ou dérive. C'est **précisément la donnée qui
manque** pour l'audit de la taxonomie (backlog). Avec cette couche, « la machine a dit `vrai_bug`,
l'humain a dit `test_a_reparer`, voici pourquoi » devient **mesurable**.

**Infirmer exige l'origine réelle** (contrainte applicative) : dire « ce n'est pas ça » sans dire
ce que c'est efface une information sans en produire.

## Endpoints

- `GET /api/repairs?project_id=&status=pending|all` — `all` inclut les **`not_required`** : c'est
  tout l'objet. Les diagnostics déjà tranchés sont exclus.
- `POST /api/repairs/{id}/verdict` — **409** si déjà arbitré : écraser en silence effacerait le
  jugement d'un autre relecteur.

`reviewer` est un **champ libre** (aucune authentification, cohérent avec le gate) — vide devient
`anonyme` : ça dit la vérité, là où une chaîne vide laisserait croire à une donnée manquante.

`cause_label` est rendu **côté serveur** via `defect_taxonomy.LABELS` — **même source que le
rapport**, plutôt qu'un second vocabulaire dans `status.ts` qui divergerait (§4.7 : jamais d'enum
brute à l'écran).

## UI

Onglet **Confirmations**, **sous Exécution** (on juge le résultat d'un run, pas le référentiel —
§8/§4.8), avec un **compteur** de la file : une file qu'on ne voit pas est une file qu'on ne
traite pas — c'est exactement ce qui a laissé 8 diagnostics en plan.

L'écran montre **machine et humain côte à côte**, jamais l'un à la place de l'autre.

⚠️ **`vrai_bug` a reçu une infobulle** : « Bug dans l'application » était affirmé **sans réserve**
alors que c'est une **déduction**. L'infobulle dit désormais que le test attendait autre chose que
ce qu'il a obtenu, et que ça peut aussi venir d'un test qui attend la mauvaise chose.

## Ce qu'on ne fait PAS

- **Aucun blocage** : un diagnostic non tranché ne retient rien. Le gate reste le **seul** verrou
  (§4.3) ; un second brouillerait la promesse.
- **Aucun recalcul des deux axes** (§4.2) : infirmer un diagnostic ne change **pas**
  `execution_status`/`functional_status`. Ces axes sont la conséquence d'une **exécution réelle** —
  un avis humain ne réécrit pas ce qui s'est passé. L'arbitrage porte sur l'**origine du défaut**.
  **Gardé par test.**
- **Pas de « rejouer » depuis cet écran** : ça touche à la réparation → `0014`.

## Tests — 15

Le diagnostic machine **intact** après infirmation (le test central), infirmer sans origine
refusé, verdict/origine inconnus refusés, un `not_required` **arbitrable** mais **absent** de la
file « à confirmer », sortie de file après arbitrage, **scope projet** (§4.8), contexte porté
(cas/module/projet), migration 8 idempotente, **les deux axes inchangés après arbitrage**, 409 si
déjà tranché, 422 sans origine, 404 inconnu, `reviewer` vide → `anonyme`.

## Suite — un trou de robustesse trouvé au passage (non corrigé)

L'exécution 10 est restée **`not_executed`** alors qu'elle a réellement tourné (ses 5
`scenario_result` sont en base, corrects). Déclencheur : une migration appliquée pendant qu'un
serveur tournait avec l'ancien code — accident de manipulation. **Mais il révèle un vrai défaut** :
`run_service._finalize_error`, le filet censé clore un run planté en `technical_error /
indetermine` (§4.5), **appelle lui-même `finalize()`** — si `finalize()` est la cause du plantage,
le filet tombe avec. L'exécution reste alors dans un état qui **ment** : « Pas lancé » pour un run
qui a tourné (§4.6). À traiter séparément.
