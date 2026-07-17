# 0021 — Graphe applicatif : la mesure du domaine, et ce qu'elle tranche

Date : 2026-07-17
Statut : **ÉTAPE 1 FAITE (mesure) — ÉTAPE 2 À ARBITRER.** Le graphe n'est pas construit : consigne
du porteur (*« ne construisez pas le graphe complet sans mon accord sur la granularité »*).
Incrément : **2** (§12 — fiabilisation & gouvernance du verdict).
Racine commune à : `0003`, `0007`, `0008`, `0012`, `0013`, `0015`, `0017`, `0019`, `0020`.

---

## ÉTAPE 1 — LE CHIFFRE

Crawl déterministe, **aucun LLM** : `scripts/crawl_domaine.py` (reproductible, méthode dans sa
docstring).

| mesure | valeur |
|---|---|
| **Routes distinctes** (normalisées `/x/{id}`) | **38** |
| Pages portant au moins un formulaire | **30** |
| Champs nommés, tous formulaires | **397 occurrences → 383 distincts** |
| `<select>` | **60**, dont **46** à options finies et énumérables |
| Transitions de route | **494** |
| Onglets internes (changent l'**état**, pas la route) | **95** |

> **397 vs 383** — vérifié plutôt que laissé traîner : **14 champs partagent un `name` avec un
> voisin de la même page**. Ce sont des **groupes de radios** (`priority` = Standard/Élevé/Urgent,
> un seul `name`, 3 `<input>`) et des `ticket_id` en doublon. C'est du HTML normal, pas une
> anomalie. Le graphe devra les **regrouper par `name`** — un radio se pilote par sa **valeur**,
> exactement comme un `<select>`.

### Couverture des 3 cas existants — **borne HAUTE**

| | sollicité |
|---|---|
| Champs | **178 / 383 = 46 %** |
| `<select>` | **35 / 60 = 58 %** |
| Routes | **5 / 38 = 13 %** |

> ⚠️ **Borne haute, volontairement grossière** : on compte un nom de champ **cité** dans le
> Gherkin/les steps, pas un champ réellement exercé. La vraie couverture est **plus basse**. Si
> même la borne haute donne 13 % des routes, la conclusion tient a fortiori.

---

## Ce que la mesure révèle — et ça tranche (a) vs (b)

**Les gros chiffres sont des répétitions, pas de la diversité.** Trois vérifications :

### 1. Les 494 transitions sont un menu, pas un graphe

**10 cibles** sont atteignables depuis **≥ 70 %** des pages (`/my/home`, `/user/account`,
`/shop/cart`, `/contactus`…) : c'est le **menu global**, répété sur chaque page.

```
361 / 494 arêtes  =  menu global (73 %)
133 / 494 arêtes  =  navigation SPÉCIFIQUE — le vrai graphe
```

### 2. Les 46 `<select>` sont 39 objets distincts, dont un monstre

**46 occurrences → 22 noms distincts → 39 couples (nom + jeu d'options).** Et `country_id` (**251
options**, sur 3 pages) pèse à lui seul plus que tout le reste : c'est une **liste de référence**,
pas une règle métier. Les vrais `<select>` métier ont **2 à 3 options** (`types_demandes`,
`fonction_materiel`, `type_investissement`…).

### 3. Les formulaires partagent un noyau — mais **42 % seulement**

Sur les **17 formulaires de service** :

| | |
|---|---|
| Champs présents dans **17/17** | `name`, `partner_name`, `partner_email`, `product`, `team_id` |
| Présents dans **14/17** | `order`, `search`, `agence` |
| **Noyau commun (≥ 70 %)** | **8 champs** |
| Champs d'un formulaire médian | **19** |
| **Part du noyau** | **42 %** |
| Champs propres à **un seul** formulaire | **81 / 129 (63 %)** |

> **Le pattern existe, mais il ne couvre pas la majorité.** 58 % d'un formulaire médian est
> spécifique — `date_mutation_client`, `numero_cheque`, `montant_cheque`, `type_lettrage`… Ce sont
> des **champs métier**, et c'est exactement là que l'agent invente : `types_demandes = "new"`
> (`0019`) est dans les 58 %, pas dans le noyau.

**⇒ Générer des patterns ne suffirait pas.** Un gabarit « formulaire de service Odoo » donnerait
les 8 champs communs — ceux que l'agent ne rate jamais — et laisserait deviner les 58 % qui posent
problème. **(b) tel qu'énoncé (« graphe partiel + génération de patterns ») ne traite pas la classe
de bugs visée.**

---

## ÉTAPE 2 — Recommandation : **(a), et le domaine est petit**

**38 routes, 30 formulaires, 397 champs, 39 selects distincts.** C'est l'ordre de grandeur des
« dizaines » du critère (a) — le crawl entier prend **~4 minutes**, sans LLM.

**Trois arguments, mesurés :**

1. **C'est déjà fait.** `scripts/crawl_domaine.py` **est** le constructeur du graphe : il produit
   déjà `pages / champs / options / transitions / onglets` en JSON (594 Ko). Il reste à le
   **figer, versionner et faire relire** — pas à l'écrire.
2. **Le coût de maintenance est borné et mesurable** : re-crawler = 4 min de machine, zéro euro.
   Un diff entre deux crawls dit exactement ce qui a bougé.
3. **Le domaine ne croît pas comme l'application** : 38 routes portent **13 modules de service**
   déjà en production. Les 3 cas existants n'en couvrent que 13 %. **Le graphe est en avance sur
   le référentiel de tests, pas en retard.**

### Ce que je recommande de NE PAS mettre dans le graphe

- **`country_id` et ses 251 options** : liste de référence, pas une règle. La citer en entier
  noierait le prompt. → **compter les options, ne pas toutes les lister** au-delà d'un seuil.
- **Le menu global (361 arêtes)** : répété partout, il n'apprend rien. → ne garder que les **133
  arêtes spécifiques**.
- **Le back-office Odoo** (`/web`, `/odoo`) : hors du produit testé. **Décision assumée** — si un
  cas vise un jour le back-office, **cette mesure est caduque**.

### La contrepartie, à dire

Un graphe est une **photo**. Il vieillit dès qu'un développeur ajoute un champ, et il dira alors
« ce champ n'existe pas » **à tort**. C'est pourquoi tout ce qui le consomme doit être
**détective** (§6 du brief + borne du principe 2), et pourquoi chaque avertissement porte **la date
du modèle**.

---

## ÉTAPE 4 — Le smoke-check : livré, et prouvé sur les données réelles

Indépendant du graphe (consigne : *« quel que soit le résultat de l'étape 2 »*).
`src/testpilot/generation/smoke_check.py` — module **pur**, aucune I/O, aucun LLM, **coût nul**.

**La preuve, sur les vraies données** : le `.feature` de `v1` **tel qu'il était en base**, passé au
modèle **tel que le crawl l'a mesuré** →

```
[valeur_option_inexistante] ligne 20 : types_demandes
    « new » n'est pas une option connue. Valeurs relevées : nouvel_entrant, remplacement_materiel…
[valeur_option_inexistante] ligne 48 : types_demandes
```

**Les 2 occurrences de `0019`, vues avant le premier run, pour $0.** Elles avaient coûté 2 timeouts
de 30 s, un diagnostic faux (`wrong_field_name` — « sélecteur introuvable », alors que le select
est là), une réparation à côté et du budget brûlé.

**8 tests**, dont deux qui verrouillent ce que le smoke-check **ne peut pas** faire :

- **`0020` n'est PAS vu** : les champs et valeurs sont corrects, c'est la **page** qui est fausse.
  Un module pur et sans état ne suit pas la navigation. Attraper `0020` demande le **graphe de
  transitions** — l'étape 3.
- **Sans modèle, il se tait — et son silence ne vaut PAS validation.** L'appelant ne peut pas le
  déduire d'une liste vide ; c'est le motif « l'absence de signal prise pour un signal positif ».

**Non branché au gate** : le contrat de sortie est celui du lint `0008` (`list[dict]`, même
bandeau), mais le brancher est une décision — je ne l'ai pas prise seul.

---

## Questions d'arbitrage

1. **(a), (b) ou (c) ?** Je recommande **(a)** — le domaine est petit (38 routes), le constructeur
   existe déjà, et **(b) ne traiterait pas la classe de bugs visée** (58 % d'un formulaire est
   spécifique, et c'est là que l'agent invente).
2. **Brancher le smoke-check au gate maintenant** (même bandeau non-bloquant que `0008`), ou
   attendre la décision sur le graphe ?
3. **Le graphe consomme-t-il le crawl à chaud, ou un JSON versionné et relu ?** Votre cadrage dit
   *« source de vérité versionnée, revue par un humain »* → un JSON en dépôt, régénéré à la
   demande, diffé avant adoption. **À confirmer** : ça fige aussi la relecture humaine dans le
   flux git plutôt que dans l'UI.
4. **`0020` reste ouverte** (navigation manquante) : le graphe la traiterait à la racine
   (transitions + point de dépôt de l'auth). On attend le graphe, ou on annote le catalogue
   maintenant (`C + A` de la note `0020`) ?

## Le motif

Dix causes, une racine : **l'agent devine une propriété de l'environnement au lieu de la lire.**
La mesure montre que ce qu'il faudrait lui donner à lire est **petit** — 38 routes, 39 selects
distincts, 133 arêtes utiles — et que **le crawl qui le mesure existe déjà**. Ce qui coûtait des
runs réels et des réparations se lit en 4 minutes de machine, une fois.
