# 0012 — Le catalogue dit ce qu'un step FAIT, pas seulement son nom (= A2 de `0007`, activée)

Date : 2026-07-16
Statut : **DÉCIDÉ et LIVRÉ** (annotation prouvée par régénération réelle)
Famille : **3ᵉ occurrence du motif `0007`** — le catalogue montre un **libellé**, l'agent doit en
déduire une **sémantique** que rien n'écrit.

---

## Le motif, pour la troisième fois

| | Ce que l'agent voyait | Ce qu'il a supposé | La réalité |
|---|---|---|---|
| `0003` | la bibliothèque non montrée | qu'il fallait écrire du custom | 43 steps existaient |
| `0007` | `je renseigne le champ "{field}"` | `{field}` = libellé humain | `{field}` = attribut HTML `name` |
| **`0012`** | `je suis **authentifié** en tant qu'utilisateur…` | que ça connecte la session | ça **vérifie** le RPC, ne connecte **rien** |

Trois fois la même racine : **le libellé ne dit pas le comportement**, et l'agent comble le vide
par une hypothèse **raisonnable et fausse**.

Ici, deux steps aux libellés quasi synonymes en français courant :

```python
@given('je suis authentifié en tant qu\'utilisateur défini dans "ODOO_USER" …')
def step_authenticated(context):
    assert context.odoo.env.uid          # VÉRIFIE la session RPC. Ne connecte RIEN.

@given('je me connecte avec mes identifiants utilisateur')
def step_login_portal(context):
    _playwright_login(context)           # CONNECTE le NAVIGATEUR.
```

L'agent a choisi le premier pour ouvrir une page du portail. Le navigateur est resté **anonyme** →
`/achat_vehicule/114` sans aucun formulaire → **les 5 scénarios du cas en échec**.

## L'angle mort de la taxonomie — plus trompeur que « juste par accident »

Le verdict automatique annonçait **« Rôle/permission manquant »**. C'était **faux**, et pas d'un
cheveu : la taxonomie a matché le mot **« role »** dans le **message d'assertion écrit par
l'agent** (« Verifier les prerequis : role group_expert_metier… »), **pas** dans un signal
applicatif. La vraie cause — session navigateur anonyme — n'a **rien** à voir.

C'est le même angle mort qu'en `0007` (« le mot-clé *timeout* suffisait à produire
`wrong_field_name` »), mais **aggravé** : là-bas le verdict était juste par chance ; ici il
**désignait une cause étrangère**, et a failli faire corriger un faux problème. Un diagnostic
guidé par les mots du testeur plutôt que par le comportement de l'application est un diagnostic
qui se cite lui-même. **Consigné au backlog comme observation** (arbitrage du porteur : à garder
pour un futur audit de la taxonomie, pas à corriger dans la foulée).

⚠️ **Ce que ça coûte concrètement** : deux fausses pistes suivies avant la vraie cause. Le rôle
`group_expert_metier` manquait **réellement** (la sonde l'a prouvé, et il a été accordé) — mais ce
n'était **pas** la cause de l'échec. Sans la sonde, on aurait « corrigé » l'environnement et
constaté que rien ne changeait.

## Décision — A2 de `0007`, activée par la docstring

`0007` différait A2 (« annotation par step ») à « plus tard, si d'autres placeholders posent le
même problème ». **Le 3ᵉ cas est arrivé** : le signal est là.

**Mécanisme** : la **première ligne de la docstring** du step devient sa note au catalogue
(`SharedStep.note`, extraite par AST comme le libellé). Rendu dans le prompt sous le libellé :

```
- je suis authentifié en tant qu'utilisateur défini dans "ODOO_USER" …
  → VÉRIFIE la session RPC (odoorpc) — ne connecte PAS le navigateur : pour ouvrir une page
    du portail, utilise « je me connecte avec mes identifiants utilisateur ».
```

**Pourquoi la docstring** plutôt qu'une table d'annotations :
- **le code reste la source de vérité** — une table à part divergerait du comportement réel, et
  personne ne la relirait en modifiant le step ;
- **coût nul là où il n'y a rien à dire** : **0 des 36 steps** avaient une docstring, donc aucun
  effet de bord ; on n'annote **que les pièges** (2 aujourd'hui) ;
- **une seule ligne** est rendue : le catalogue est un **prompt**, pas une documentation — le
  noyer le rendrait moins lu.

Une ligne d'en-tête dit à l'agent de **lire les notes** : une annotation que rien ne signale
serait une annotation ignorée.

## Preuve — régénération réelle

Le cas a été **supprimé puis régénéré** avec le catalogue annoté (la contrainte d'unicité de la
migration 5 refusait le doublon — elle a fonctionné). Résultat, dans le `Contexte` du nouveau
Gherkin :

```gherkin
Et je suis authentifié en tant qu'utilisateur défini dans "ODOO_USER" …   ← vérifie le RPC
Et je me connecte avec mes identifiants utilisateur                        ← ET connecte le navigateur
```

**L'agent emploie désormais les deux**, dans le bon ordre — c'est la lecture correcte, pas un
simple remplacement. Il a compris que l'un ne remplace pas l'autre.

⏭️ **Preuve par EXÉCUTION : en attente du gate.** Le cas est **non relu** (`gate.allowed = False`).
L'invariant §4.3 s'applique — « déjà généré ailleurs » n'exempte pas — et **un cas généré par l'IA
ne peut pas être relu par l'IA** : ce serait vider le gate de son sens. L'exécution attend une
relecture **humaine**.

## Portée

Protège les 3 modules restants à importer (`commande_portail`, `remboursement_client`,
`nouvel_arrivant`) : tous naviguent sur le portail, tous auraient pu tomber dans le même piège.

## Tests

5 tests : note extraite de la 1ʳᵉ ligne de docstring, step sans docstring → pas de note (on
n'annote que les pièges), **les deux steps d'authentification distingués dans le prompt**,
l'en-tête dit de lire les notes, et un step à double décorateur (`@when`+`@then`) n'apparaît pas
deux fois dans la même section.
