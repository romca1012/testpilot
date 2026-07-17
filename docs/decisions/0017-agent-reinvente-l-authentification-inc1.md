# 0017 — L'agent réinvente l'authentification que la bibliothèque résout déjà

Date : 2026-07-17
Statut : **À ARBITRER** — note d'abord, aucun code.
Famille : `0012` (l'agent ignore ce que fait un step partagé) × `0003` (ne pas réinventer ce que
la bibliothèque fournit).
**Bloquant de fait pour clore `0016`** — voir « Pourquoi ça bloque » ci-dessous.

---

## Le fait mesuré

Rejeu réel du cas 1 (exécutions 20 → 22), budget 2, **les deux tentatives échouent** :

```
playwright._impl._errors.TimeoutError: Page.fill: Timeout 30000ms exceeded.
Call log:
  - waiting for locator("[name=\"login\"]")
    - locator resolved to <input id="login" type="text" name="login" required class="form-control"/>
    - fill("admin")
  - attempting fill action
    2 × waiting for element to be visible, enabled and editable
      - element is not visible
```

Le step en échec est **`Soit le demandeur est authentifié sur le portail des services`** — un
libellé **inventé par l'agent**. La bibliothèque partagée, elle, fait exactement ce travail et
gère précisément ce piège (`_base_steps.py:189-190`, `_base_helpers.py:135-136`) :

```python
context.page.wait_for_selector("input[name='login']", state="attached", timeout=15000)
context.page.locator("input[name='login']").fill(context.odoo_user, force=True)
```

`state="attached"` et `force=True` : **le champ de login existe mais n'est pas visible.** Le step
partagé `je me connecte avec mes identifiants utilisateur` le sait. L'agent, qui a réécrit sa
propre authentification avec un `fill` nu, ne le sait pas — et ne peut pas le savoir.

**Ce n'est pas de l'aléa LLM.** `v9` (la réparation qui a réussi, exec 17) **déléguait** l'auth au
step partagé — son résumé le dit : *« step_auth_portail devient une simple vérification de
précondition »*. `v10` et `v11` l'ont réimplémentée. Même cause, résultats opposés.

## Le contraste qui donne la réponse

Le même rejeu montre un garde-fou qui **fonctionne**, sur exactement le même agent :

| | garde-fou | résultat |
|---|---|---|
| **Transport** (`0003`) | `write_steps_file` refuse `import requests` et `/web/dataset` (AST + texte) | `v10`/`v11` **ont corrigé** le `HTTPError 404` — l'agent n'avait **pas le choix** |
| **Authentification** | *aucun* | `v10`/`v11` réinventent l'auth et échouent |

Le `404` de `v1` est d'ailleurs un **héritage** : avec le garde-fou `0003` d'aujourd'hui, `v1`
n'aurait jamais pu être écrite. Le garde-fou déterministe a fait son travail ; il manque
simplement son équivalent pour l'auth.

## La racine, et une tension qu'il faut nommer

L'échec du cas 1 était dans le step de **baseline RPC**. Pourquoi l'agent a-t-il touché à
l'**auth** ? Parce que `write_steps_file` **remplace le fichier entier**, et que le contrat le lui
impose (correctif du **bug 2 de `0014`**) :

> *« Rends le fichier ENTIER — tous les steps, y compris ceux que tu ne modifies pas : ce que tu
> n'écris pas est PERDU. »*

Chaque réparation réécrit donc ~14 000 caractères de code **qui marchait**, pour corriger un step.
Le correctif du bug 2 de `0014` est ce qui rend `0017` possible : deux garde-fous en tension.

Les protections existantes ne couvrent pas ce cas :

- `reserved_steps` refuse de **redéfinir un step partagé par son LIBELLÉ**. L'agent n'a rien
  redéfini : il a **inventé un autre nom** pour le même travail. **Le garde-fou bloque la
  collision de noms, pas la duplication de comportement.**
- Le catalogue des steps partagés **est** dans le prompt de réparation
  (`build_repair_prompt`) — le voir ne suffit donc pas.

## Pourquoi ça bloque `0016`

Le chemin positif de `A` (« un test qui tourne mais révèle un vrai bug est adopté ») exige un cas
qui **parte d'une erreur technique** et dont la réparation produise une version **exécutable**.
Mesuré, aucun cas alternatif ne convient :

| cas | dernier run | peut-il servir ? |
|---|---|---|
| 2 — Validation champ requis | `success/conforme` | **Non** : le test passe → aucun échec → 0 tentative de réparation (mesuré : 0 diagnostic, 0 réparation) |
| 6 — Achat véhicule | `success/non_conforme` | **Non** : le test tourne déjà → le circuit s'arrête sur `vrai_bug` → 0 tentative (mesuré : 1 diagnostic, **0** réparation) |
| 1 — Demande de matériel | `technical_error` | Le seul possible — **et c'est celui que `0017` bloque** |

Ironie utile : **c'est le succès de la journée qui a retiré les témoins.** Les cas 2 et 6 n'ont
plus d'erreur technique, donc plus rien à réparer.

## Options

**A — Annoter le catalogue** (remède `0012`). Le step partagé d'auth porte une note : *« le champ
login n'est pas visible sur ce portail ; un `fill` nu échoue ; ce step le gère (`force=True`). Ne
réimplémente jamais l'authentification. »*
Coût : quasi nul. **Limite** : c'est du prompt, donc l'obéissance d'un LLM — ce que ce projet a
écrit noir sur blanc ne pas considérer comme un garde-fou (`0015`).

**B — Garde déterministe à l'écriture, sur le modèle EXACT de `0003`.** `write_steps_file` rejette
un fichier qui refait l'authentification, avec un message qui **nomme** le step partagé à utiliser.
Coût : une heuristique, et un **risque de faux positif** réel — un cas qui testerait légitimement
la page de login (« connexion refusée avec un mauvais mot de passe ») serait bloqué. À cadrer.

**C — S'attaquer à la racine : ne plus exiger la réécriture du fichier ENTIER.** Une réparation
ciblée ne toucherait pas au code qui marche.
Coût : **rouvre le bug 2 de `0014`** (l'agent rendait 1 step sur 4, les 3 autres devenaient
`undefined`). Chantier réel, à ne pas improviser.

**D — Statu quo + budget plus large.** Coût : brûle des appels LLM au hasard, **n'atteint jamais
zéro erreur technique** (critère 2), et ne clôt pas `0016`.

## Recommandation (à valider — rien n'est tranché)

**B porteur + A en renfort** — la forme exacte du verdict de `0007` (« le correctif technique
porte, le prompt renforce »). L'argument n'est pas théorique : **`0003` prouve que ce type de
garde marche sur cet agent précis**, dans ce rejeu précis. L'agent a corrigé le transport parce
qu'un garde-fou déterministe le lui imposait, et a raté l'auth parce que rien ne le lui imposait.

`C` est probablement juste sur le fond — réécrire 14 000 caractères pour corriger un step est une
source de régression permanente — mais c'est un chantier qui rouvre un défaut déjà payé. À traiter
comme une dette nommée, pas dans la foulée.

## Questions d'arbitrage

1. **A, B, A+B, ou C ?**
2. **Où vit la garde ?** ⚠️ Le garde-fou transport de `0003` a déjà tranché — et **mal** :
   `_FORBIDDEN_ENDPOINTS = ("/web/dataset", "/jsonrpc", "/xmlrpc")` sont des endpoints **Odoo**, en
   dur dans `tools/write.py`, un module générique. **C'est exactement la faute que `0015` vient de
   retirer de la taxonomie** (`team_id` dans un module « connector-agnostic »). On reproduit le
   placement existant (cohérent, mais on aggrave la dette), ou on met la règle d'auth dans les
   **règles du connecteur** et on note la dette de `0003` ?
3. **Le contrat « fichier ENTIER »** (`C`) : dette nommée au backlog, ou chantier à ouvrir
   maintenant ?

## Un point ouvert, que je ne tranche pas

`force=True` dans le step partagé est lui-même un **contournement** : il passe outre « element is
not visible ». Si le champ de login est caché pour une raison légitime (formulaire replié derrière
un bouton), le geste correct serait de **déplier**, et `force=True` masque peut-être un vrai
comportement de l'application. Je n'ai pas mesuré ce point — je le signale plutôt que de
l'affirmer, et il ne conditionne pas l'arbitrage ci-dessus.

## Le motif

Encore une **erreur technique que l'outil se fabrique à lui-même** — ni l'application testée, ni
le test écrit par un humain n'y sont pour rien. C'est le critère 2 à l'œuvre : chaque garde-fou
manquant devient une erreur technique à diagnostiquer plus tard. Et le motif précis est celui de
`0012` : **l'agent ne sait pas ce qu'un step partagé FAIT**, donc il le refait — moins bien.
