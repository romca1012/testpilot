# 0014 — Réparation automatique : le gate autorise, le circuit décide, l'agent propose

Date : 2026-07-16
Statut : **DÉCIDÉ et LIVRÉ** — les deux chemins prouvés en conditions réelles.
Migration : **9** (`review_decision.repair_budget`)
Remplace : rien. **Décale** `0013` (qui remplaçait `0001`).

---

## Le constat : un pilier annoncé qui n'existait pas

La réparation était **diagnostiquée, jamais exécutée**. Mesuré :

| Ce qui existait | Ce que ça faisait |
|---|---|
| `defect_origin.diagnose()` | **classe** l'échec |
| table `repair_attempt` | **enregistre** le diagnostic (8 lignes, `what_was_tried` **vide partout**) |
| `repair_circuit.evaluate()` | **circuit breaker complet et testé** — **jamais appelé** |
| prompt « PILIER 3 — EXÉCUTION ET RÉPARATION » | doctrine complète : recettes, anti-maquillage, `.feature` gelé |
| `config.MODEL_REPAIR` | un modèle dédié, configuré |
| `executor.max_retries` | relance **à l'identique** sur timeout — ce n'est pas réparer |

Ce qui manquait : **le réparateur**. Preuve : **aucun cas n'avait de v2** (3 versions pour 3 cas).
Et le prompt promettait à l'agent un outil `run_behave` **qui n'existait pas**.

Toute la machinerie de sécurité était là. L'organe qu'elle protège n'avait jamais été écrit.

## Le nœud : réparer exige d'exécuter, exécuter exige le gate

§4.3 : *le gate humain est obligatoire avant la première exécution d'une version générée par
IA*. Or réparer, c'est exécuter → constater → corriger → **réexécuter**.

| Option | Pourquoi écartée / retenue |
|---|---|
| **A** — réparer avant le gate | la boucle exécuterait du code IA **non relu** : §4.3 contourné |
| **B** — un gate par itération | ce n'est plus une boucle, c'est un **ping-pong** ; le §6 veut une réparation « invisible pour l'utilisateur » |
| **C** — **le gate autorise N tentatives** | ✅ **retenu** — le garde-fou n'est ni contourné ni consultatif : il **décide**, une fois, en connaissance de cause |

**Défaut = 2, pas 0** : un défaut à 0 rendrait la réparation opt-in à chaque relecture — donc
visible et manuelle, soit l'option B qu'on venait d'écarter. Le relecteur descend à 0 pour
l'interdire. `budget=0` coupe au premier tour du circuit (`0 >= 0`) **sans cas particulier** et
sans engager un appel LLM.

## Les trois décisions de conception

**1. Design (b) — l'orchestrateur pilote, l'agent propose.** `circuit.evaluate()` décide ; l'agent
n'a **aucun outil pour exécuter**. Lui donner `run_behave` remettrait le garde-fou dans les mains
du composant qu'il encadre — et `0012` a montré que le circuit lit un texte que **l'agent écrit
lui-même**.

**2. Modèle B — une exécution = un run réel d'une version.** Chaque ligne reste vraie (une
version, un verdict, un run) : §4.2 tient **littéralement, ligne par ligne**. Le prix est un
historique plus fourni ; c'est la trace honnête. (Modèle A — une exécution = toute la session —
aurait fait **mentir** `version_id` : la ligne dirait « v1 » quand le verdict vient de v3.)

**3. Option (i) — une version réparée n'est JAMAIS approuvée d'office.** Si la réparation résout,
la version devient la référence **et le cas repasse « à relire »** pour ratification. L'option
(ii) — étendre l'autorisation à v2 — aurait exigé une `review_decision` signée par l'IA :
**l'auto-approbation déjà écartée**. Une version que personne n'a humainement relue n'est jamais
approuvée, quelle que soit la justification.

Résultat : la réparation est **invisible pendant la session** (§6), et **jamais exécutable sans
autorisation explicite** après (§4.3). Si elle échoue, la référence reste la version qu'un
**humain** a approuvée ; les tentatives demeurent en historique.

## Ce que le RUN RÉEL a trouvé — et que 10 tests avaient laissé passer

**Trois bugs, dont deux à moi.**

**Bug 1 — le circuit prenait « le test n'a pas tourné » pour « le test passe ».** Dry-run en
échec → `real_run=None` → liste d'échecs vide → **exactement comme un test qui passe** →
`evaluate([])` → `resolved` → la boucle **adoptait une version cassée en proclamant sa victoire**.
Mesuré : l'exécution 13 (v7) avait **0 scénario**. C'est le **faux négatif** (§4.4) — et le motif
que je venais de traquer trois fois (`0010` `pass`, `0011` `warn+return`, `0013` diagnostic jamais
tranché) : **l'absence de signal prise pour un signal positif**. → `a_tourne()`, vérifié **avant**
`evaluate`. Le circuit ne connaît que des ÉCHECS : la distinction lui est structurellement
impossible, c'est à l'orchestrateur de la faire.

**Bug 2 — l'agent rendait un extrait, pas le fichier.** v2 : 4 steps → v7 : **1 step**.
`write_steps_file` **remplace** ; les 3 autres steps ont disparu → `undefined` → dry-run en échec.
Deux causes : le **contrat n'était écrit nulle part** (« Écrit le fichier _steps.py… »), et l'agent
**n'avait pas le contenu actuel** — il réécrivait de mémoire. → contrat explicite dans la
description que l'agent lit à **chaque appel** + contenu courant transmis. Même famille que
`0012` : une capacité dont le contrat n'est pas écrit.

**Bug 3 — le disque divergeait de la base.** Anticipé au cadrage, **pas traité** : j'ai codé sans.
Le runner lit les fichiers **sur disque** ; la tentative de l'agent y restait. Base « v2 » (4 steps)
/ disque « v7 » (1 step) → le prochain run aurait joué v7 **en prétendant v2** (§4.6), et le
verdict aurait porté sur un code que personne n'a approuvé. → `_sync_disque()` réécrit la version
de **référence** après chaque boucle.

## ⚠️ Le gate a tenu pendant que le circuit se trompait

Avec le bug 1 **actif**, la boucle a proclamé une réparation réussie et adopté une version
cassée. **v7 n'a jamais été auto-approuvée** : `is_version_approved(7) = False`, cas `to_review`.

**Une couche a défailli, la couche du dessous a tenu.** C'est ce que l'architecture en couches a
coûté à construire, et ce qu'elle vient de rendre.

## Preuve en conditions réelles

**Chemin « arrête »** — cas 6 : `assertion_mismatch` → `vrai_bug` → **aucune réparation**,
`what_was_tried` vide, **zéro appel LLM**.

**Chemin « répare »** — cas 2, après les 3 correctifs :

```
exec 14 (v2) : technical_error / indetermine   2/3 scénarios   ← le TypeError
exec 15 (v8) : success / conforme             3/3 scénarios   ← réparé
```

**Première exécution verte du projet** (1/12 ; l'audit du matin disait 0/8). Le correctif de
l'agent :

```diff
-    tickets = context.odoo.env["helpdesk.ticket"].search(
+    tickets = context.odoo.env["helpdesk.ticket"].search_read(
+        ["id", "name", "team_id"],
```

— exactement la cause trouvée à la main. Les 3 correctifs vérifiés **séparément** : 3 scénarios
(le test a tourné), v8 = 4 steps (fichier entier), `disque == v8`.

**v8 ratifiée par le porteur** (`reviewer: romaric`) → cas 2 **`validated`** : le premier du
projet.

## Ce qu'on ne fait PAS

- **Pas de blocage** : un diagnostic non tranché ne retient rien. Le gate reste le **seul** verrou.
- **On ne souffle pas son diagnostic à l'agent** : le rapport d'échec est **factuel**. La
  taxonomie classe par mots-clés (`0012`) ; lui transmettre sa conclusion l'enfermerait dans une
  piste qui peut être fausse — le cas 6 l'a prouvé.
- **Pas de « rejouer » depuis l'écran de confirmation** (`0013`).

## ⚠️ Fragilité connue, non résolue — à traiter en priorité

**Ce qui est réparable se décide en partie sur des mots-clés dans des NOMS DE STEPS.** Mesuré : le
`TypeError` du cas 2 n'est classé `test_a_reparer` que parce que son step s'appelle `team_id` ; le
même `TypeError` **nu** tombe en `indetermine` et le circuit s'arrête. Le `step_text` **l'emporte**
sur l'erreur réelle (priorité des catégories).

**Depuis `0014`, le risque bascule** : un **vrai bug** dont le step porte par malchance un mot-clé
technique serait classé `test_a_reparer` → la boucle **réparerait un test correct contre une
application cassée**. Direction du **faux négatif**, §4.4. Ce qui protège aujourd'hui : la règle
anti-maquillage du prompt et le plafond de budget — l'obéissance d'un LLM et un compteur, **pas**
un garde-fou déterministe. → entrée **prioritaire** au backlog.
