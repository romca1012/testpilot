# Rapport de continuité — TestPilot

> # 📍 CE DOCUMENT EST PÉRIMÉ — LIRE `docs/PLAN.md` D'ABORD
>
> 🔴 **UNE DÉCISION ATTEND LE PORTEUR** : `PLAN.md` §2bis — proposition d'architecture
> (« le LLM produit une intention, un résolveur déterministe l'exécute »). Elle commande toute
> la suite : **tant qu'elle n'est pas tranchée, on corrige les erreurs cause par cause**.
>
> **`docs/PLAN.md` (2026-07-21) est le point d'entrée à la reprise.** Il dit l'état RÉEL, les
> décisions prises, et la route jusqu'au produit fini. Ce rapport-ci s'arrête au 2026-07-17 : il
> garde sa valeur d'**historique** (les leçons, les bugs trouvés, les décisions `0001`–`0022`),
> mais son §3 (modèle de données) et sa section « la suite » sont **caducs**.

> # ⚠️ À LIRE AVANT TOUT LE RESTE
>
> **Le brief produit (`docs/brief-produit-outil-test-management-ia.md`) est la SEULE source de
> vérité sur ce qui est voulu pour TestPilot.**
>
> **Toute déviation proposée doit être signalée comme telle et validée avant implémentation,
> jamais actée en autonomie.** Y compris — et surtout — quand elle paraît techniquement
> évidente, quand un incident du jour semble la réclamer, ou quand c'est *moi* qui la propose.
>
> Ce document, `PRINCIPES.md`, le backlog et les décisions `0001`–`0017` sont **subordonnés** au
> brief. Quand l'un d'eux le contredit : **c'est lui qui est caduc**, et la correction se fait
> **dans le document**, pas seulement dans la conversation.
>
> Le brief ne se modifie pas en silence non plus : il a un **journal des amendements** en tête.
> Un amendement s'y inscrit, daté et motivé, sur décision du porteur — jamais autrement.
>
> **Deux décisions du brief à ne plus re-débattre** (elles ont déjà été rouvertes une fois) :
> - **§6 — l'agent a le droit d'explorer l'application par lui-même.** La spec est un cadre, pas
>   une vérité absolue. Le pivot « Gherkin-only depuis une bibliothèque de steps fixe » est
>   **REJETÉ** *(2026-07-17)*.
> - **§11.2 — la mitigation du coût est « bien calibrer le garde-fou tentatives + budget »**, pas
>   restreindre ce que l'agent a le droit d'écrire.

> Document de reprise. À lire en premier après un `/clear`. Il fige **ce qui est décidé**
> (à ne pas re-débattre), **ce qui est vrai du code aujourd'hui**, et **ce qui reste ouvert**.
>
> **Version 5 — 2026-07-17.**

> ### ⚠️ Ce document est PÉRIMÉ au-delà du 2026-07-17 (schéma, décisions, backlog)
>
> Rien n'a été rétro-corrigé ci-dessous (chantier trop lourd pour sa valeur) — **le §3 (modèle
> de données) dit `user_version = 12`, la base réelle est à `14`** ; les décisions `0018` à
> `0022` n'y figurent pas. **Pour l'état courant, se fier à `docs/BACKLOG.md`** (source vivante,
> mise à jour le 2026-07-20) et à `docs/decisions/0022-structure-cas-run-et-resultats-inc1.md`
> (la structure cible : cas/run/résultats, qui **remplace** la lecture du §3 ci-dessous sur ces
> points). Résumé de ce qui s'est passé depuis la v5 de ce document :
> - Front TestRail livré (`CasesShell`, liste + détail 4 onglets, module Exécutions) branché sur
>   les vraies données, rien de fabriqué pour ce qui n'existe pas encore (Plans, jalons…).
> - `0022` : 8 décisions du porteur figeant l'anatomie du cas, le flux de génération en 2 passes,
>   le modèle Run/Plan, le versioning (le cas ENTIER, métier + technique, dans une version).
> - Livré depuis (migration 14) : les champs métier (préconditions/étapes/résultat attendu)
>   existent en base, versionnés avec le Gherkin, éditables (`PATCH /cases/{id}/metier`).
> - **Plan validé (porteur, 2026-07-20)**, voir `BACKLOG.md` § « Plan validé » : (1) CRUD
>   Spécification minimal, (2) génération un angle par appel (étape 3, structure dans `0022`),
>   (3) modèle Run/Plan (exécution nommée transverse, débloquée), (4) backend des 3 onglets
>   (défauts/historique/snapshot).

---

## 0. Session du 2026-07-17 (v5) — ce qui vient d'être fait

**Huit commits.** Tests : **419 Python · 36 vitest**, tout vert. **Base migrée : `user_version` 9 → 12.**

> ### 🔴 EN ATTENTE D'ARBITRAGE — à lire avant de reprendre
>
> **`0020` — le test clique un onglet qui est sur une autre page.** 5ᵉ rejeu, 5ᵉ cause distincte.
> Sondé (coût zéro) : `playwright_login` dépose le test sur `/my/home`, l'onglet « Ordinateurs »
> vit sur `/myservices` — où il est visible, activé, et **le click réussit**. Le locator est bon,
> l'application va bien : **étape de navigation manquante**. Le step d'auth **navigue sans le
> dire** — 4ᵉ occurrence du motif `0012`.
> **Recommandation : `C + A`** (annoter le catalogue, puis laisser la boucle repartir de `v10`).
> → **Aucun code avant arbitrage** (consigne tenue). Voir `decisions/0020-…md`.
>
> ### ✅ `0018` EST PROUVÉE EN RÉEL — le résultat du rejeu
>
> `v8 → v10` **ADOPTÉE** : pour la **première fois**, la boucle garde un test à moitié réparé
> (1/3 vert) au lieu de le jeter. **Le prochain rejeu repartira de `v10`, pas de `v1`** — le
> rachat de $0,41 par rejeu s'arrête.
>
> ⚠️ **`0016` (chemin positif) reste NON prouvé** : le test ne tourne pas *entièrement* (1/3).
> **Ce sont deux questions distinctes** — un progrès partiel adopté prouve `0018`, pas `0016`.
> Le script de rejeu les confondait ; corrigé.

| # | commit | ce que c'est |
|---|---|---|
| `3a744a4` | **Fix P0 — dry-run branché** | `propose_fix` recevait `dry_runner=None` : **aucun correctif n'était validé par rien** avant un run réel de ~300 s, alors que la docstring de `repair_agent` promet l'inverse. **C'est la cause directe de l'échec du rejeu** (v12 a supprimé son step d'auth sans toucher au `.feature` → `undefined` → `RUN_FAILED`). Effet de bord : le chemin heureux passe de **2 appels LLM à 1**. |
| `edc4002` | **CostTracker — le plafond borne le CAS** | `propose_fix` créait un tracker **neuf à chaque tentative** : `COST_LIMIT_PER_RUN_USD = $2` bornait un **appel**, pas un run. Un cas pouvait coûter **jusqu'à $6** contre $1,08 au §9. Garde-fou **décoratif**, appliqué à l'argent. Corrigé + calibré. |
| `3f53d0d` | **Recadrage sur le brief** | Brief amendé (budget), pivot rejeté, `0017` re-statué, borne du principe 2, incréments réalignés sur le §12. |
| `be14211` | **Rapport de continuité v4** | Le rappel « le brief est la seule source de vérité » en tête de document. |
| `eccc8f5` | **Le coût du chemin ÉCRAN entre au ledger** *(migration 12)* | `CostRepo.add_entry` n'était appelé que par la CLI et `repair_service` : **un cas créé par l'écran ne traçait aucun coût de génération**. Défaut **structurel** — le ledger reliait un coût à un cas par `JOIN execution`, or une génération **n'a pas d'exécution**. → `test_case_id` devient le lien. **Trouvé en branchant** : `SpecAnalyzer()` était sans tracker → l'**analyse** ne coûtait rien à personne, sur les deux chemins. |
| `7938b7b` | **Mesure réelle + recalibrage** | La génération coûte **4× moins** que cru. Plafond **$2,00 → $0,50**. |
| `0fcae0d` | **Docs alignés sur la mesure** | Le §9 est tenu à 65 %, le $0,4529 était un régime révolu. |
| `904713e` | **Nettoyage + trace** | Cas 7/8 (artefacts de mesure) retirés ; section « les bugs que seul le réel trouve ». |

### Le rejeu du cas 1 — ÉCHEC, et ce qu'il prouve quand même

**Chemin : l'écran** (`POST /api/cases/1/runs`) — le parcours réel, et celui qu'on venait de
fiabiliser côté mesure.

| exécution | version | verdict | scénarios |
|---|---|---|---|
| 25 | v1 | `technical_error / indetermine` | 0/3 |
| 26 | v6 *(réparation 1)* | `technical_error / indetermine` | 0/3 |
| 27 | v7 *(réparation 2)* | `technical_error / indetermine` | **1/3** ✅ |

**Tous les garde-fous livrés aujourd'hui ont porté, et c'est mesuré :** `v7` **délègue** l'auth au
step partagé (annotation `0017`), aucun `import requests` (`0003`), **aucun step `undefined`** (le
fix P0 — c'était la cause de l'échec précédent), plafond de coût jamais atteint ($0,4129 ≤ $0,62).

**Les causes s'enfoncent, rejeu après rejeu** — chacune plus profonde que la précédente :
`404` → `TimeoutError` d'auth → step `undefined` → **`select[name='types_demandes']`**.
Sondé : **ce champ existe et est visible** sur le vrai formulaire → `test_a_reparer` est le bon
diagnostic, ce n'est **pas** un bug applicatif. Cause exacte **non diagnostiquée** : budget épuisé.

**Le coût d'une réparation, re-mesuré** : **$0,2065/tentative** contre $0,2895 avant le fix P0
(**−29 %**) — le dry-run supprime un appel LLM perdu. ⚠️ 2 échantillons **très dispersés**
($0,3088 vs $0,1041) : le coût suit le nombre de tours ReAct, pas un tarif fixe.

⚠️ **Le « TOTAL du cas 1 = $1,1552 = 107 % du §9 » n'est PAS un dépassement du brief.** Le §9
mesure une **création** ; le cas 1 cumule **5 sessions de débogage de l'outil** et 7 versions. Une
création réelle mesurée vaut **$0,1207 = 11 %**. → question 2 de `0018`.

### ⚠️ Le bug que 416 tests verts n'ont pas vu

J'ai mis `CREATE INDEX … ON cost_ledger(test_case_id)` dans `schema.sql`. Or **`schema.sql`
s'exécute AVANT les migrations** : sur une base antérieure la colonne n'existe pas encore →
`no such column` → **toute ouverture de la base plante**, application comprise. Aucun test ne l'a
vu : ils partent tous d'un schéma **neuf**. **La vraie base l'a attrapé à la première ouverture.**
Le codebase documentait déjà la leçon (index d'unicité, `idx_case_module`) — je l'ai rejouée.
L'index vit maintenant dans la migration seule, et un test reconstruit une base d'avant la colonne.
*(Méthode §8.8 : un test vert ne prouve pas qu'un utilisateur voit la bonne chose.)*

### 🎉 Le §9 est tenu — et pour la première fois mesuré sur le chemin des utilisateurs

**Mesure réelle** (route HTTP, vraie base, vraie instance Odoo, spec `demande_materiel`) :

| poste | coût | % du §9 ($1,08) |
|---|---|---|
| Analyse *(jamais mesurée avant ce jour)* | $0,0157 | 1 % |
| Génération *(chemin écran)* | $0,1050 | 10 % |
| **Création d'un cas** | **$0,1207** | **11 %** |
| + 2 réparations au tarif mesuré | **$0,6997** | **65 %** |

**⚠️ Le `$0,4529` n'est pas « le coût de la génération » : c'est le coût d'AVANT les garde-fous.**
Sur la **même spec**, l'agent écrit aujourd'hui **1 973 caractères de steps contre 15 312** (7,8×
moins) et couvre **plus** (4 scénarios / 44 assertions contre 3) : il réutilise la bibliothèque au
lieu de tout réinventer. **Le travail de prompt (catalogue `0003`, notes `0012`, contrat `0007`
A1) a coûté 0 € et divisé la génération par ~4.** C'est la première fois qu'on peut le chiffrer.

> **Le §9 n'est pas tenu par un plafond — il est tenu parce que l'agent travaille mieux.**

### Ce qu'il faut savoir avant de citer un chiffre de coût

- **Le §9 est l'unique cible de coût du produit** : moins de 1 €/cas. Le « 50 €/mois » est
  **retiré du périmètre produit** (budget de dev du porteur) — brief amendé, `MONTHLY_BUDGET_*`
  reste en config **lu par personne**, volontairement.
- **Ne JAMAIS moyenner les deux régimes** de génération : $0,22 est un chiffre qui n'est jamais
  arrivé. Le script de mesure montre la **dernière** (le régime actuel) et la **pire** (ce sur
  quoi un plafond se calibre).
- **`$1,0319` n'est PAS une mesure** — extrapolation (`$0,4529 + 2 × $0,2895`), **et sur le
  mauvais régime**. Le ledger ne contient **qu'une** réparation réelle.
- **Le bug du CostTracker ne faussait pas les chiffres.** Avec un tracker neuf, chaque ligne du
  ledger était **juste**. Il ne corrompait pas le **comptage**, il rendait le **plafond**
  inopérant. Deux défauts distincts, longtemps confondus.
- **`$0,2895` est périmé à la baisse** : mesuré avec `dry_runner=None`, donc 2 appels LLM par
  tentative. Le fix P0 en supprime un. **Non re-mesuré** → au rejeu du cas 1.
- Mesures reproductibles : `scripts/mesure_cout_cas.py` (gratuit, lit le ledger) et
  `scripts/mesure_generation_chemin_ecran.py` (⚠️ **dépense ~$0,12 et écrit dans la vraie base**).

### Les plafonds, et ce qu'ils ne garantissent pas

| plafond | valeur | calibrage |
|---|---|---|
| `COST_LIMIT_PER_RUN_USD` *(génération)* | **$0,50** *(était $2,00 = 16,6× le réel)* | 4,8× le coût actuel, **et** au-dessus du pire jamais mesuré → n'aurait fait échouer aucune génération connue |
| `REPAIR_COST_LIMIT_PER_CASE_USD` | **$0,62** | = $1,08 − $0,4529 (pire génération) — on borne sur le pire |
| `REPAIR_BUDGET_DEFAULT` | **2** *(inchangé)* | 2 × $0,2895 = $0,5790 ≤ $0,62 : la mesure ne demande pas de descendre à 1 |

⚠️ **$0,50 + $0,62 = $1,12 = 104 % du §9** si les deux saturaient **ensemble**. Ce cas exige que
la génération coûte 4,8× sa valeur mesurée — le plafond a alors déjà coupé et un humain est dans
la boucle. **Les plafonds sont un filet anti-emballement, pas le mécanisme qui délivre le §9.**
Les serrer davantage ferait échouer des créations légitimes : on paierait plus cher que ce qu'on
économise.

### La suite, dans l'ordre

1. 🔴 **Arbitrer `0020`** (navigation manquante). Recommandation : **`C + A`** — `C` d'abord
   (annoter le catalogue : le step d'auth dépose sur `/my/home`, le catalogue est sur
   `/myservices`), **puis** `A` (laisser la boucle repartir de `v10` avec son budget entier).
   L'ordre compte : sans `C`, `A` fait deviner l'agent sur une information que la bibliothèque
   possède. **Aucun code avant arbitrage.**
2. **Rejeu du cas 1** une fois `0020` tranché — le **premier** rejeu où observer la boucle
   *converger* a un sens : elle repart de `v10` (1/3 vert), avec son budget entier.
3. **Exécution nommée transverse multi-modules** — §12 **Incrément 1**, dernier gros manque du §7.
   *(Décidé : après `0018` — qui est livrée et prouvée. Reste à statuer une fois `0016` clos.)*

### Les 5 rejeux, et pourquoi ils ne se répètent pas

Chaque rejeu descend d'une couche. Ce n'est pas la même erreur qui revient — c'est la suivante :

| # | cause | réglée par |
|---|---|---|
| 1 | `HTTPError 404` — transport réinventé | garde AST `0003` |
| 2 | `TimeoutError [name=login]` — auth réinventée | annotation `0017` |
| 3 | step `undefined` — `.feature` désynchronisé | **fix P0** (dry-run branché) |
| 4 | `select_option` — valeur `"new"` inventée | `0019` A + D |
| 5 | `get_by_role("tab")` — **mauvaise page** | `0020` — **à arbitrer** |

✅ **Fait** : les cas 7 et 8 (artefacts de mesure) ont été **retirés** du référentiel sur décision
du porteur — script tracé, garde-fou d'identité, backups conservés. Référentiel : cas 1, 2, 6.

---

## 1. Vue d'ensemble

> **Révisé le 2026-07-17 — recalage sur le découpage du brief §12.**
> Le découpage ci-dessous est **celui du brief, littéralement**. L'étiquette
> « **Incrément 1.1 — Interface** » employée jusqu'ici était une **invention de séance** : elle
> ne figure nulle part au brief, et elle rangeait sous « Interface » un travail qui est en
> réalité celui de l'**Incrément 2** (garde-fou tentatives + budget, verdict à deux axes,
> diagnostic `vrai_bug`/`test_a_reparer`, réparation automatique, suivi des coûts). Ce n'est pas
> un jugement sur le travail fait — c'est le vocabulaire qui était faux.
> **Aucun incrément ne s'invente : les seuls noms valides sont ceux du §12.**

| Incrément (§12 du brief) | État |
|---|---|
| **Incrément 0 — Preuve de concept** | ✅ **Terminé.** Pipeline complet `spec → analyse → génération → gate → exécution → verdict 2 axes → rapport`, prouvé de bout en bout sur un cas réel (`demande_materiel`) contre une instance Odoo neutralisée. |
| **Incrément 1 — Cœur du référentiel & exécution** | 🟡 **En cours.** **Livré** : hiérarchie Projet→Module→Cas (`0004`) + connecteur au projet (`0005`) ; séparation UX Gestion/Exécution (§8) ; historisation (`test_case_version`) ; API FastAPI + SPA Vite/Vue ; explorateur Modules→Cas. **Reste** : **exécutions nommées transverses multi-modules** (le dernier gros manque du §7), archivage, rôles & permissions (QA / lead / admin / client externe). |
| **Incrément 2 — Fiabilisation & gouvernance du verdict** | 🟡 **En cours, largement avancé** — c'est l'essentiel du travail des 2 derniers jours, longtemps mal étiqueté « Interface ». **Livré** : garde-fou de validation humaine sur les diagnostics (`0013`) ; garde-fous **tentatives + budget** par cas (`0014`, budget porté par le gate) ; réparation automatique (`0014`) ; diagnostic sur signal du runtime (`0015`) ; critère d'adoption à deux axes (`0016`) ; suivi des coûts (`cost_ledger`, `BUDGET_PER_CASE_*`). **Reste** : calibrage des seuils (§6/§11.2) ; mode dev/utilisateur ; tableau de bord des modules « à retester » ; coûts réels Anthropic (aujourd'hui `estimated`). |
| **Incrément 3 — Élargissement du périmètre validé** | Non commencé. Ordre fixé au brief : (1) gestion de projet type Jira, (2) charge/perf, (3) sécurité, (4) CI/CD. |
| **Incrément 4 — Extension multi-connecteurs** | Non commencé. L'architecture est posée (`connector_type` au projet, `0005`). |
| **— Dette transverse, hors découpage §12** | **Mot de passe de connexion en clair** dans SQLite — bloquant avant tout déploiement client. ⚠️ Rangée « Incrément 2 » jusqu'ici : c'était faux, l'Incrément 2 du brief est la **gouvernance du verdict**, pas la sécurité. Cette dette n'appartient à aucun incrément du brief. |

**Tests : 311 Python · 36 vitest · build front OK.** Tout est vert au moment de ce rapport.

**Stack** : Python 3.10, FastAPI + SQLite (portable PostgreSQL), Behave + Playwright + odoorpc,
Anthropic (Claude), frontend Vite + Vue 3 + Tailwind (dark, esprit « Linear »).

**Lancer** : `python -m uvicorn testpilot.api.app:app --port 8011` (⚠️ le port 8000 est occupé
par un autre serveur, hors projet). CLI : `testpilot run specs/demande_materiel.md --yes`.

⚠️ **État de la reprise** :
- **Écart 3 CORRIGÉ et commité** (`c10b754`) : `meaningful_error()`, 3 tests, **168 verts**.
- **Écart 2 : décision `0008` livrée entièrement (A + C).** A = prompt (Règle 4 + `[Limite]`),
  prouvée par re-génération (cas **3**). C = lint non-bloquant au gate (`assertion_lint.py`,
  `GateOut.lint_warnings`, bandeau `ReviewGate.vue`). Preuve réelle : cas 2 signalé, cas 3 propre.
- **Scripts d'enquête/preuve commités** (reproductibles) : `scripts/confirm_ecart_parametres_steps.py`,
  `probe_traceback_complet.py`, `probe_champs_formulaire.py`, `prove_A_falsifiabilite.py`.
  Bases `.bak` gitignorées.
- **Cas 3** = artefact de preuve de A (re-génération) — **conservé** (décision du porteur).
  Backup avant sa création : `data/testpilot.db.pre-preuve-A.bak`.
- ✅ **`0014` — RÉPARATION AUTOMATIQUE LIVRÉE.** Le pilier annoncé qui n'existait pas : la
  boucle existe, **les deux chemins sont prouvés en réel**. Cas 2 : `technical_error` (2/3) →
  1 tentative → **`success / conforme` 3/3** — la **première exécution verte du projet**. v8
  **ratifiée** par le porteur → cas 2 **`validated`** (le premier). Cas 6 : `vrai_bug` → aucune
  réparation. ⚠️ **Le gate a tenu pendant que le circuit se trompait** (bug 1 actif : v7 jamais
  auto-approuvée) — l'architecture en couches a rattrapé une couche défaillante.
  → `decisions/0014-…md`.
- **Écart 1 : décision `0007` — CLOSE.** B ✅, B+ ✅ (au **2ᵉ essai**), A1 ✅ **mesuré**. Tout est
  prouvé **en conditions réelles**, capture d'écran à l'appui (exécution 7 du cas 2).
  ⚠️ **À lire absolument dans la note** : le **premier jet de B+ était AVEUGLE en run réel** et
  avait pourtant été livré « prouvé » — il lisait le marqueur dans la sortie de Behave, or Behave
  capture stdout/stderr/logging et ne les recrache pas sur un scénario vert **dès qu'un
  `environment.py` est présent** (ce que le runner assemble toujours). Le test de garde avait le
  **même angle mort que le code** (il omettait `environment.py`) ; seul le **re-run réel exigé par
  le porteur** l'a démasqué. Correctif : **fichier sidecar** (`TP_FIELD_FALLBACK_FILE`), qui
  supprime la dépendance au routage de Behave au lieu de la maîtriser.
  **Écart 4 : DIAGNOSTIC FAUX, classé** (3ᵉ après `0002` et `0007`) — ce n'était pas un bug.
  `report_json_path`/`report_html_path` étaient des **colonnes mortes** (jamais alimentées, ni
  par la CLI ni par l'API ; jamais lues nulle part). **Supprimées** (migration 7). Le rapport
  d'un run API a toujours fonctionné : il est **reconstruit depuis la base**.

---

## 2. Décisions structurantes tranchées (NE PAS re-débattre)

Chaque décision a sa note détaillée dans `docs/decisions/`.

### 2.1 Hiérarchie Projet → Module → Cas (§7) — `0004`
- Le socle Inc. 0 n'avait qu'un **champ texte `module`** sur `test_case`. Trou de conception.
- **Découverte clé** : ce champ avait un **double rôle conflaté** — métier (module affiché) ET
  technique (`case["module"]` servait à trouver le fichier `{module}.feature`).
- **Décision** : séparer. `module_id` (FK métier) **et** `feature_slug` (nom du `.feature`,
  technique, propre au cas). La colonne texte `module` a été **supprimée** (pas laissée inerte).
- Migration versionnée par `PRAGMA user_version` dans `store/db.py`, idempotente, gardée par
  introspection. Appliquée à la vraie base (backups `data/testpilot.db.pre*.bak`, gitignorés).

### 2.2 Le connecteur vit sur le PROJET, pas sur le cas — `0005`
- **Projet = l'application/ERP sous test** (ex. « Portail Sapian »). **Pas de niveau Client
  au-dessus** : « client externe » est un **rôle utilisateur** (§2), pas une entité.
- « Odoo » est une **valeur de connecteur**, **jamais** un nom de projet (l'erreur de la
  migration 1, corrigée : projet renommé « Odoo » → « Portail Sapian »).
- `project` porte `connector_type` + `base_url`/`database`/`username`/`password`.
  `test_case.connector_type` supprimé.
- **Runtime câblé dessus** (fait) : `connectors/runtime_env.py` traduit le projet en variables
  d'env, injectées dans le sous-processus behave ; `OdooConnector.from_project`. Sinon
  l'interface promettait un multi-projet que tout run trahissait en tapant la config globale.
- Le mot de passe est **write-only côté API** (jamais renvoyé). Stockage en clair = dette
  documentée → Incrément 2.

### 2.3 Un cas = un fichier `.feature` (PAS un scénario) — `0006`
- La granularité fine existe déjà **là où elle compte** : `scenario_result`, 2 statuts par
  scénario. La page détail module **déplie** les scénarios du dernier run à l'intérieur du cas.
- Migrer vers une granularité scénario impliquerait versioning/gate au niveau scénario :
  refonte lourde **non justifiée**. À revisiter seulement si ça devient réellement limitant.

### 2.4 Priorité de lecture, JAMAIS de `position` décorative — `0006` ⚠️ **amendée par `0009`**
- `test_case.priority` (`low|medium|high`) = **étiquette de lecture** assumée.
- ~~**Pas de colonne `position`.**~~ → **AMENDÉ par `0009`** (2026-07-16, demande du porteur).
  Ce que 0006 refusait — et qui reste refusé — c'est une position **décorative** : celle de
  l'ancien prototype existait en base et n'était **jamais alimentée** (tri réel = date de
  création), promettant un ordre que rien n'honorait. `0009` introduit un ordre **réellement
  honoré** par le tri (`ORDER BY position, id`) qui ne promet **rien** sur l'exécution. Les deux
  propriétés sont indissociables : non honoré = le champ mort de 0006 ; pilotant l'exécution =
  le piège §4.6. **Voir `0009` avant de toucher à ce champ.**
- Pour un cas automatisé, l'ordre d'exécution réel reste celui des scénarios **dans le
  `.feature`** — `position` ne l'atteint jamais (gardé par test).
- L'infobulle de la priorité **dit explicitement** qu'elle n'ordonne pas l'exécution ; celle de
  l'ordre manuel aussi.
- ⚠️ Depuis `0009`, **la priorité n'ordonne plus la liste** (elle le faisait avant) : c'est une
  pure étiquette, ce que ce §2.4 affirmait déjà sans que le tri le reflète.
- Un ordre **d'exécution** réel viendra avec l'**Exécution nommée transverse** (§7), où il aura un
  référent — ce sera **sa** décision, elle n'hérite pas de l'ordre d'affichage.

### 2.5 « Ajouter un cas » = fournir une SPEC — `0006`
- **Jamais de coquille manuelle inerte.** `POST /api/modules/{id}/cases` accepte
  `spec_content` (ou `spec_path`) et enchaîne **spec → analyse → génération → gate**, en
  imposant le `module_id`. Tâche de fond (202 + polling du job), comme les exécutions.
- Raison : un cas sans version ni Gherkin afficherait un cas qui ne teste rien (§3) — c'était
  précisément le « cas fantôme » de l'ancien prototype.
- Après génération, on emmène vers le détail du cas : la version existe mais **n'est pas
  relue** — le gate reste souverain.

### 2.6 Ancien prototype (`../testpilot-agent`) = inspiration ponctuelle, jamais un modèle
- Il a été conçu **avant** les invariants actuels. Limites identifiées : référentiel **scindé**
  (cas automatisé = pas de ligne en base, identité `auto:{suite}:{nom_scénario}` parsée du
  fichier → régénération = identité perdue), **statut mono-axe**, **pas de gate**.
- Repris : la **palette** (`main.css`), quelques primitives UI, la moitié RPC du connecteur
  Odoo, le harnais Behave (`environment.py` + bibliothèque de steps).
- Rejeté : son organisation de pages/navigation, son modèle de statut.

### 2.8 « Gestion des cas » est un EXPLORATEUR ; la première vue d'un projet est sa STRUCTURE
- **Trou constaté (2026-07-16)** : aucune vue ne rendait le niveau **Module**. L'onglet ouvrait
  la table plate de **tous** les cas, où le module n'était qu'un sous-titre — la hiérarchie
  `0004` (Projet → Module → Cas) existait en base mais **pas à l'écran**.
- **Décision** : la première vue d'un projet est **Modules** (`ModulesOverview`) ; on ouvre un
  module pour voir ses cas. La table plate **survit** en vue transverse « Tous les cas »
  (`/cases/all`) — elle garde ses compteurs, rien n'est perdu.
- **Arbre Modules → Cas** (`ModuleTree`) rendu par **`AppShell`, dans la barre latérale**, sous
  les onglets — **pas** dans une seconde colonne : deux bandeaux de navigation côte à côte
  gaspillaient l'espace (arbitrage du porteur). Les routes restent donc **à plat** (pas de route
  layout) et le contenu garde toute sa largeur ; état partagé dans `lib/useProjectTree.ts`.
- **L'arbre n'apparaît QUE sur les routes de gestion** (`CASES_ROUTES` dans `AppShell`) : un arbre
  de cas au-dessus d'une vue d'exécution brouillerait la séparation §8 (§4.8).
- **Deux niveaux, JAMAIS récursif** : il n'existe pas de sous-module (`0004`). Un arbre récursif
  promettrait une profondeur que le modèle n'a pas (§4.6). *(L'ancien prototype avait des
  sections récursives — inspiration ponctuelle, pas un modèle : §2.6.)*
- **Aucun statut fusionné dans l'arbre** : seul `validation_status` (mono-axe par nature) y
  figure, en **icône + mot en infobulle** — jamais la couleur seule, jamais les deux axes
  fusionnés (§4.1, §4.7). Les deux axes restent dans la table et le détail.
- ⚠️ **Bug SERVEUR trouvé au passage, corrigé** : `sqlite3.ProgrammingError: SQLite objects
  created in a thread can only be used in that same thread` → **HTTP 500 intermittent**. FastAPI
  exécute une dépendance `yield` **synchrone** (`api.deps.get_conn`) dans un thread du pool et
  l'endpoint dans un **autre** : la connexion (pourtant une par requête) change de thread en
  route. Correctif : `check_same_thread=False` dans `db.connect()` — il lève le contrôle de
  propriété, **n'ajoute aucun verrou** : l'invariant « une connexion par requête » reste ce qui
  rend l'ensemble correct. **Latent depuis toujours** : `TestClient` est synchrone et sérialise
  tout, donc 200 tests verts ne pouvaient pas le voir. Il a fallu un vrai navigateur chargeant
  l'arbre **en parallèle** de la page. 3 tests de non-régression (`tests/test_conn_threads.py`).

### 2.10 On n'efface JAMAIS un run — on annote (règle du porteur, 2026-07-16)
- **Aucune suppression d'exécution, jamais.** Cohérent avec §1/§5 du brief et avec la règle déjà
  actée pour projets/modules : **archivage, jamais de perte d'historique**.
- **Un échec est une donnée, pas un déchet.** La chaîne `v1 → v7 cassée → v2 restaurée → v8` est
  **la preuve que le gate a tenu** pendant que le circuit se trompait (`0014`) : l'effacer
  supprimerait le fait le plus instructif de la journée.
- Si le volume devient bruyant : **annoter** (« affecté par le bug X, corrigé »), jamais masquer.
- ⚠️ **Seule exception, et elle est étroite** : une trace **cassée par accident de manipulation**
  et **sans valeur de preuve** (l'exécution 10, restée `not_executed` parce qu'une migration a
  tourné serveur allumé). Décidée **explicitement par le porteur**, jamais par défaut.

### 2.9 Unicité des noms — un nom réutilisé = une info dupliquée à regrouper (migration 5)
- **Portées** : **projet** = global · **module** = par projet (deux projets peuvent avoir
  « Facturation » — ce n'est **pas** une duplication) · **titre de cas** = par module ·
  **`feature_slug`** = global.
- **Deux couches complémentaires, pas redondantes** : garde **applicative** dans les repos
  (`_key`/`casefold`, **Unicode**) qui lève `DuplicateName` → **HTTP 409** avec un message qui
  nomme le conflit ; **index UNIQUE** en base (`COLLATE NOCASE`) en filet de dernier recours.
  ⚠️ `COLLATE NOCASE` ne replie que l'**ASCII** : « CAFÉ » vs « Café » n'est attrapé que par la
  garde applicative. C'est la raison d'être des deux couches.
- **`feature_slug` global** : il nomme `{slug}.feature` dans un répertoire **commun** — deux cas
  au même slug écriraient dans le **même fichier**, l'un écrasant les tests de l'autre. Bug
  **latent** (jamais déclenché : `unique_feature_slug()` déduplique déjà à la génération), du
  même profil que le bug SQLite de concurrence. Index **partiel** (`WHERE feature_slug != ''`) :
  un slug vide ne produit aucun fichier, donc aucune collision.
- **Créer un cas par spec valide le titre AVANT** de lancer la tâche de fond : sinon on paierait
  un appel LLM de plusieurs minutes pour finir en job « failed » à l'insertion.
- **Les index vivent dans la migration, pas dans `schema.sql`** : ce fichier s'exécute *avant*
  les migrations, or `test_case.module_id`/`feature_slug` peuvent manquer sur une base
  antérieure (même raison que `idx_case_module`).
- **Ménage du référentiel réel (2026-07-16)** : les « doublons » vus à l'écran n'en étaient pas
  — trois **titres différents** tronqués par la colonne de l'arbre, dont deux **artefacts de mes
  propres scripts de preuve** (0007 A1, 0008 A). Audit : **zéro doublon** à tous les niveaux.
  Sur décision du porteur : cas 1 renommé (`demande_materiel` → « Demande de matériel »), cas 3
  et 4 supprimés avec leur descendance. Backup : `data/testpilot.db.pre-menage-unicite.bak`.
  ⚠️ **Leçon** : les scripts de preuve écrivent dans la **vraie** base — c'est ce qui donne des
  preuves réelles, mais ça laisse des déchets. À nettoyer derrière, ou à isoler.

### 2.7 Autres décisions actées
- **Navigation** : le projet est un **contexte porté par l'URL** (`/projects/:pid/...`), au-dessus
  des deux onglets **Gestion des cas / Exécution** (séparation §8 **structurelle**). Aucune vue
  ne mélange deux projets (filtres API + `pid` systématique côté front).
- **Vocabulaire** : **aucune valeur d'enum brute à l'écran**. Tout passe par
  `frontend/src/lib/status.ts`. Libellés courts + **infobulle « i »** pour les explications.
- **Shim `features.*`** dans `behave_runtime/environment.py` : le prompt impose
  `from features.environment import register_created` alors que le runner assemble un layout
  **plat**. Le shim (alias `sys.modules`) fait le pont — **ce n'est pas un oubli**, c'est
  documenté dans le fichier. Ne pas le supprimer.

---

## 3. Modèle de données actuel (`user_version = 12`)

```
project        id, name, description, created_at,
               connector_type, base_url, database, username, password   ← connecteur (0005)
   └─ module   id, project_id, name, description, created_at
        └─ test_case  id, title, description, origin, validation_status,
                      module_id,          ← rangement MÉTIER (0004)
                      feature_slug,       ← nom du .feature, TECHNIQUE (0004)
                      priority,           ← étiquette de lecture (0006, migration 3)
                      position,           ← ordre d'AFFICHAGE manuel (0009, migration 6)
                      current_version_id, last_execution_status,
                      last_functional_status, last_executed_at,
                      author, created_at, updated_at
             ├─ test_case_version  id, test_case_id, version_number, spec_content, spec_hash,
             │                     feature_content, steps_content, feature_path, steps_path,
             │                     change_summary, created_at, created_by
             ├─ review_decision    id, test_case_id, version_id, decision, reviewer,
             │                     comment, decided_at
             └─ execution          id, test_case_id, version_id,
                                   execution_status, functional_status,   ← LES 2 AXES
                                   scenarios_total/passed/failed, cost_usd, iterations,
                                   duration_seconds,   ← (report_*_path SUPPRIMÉS, migration 7)
                                   field_fallbacks,    ← replis libellé→name du run (0007 B+)
                                   trigger, started_at
                   ├─ scenario_result  id, execution_id, scenario_name,
                   │                   execution_status, functional_status,  ← 2 axes/scénario
                   │                   failure_type, cause_category, error_summary
                   └─ repair_attempt   id, execution_id, attempt_number, failure_signature,
                                       cause_category, defect_origin, confirmation_status,
                                       confirmed_by, confirmed_at, what_was_tried, created_at
cost_ledger    id, period_month, test_case_id,  ← le CAS qui a coûté : le lien du §9 (migration 12)
                   execution_id,                ← contexte facultatif (une génération n'en a pas)
                   phase, model, cost_usd, source, created_at
```

**Migrations** (`store/db.py`, `PRAGMA user_version`) : 1 = project/module + feature_slug ;
2 = connecteur sur projet + `Odoo`→`Portail Sapian` ; 3 = `priority` ; 4 = `field_fallbacks`
sur `execution` (0007 B+) ; 5 = index UNIQUE d'unicité des noms (§2.9) ;
6 = `test_case.position` (ordre d'affichage manuel, `0009`) ;
7 = suppression des colonnes mortes `report_*_path` (écart 4 : diagnostic faux) ;
8 = verdict humain sur les diagnostics (`0013`) ; 9 = `review_decision.repair_budget` (`0014`) ;
10 = `scenario_result.step_text` persisté pour l'audit (`0015`) ;
11 = `execution.error_message` (la raison d'un plantage, à l'écran) ;
12 = **`cost_ledger.test_case_id`** — le coût appartient au **cas**, l'exécution n'en est qu'un
contexte. Sans elle, le coût de génération du chemin écran n'avait **aucune exécution où
s'accrocher** et était perdu : le §9 y était structurellement inmesurable.
Non implémenté du §7 : l'**Exécution nommée transverse**.

### ⚠️ Les bugs que SEUL le réel trouve — une suite verte ne garantit rien sur l'intégration

*Famille de défauts qui partagent une cause : **les tests partent tous d'un monde neuf et
sérialisé**, alors que la production tourne sur une base existante, en parallèle, avec un vrai
navigateur. Chaque occurrence a été trouvée par le réel, jamais par la suite. Ce n'est pas une
critique des tests : c'est la limite structurelle de ce qu'un test peut voir. → méthode §8.8.*

| # | le défaut | pourquoi les tests étaient aveugles | trouvé par |
|---|---|---|---|
| **1** | **`schema.sql` : un index sur une colonne de migration** *(2026-07-17)* — `CREATE INDEX … ON cost_ledger(test_case_id)` placé dans `schema.sql`, qui **s'exécute AVANT les migrations** → `no such column: test_case_id` → **toute ouverture d'une base existante plante**, application comprise. | Les **416 tests verts** partent d'un schéma **neuf**, où `CREATE TABLE` crée déjà la colonne. Le défaut n'existe que sur une base **antérieure** — soit **exactement le cas de tous les utilisateurs**. | La **vraie base**, à la première ouverture. Gardé depuis par `test_une_base_SANS_la_colonne_s_ouvre_toujours` (vérifié comme échouant sur le schéma fautif). |
| **2** | **Connexion SQLite passée entre threads** *(§2.8)* — `sqlite3.ProgrammingError` → **HTTP 500 intermittent**. FastAPI exécute la dépendance `yield` synchrone dans un thread du pool et l'endpoint dans un **autre**. | `TestClient` est **synchrone et sérialise tout** : sans requêtes concurrentes, le pool réutilise le même thread. **200 tests verts** ne pouvaient pas le voir. | Un **vrai navigateur** chargeant l'arbre **en parallèle** de la page. |
| **3** | **Marqueur de repli aveugle en run réel** *(`0007` B+)* — le 1ᵉʳ jet lisait le repli dans la sortie de Behave, qui **capture stdout/stderr et ne les recrache pas sur un scénario vert** dès qu'un `environment.py` est présent. | Le **test de garde partageait l'angle mort du code** : il omettait `environment.py`, que le runner assemble pourtant toujours. Un test écrit avec la même hypothèse fausse que le code **valide l'erreur**. | Le **re-run réel exigé par le porteur**. Correctif : fichier sidecar — supprimer la dépendance plutôt que la maîtriser. |

> **La leçon commune, et elle vaut pour la suite** : ces trois défauts étaient **invisibles par
> construction**. Le réflexe « la suite est verte, donc c'est bon » les aurait tous laissés
> passer — et deux d'entre eux plantaient l'application chez l'utilisateur. **Le seul remède
> connu reste le §8.8 : vérifier en conditions réelles quand c'est possible.**
>
> *(Le n°1 est d'autant plus net que le codebase **documentait déjà la leçon** — les index
> d'unicité et `idx_case_module` vivent dans leur migration pour cette raison exacte, et le
> commentaire de `schema.sql` le disait. Je l'ai rejouée quand même : une leçon écrite n'est pas
> une leçon appliquée — c'est le principe 6 de `PRINCIPES.md`, cette fois contre moi.)*

---

## 4. Invariants à NE JAMAIS régresser

1. **Les deux axes ne fusionnent jamais** (§5). `execution_status` (le test a-t-il pu tourner ?)
   et `functional_status` (l'app est-elle conforme ?) sont deux jugements distincts, partout :
   base, API, rapport, UI (`StatusPair`). Jamais un badge unique « OK/KO ».
2. **Un statut n'est jamais déclaratif** : il est toujours la conséquence d'une exécution réelle.
3. **Le gate de relecture humaine est obligatoire avant la première exécution** d'une version
   générée par IA (§4). Il dépend de l'approbation de la **version**, jamais du module/projet.
4. **Asymétrie du défaut** (§5) : un `vrai_bug` se remonte **directement** ; un
   `test_a_reparer` ou un `indetermine` exige une **confirmation humaine** (faux-négatif
   inacceptable, faux-positif acceptable).
5. **Un échec technique ne vaut jamais « conforme »** : en cas de plantage, le run est clos en
   `technical_error / indetermine` — jamais un faux succès.
6. **Jamais « affiché ≠ réel »** : ce que l'UI promet, le runtime doit le tenir (leçon du
   câblage connexion-projet ; raison du refus d'un `position` décoratif).
7. **Aucune valeur d'enum brute à l'écran** ; aucun libellé qui se contredit (ex. « Jamais
   lancé » sur un cas qui a un verdict → corrigé en « Non validé »).
8. **Séparation Gestion des cas / Exécution** visible et structurelle (§8), sous le contexte
   Projet. **Aucun mélange inter-projets**.
9. **Garde-fou anti-production** : `ODOO_ENV=prod` fait échouer le harnais. Un projet ne peut
   **jamais** produire cette variable.
10. **Coûts** : cap par-run (`COST_LIMIT_PER_RUN_USD`) + provenance honnête du coût
    (`estimated` vs `anthropic_api` — le label `anthropic_api` **uniquement** si un chiffre réel
    a été mesuré).
    **L'unique cible de coût du produit est le §9 du brief : moins de 1 € par nouveau cas de
    test** (génération + exécution + rapport, **réparations cumulées comprises**). Il n'y en a
    **pas d'autre**.
    ✅ **Le « budget 50 €/mois » n'est PAS un garde-fou produit** — c'est le **budget de
    développement du porteur**. Ne pas le ré-implémenter, ne rien construire dessus.
    *(Mis à jour le 2026-07-17 : ce point n'est plus une divergence non résolue entre le code et
    le brief. Le **brief lui-même a été amendé** — §6, §9, §11.2 + journal des amendements en
    tête — sur arbitrage du porteur. `config.MONTHLY_BUDGET_EUR/_USD` existe et n'est lu par
    personne : c'est **voulu**, pas un oubli.)*

---

## 5. Historique des commits

```
b0235b8  Page détail module (0006) : priorité de lecture, ajout par spec, dépliage scénarios
14e0e41  Réutilisation des steps partagés (0003, A+B) : catalogue montré, AST, transport refusé
24b8ee6  Parser des steps errored (0002) : formatter maison, error_text(), http_error
70f8792  Runtime branché sur la connexion du projet (fin de l'incohérence affiché/réel)
769561c  Redesign CaseDetail (dernier résultat, relecture/exécution, onglets code, historique)
39da584  Fix vocabulaire validation ('Jamais lancé' → 'Non validé')
20851d5  Passe design ExecutionsList + ReportView
7b7b24a  Backlog centralisé
629d365  Connecteur au niveau Projet (0005) + migration 2
e280182  Gestion projets (création/suppression cascade/renommage)
a2b5599  Nav projet (URL, sélecteur, fil d'Ariane)
f5fd54f  Hiérarchie Projet→Module→Cas (0004) + migration 1
7f8c1b0  Passe UX (vocabulaire, arborescence, alignements)
3ee5465  Frontend fonctionnel (SPA, 2 axes, gate)
f5b48ad  Backend API
--- Incrément 0 ---
23c0af1  e2e demande_materiel + correctifs connecteur/CLI
0a38095  Harnais Behave · cbc03a2 Connecteur Odoo · 14eeca1 Reporting+CLI
8ddf9ae  Guardrails · 46cbef9 + 02f74f5 Verdict · 4373458 Execution
e6aab00  Generation · 73294b6 Analysis · b0b5c01 Socle
```

---

## 6. Runs e2e réels — TERMINÉS, concluants, **4 écarts trouvés (1 corrigé, 3 ouverts)**

Deux passages successifs sur la vraie base et la vraie instance Odoo. Le premier a **généré**
le cas 2 ; le second l'a **exécuté** pour prouver l'écart que le premier avait fait soupçonner.

### 6.0 Run #1 — génération (`scripts/run_reel_0003_0006.py`)

**But** : valider **en un passage** (a) le flux 0006 « ajouter un cas par spec » et (b) l'effet
réel de 0003 « l'agent réutilise-t-il les steps partagés ? ».

**Dispositif** : passe par la **vraie route HTTP** (`POST /api/modules/1/cases`) via
`TestClient` (qui exécute la tâche de fond de façon synchrone), sur la **vraie base**. Spec :
`specs/validation_champ_requis.md` (variante réelle de `demande_materiel`, ciblée sur la
validation d'un champ requis — un besoin qui **exige** le comptage de tickets, donc le step
partagé). Base sauvegardée : `data/testpilot.db.pre-run-reel.bak`. **Rejouable** :
`PYTHONUTF8=1 python scripts/run_reel_0003_0006.py`.

### (a) Flux 0006 — ✅ **validé de bout en bout**
```
POST /api/modules/1/cases        → HTTP 202
job                              → done, case_id = 2
projet / module                  → Portail Sapian / Demande materiel   (module imposé ✓)
validation_status                → never_executed
gate.allowed                     → False   ← généré mais NON RELU (invariant §4 tenu ✓)
versions                         → 1
```
Aucune coquille : le cas naît **avec** sa version, son Gherkin et ses steps.

### (b) Mesure 0003 — ✅ **validé en conditions réelles**
| Mesure | Résultat |
|---|---|
| Steps partagés réutilisés | **16 / 37 libellés uniques** |
| **Step de comptage partagé réutilisé** | ✅ **OUI** — les trois : `…est enregistré pour comparaison`, `…augmente de 1`, `…n'a pas augmenté` |
| Steps custom écrits | **4**, dont l'**existence** est à chaque fois justifiée (chaîne de 300 car., chemin de redirection, `team_id`, cohérence chaîne longue) — ⚠️ mais voir l'**écart 2** du §6.1 : *écrire* un step custom légitime ne veut pas dire le **bien écrire**, et celui de la « cohérence chaîne longue » ne peut jamais échouer |
| Transport brut (`requests`/`urllib`/`/web/dataset`) | ✅ **Aucun** |

Avant 0003 : l'agent inventait `_count_tickets` avec `requests` → 404, tuant les 3 scénarios.
Après : il réutilise la bibliothèque et n'écrit du custom que là où c'est justifié.

### Nuance de mesure à connaître
`steps_library.catalogue()` renvoie **43 déclarations** pour **37 libellés uniques** : certaines
fonctions portent deux décorateurs (`@when` **et** `@then` sur le même libellé). Les deux
chiffres sont corrects, ils ne mesurent pas la même chose.

---

### 6.1 Run #2 — confirmation de l'écart (`scripts/confirm_ecart_parametres_steps.py`)

**But** : prouver **par une exécution** l'écart soupçonné au run #1, plutôt que par la seule
lecture du helper (§8.5).

**Manipulation assumée** : la version 2 a été **approuvée délibérément** au gate pour pouvoir
l'exécuter. Ce n'est **pas** une validation de complaisance — c'est le seul moyen d'exécuter un
cas qu'on sait cassé. La `review_decision` en base (reviewer `confirmation-ecart`) porte un
commentaire qui le dit explicitement. Base sauvegardée :
`data/testpilot.db.pre-confirmation-ecart.bak`.

**Résultat de l'exécution 2** : `technical_error / indetermine`, 3 scénarios (1 passé, 2 en
échec), ~324 s. Classification obtenue : `ui_timeout` → `wrong_field_name` → « Champ/sélecteur
introuvable » → `test_a_reparer`. **La taxonomie 0002 est validée de bout en bout.**

### ✅ ÉCART 1 — CONFIRMÉ PAR EXÉCUTION (sémantique des paramètres de steps)

⚠️ **Le verdict seul ne prouvait rien** : d'après `defect_taxonomy.py`, le mot-clé « timeout »
suffit à produire `wrong_field_name`, et `ui_timeout` y tombe aussi par repli (`_TYPE_FALLBACK`).
**N'importe quel** timeout aurait donné ce verdict. La preuve a exigé de rejouer le scénario en
capturant le traceback complet (`scripts/probe_traceback_complet.py`) :

```
playwright._impl._errors.TimeoutError: Locator.fill: Timeout 30000ms exceeded.
Call log:
  - waiting for locator("[name='Raison de la demande']")
```

Et la sonde du formulaire réel (`scripts/probe_champs_formulaire.py`) tranche la dernière
ambiguïté — le champ **existe**, sous le nom technique `name` :

```
[visible] name='name'  <input/text>  libellé affiché : 'Raison de la demande *'
```

→ **erreur de PARAMÉTRAGE** (`test_a_reparer`), **pas** un bug applicatif. Diagnostic clos.

#### ⚠️ Correction du diagnostic initial (le rapport précédent avait tort sur ce point)

Le rapport parlait d'une « incohérence interne » de l'agent. **C'est inexact, et ça change le
correctif.** Le step *custom* écrit par l'agent fait :

```python
locator = page.get_by_label(field)   # résout le LIBELLÉ humain — et ça marche
```

L'agent applique un modèle **cohérent** : libellé humain pour l'UI, nom technique pour le RPC.
Les deux conventions sont défendables. Le vrai problème : le placeholder `{field}` de la
bibliothèque partagée signifie « attribut HTML `name` » **sans le dire nulle part**. Ce n'est
pas une confusion de l'agent, c'est un **désaccord de convention**.

→ **Décision `0007` tranchée** (`docs/decisions/0007-…md`). Racine de **famille commune** avec
`0008`/`0003` (trou de consigne : le catalogue montre le libellé, pas la sémantique de
`{field}`), **mais** — contrairement à `0008` — un remède **technique** existe (un champ est
résoluble par `name` *et* par libellé). **Bug DÉTERMINISTE** : reproduit à l'identique cas 2
**et** cas 3. Verdict : **B porteur** (helpers UI tolérants, `name` d'abord / libellé en repli,
**repli TRACÉ** et visible en mode dev §5 — jamais silencieux, sinon une vraie régression Odoo
serait absorbée) **+ A1** (annotation catalogue `{field}` = attribut HTML `name`, **maintenant**).
À implémenter (plan à valider).

### ⚠️ ÉCART 2 — un « conforme » qui ne vaut rien (LE PLUS GRAVE, non corrigé)

Le scénario `[Limite]` est passé **`success / conforme`**. Son assertion générée :
```python
else:
    error_visible = (...)
    assert error_visible or "/your-ticket-has-been-submitted" not in current_url
```
Dans la branche `else`, on sait déjà que l'URL **ne contient pas** le chemin de succès : le
`not in` est **toujours vrai** par construction, donc `error_visible or True` **toujours vrai**.
L'assertion ne peut **jamais** échouer — et la branche `if` n'assertit rien du tout.
**Ce step passe quoi que fasse l'application.**

C'est frontalement l'**invariant §4.2** (« un statut n'est jamais déclaratif ») et une fabrique
à **faux-négatifs** — que le §4.4 déclare **inacceptables**. L'écart 1 est bruyant (il casse le
test, on le voit) ; celui-ci est **silencieux et ment dans le bon sens**. Défaut du **code
généré**, pas du produit — famille distincte de l'écart 1 (l'agent écrit des assertions qui ne
peuvent pas échouer).

→ **Décision `0008`** (`docs/decisions/0008-…md`) : **A** (prompt — falsifiabilité + `[Limite]`
en **disjonction falsifiable**) **+ C** (lint non-bloquant surfacé au gate) **+ extension
contextuelle**. **Point structurant** : une tautologie **passe à l'exécution**, donc ni dry-run
ni run réel ne peuvent l'attraper — seuls prévenir (prompt), détecter statiquement (avant le
gate) ou faire trancher l'humain (gate) sont possibles. **A ✅ + C ✅ livrés et prouvés**
(prompt + lint non-bloquant au gate ; cas 2 signalé, cas 3 propre). Nuance de racine : la **spec**
portait ici l'ambiguïté (l.60-63) — d'où une règle de *falsifiabilité*, pas d'attendu unique.

### ✅ ÉCART 3 — CORRIGÉ (le message d'erreur porte enfin la cause)

**Diagnostic affiné** (le rapport disait « on stocke le début » — c'est vrai mais insuffisant) :
`behave_result.py` construisait `BehaveScenario.error = err[:300]`, la **tête** du traceback
(frames internes de Behave/Playwright), inexploitable. Le résumé déjà extrait par
`classify_failure` **s'arrête à la première ligne** (`(.+?)(?:\n|$)`) — or le sélecteur fautif
est dans le bloc **`Call log:`** de Playwright, **après** ce retour à la ligne. Réutiliser ce
résumé n'aurait donc **pas** suffi.

**Correctif** : nouveau helper `meaningful_error()` qui repart de la **dernière ligne
d'exception** jusqu'à la fin (message + `Call log`), avec repli sur la queue si aucune ligne
d'exception n'est identifiable. Branché sur le champ scénario. `classify_failure`,
`failure_type`, `BehaveFailure.raw` **inchangés** (aucune régression du symptôme).

**Preuve (exécution 3, re-run réel du cas 2)** : le sélecteur apparaît maintenant en base et à
l'API —
```
error_summary : playwright…TimeoutError: Locator.fill: Timeout 30000ms exceeded.
                Call log:
                  - waiting for locator("[name='Raison de la demande']")
```
3 tests de non-régression ajoutés (`tests/test_errored_steps.py`), suite complète **168 verte**.

⚠️ **Visibilité à l'écran — pas encore complète** : le message corrigé remonte au data-layer et
à l'API. Mais (a) `ReportView` l'affiche (`s.error`) **via le rapport JSON** — absent pour les
runs déclenchés par l'API — ⚠️ **faux** : le rapport est reconstruit depuis la base et répond
(200), cf. écart 4 « classé » ci-dessous ; (b) le **dépliage** de la
page cas (`CaseRow`) n'affiche que les deux axes, **pas** la cause — c'est un choix de design de
`0006`, pas un bug. Surface l'erreur dans le dépliage = **choix produit à trancher**, non fait.

### ⚠️ ÉCART 4 — les runs déclenchés par l'API ne produisent aucun rapport (non corrigé)

`report_json_path` et `report_html_path` sont **vides** pour l'exécution 2 : `run_service._persist`
ne les écrit jamais, alors que la **CLI** le fait (cf. `data/reports/demande_materiel_v1.json`,
produit par le run CLI). L'UI promet un rapport que le runtime ne produit pas → **invariant §4.6**
(« jamais affiché ≠ réel »).

### Suite à donner — ordre arrêté avec le porteur (2026-07-15)

**Décidé** : traiter **écart 3 d'abord** (correctif pur, sans décision, outille les autres) →
**puis écart 2** (génération, avec décision une fois le diagnostic fiable) → **puis `0007`**
pour l'écart 1 (décision + plan écrits avant tout code).

- ✅ **Écart 3 — FAIT** (commit `c10b754`).
- ✅ **Écart 2 — FAIT (`0008`, A + C).** A : prompt (Règle 4 + `[Limite]` falsifiable), prouvé
  par re-génération (cas 3). C : lint pur `assertion_lint.py` (dont motif contextuel exact) →
  `GateOut.lint_warnings` + bandeau non-bloquant `ReviewGate.vue`. Preuve réelle : cas 2 signalé,
  cas 3 propre. Détail : `docs/decisions/0008-…md`.
- ✅ **Écart 1 / `0007` — CLOS. B + B+ + A1, tous prouvés en réel.**
  - **B** : helpers UI tolérants (`resolve_field_name`, name-d'abord/libellé-en-repli, repli
    tracé). Prouvé : le cas 2 ne timeoute plus sur le champ.
  - **B+** : le repli remonte jusqu'à l'écran (bandeau + pastille), **au 2ᵉ essai**. Le 1ᵉʳ jet
    lisait le marqueur dans la sortie de Behave et était **aveugle en run réel** — Behave capture
    stdout/stderr/logging et ne les recrache pas sur un scénario vert **dès qu'un `environment.py`
    est présent** (toujours assemblé par le runner). Le **test de garde partageait l'angle mort du
    code** (il omettait `environment.py`) ; le **re-run réel** l'a démasqué, aucun test ne
    l'aurait fait. Correctif : **fichier sidecar** `TP_FIELD_FALLBACK_FILE` (arbitrage du porteur :
    supprimer la dépendance au routage de Behave plutôt que la maîtriser). Garde réécrit sur le
    **vrai `BehaveRunner`** avec `environment.py` assemblé — **vérifié qu'il échoue sur l'ancienne
    implémentation**. Preuve : exécution 7 du cas 2 + capture d'écran.
  - **A1** : contrat `{field}` = nom technique dans le catalogue. **Mesure d'obéissance faite** :
    l'agent écrit `champ "name"` là où les cas 2 et 3 écrivaient `champ "Raison de la demande"`.
    Réserve : **1 échantillon**, LLM non déterministe.
  - Scripts : `measure_A1_nom_technique.py`, `prove_Bplus_repli_surface.py`,
    `probe_capture_behave_reelle.py`, `probe_marqueur_run_reel.py`, `shot_Bplus_ecran.py`.

- ❌ **Écart 4 — DIAGNOSTIC FAUX, classé (2026-07-16).** Les deux affirmations de la note étaient
  inexactes, **mesuré** : (a) « alors que la CLI le fait » → la CLI ne persiste **pas** ces chemins
  non plus (son `finalize()` ne les passe pas ; elle écrit des fichiers dans `data/reports/` sans
  les stocker) ; (b) « l'UI promet un rapport que le runtime ne fournit pas » → `GET
  /api/executions/7/report(.html)` répond **200** pour un run API : `build_report_for_execution`
  le **reconstruit depuis la base**, sans fichier. Le vrai défaut était l'**inverse** : deux
  **colonnes mortes**, jamais alimentées **ni lues** (aucun lecteur dans tout le code, l'API ne
  les exposait même pas) — le `position` décoratif de §2.4, la colonne `module` de `0004`.
  **Correctif : suppression** (migration 7) plutôt qu'écrire du code pour alimenter ce que
  personne ne lit. **Leçon** : un diagnostic non vérifié a failli piloter un chantier entier.

État : cas 2 = **vrai cas** du référentiel, version 2 approuvée (délibérément), **exécutée 3
fois** (exécutions 2 = confirmation, 3 = preuve du correctif d'écart 3). Bases restaurables :
`data/testpilot.db.pre-run-reel.bak` (avant génération), `…pre-confirmation-ecart.bak` (avant
approbation), `…pre-ecart3-verif.bak` (avant re-run de preuve).

---

## 7. Backlog ouvert (voir `docs/BACKLOG.md`)

⚠️ **L'ordre ci-dessous est une RECOMMANDATION, pas une décision** — les rangs 1 à 3 sortent des
écarts trouvés au run #2 (§6) et n'ont **pas** été arbitrés par le porteur. À trancher à la
reprise (voir « Suite à donner » du §6).

| Priorité | Item |
|---|---|
| ✅ **FAIT** | **Message d'erreur détruit avant l'écran** (écart 3 du §6) : `meaningful_error()` remonte la cause (message + `Call log` avec le sélecteur) au lieu de la tête du traceback. Prouvé sur l'exécution 3, 168 tests verts. *Reste* : visibilité complète à l'écran (dépend de l'écart 4 + choix d'affichage dans le dépliage). |
| ✅ **FAIT** | **Assertion tautologique → faux « conforme »** (écart 2 du §6). Décision `0008`, **A + C livrés et prouvés**. **A** : prompt (Règle 4 falsifiabilité + `[Limite]` en disjonction falsifiable). **C** : lint pur `assertion_lint.py` (dont motif contextuel exact de l'écart 2) → `GateOut.lint_warnings`, bandeau non-bloquant dans `ReviewGate.vue`. Preuve réelle : gate du cas 2 signale la tautologie, cas 3 (re-généré) propre. 181 Python + 15 vitest verts. |
| ✅ **FAIT** | **Sémantique des paramètres de steps** (écart 1, `0007` — **CLOS**). **B** : helpers UI tolérants (name-d'abord / libellé-en-repli, repli tracé). **B+** : repli → `execution.field_fallbacks` (migration 4) → bandeau `FieldFallbackNotice` + pastille d'historique, **visible même sur un run vert** ; transport par **fichier sidecar** (`TP_FIELD_FALLBACK_FILE`) — le 1ᵉʳ jet lisait la sortie de Behave et était **aveugle en run réel**, cf. la note. **A1** : contrat `{field}` = nom technique au catalogue, **obéissance mesurée**. Prouvé en réel (exécution 7 du cas 2 + capture). |
| ❌ **CLASSÉ — diagnostic faux** | **Runs API sans rapport** (écart 4) : **le bug n'existait pas**. La CLI ne persistait pas ces chemins non plus, et le rapport d'un run API répond bien (reconstruit depuis la base). `report_json_path`/`report_html_path` étaient des **colonnes mortes** → **supprimées** (migration 7). 3ᵉ diagnostic corrigé après vérification, après `0002` et `0007`. |
| **5** | **Exécution nommée transverse** (§7, JTBD essentiel §3) : regroupement de cas de modules différents, rapport attaché à l'exécution. L'UI laisse déjà la porte ouverte (badge « Cas unique / Suite transverse », champ `suite_name` réservé côté API). C'est **le dernier gros manque du §7**. |
| **6** | **Confirmations `pending_human`** (`0001`) : écran de traitement de la file des origines de défaut. |
| **7** | **Édition de la connexion d'un projet** : `PATCH /api/projects/{id}` ne gère que nom/description. |
| **8** | `testpilot run --project` : lever l'implicite (la CLI prend le **premier** projet). Sans effet observable tant qu'il n'y a qu'un projet réel. |
| **9 — observation** | Quasi-doublons sémantiques (volet C de `0003`) : écarté, à reconsidérer avec des exemples concrets après plusieurs runs. |
| **Dette transverse — bloquant client** | **Mot de passe de connexion en clair** dans SQLite. Atténué (write-only côté API) mais à chiffrer / passer en gestionnaire de secrets **avant tout déploiement client**. ⚠️ Étiquetée « Inc. 2 » jusqu'au 2026-07-17 : faux (l'Incrément 2 du brief = gouvernance du verdict). N'appartient à aucun incrément du §12. |

---

## 8. Méthode de travail à maintenir

1. **Proposer un plan avant de coder.** Pour tout chantier non trivial : arborescence, endpoints,
   composants, schéma — puis **attendre la validation**.
2. **S'arrêter aux décisions structurantes.** Modèle de données, sémantique produit, ce qu'un
   mot veut dire à l'écran : ce sont des choix du porteur, pas des détails d'implémentation.
3. **Ne jamais enchaîner plusieurs choix engageants sans validation explicite.**
4. **Signaler les écarts plutôt que de les arrondir** — même mineurs, même quand ça oblige à
   corriger sa propre analyse antérieure (cf. la note `0002`, dont le diagnostic initial était
   faux et a été corrigé au dossier plutôt que laissé tel quel).
5. **Mesurer plutôt que supposer.** Lire la source (celle de Behave a livré la vraie cause de
   `0002`), compter, prouver — les trois plus gros bugs de ce projet ont été trouvés en
   vérifiant une hypothèse, pas en la croyant.
6. **Auditer l'ancien prototype comme source d'inspiration ponctuelle**, jamais comme modèle.
7. **Tests avant commit**, commits atomiques par brique logique, **sans attribution Claude**
   dans les messages.
8. **Vérifier en conditions réelles** quand c'est possible (capture d'écran, run réel) — un test
   vert ne prouve pas qu'un utilisateur voit la bonne chose.
