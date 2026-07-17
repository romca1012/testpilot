# 0018 — La boucle rachète les mêmes correctifs à chaque rejeu

Date : 2026-07-17
Statut : **À ARBITRER** — note d'abord, aucun code. *(Consigne du porteur : en cas d'échec, ne pas
relancer à l'aveugle ; documenter la cause et remonter avant tout code.)*
Incrément : **2** (§12 du brief — fiabilisation & gouvernance du verdict).
Famille : prolonge `0016` (les deux axes dans la boucle) et `0017` (le rayon d'explosion).

---

## Le fait mesuré : 4ᵉ rejeu, 4ᵉ cause distincte — et c'est un progrès réel

Rejeu du 2026-07-17 (soir), **chemin écran** (`POST /api/cases/1/runs`), budget 2, dry-run branché :

| exécution | version | verdict | scénarios |
|---|---|---|---|
| 25 | v1 | `technical_error / indetermine` | 0/3 |
| 26 | v6 *(réparation 1)* | `technical_error / indetermine` | 0/3 |
| 27 | v7 *(réparation 2)* | `technical_error / indetermine` | **1/3** ✅ |

**Les garde-fous livrés aujourd'hui ont TOUS porté, et c'est mesurable :**

| garde-fou | preuve dans ce rejeu |
|---|---|
| Annotation d'auth (`0017`) | **v7 délègue au step partagé** (`je me connecte avec mes identifiants`), ne code plus `name="login"` en dur |
| Garde transport (`0003`) | aucun `import requests` dans v6 ni v7 |
| **Dry-run branché** (fix P0) | **aucun step `undefined`** — l'échec du rejeu précédent ne s'est pas reproduit |
| Plafond de coût par cas | réparations à $0,4129 ≤ $0,62 : n'a pas eu à couper |
| Principe 5 (non-régression) | rien à protéger (0 scénario vert au départ) — n'a pas bloqué |

**La progression des causes, rejeu après rejeu** — chacune est plus profonde que la précédente :

```
rejeu 1 : HTTPError 404            (transport réinventé)      → corrigé par 0003
rejeu 2 : TimeoutError [name=login] (auth réinventée)         → corrigé par 0017 (annotation)
rejeu 3 : step undefined            (.feature désynchronisé)  → corrigé par le fix P0 (dry-run)
rejeu 4 : TimeoutError select[name='types_demandes']          ← ICI
```

**L'agent pèle une couche par tentative. Le test n'a jamais été aussi près de tourner.**

---

## La cause immédiate — ce n'est PAS un bug applicatif

```
playwright._impl._errors.TimeoutError: Locator.select_option: Timeout 30000ms exceeded.
Call log:
  - waiting for locator("select[name='types_demandes']").first
```

**Sonde du vrai formulaire** (`scripts/probe_champs_formulaire.py`) — le champ **existe et est
visible** :

```
[visible] name='types_demandes'  <select>  libellé affiché : 'Type de demande'
```

→ Le diagnostic `wrong_field_name` → **`test_a_reparer`** est **correct** : l'application va bien,
c'est le test qui ne trouve pas un champ pourtant présent (mauvaise page, ou état de page
différent — **non diagnostiqué : le budget était épuisé**). Le scénario `[ERREUR]` passe
(`success/conforme`), les deux autres non.

---

## ⚠️ LE VRAI PROBLÈME, ET IL EST STRUCTUREL : v7 est jetée

`v7` est **objectivement meilleure** que `v1` : elle délègue l'auth, ne réinvente aucun transport,
et fait passer **1 scénario sur 3** là où `v1` en passe **0**. Elle est pourtant **rejetée**, et le
disque **rembobiné sur `v1`**.

**Pourquoi** : `est_executable` exige `derive_verdict(outcome).execution_status == success` — donc
que **TOUS** les scénarios tournent techniquement. Avec 2 scénarios sur 3 en `technical_error`, le
verdict global est `technical_error` → non exécutable → non adoptée.

> **`0016` a corrigé « réparée = passe au vert » en « réparée = tourne ». Mais « tourne » est
> resté du tout-ou-rien.** Une version où 1/3 des scénarios tournent proprement est traitée
> exactement comme une version où 0/3 tournent.

### La conséquence, chiffrée : on rachète les mêmes correctifs à chaque rejeu

Chaque rejeu **repart de `v1`** — donc de l'`HTTPError 404`. Le budget de 2 tentatives est dépensé
à **re-corriger ce qui l'avait déjà été au rejeu précédent** :

- tentative 1 → re-corrige la navigation / le transport *(déjà fait au rejeu 1)*
- tentative 2 → re-corrige l'auth *(déjà fait au rejeu 2)*
- budget épuisé → **tout est jeté** → le rejeu suivant recommencera par le 404

**Coût de ce rachat : $0,4128 par rejeu, pour ré-acheter du travail déjà payé.** Le cumul du cas 1
atteint **$1,1552**, et c'est **cette boucle** qui l'explique — pas la cherté d'une réparation.

> **La boucle ne peut pas converger.** Elle a besoin de ~4 tentatives pour atteindre le fond ; elle
> en a 2 ; et elle ne garde rien entre deux sessions. Augmenter le budget ne suffirait pas : sans
> adoption du progrès partiel, chaque session **recommence à zéro**.

---

## Ce que le §9 mesure vraiment — une question à trancher au passage

`total_for_case_usd(1)` = **$1,1552 = 107 % du §9**, et le script affiche « ⚠️ DÉPASSE ».
**Ce n'est pas un dépassement au sens du brief.** Le §9 dit : *« Coût — nouveau cas de test
(génération + exécution + rapport) : < 1 € »*. Il mesure une **création**, une fois. Le cas 1, lui,
cumule **5 sessions de débogage de l'outil** et 7 versions.

**Mesuré sur une création réelle** (chemin écran, ce matin) : **$0,1207 = 11 % du §9**. C'est
**ça**, le §9 — et il est tenu, largement.

→ **À trancher** : `total_for_case_usd` répond à « combien ce cas a coûté depuis toujours », pas à
la question du §9. Faut-il mesurer le §9 **par création** (première génération + premier run) et
compter le reste comme du coût d'exploitation ? *Je ne tranche pas : c'est une définition produit.*

---

## Le coût d'une réparation, re-mesuré (le fix P0 a payé)

| | coût/tentative |
|---|---|
| Référence d'avant le fix P0 *(avec un tour LLM perdu)* | $0,2895 |
| **Ce rejeu** : $0,3088 puis **$0,1041** | **$0,2065 en moyenne — −29 %** |

Le dry-run branché supprime un appel LLM par tentative sur le chemin heureux : **mesuré, plus
extrapolé**. ⚠️ **2 échantillons, et très dispersés** ($0,3088 vs $0,1041) : le coût dépend du
nombre de tours de la boucle ReAct, pas d'un tarif fixe. Le plafond $0,62 reste correct.

---

## Options — à arbitrer, rien n'est tranché

**A — Adopter sur le PROGRÈS de l'axe exécution, pas sur sa perfection.**
Adopter si le nombre de scénarios en `technical_error` **diminue** strictement (et que le principe
5 ne signale aucune régression). `v7` (2 échecs techniques) serait adoptée contre `v1` (3) ; le
rejeu suivant repartirait de `v7` et attaquerait `types_demandes` **avec son budget entier**.
*Pour* : la boucle converge, chaque session capitalise, le rachat disparaît. Coût **nul** (les deux
runs sont déjà faits — c'est la même donnée que le principe 5).
*Contre* : on adopte une version **non relue** qui ne tourne pas encore entièrement — mais elle
repasse déjà `to_review` (§4.3), donc un humain ratifie.

> ### 🔴 **`A` A UN TROU, ET JE L'AI MESURÉ AVANT DE LA RECOMMANDER**
>
> « Moins d'échecs techniques » **s'obtient en supprimant les scénarios qui échouent.** J'ai
> vérifié les deux cas contre le code réel de `regressions()` :
>
> | l'agent supprime… | le principe 5 mord ? |
> |---|---|
> | un scénario qui **passait** (`success/conforme`) | ✅ **oui** — `regressions()` rend `['A']`, adoption refusée |
> | un scénario **en échec technique** | ❌ **NON** — `regressions()` rend `[]` |
>
> Le principe 5 ne surveille que les scénarios **verts** avant/après. Supprimer les deux scénarios
> qui échouent fait tomber le compteur d'échecs de 2 à 0 : **`A` adopterait une version qui a
> supprimé la moitié de la couverture**, et le run suivant paraîtrait *parfait*.
>
> C'est **exactement** le motif que `PRINCIPES.md` nomme comme le plus dangereux : *« l'absence de
> signal prise pour un signal positif — sous sa forme la plus dangereuse, puisque supprimer la
> couverture améliore les chiffres »*. `A` telle quelle **rouvre cette porte**.
>
> **`A` n'est donc recevable qu'accompagnée d'une garde de couverture** : le nombre de scénarios
> du `.feature` ne doit pas diminuer (ou aucun scénario nommé ne doit disparaître — le
> `scenario_name` est persisté, la comparaison est gratuite). Coût **nul**, même donnée que le
> principe 5. **Sans elle, je ne recommande pas `A`.**

**B — Augmenter le budget de tentatives.**
*Contre* : ne règle **rien** seul. Sans adoption du progrès partiel, la session suivante recommence
à zéro de toute façon. Et ça coûte linéairement ($0,21/tentative).

**C — Ne pas rembobiner le disque quand la réparation échoue.**
Garder la dernière version tentée comme point de départ du prochain rejeu, sans la promouvoir
`current_version`.
*Contre* : réintroduit exactement le « affiché ≠ réel » que `_sync_disque` a été écrit pour tuer
(la base dirait `v1`, le disque exécuterait `v7`). **À écarter sous cette forme.**

**D — Statu quo : l'humain reprend la main après épuisement du budget.**
C'est ce que le **§6 du brief** prévoit (*« le premier seuil atteint déclenche une escalade vers un
humain avec un rapport de ce qui a été essayé »*), et le rapport existe (`what_was_tried`).
*Contre* : l'escalade actuelle **jette le travail** en même temps qu'elle escalade. L'humain
reprend un cas rembobiné sur `v1`, et ne voit pas que `v7` faisait passer un scénario.

### Recommandation (à valider)

**`A` + garde de couverture, et jamais `A` seule.** C'est le seul changement qui fasse **converger**
la boucle, il est à **coût nul** (mêmes runs, déjà payés), et il ne touche **pas** au droit de
l'agent d'explorer (§6/§11.2 du brief : on n'ajuste pas ce qu'il **écrit**, on ajuste ce qu'on
**garde**). La garde de couverture n'est pas un raffinement optionnel : sans elle, `A` transforme
« supprimer la couverture » en **stratégie gagnante**.

**`D` reste vrai et compatible** : l'escalade du §6 a toujours lieu au seuil, mais elle escalade
alors un cas **qui a progressé** au lieu d'un cas rembobiné sur `v1`.

**`B` est à écarter seule** (ne règle rien sans `A`), **`C` est à écarter** (rouvre « affiché ≠
réel »).

## Questions d'arbitrage

1. **`A` + garde de couverture, `D` seul (statu quo), ou autre chose ?**
2. **Le §9 se mesure-t-il par CRÉATION** (première génération + premier run), le reste étant du
   coût d'exploitation ? Ou le cumul de la vie d'un cas est-il la bonne mesure ? *(Aujourd'hui
   `total_for_case_usd` dit « depuis toujours » — d'où le « 107 % » alarmant et faux.)*
3. **`types_demandes`** : le prochain rejeu (avec `A`, en repartant de `v7`) l'attaquerait avec son
   budget entier. **On tente, ou on diagnostique à la main d'abord ?** *(Le champ existe et est
   visible : la piste la plus probable est que le test n'est pas sur la bonne page — non vérifié.)*

## Le motif

Encore une **erreur que l'outil se fabrique à lui-même** — mais cette fois ce n'est pas l'agent qui
la produit, c'est **la boucle qui refuse son propre progrès**. Le motif de `0016` remonte d'un
cran : on avait corrigé « le test doit PASSER » en « le test doit TOURNER » ; il reste
« il doit tourner **ENTIÈREMENT** », et un test à moitié réparé vaut zéro. **Le tout-ou-rien est
plus tenace que l'axe qu'il habite.**
