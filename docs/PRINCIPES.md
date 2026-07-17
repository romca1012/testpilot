# Principes d'architecture — TestPilot

> **Document permanent**, au même rang que les invariants §4/§5 du brief. Ce n'est **pas** une
> décision numérotée : les décisions tranchent un cas, ces principes disent ce qu'on ne
> re-débat plus. Toute décision future doit s'y conformer ou dire explicitement pourquoi elle
> s'en écarte.
>
> Date : 2026-07-17. Statut : **À VALIDER par le porteur.** Aucun code avant validation.

---

## Le constat qui les fonde

Six incidents en une journée — `0007`, `0008`, `0012`, bug 2 de `0014`, `0015`, `0017` — et **une
seule erreur de conception** derrière tous :

> **On a traité le texte écrit par l'agent comme une source de vérité.**

Un LLM ne peut pas garantir structurellement la cohérence entre ce qu'il *dit* faire et ce qu'il
*fait*. Chaque décision appuyée sur son texte a produit un bug. Chaque bascule vers un signal
déterministe du runtime (type d'exception, rendu de Behave, résultat AST) a fait disparaître le
problème — mesuré, pas supposé.

Ce document transforme ce constat en règles, et dit **où le projet les respecte déjà et où non**.

---

## La contrainte de coût, d'abord — parce qu'elle juge les principes

**§9 du brief : moins de 1 € pour la génération + exécution d'un nouveau module.** Avec
`EUR_USD_RATE = 1.08`, le plafond est **≈ $1,08**.

### Ce qui est mesuré — ✅ **le §9 est mesurable depuis le 2026-07-17**

| | mesure réelle | statut |
|---|---|---|
| Génération d'un module (cas 1) | **$0,4529** ≈ **0,42 €** — **42 % du budget** | mesuré |
| Réparations d'avant le correctif (×5 : v7→v11) | **perdues — aucune trace** | irrécupérable |
| Réparations à partir de maintenant | comptées, **tentatives ratées comprises** | mesuré |

Les deux défauts que ce document nommait :

1. ~~Le budget §9 n'est pas mesuré sur le chemin de l'UI~~ → **corrigé.**
   `config.BUDGET_PER_CASE_EUR/_USD` nomme enfin le §9 (il n'existait dans **aucune** constante) ;
   `repair_service._record_cost` écrit au ledger **avant tout `break`** — un agent qui ne propose
   **rien** a quand même coûté, et ne compter que les réussites donnerait un budget flatteur ;
   `CostRepo.total_for_case_usd` / `breakdown_for_case` donnent le total **et** son explication.
2. **Le plafond configuré contredit toujours le §9.** `COST_LIMIT_PER_RUN_USD = 2.00` ≈ **1,85 €**
   — près du **double**. **Conservé tel quel, et gardé par un test** : changer un plafond sans
   mesure serait exactement ce que ce document reproche. À arbitrer une fois qu'on aura des runs
   mesurés.

> Le motif §4.6 appliqué à l'argent : le brief affichait 1 €, le code plafonnait à 1,85 €, et le
> chemin réel ne mesurait rien. Le troisième terme est réglé ; le deuxième attend une mesure.

### Tarifs en vigueur (`guardrails/cost_tracker`)

| modèle | usage | input | output |
|---|---|---|---|
| `claude-sonnet-4-6` | génération | $3 / M | $15 / M |
| `claude-haiku-4-5` | **réparation** | $0,80 / M | $4 / M |

**Ordre de grandeur d'une réparation** (estimé sur les tailles réelles : `v9` = 13 971 car.,
`v10` = 12 704, `v11` = 13 370 → ~4 000 tokens de sortie) : **~$0,015–0,05 par tentative** sur
Haiku. Deux tentatives ≈ **$0,03–0,10**.

**Budget type d'un module** : génération $0,45 + 2 réparations ~$0,05 ≈ **$0,50 ≈ 0,46 €** —
**~46 % du plafond**. Il reste donc de la marge, mais elle n'est pas mesurée.

---

## Principe 1 — La vérité vient du runtime, jamais du texte de l'agent

**Règle.** Aucune classification, aucun statut, aucun diagnostic ne décide sur du texte écrit par
l'agent. Le texte de l'agent **informe un humain** (`what_was_tried`, `change_summary`,
`error_summary`) — il n'entre **jamais** dans un algorithme de décision.

**Coût : nul.** C'est du code et de l'analyse statique. Aucun appel LLM, aucun run.

### Où c'est respecté (vérifié)

| composant | signal utilisé | statut |
|---|---|---|
| `defect_taxonomy.classify_failure` | type d'exception + rendu `ASSERT FAILED:` de Behave | ✅ depuis `0015` |
| `verdict/status.derive_verdict` | statut de scénario Behave | ✅ |
| `repair_agent` → `proposal.changed` | `bool(state.steps_content …)` — posé par **l'outil**, pas par la prose | ✅ |
| `tools/write.py` | AST (imports, labels de steps), ASCII | ✅ |
| `generation/assertion_lint` | AST | ✅ depuis `0008` C |

### La violation trouvée — ✅ **corrigée le 2026-07-17**

**`guardrails/repair_circuit.failure_signature`** indexait la détection de stall sur
`scenario_name`, **écrit par l'agent** dans le `.feature`. Comme l'agent réécrit le fichier entier
à chaque tentative, **renommer un scénario suffisait à changer la signature** → l'absence de
progrès devenait invisible → le budget brûlait sur un test qui n'avance pas. Le garde-fou
dépendait du composant qu'il encadre.

La signature se dérive maintenant de trois faits que l'agent ne produit pas : la **cause**
(décidée par le type d'exception depuis `0015`), les **types d'exception** réellement levés, et le
**nombre** d'échecs (insensible à un renommage).

**Un second défaut est tombé avec** : l'ancienne signature ne distinguait pas un `TypeError` d'un
`AttributeError` (même cause, même scénario → **même signature**). Elle prenait donc un **vrai
progrès** — une erreur remplacée par une autre — pour un stall. Le correctif tranche dans les deux
sens.

**Contrepartie assumée** : la signature est plus grossière → un stall peut être détecté à tort.
C'est la direction sûre (§4.4) : un faux stall arrête la réparation, un stall manqué dépense pour
rien.

### 🔎 Trouvé en corrigeant : le stall est un garde-fou **décoratif**

`repair_service` passe `max_iterations = budget` du gate (défaut **2**), alors que `stall_limit`
vaut **3**. `evaluate` coupe donc sur le plafond d'itérations **avant** que `repeat_count` puisse
atteindre 3 : **le stall ne se déclenche jamais en dessous d'un budget de 4.**

Même famille que le `position` décoratif de `0006` ou les chemins de rapport de la migration 7.
**Documenté et gardé par test, volontairement pas « corrigé »** : ajuster une constante sans
mesure serait précisément ce que ce document reproche. La signature, elle, est désormais correcte
le jour où un relecteur accorde un budget plus large.

---

## Principe 2 — Contrainte structurelle, jamais instruction de prompt seule

**Règle.** « Ne fais pas X » dans un prompt ne suffit **jamais** seul. Tout comportement interdit
est soit **rendu impossible**, soit **détecté automatiquement**. Le prompt renforce ; il ne garde
pas.

**Coût : nul.** Validation à l'écriture = code pur, exécuté avant tout appel LLM supplémentaire.
Mieux : un rejet à l'écriture **économise** un run réel.

**La preuve mesurée est dans le rejeu de cet après-midi** — même agent, même run, deux règles :

| règle | forme | résultat mesuré |
|---|---|---|
| « n'utilise pas `requests` » | **garde AST** (`_FORBIDDEN_IMPORTS`, `_FORBIDDEN_ENDPOINTS`) | `v10`/`v11` **ont corrigé** le `HTTPError 404` — l'agent n'avait pas le choix |
| « réutilise les steps partagés » | **prompt + catalogue** | `v10`/`v11` **ont réinventé l'auth** → timeout (`0017`) |

### ⚠️ CORRECTION (2026-07-17, après vérification) — mon exemple phare était faux

J'avais écrit ici que le correctif du **bug 2 de `0014`** (« rends le fichier ENTIER ») n'était
qu'une **instruction de prompt**, et qu'« un agent qui rend 1 step sur 4 est arrêté par sa bonne
volonté ». **C'est faux, vérifié dans le code :**

- `react_loop.py:127` et `:131` — toute écriture remet `state.dry_run_passed = False`
  (« le contenu a changé : revalider ») ;
- `react_loop._maybe_dry_run` échoue si `result.undefined_steps` et **renvoie la liste à l'agent**
  pour qu'il corrige dans la **même** session ;
- `executor.execute` refait la vérification : `if not (dry.success and not dry.undefined_steps …)`
  → `dry_run_passed=False`.

Un step perdu est donc **déjà** rattrapé par un garde-fou déterministe, **deux fois**. La phrase
du prompt est un *indice* utile à l'agent, pas le garde-fou — et c'est exactement la forme que le
principe 2 demande. **Le principe 2 est mieux respecté que je ne l'ai écrit.**

*(Le bug 2 de `0014` a fait des dégâts parce que le **bug 1** — `real_run=None` lu comme « aucun
échec » — masquait l'échec du dry-run. Bug 1 est corrigé ; le filet fonctionne.)*

### Le trou réel, que le dry-run ne peut PAS voir

Un step n'est `undefined` que si le `.feature` le **réclame encore**. Si l'agent réécrit **les deux
fichiers** et **supprime un scénario avec son step**, le dry-run est **satisfait** — rien n'est
undefined. Le test perd un scénario **en silence**, et le run suivant paraît *meilleur* :
moins de scénarios, donc moins d'échecs.

> C'est **« l'absence de signal prise pour un signal positif »**, à nouveau — et sous sa forme la
> plus dangereuse, puisque supprimer la couverture **améliore** les chiffres.

Aucune analyse statique du seul fichier de steps ne le voit : il faut comparer le **run d'avant**
au **run d'après**. C'est exactement le **principe 5**, et c'est gratuit (les deux runs existent).

### Violation confirmée

- **`0017`** : rien n'empêche de réinventer l'authentification. `reserved_steps` bloque la
  **collision de libellés**, pas la **duplication de comportement**. C'est le manquement réel du
  principe 2 — et le seul.

---

## Principe 3 — Édition ciblée, jamais réécriture complète pour un changement local

**Règle.** Un changement local ne réécrit pas 14 000 caractères de code qui marchait.

### Le coût réel, chiffré — et il renverse l'argument

Le porteur demande si un diff structuré **augmente** les appels. **Mesuré : non, il les diminue.**

| | sortie par tentative | coût Haiku ($4/M) |
|---|---|---|
| aujourd'hui (fichier entier) | ~13 000–14 000 car. ≈ 4 000 tok | **~$0,016** |
| avec diff ciblé | ~1 000 car. ≈ 300 tok | **~$0,001** |

**Économie : ~$0,015 par tentative.** Sur un budget de $1,08, c'est **du bruit** — et un patch qui
échoue à s'appliquer coûterait un appel de plus (~$0,02), ce qui annulerait le gain.

> **Conclusion honnête : l'argument pour le principe 3 n'est PAS le coût. C'est le rayon
> d'explosion.** Le cas 1 a échoué parce que l'agent, forcé de tout réécrire pour corriger un step
> RPC, a aussi réécrit l'authentification qui marchait. Chaque réparation rejoue ce risque sur
> l'intégralité du fichier.

### Faisabilité et tension

Le principe 3 **rouvre le bug 2 de `0014`** : c'est parce que l'agent rendait un fichier partiel
que le contrat « fichier ENTIER » existe. On ne peut pas simplement revenir en arrière.

**Version dégradée, dans le budget, disponible immédiatement (coût nul)** : garder le contrat
« fichier entier » **et** ajouter la garde AST du principe 2 (« aucun step déclaré ne disparaît »).
Elle ne réduit pas le rayon d'explosion (l'agent peut toujours abîmer le *corps* d'un step qu'il
conserve), mais elle ferme le bug 2 **structurellement** et **sans coût**, ce qui est la moitié du
problème réglée à zéro euro.

**Version complète** (outil d'édition par step/par diff) : à chiffrer sur un chantier dédié —
techniquement plausible (l'AST donne des ancres par nom de fonction de step), mais elle change le
contrat de l'outil et doit être prouvée par run réel avant adoption.

---

## Principe 4 — Un seul point de vérité par règle métier partagée

**Règle.** Le verdict à deux axes (§4.1) a **une** implémentation, testée, appelée par tous.

**Coût : nul.**

### Vérifié — et je dois corriger le cadrage

| appelant | comment | statut |
|---|---|---|
| `verdict/status.derive_verdict` | **l'unique implémentation** | ✅ source |
| `repair_service.est_executable` | délègue à `derive_verdict` | ✅ (depuis `0016`) |
| `run_service._persist`, `cli` | `derive_verdict` | ✅ |
| `report_service._verdict_from_db` | **lit** les statuts stockés — mapper, pas 2ᵉ implémentation | ✅ |
| `review_gate.validation_status_after_run` | reçoit `execution_status` | ✅ |

> ⚠️ **`0016` n'a PAS été causée par une duplication.** Je l'ai vérifié : il n'y a pas de seconde
> implémentation des deux axes. `0016` venait d'un **critère qui lisait le mauvais axe** — la
> boucle fusionnait « tourne » et « passe ». Le principe 4 reste juste et vaut d'être écrit, mais
> il n'aurait **pas** empêché `0016`. Seul le principe qui dit « les deux axes ne fusionnent
> jamais » (§4.1) l'aurait fait — et il existait déjà, il n'était simplement pas appliqué là.
>
> La leçon est donc plus dure que « ne dupliquez pas » : **un invariant écrit n'est pas un
> invariant appliqué.** D'où le principe 6.

---

## Principe 5 — Garde de non-régression avant toute adoption

**Règle.** Adopter une version réparée exige non seulement « le run cible tourne », mais **« aucun
scénario qui passait avant ne casse maintenant »**.

### Coût : **ZÉRO run supplémentaire, zéro appel LLM.** Voici pourquoi

La boucle exécute **déjà** le test avant (`exec N`, version de départ) **et** après
(`exec N+1`, version réparée). Les deux sont **persistés avec leurs résultats par scénario**
(`scenario_result`). Comparer les deux est une **requête SQL** sur des runs **déjà payés**.

Preuve sur les données réelles d'aujourd'hui — le matériel est là, il n'est simplement pas lu :

```
exec 20 (v1)  → 3 scénarios, 0 passent   (avant réparation)
exec 21 (v10) → 3 scénarios, 0 passent   (après réparation)
```

**Règle proposée, à coût nul** : refuser l'adoption si un scénario `success/conforme` de `exec N`
n'est plus `success/conforme` dans `exec N+1`. Sur le cas 1, rien à protéger (0 passant avant) ;
sur un cas comme le 2 (2/3 passants avant réparation), la garde aurait un vrai mordant.

**Second volet, également gratuit** : la garde AST du principe 2 (« aucun step ne disparaît »)
détecte la perte de steps **à l'écriture**, avant même le run — c'est exactement le diff textuel
sans coût que le porteur évoque, en plus robuste (AST plutôt que texte).

> **Le principe 5 est donc réalisable dans sa version COMPLÈTE à coût marginal nul.** Aucune
> version dégradée nécessaire.

---

## Principe 6 — Toute affirmation d'un prompt doit avoir sa vérification

**Règle.** Si un prompt (ou une description d'outil) affirme quelque chose sur un outil, un
format ou une contrainte, un test lie cette affirmation au code qui l'applique.

**Coût : nul.** Tests statiques sur des fichiers.

### Ce qui existe déjà (`tests/test_prompt_honnete.py`)

- `test_aucun_prompt_ne_cite_un_outil_inexistant` — le motif, pas les 4 cas trouvés ;
- `test_les_outils_fantomes_ont_disparu` — `run_behave`, `recall_memory`, `save_memory`, `list_models` ;
- `test_le_plafond_annonce_est_le_plafond_reel` — « ≤15 » quand la boucle coupait à 25 ;
- `test_le_prompt_de_generation_ne_promet_ni_run_reel_ni_reparation` ;
- `test_le_prompt_de_reparation_existe_et_interdit_le_maquillage`.

### Généralisations identifiées (promesses aujourd'hui non vérifiées)

1. **Les descriptions d'outils affirment des validations.** `write_steps_file` annonce
   *« Validé : ASCII, pas de step partagé redéfini »*. Si `write.py` change ses validations, la
   description **ment à l'agent** et rien ne le signale. → test liant chaque contrainte annoncée à
   la validation réelle.
2. **« Tu ne lances aucune exécution »** (prompt de réparation) est une affirmation sur l'**absence**
   d'un outil. → test : aucun outil d'exécution dans la liste passée à l'agent de réparation.
   C'est le design (b) de `0014` ; aujourd'hui rien ne le garde.
3. **Le catalogue cite des steps partagés** : chaque libellé cité doit exister dans la
   bibliothèque. Partiellement couvert (`test_prompt_expose_tous_les_steps_partages`) parce que le
   catalogue est **généré** — donc structurellement vrai. Bon exemple : **générer plutôt que
   décrire** est la forme la plus forte du principe 6.
4. **Le prompt annonce un modèle et des plafonds** : couvert pour `MAX_ITERATIONS`, pas pour le
   budget de réparation ni le plafond de coût.

---

## Ré-évaluation de `0016` et `0017` à la lumière de ces principes

Le porteur a raison : le cadre change les réponses.

### `0016` — ce qui change

`A` (adopter sur l'axe exécution) reste juste, **mais il était incomplet**. Le principe 5 le
complète à coût nul : `A` seule adopte une version qui tourne **même si elle a cassé un scénario
qui passait**. Sur le cas 1 ça ne se voyait pas (0 passant avant) ; sur un cas partiellement vert,
`A` seule serait une régression silencieuse.

> **`A` + garde de non-régression** — et la garde ne coûte rien, puisque les deux runs existent
> déjà. Ce n'est plus une option : c'est le principe 5.

L'option `(iii)` (afficher la version d'origine du verdict) reste inchangée et conforme au
principe 1 : on surface, on ne recalcule pas.

### `0017` — ce qui change beaucoup

Ma recommandation était « **B porteur + A en renfort** » (garde d'auth + annotation du catalogue).
**Le principe 2 la confirme mais en déplace le centre**, et le principe 3 en réduit la portée :

1. **Le vrai levier n'est pas une garde anti-auth** — c'est le **rayon d'explosion**. Si l'agent
   ne réécrivait pas l'auth pour corriger un step RPC, `0017` n'existerait pas. Une garde
   spécifique à l'auth traite le symptôme du jour ; demain il réinventera autre chose.
2. **La garde AST « aucun step ne disparaît » (coût nul) ne suffit pas** pour `0017` : l'agent n'a
   pas supprimé le step d'auth, il l'a **réécrit moins bien**. Il faudrait « aucun step conservé
   ne change **de corps** s'il n'est pas en cause » — vérifiable par AST, et **à coût nul**.
   C'est une garde **générique** (pas Odoo, pas auth) qui aurait attrapé `0017`.
3. **La question de placement se dissout** : une garde générique « ne modifie pas un step qui
   n'est pas en cause » n'a **rien de spécifique au connecteur** — donc elle ne rejoue pas la
   faute de `0015` (`team_id` figé dans un module générique), contrairement à une garde qui
   filtrerait `[name="login"]`.

> **Recommandation révisée pour `0017`** : privilégier la garde **générique et gratuite** (« un
> step non concerné par l'échec ne doit pas changer ») plutôt qu'une garde **spécifique à
> l'authentification**. Elle attrape `0017`, elle attrape le bug 2 de `0014`, et elle ne
> hardcode aucun connecteur. L'annotation du catalogue (`A`) reste en renfort.
>
> ⚠️ **Limite à ne pas taire** : cette garde suppose qu'on sache quels steps sont « en cause » —
> or on le sait, et par un signal du runtime : `scenario_result.step_text` est **persisté depuis
> la migration 10** (`0015`). Le principe 1 rend le principe 3 applicable. Reste à mesurer si
> l'agent a parfois **besoin** de toucher un step voisin pour une correction légitime ; si oui, la
> garde doit être **détective** (signalée au gate, comme le lint `0008` C) plutôt que
> **bloquante**. **Non mesuré — à trancher, pas à supposer.**

---

## Tableau de bord des principes

| # | principe | coût | respecté ? | manquement principal |
|---|---|---|---|---|
| 1 | Vérité du runtime | **nul** | ✅ **livré** | `failure_signature` dérive du runtime (cause + types d'exception + nombre). **Trouvé au passage : le stall est INATTEIGNABLE par défaut** (`stall_limit`=3 > budget=2) |
| 2 | Structure > prompt | **nul** | 🟡 large | reste **`0017`**, seul manquement. Le contrat « fichier ENTIER » EST gardé — par le dry-run, deux fois |
| 3 | Édition ciblée | **~nul** (−$0,015/tentative) | 📌 **dette** | couvert *en pratique* par le principe 5 → backlog, pas chantier (arbitré) |
| 4 | Point de vérité unique | **nul** | ✅ | aucun (vérifié) — mais n'aurait pas empêché `0016` |
| 5 | Garde de non-régression | **nul** (runs déjà payés) | ✅ **livré** | **seul filet possible contre la perte SILENCIEUSE d'un scénario** |
| 6 | Promesses de prompt vérifiées | **nul** | ✅ **livré** | promesses liées au COMPORTEMENT réel, pas au texte |
| — | **Mesure du budget §9** | **nul** | ✅ **livré** | mesuré par cas (cas 1 = $0,4529 = 42 %). Plafond $2,00 ≈ 1,85 € **conservé et gardé par test** |

**Aucun des six principes ne dépasse le budget.** Le coût n'est pas l'obstacle : c'est un
non-sujet, et le rappeler est le premier résultat de ce document. **Les principes 1, 2, 4, 5 et 6
sont à coût strictement nul.** Le principe 3 dans sa version complète est un chantier de
**conception**, pas de budget.

**Ordre proposé** (à valider) : la mesure du budget §9 d'abord — sans elle, ces principes se
jugent à l'aveugle sur la seule contrainte chiffrée du brief — puis 2 et 5 (une même garde AST +
une requête SQL, coût nul, ferment le bug 2 de `0014` et complètent `0016`), puis 1 et 6, puis 3.

## Ce que ces principes ne disent pas

Ils ne disent pas que l'agent est mauvais. Ils disent que **la fiabilité ne se demande pas, elle
se construit** : chaque fois qu'on a demandé, on a eu un bug ; chaque fois qu'on a rendu
impossible ou détecté, le problème a disparu. Un LLM est excellent pour **proposer** — `v9` a
diagnostiqué et corrigé un vrai défaut de transport que personne n'avait vu. Il n'est pas un
garde-fou de lui-même.
