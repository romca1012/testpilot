# 0020 — Le test clique un onglet qui se trouve sur une autre page

Date : 2026-07-17
Statut : **À ARBITRER** — note d'abord, aucun code. **Diagnostic fait À LA MAIN, coût LLM : zéro.**
*(Consigne permanente du porteur : en cas d'échec sur une nouvelle cause, documenter et remonter
sans relancer à l'aveugle.)*
Incrément : **2** (§12 — fiabilisation & gouvernance du verdict).
Famille : `0012` (l'agent ne sait pas ce qu'un step partagé FAIT) × `0019` (l'agent devine au lieu
de lire).

---

## Le fait, mesuré sans dépenser un centime

Rejeu du cas 1 (2026-07-17, chemin écran), `exec 30` / `v10` — 2 scénarios sur 3 :

```
playwright._impl._errors.TimeoutError: Locator.click: Timeout 30000ms exceeded.
Call log:
  - waiting for get_by_role("tab", name="Ordinateurs")
```

**Sonde de l'application réelle** (`/tmp/probe_page.py`, via le helper partagé `playwright_login`) :

| page | onglet « Ordinateurs » |
|---|---|
| `/en/my/home` — **là où `playwright_login` dépose le test** | **0** |
| `/en/myservices` — la page du catalogue | **1** — visible, activé, **et le click RÉUSSIT** |

→ **Le locator du test est correct. L'application va bien. Le test n'est simplement pas sur la
bonne page.** Il s'authentifie, atterrit sur `/my/home`, puis clique un onglet qui vit sur
`/myservices` — sans jamais y naviguer.

**Diagnostic `test_a_reparer` : correct.** Cause `wrong_field_name` (« champ/sélecteur
introuvable ») : **trompeuse** — le sélecteur est bon, c'est la **page** qui est fausse. La
catégorie juste serait `wrong_navigation`, qui existe déjà.

---

## La racine : le step d'auth dépose quelque part, et personne ne le dit

`playwright_login` (bibliothèque partagée) finit sur **`/my/home`** — le tableau de bord du
portail, pas le catalogue. **Rien ne le dit à l'agent** : ni le libellé du step
(« je me connecte avec mes identifiants »), ni sa note de catalogue.

L'agent suppose donc qu'après authentification il est « sur le portail », et enchaîne directement
sur un onglet du catalogue. **C'est exactement le motif de `0012`** — *le libellé ne dit pas ce que
le step FAIT* — et c'est la 4ᵉ occurrence de cette famille (`0007`, `0012`, `0017`, `0019`).

> Le step d'auth a un **effet de bord non documenté** : il navigue. Un step qui navigue sans le
> dire oblige le suivant à deviner où il se trouve.

---

## Ce que ce rejeu a prouvé au passage — à ne pas perdre de vue

`0018` **fonctionne** : `v10` a été **adoptée** (`v8 → v10`) alors que le test ne tourne pas
entièrement (1/3). **Le prochain rejeu repartira d'ici, pas de `v1`.** C'est la première fois que
la boucle garde son progrès — le rachat de $0,41/rejeu s'arrête.

Et `0019` a payé : les deux timeouts de 30 s ont disparu, `exec 29` a tourné en **64 s** contre
~300 s, et une réparation coûte désormais **$0,2170** contre $0,2895 (**−25 %**).

---

## Options — à arbitrer, rien n'est tranché

**A — Laisser la boucle la traiter.** Elle repart maintenant de `v10` avec son **budget entier**
(2 tentatives, ≤ $0,62), au lieu de le gaspiller à re-corriger le 404 et l'auth.
*Pour* : c'est **précisément** ce que `0018` a débloqué, et le premier rejeu où observer la boucle
**converger** a un sens. Coût borné et mesuré.
*Contre* : on paie l'agent pour trouver ce qu'une sonde de 3 s a déjà trouvé — le reproche fait à
`0019`. **Nuance** : ici on ne sait pas *comment* l'agent corrigera (naviguer avant ? utiliser un
step de navigation existant ?), alors que pour `0019` la correction était univoque (une valeur).

**B — Corriger à la main**, comme `0019` D : ajouter l'étape de navigation vers `/myservices`.
*Pour* : coût zéro, débloque immédiatement.
*Contre* : **corrige UN cas, pas le motif.** Le prochain module rejouera la même supposition. Et
on écrit du Gherkin à la place de l'agent — à faire deux fois, on ne teste plus l'outil.

**C — Annoter le catalogue** (remède `0012`) : la note du step d'auth dit **où il dépose** —
*« termine sur /my/home (tableau de bord). Le catalogue est sur /myservices : navigue avant de
cliquer un onglet produit. »*
*Pour* : traite la **racine**, protège tous les cas futurs, coût nul. `0012` a **déjà prouvé** que
ce remède porte sur cet agent : *« l'agent emploie désormais les deux steps, dans le bon ordre »*,
et `0017` l'a re-prouvé (`v7` délègue enfin l'auth).
*Contre* : c'est du prompt, donc de l'obéissance — jamais un garde-fou (principe 2). En renfort,
pas en garde.

**D — Corriger la taxonomie** : `Locator.click` en timeout sur un `get_by_role("tab"…)` est une
**navigation** erronée, pas un champ introuvable.
*Contre* : traite le symptôme. Et **attention au piège de `0019`** : `TimeoutError` est ambigu (il
couvre aussi le vrai champ introuvable). Le distinguer exigerait de lire le message — donc du
texte — ou de lever une exception dédiée depuis le helper, ce que `0019` a fait pour les options.

### Recommandation (à valider)

**C + A**, dans cet ordre — et l'ordre compte :
- **`C` d'abord** (coût nul, une ligne) : il retire la **supposition** que l'agent est forcé de
  faire. Sans lui, `A` fait deviner l'agent sur une information que la bibliothèque possède.
- **`A` ensuite** : la boucle repart de `v10` avec son budget entier **et** l'information qui lui
  manquait. C'est le test grandeur nature de `0018` — la boucle converge-t-elle quand elle garde
  son progrès **et** qu'on ne lui cache rien ?

`B` seulement si `C + A` échoue : corriger à la main deux fois de suite reviendrait à écrire le
test nous-mêmes, et l'outil n'aurait plus rien prouvé. `D` à reprendre si le mauvais classement
coûte encore une tentative — mais `C` supprime la cause en amont.

## Questions d'arbitrage

1. **`C + A`, `B`, ou autre chose ?**
2. **Le motif `0012` en est à sa 4ᵉ occurrence** (`0007`, `0012`, `0017`, `0020`) : *le libellé
   d'un step ne dit pas ce qu'il fait*. On continue à annoter au cas par cas, ou c'est le signe
   qu'il faut **générer** la note depuis le code (le principe 6 dit : *« générer plutôt que
   décrire est la forme la plus forte »*) ?
3. **`playwright_login` navigue** — est-ce l'effet de bord qui est fautif, plutôt que son
   annotation manquante ? Un step « je me connecte » qui **déplace la page** est peut-être le vrai
   défaut de conception. *(Non tranché : ça touche la bibliothèque partagée, donc tous les cas.)*

## Le motif

**Quatrième occurrence de `0012` en trois jours.** L'agent ne peut pas savoir ce qu'un step partagé
fait — ici, qu'il **navigue** — donc il suppose. Et comme toujours, l'outil a diagnostiqué de
travers : `wrong_field_name` (« sélecteur introuvable ») pour un sélecteur parfaitement correct sur
la mauvaise page. **On répare le sélecteur, jamais la navigation.**
