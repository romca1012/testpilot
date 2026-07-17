# 0019 — `select_option` : une valeur inventée produit une erreur qui accuse le mauvais coupable

Date : 2026-07-17
Statut : **À ARBITRER** — note d'abord, aucun code. **Diagnostic fait À LA MAIN, coût LLM : zéro**
(consigne du porteur : *« on ne dépense pas de budget pour deviner une deuxième fois »*).
Incrément : **2** (§12 — fiabilisation & gouvernance du verdict).
Famille : `0007` (le sens d'un paramètre de step) × `0002` (le message d'erreur ment sur la cause).

---

## Le fait, mesuré sans dépenser un centime

Le rejeu du cas 1 (exec 27, `v7`) échoue sur 2 scénarios /3 :

```
playwright._impl._errors.TimeoutError: Locator.select_option: Timeout 30000ms exceeded.
Call log:
  - waiting for locator("select[name='types_demandes']").first
```

**Sonde du vrai formulaire** (`/formulaire/1`, via le helper partagé `playwright_login`) :

```
select[name='types_demandes']  →  count=1, visible=True, enabled=True
OPTIONS RÉELLES :
   'nouvel_entrant'        | 'Demande de nouvel entrant'
   'remplacement_materiel' | 'Remplacement de matériel existant'
```

**Le `.feature` généré demande :**

```gherkin
Et le champ demande "types_demandes" est rempli avec "new"
```

→ **`"new"` n'existe pas.** Les seules valeurs sont `nouvel_entrant` et `remplacement_materiel`.

---

## ⚠️ L'erreur accuse le mauvais coupable — et toute la chaîne l'a crue

`Locator.select_option: waiting for locator("select[name='types_demandes']")` **donne à croire
que le select est introuvable**. Il ne l'est pas : il est là, visible, activé — et le code du step
le vérifie lui-même (`if locator.count() > 0:` **avant** l'appel). Playwright attend en réalité
l'**option** `value="new"`, qui n'arrivera jamais ; son message de log, lui, ne nomme que le
**locator du select**.

**Toute la chaîne a suivi cette fausse piste :**

| couche | ce qu'elle a conclu | juste ? |
|---|---|---|
| `defect_taxonomy` | `ui_timeout` → **`wrong_field_name`** → « Champ/sélecteur introuvable » | ❌ **faux** — le champ est là |
| l'agent de réparation | a cherché un problème de **sélecteur** | ❌ a corrigé à côté |
| moi, au rapport du rejeu | « le champ existe pourtant… cause non diagnostiquée » | 🟡 j'ai vu l'anomalie sans la trancher |

> **C'est `0002` qui se rejoue** : le message d'erreur ne porte pas la vraie cause, et tout ce qui
> le lit se trompe **dans la même direction**. Et c'est `0007` sur le fond : **le paramètre d'un
> step a une sémantique que rien ne dit** — `{value}` d'un `<select>` doit être une **valeur
> d'option existante**, pas un libellé, pas une invention.

**Le diagnostic `test_a_reparer` reste correct** (l'application va bien), mais **sa cause est
fausse**, donc l'agent répare la mauvaise chose — et rebrûle du budget à chaque tentative.

---

## Pourquoi l'agent invente `"new"`

La spec ne fixe pas la valeur. L'agent a **inventé un identifiant plausible** (`new` pour « nouvel
entrant ») au lieu de **lire les options réelles**. Il en a pourtant les moyens : `inspect_form`
existe, et la sonde ci-dessus prend 3 secondes.

C'est le motif de `0003`/`0012` transposé aux **données** : l'agent réinvente ce que l'application
sait déjà — sauf qu'ici il ne réinvente pas du code, il **devine une valeur**.

---

## Options — à arbitrer, rien n'est tranché

**A — Rendre l'erreur honnête** *(coût nul, aucun LLM)*. Le step partagé/le helper vérifie que la
valeur existe **avant** `select_option`, et échoue avec un message qui nomme la vraie cause **et
les valeurs possibles** :
> *« `types_demandes` : la valeur "new" n'existe pas. Options : nouvel_entrant,
> remplacement_materiel. »*
*Pour* : transforme un timeout de 30 s trompeur en échec **instantané et exploitable** ; l'agent
reçoit la bonne information et corrige **du premier coup** ; `defect_taxonomy` cesse de classer
`wrong_field_name` à tort. Économise 30 s × N tentatives **et** des réparations à côté.
*Attention* : ce helper est **dans la bibliothèque partagée** → il protège **tous les cas futurs**
(comme `0010`/`0011`).

**B — Corriger la taxonomie** : un `select_option` en timeout n'est pas `wrong_field_name`.
*Pour* : `0015` a posé la règle — classer sur le **signal**, pas sur le texte. Ici le signal
(`TimeoutError` + `select_option` dans le message **écrit par Playwright**, pas par l'agent) permet
une catégorie propre : « valeur d'option inexistante ».
*Contre* : traite le **symptôme** en aval. `A` supprime la cause en amont.

**C — Annoter le catalogue** (remède `0012`) : *« la valeur d'un `<select>` doit être une valeur
d'option existante — ne l'invente jamais, lis-la »*.
*Contre* : c'est du prompt, donc de l'obéissance — ce que ce projet refuse de considérer comme un
garde-fou (`PRINCIPES.md`, principe 2). **En renfort uniquement.**

**D — Corriger le `.feature` du cas 1 à la main** (`"new"` → `"nouvel_entrant"`).
*Pour* : débloque **immédiatement** le rejeu et le chemin positif de `0016`.
*Contre* : **corrige UN cas, pas le motif** — le suivant réinventera une valeur ailleurs. Et ça
touche un artefact généré par l'IA, que le gate doit relire.

### Recommandation (à valider)

**A + D** : `A` ferme le motif **structurellement et à coût nul** dans la bibliothèque partagée
(donc pour tous les cas futurs) ; `D` débloque le cas 1 **maintenant**, pour que le rejeu `0018`
prouve enfin le chemin positif de `0016` — sinon il rebutera sur cette même valeur, avec un budget
gaspillé à chercher un sélecteur qui n'a aucun problème.
`C` en renfort, `B` à faire si `A` ne suffit pas (mais `A` rend l'échec explicite **avant** la
taxonomie, donc `B` perd sa raison d'être).

## Questions d'arbitrage

1. **A + D, ou A seule** (et on laisse le rejeu re-tenter avec son budget) ?
2. **`D` touche un `.feature` généré par l'IA.** On corrige la valeur à la main et on **ratifie au
   gate** (§4.3), ou on laisse l'agent le refaire une fois `A` en place — ce qui coûte une
   tentative mais garde la main de l'IA sur ses artefacts ?
3. **`B`** : la taxonomie doit-elle distinguer « valeur d'option inexistante » de « champ
   introuvable », ou `A` suffit-elle ?

## Le motif

**Trois fois le même jour** : `0017` (l'agent réinvente l'auth), `0018` (la boucle jette son propre
progrès), et maintenant `0019` — **l'agent invente une donnée que l'application pouvait lui
dire**. Et comme en `0002`, l'outil s'est menti à lui-même : le message d'erreur accusait le
sélecteur, la taxonomie l'a cru, l'agent a réparé à côté, et le budget a brûlé. **Une erreur
technique que l'outil se fabrique, puis diagnostique de travers.**
