# 0008 — Génération : empêcher une assertion infalsifiable (faux « conforme ») — Inc. 1

Date : 2026-07-15
Statut : **DÉCIDÉ et IMPLÉMENTÉ** (arbitrage du porteur, 2026-07-15). **A et C faits et prouvés**
(prompt + lint non-bloquant au gate avec extension contextuelle). Voir § *Suivi d'implémentation*.
Priorité : **1** — cf. `BACKLOG.md`

> **Numérotation** : `0007` est réservé à l'**écart 1** (sémantique des paramètres de steps —
> décision à venir, cf. ordre convenu au §6/§7 de `CONTINUITE.md`). Cette note porte `0008`
> bien qu'écrite **avant** `0007`, parce que l'écart 2 est traité en premier (il est plus
> dangereux). Le « trou » 0007 est donc intentionnel et temporaire.

---

## Contexte — l'écart 2 du run #2

Au run réel #2 (`CONTINUITE.md` §6.1), le scénario `[Limite]` du cas 2 est passé
**`success / conforme`**. Or son step custom généré ne peut **jamais** échouer :

```python
# @then("le formulaire traite la chaîne longue de manière cohérente")
if "/your-ticket-has-been-submitted" in current_url:
    context.long_string_accepted = True            # branche if : AUCUNE assertion
else:
    error_visible = (...)                          # calculé…
    context.long_string_accepted = False
    assert error_visible or "/your-ticket-has-been-submitted" not in current_url, (...)
```

Dans la branche `else`, on **sait déjà** que l'URL ne contient pas le chemin de succès : le
`... not in current_url` est **toujours vrai** par construction, donc `error_visible or True`
vaut **toujours vrai**. L'assertion ne contraint rien ; la branche `if`, elle, n'assertit rien
du tout. **Le step passe quoi que fasse l'application.**

## Pourquoi c'est grave (et pourquoi priorité 1)

- Viole l'**invariant §4.2** (« un statut n'est jamais déclaratif ») : ici un `conforme` sort
  d'une assertion vide, pas d'une observation réelle.
- Viole l'**asymétrie du défaut §4.4** : c'est un **faux-négatif** (l'app pourrait être en
  faute, le test dit « conforme ») — la catégorie que le projet déclare **inacceptable**.
- **Silencieux** : contrairement à l'écart 1 (qui casse le test, donc se voit), celui-ci
  produit un vert. Il ment *dans le bon sens* pour qui regarde vite. C'est exactement le genre
  de faux positif que les deux axes sont censés rendre impossible.

## Point structurant : le DYNAMIQUE ne peut pas l'attraper

Une tautologie **passe à l'exécution, par définition**. Ni le `dry_run` (qui ne fait que
vérifier le parsing) ni le run réel ne peuvent la détecter : un `assert True` réussit. Le
diagnostic fiabilisé par l'écart 3 (le message d'erreur porte enfin la cause) **n'aide pas
ici** — il n'y a pas d'erreur à lire, puisque rien n'échoue. Donc **seuls trois leviers**
existent : (a) **prévenir** à la génération (prompt), (b) **détecter statiquement** avant le
gate, (c) **faire trancher l'humain** au gate. On ne pourra jamais s'appuyer sur une exécution.

## Ce qui, aujourd'hui, a laissé passer un `assert` infalsifiable

Mesuré sur le prompt (`generation/prompts/system_prompt.md`) et le garde-fou
(`generation/tools/write.py`) :

1. **Le prompt interdit le maquillage EN RÉPARATION, pas la vacuité À LA GÉNÉRATION.** Les
   règles fortes (« ne maquille pas l'assertion », « ne force jamais un vert », Pilier 3
   § *Constat produit vs test à réparer*) visent le moment où l'agent **répare un rouge**. Elles
   ne disent **rien** sur l'écriture initiale d'une assertion qui, dès la première passe, ne
   peut pas rougir. La notion de **falsifiabilité** (« une assertion doit pouvoir échouer si
   l'app se comporte mal ») est absente.
2. **Le `[Limite]` invite un résultat incertain — et ici la SPEC elle-même le fait.** La
   couverture minimale demande un scénario `[Limite]` sans exiger une assertion **falsifiable**.
   Pire : `specs/validation_champ_requis.md` (l.60-63) prescrit littéralement « soit le ticket
   est créé…, soit une erreur… » — l'agent a **fidèlement** traduit la spec. La racine n'est
   donc **pas** que l'agent invente l'ambiguïté ; c'est qu'**une issue multiple est parfois
   légitime**, et que rien n'imposait que l'assertion reste **falsifiable** malgré tout.
   ⚠️ **Conséquence sur A** : exiger « un attendu unique » serait **faux** (ça contredirait une
   spec légitimement multi-issues). La bonne règle vise la **falsifiabilité** : si plusieurs
   issues sont acceptables, affirmer leur **disjonction** (qui échoue sur une 3ᵉ issue) + un
   invariant garanti dans tous les cas — jamais `A or non-A`. La spec fournissait justement cet
   invariant (« aucun ticket partiel »), que le Gherkin avait encodé dans un *second* step ; le
   step vacant était celui du « comportement cohérent ». Trou de consigne, pas désobéissance
   (même nature que 0003 : on demande, mais on n'outille pas la bonne propriété).
3. **`write_steps_file` ne contrôle pas la falsifiabilité.** Ses 4 gardes (guillemets ASCII,
   `ast.parse`, transport interdit, `AmbiguousStep`) sont toutes **syntaxiques/structurelles**.
   Aucune ne regarde ce qu'une assertion *contraint*. C'est le seul point du pipeline où une
   analyse statique de la sémantique des assertions pourrait vivre — elle n'existe pas.

## Options pour l'empêcher à la source

### Option A — Renforcer le prompt (prévention)
Ajouter une règle de **falsifiabilité** aux « Règles de code universelles » et durcir la
consigne `[Limite]` :
- « Toute assertion doit pouvoir **échouer** si l'application se comporte mal. N'écris jamais un
  `assert` toujours vrai (`assert X or <toujours vrai>`, `assert True`, comparaison triviale). »
- « Un scénario `[Limite]` doit **affirmer un résultat défini et unique** (soit succès attendu,
  soit erreur attendue), pas “l'un ou l'autre convient”. Si le résultat est réellement
  indéterminé, choisis l'attendu le plus probable et laisse le scénario rouge s'il ne se produit
  pas — ce sera remonté comme constat produit. »
- Coût : quasi nul. Bénéfice : attaque la **cause** (le modèle mental de l'agent). Limite :
  repose sur l'obéissance du LLM — à **mesurer** par re-génération, jamais présumé (§8.5).

### Option B — Validation statique post-génération (détection, bloquante)
Ajouter un 5ᵉ contrôle dans `write_steps_file`, sur l'AST déjà parsé. **Sous-ensemble à haute
confiance seulement** (sinon on bloque du code légitime — un faux positif ici **empêche la
génération**, coût réel) :
- `assert` dont le test est une **constante vraie** (`assert True`, `assert 1`, `assert "x"`).
- `assert A or B` dont **un opérande est une constante vraie**.
- step `@then` dont le corps ne contient **ni `assert`, ni `raise`, ni appel à un helper
  d'assertion connu** — un « Alors » qui n'affirme rien.
- ⚠️ La tautologie **contextuelle** exacte de l'écart 2 (`assert … or X not in Y` dans le
  `else` d'un `if X in Y`) est détectable par un motif AST ciblé (repérer l'opérande = négation
  de la condition englobante), mais c'est **fragile** et étroit. À considérer comme un motif
  spécifique, pas comme la garantie générale.
- Coût : modéré, testable unitairement (comme les gardes existantes). Bénéfice : filet
  mécanique déterministe. Limite : ne couvre **que** le sous-ensemble trivial ; le cas réel
  d'écart 2 n'y tombe que via le motif fragile.

### Option C — Lint non-bloquant surfacé au GATE (assistance humaine)
Au lieu de bloquer la génération, faire calculer un **avertissement** (« assertion possiblement
vacue dans le step X ») affiché **au relecteur** dans l'écran de gate. Le gate **reste
souverain** (invariant §4.3 : c'est l'humain qui approuve la version) ; la machine **conseille**,
elle ne décide pas.
- Coût : modéré (calcul + un bandeau dans l'UI de relecture). Bénéfice : **aucun faux positif
  bloquant** (au pire un avertissement ignoré), et ça **muscle le gate** exactement là où
  l'écart 2 lui a échappé. Limite : suppose que le relecteur lise l'avertissement.

### Combinaisons
A et C ne s'excluent pas et se complètent bien : **A prévient** (le plus souvent l'assert vacue
ne sera même pas écrite), **C rattrape** ce qui passe (sans jamais bloquer à tort). B apporte un
filet déterministe **pour le sous-ensemble trivial**, au prix d'un risque de faux positif — à
n'activer que sur des motifs à confiance quasi certaine.

## Sur « l'option B — rendre le step tolérant » évoquée plus tôt

Cette option-là appartient à l'**écart 1** (le libellé humain passé à un step qui attend le nom
technique `name` → repli `get_by_label`). Elle **ne touche pas** l'écart 2 : une assertion
tautologique n'est ni un problème de transport ni de sélecteur — la rendre « tolérante » n'aurait
aucun sens (elle est déjà « tolérante » à l'excès : elle tolère *tout*). Maintenant que le
diagnostic est **fiable** (grâce à l'écart 3, on lit la vraie cause à l'écran), je **maintiens**
que ces deux écarts sont de **familles disjointes** et doivent être traités séparément :
l'écart 1 est un problème de **paramétrage** (relève de `0007`), l'écart 2 un problème de
**falsifiabilité des assertions** (cette note). Le diagnostic fiabilisé ne fait pas migrer
l'option « step tolérant » vers l'écart 2 ; il la laisse où elle est, dossier `0007`.

## Recommandation (à valider — rien n'est tranché)

**A + C** en premier : la règle de falsifiabilité dans le prompt (prévention à coût nul) **et**
le lint d'avertissement au gate (rattrapage sans faux positif bloquant). **B** seulement pour le
sous-ensemble trivial et à confiance quasi certaine (`assert True`, `or <constante vraie>`,
`@then` sans aucune assertion), **sans** viser le motif contextuel fragile. Puis **mesurer** :
re-générer le cas 2 et vérifier que le `[Limite]` porte désormais une assertion falsifiable
(§8.5 — prouver, pas présumer).

## Verdict (arbitrage du porteur — 2026-07-15)

**Décision confirmée et propre** (cette note, `0008`). Options retenues :

1. **A (prévention par prompt) — RETENUE.** Expliciter la notion de **falsifiabilité**, et
   **fermer le trou de consigne sur `[Limite]`** : exiger un **attendu défini**, jamais « l'un
   ou l'autre convient ».
2. **C (lint non-bloquant surfacé au gate) — RETENUE.**
3. **B (garde statique) — INCLUSE mais strictement NON-bloquante**, limitée au sous-ensemble
   trivial qu'elle sait couvrir proprement. **Jamais de blocage automatique de la génération sur
   cette base** : un faux positif qui bloque coûte plus cher (itérations, budget) que ce qu'il
   rapporte — risque déjà identifié au **brief §11.2**. B ne fait donc qu'**alimenter le signal
   de C** (avertissement), elle n'a pas de pouvoir de rejet.
4. **Toucher le gate maintenant est validé** : c'est le **point d'implémentation de C**, pas une
   extension de périmètre. Le gate est déjà le contrôle humain obligatoire (invariant §4.3) ; on
   y **ajoute un signal**, on ne change pas sa nature.

**Ordre d'implémentation** : **A d'abord** (si vraiment coût nul), **C ensuite**. Plan détaillé
à valider avant tout code.

Conséquence sur les options ci-dessus : B **cesse d'être un garde bloquant** dans
`write_steps_file` ; sa détection (sous-ensemble trivial) devient une **entrée du lint C**. La
distinction « bloquant / advisory » est ainsi tranchée en faveur de l'advisory partout.

## Ce qu'on ne fait PAS

- Pas de faux positif **bloquant** sur du code légitime : une garde trop zélée dans
  `write_steps_file` coûte des itérations et casse la génération — pire que le mal.
- Pas de gate transformé en **bruit** : un avertissement qui se déclenche à tort à chaque run
  serait vite ignoré, et l'invariant du gate souverain perdrait son sens.
- Pas d'illusion de **preuve dynamique** : on n'ajoute pas un « run qui vérifierait » — une
  tautologie passe le run. La garantie est statique (B), préventive (A) ou humaine (C).

## Questions d'arbitrage — TRANCHÉES

Ces questions ont été posées pour l'arbitrage ; elles sont désormais **résolues** (voir
§ *Verdict*). Conservées ici pour la traçabilité du raisonnement.

1. **Quelles options** ? → **A + C**, avec **B non-bloquante** en entrée du lint C.
2. **B bloquant ou non** ? → **Non-bloquant**, borné au sous-ensemble trivial (brief §11.2 : un
   faux positif bloquant coûte plus qu'il ne rapporte).
3. **C justifie-t-il de toucher le gate maintenant** ? → **Oui** : point d'implémentation de C,
   pas une extension de périmètre (on ajoute un signal au contrôle humain existant).
4. **Décision propre** ? → **Oui**, `0008` confirmée — famille distincte de `0007` (écart 1).

Extension retenue **en plus** du verdict initial (arbitrage complémentaire du porteur) :
**détecteur contextuel** dans C — le motif exact de l'écart 2 (`assert … or X not in Y` dans le
`else` d'un `if X in Y`). Écarté au départ car fragile *en bloquant* ; réintégré car **C est
non-bloquant** → un faux positif ne coûte qu'un avertissement ignorable. Sans lui, le filet ne
couvre pas le cas exact qui a motivé l'investigation.

## Suivi d'implémentation

### A — prompt (falsifiabilité + `[Limite]`) — ✅ FAIT et PROUVÉ (2026-07-15)
- `generation/prompts/system_prompt.md` : **Règle 4 « Une assertion doit pouvoir échouer »**
  (avec le piège `else`/négation en exemple explicite) + consigne `[Limite]` reformulée en
  **falsifiabilité** (disjonction des issues acceptables + invariant), **pas** « attendu unique »
  (cf. affinage du point 2 : la spec peut être légitimement multi-issues).
- **Preuve** (§8.5) : re-génération réelle du même spec (`scripts/prove_A_falsifiabilite.py`,
  cas **3** créé). Le `[Limite]` produit désormais un `@then` **falsifiable** — invariant
  `partial_count == 0` **et** disjonction `issue_a or issue_b or issue_c` qui **échoue** sur une
  3ᵉ issue (redirection sans création, création sans redirection, ticket partiel). Plus aucune
  tautologie `A or non-A`.
- Note pour C : la règle « `@then` sans `assert`/`raise` = test vide » ne vaut **que** pour les
  steps d'assertion (`@then`) — un `@when`/`@given` d'action n'assertit légitimement rien. Le
  lint devra filtrer par décorateur.

### C — lint non-bloquant au gate (+ extension contextuelle) — ✅ FAIT et PROUVÉ (2026-07-15)
- **Module pur** `generation/assertion_lint.py` (`lint_steps` → liste d'avertissements, AST, aucune
  I/O). Trois motifs : `always_true_constant`, `tautology_negation_in_else` (**motif exact de
  l'écart 2**), `then_without_assertion` (filtré par décorateur — un `@when` d'action n'est jamais
  signalé). Négation reconnue par **égalité structurelle stricte** (anti-faux-positif).
- **API** : `GateOut.lint_warnings` (schéma `LintWarning`), calculé dans `routes/cases.py` depuis
  les steps de la version courante. **N'affecte jamais `allowed`** — le gate reste souverain.
- **Front** : bandeau non-bloquant dans `ReviewGate.vue` (ton *warning*, n'empêche pas
  l'approbation).
- **Tests** : `tests/test_assertion_lint.py` (11) — dont **anti-faux-positif étendu** aux
  variantes légitimes du motif contextuel (autre variable / autre comparateur / sans négation /
  hors `else`) **et** preuve sur le **contenu exact** de l'écart 2 ; plus 2 tests API
  (`test_api.py`) : le contenu exact de l'écart 2 est **signalé au gate sans bloquer**, et une
  assertion saine ne produit rien. Suites **181 Python + 15 vitest + build** verts.
- **Preuve en conditions réelles** (§8.8) : sur la vraie base, le gate du **cas 2** (la
  tautologie d'origine) affiche `tautology_negation_in_else` (l.101) ; le **cas 3** (re-généré
  après A) n'affiche **aucun** avertissement. A et C se valident mutuellement.
