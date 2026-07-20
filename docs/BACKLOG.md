# Backlog — reports assumés

Point d'entrée unique des travaux **différés et documentés** (chaque entrée renvoie à sa
décision détaillée dans `docs/decisions/`). Ordonné par incrément cible.

> ⚠️ **Le brief produit est la seule source de vérité** ; ce backlog lui est subordonné. Toute
> déviation doit être signalée et validée, jamais actée en autonomie.
>
> **Les noms d'incréments sont ceux du §12 du brief, et eux seuls** — aucun ne s'invente.
> *(Révisé le 2026-07-17 : les sections ci-dessous portent des étiquettes d'incrément héritées
> d'un découpage de séance qui ne correspond pas au §12 — notamment « Incrément 1 » pour du
> travail relevant de l'Incrément 2, cf. `CONTINUITE.md` §1. **Re-sectionner ce fichier suppose
> une dizaine d'arbitrages limites** — `0008`, `0010`, `0011` sont-ils de la génération ou de la
> gouvernance du verdict ? — **à trancher avec le porteur, pas seul.** L'étiquetage est faux, le
> contenu ne l'est pas.)*

## Dette transverse — n'appartient à aucun incrément du §12

*(Révisé le 2026-07-17 : cette section s'appelait « Incrément 2 » — faux, l'Incrément 2 du brief
est la **gouvernance du verdict**, pas la sécurité.)*

- [ ] **Secret de connexion en clair** — le mot de passe de connexion d'un projet est stocké
  en clair dans SQLite. Acceptable en dev local (instance Odoo neutralisée), **inacceptable
  avant le premier déploiement client**. À traiter : chiffrement au repos ou gestionnaire de
  secrets. Atténuation déjà en place : l'API ne renvoie jamais le mot de passe (write-only).
  → voir `decisions/0005-connecteur-au-niveau-projet.md`.

- [ ] 🔴 **`test_case_version.spec_content` à SUPPRIMER — dette contractée à l'étape 1 de la
  séparation (migration 13, 2026-07-19).** La spec est désormais la **source unique** portée par
  `case_group.spec_content` ; `version.spec_content` n'est plus qu'une **copie legacy**, gardée
  uniquement parce que la génération/réparation l'écrivent/le lisent encore. **À solder à l'étape 3**
  (génération « un angle par appel » recâblée sur `case_group.spec_content`) : le champ deviendra
  vide et inutilisé, puis **supprimé par migration dédiée**. Il ne doit **jamais** redevenir une
  source de vérité. `spec_hash` reste (référence de la spec ayant produit le cas). → décision de
  séparation (à consigner en `decisions/` à l'étape 2).

## Séparation « Spécification → cas par angle » (rouvre 0006, décision du porteur 2026-07-19)

Étape 1 (schéma) **livrée** : `case_group` (la Spécification, qui porte le document `spec_content`
+ `spec_hash`), colonnes `group_id`/`angle` sur `test_case`, migration 13 (legacy 1:1). Restent :

- [ ] **Étape 3 — génération « un angle par appel ».** Chaque cas naît de son propre appel
  `découverte → confirmation de périmètre → génération` (§4bis), lisant la spec depuis
  `case_group.spec_content`. Supprime le prompt « triptyque 3 scénarios ». **Solde la dette
  `spec_content`** (ci-dessus). Cohérence inter-cas garantie par l'annuaire (contrainte champs
  requis déjà livrée), pas par un contexte LLM partagé.
  - 🔴 **Le TITRE d'un cas = une phrase MÉTIER décrivant ce qui est vérifié, JAMAIS un préfixe
    d'angle brut.** Pas de `[NOMINAL]`/`[ERREUR]`/`[LIMITE]` dans le titre (exemple TestRail réel
    fourni : titre « Réception et délivrance d'une commande »). `angle` reste une **métadonnée
    interne** (nominal/erreur/limite/autre), jamais affichée dans le titre — utile pour une vue de
    couverture ou suggérer les angles manquants d'une spécification.

- [ ] **Étape 2 — UI/API de la Spécification.** CRUD Spécification ; écran module = Spécifications
  → cas ; vocabulaire métier (« étapes », plus « scénario » — cf. le point vocabulaire).
  - **Disposition d'un cas, inspirée de TestRail** (exemple réel fourni) : **ID + titre** en
    en-tête ; un **bloc métadonnées** (état, priorité si pertinent) ; puis **sections séparées** :
    **Préconditions** (contexte en langage clair) · **Étapes** numérotées simples (« 1. Ouvrir…,
    2. Aller dans… » — PAS du Gherkin Given/When/Then affiché) · **Résultat attendu** = UNE phrase
    de verdict global (« La commande est réservée puis délivrée. »), pas un résultat par étape.
  - Le **Gherkin technique reste réservé au mode dev** (§5 du brief : mode dev vs mode utilisateur).
  - À consigner en `decisions/` (numéro à attribuer) au démarrage de l'étape 2.

## Coût — le §9 du brief (moins de 1 €/cas), l'unique cible de coût du produit

- [x] **CostTracker : le plafond bornait un APPEL, pas un cas** — *fait le 2026-07-17*
  (`edc4002`). `propose_fix` créait un tracker **neuf à chaque tentative** → chacune repartait au
  plafond entier → un cas pouvait coûter **génération ($2) + budget × $2 = jusqu'à $6**, contre
  **$1,08** au §9. Garde-fou **décoratif** (le `position` de `0006`, le stall du circuit),
  appliqué à l'argent. Corrigé : **un seul** tracker partagé pour toute la boucle, escalade
  humaine au premier seuil (§6). Calibré sur le PIRE observé (c'est ainsi qu'on borne) :
  `REPAIR_COST_LIMIT_PER_CASE_USD = $0,62` (= $1,08 − $0,4529, la pire génération jamais mesurée) ;
  `REPAIR_BUDGET_DEFAULT` **reste à 2** (2 × $0,2895 = $0,5790 ≤ $0,62 — la mesure ne demande pas
  de descendre à 1). 5 tests, dont 3 vérifiés comme échouant sur le code d'avant.
- [x] **Le coût de génération du chemin ÉCRAN n'était pas au ledger** — *fait le 2026-07-17*
  (`eccc8f5`). `CostRepo.add_entry` n'était appelé que par `cli.py` et `repair_service` : un cas
  créé par l'écran ne laissait **aucune trace** de son coût de génération. **Défaut structurel** :
  le ledger reliait un coût à un cas par `JOIN execution`, or une génération **n'a pas
  d'exécution** — brancher l'appel n'aurait rien donné. → **migration 12** (`test_case_id` devient
  le lien). **Trouvé en branchant** : `SpecAnalyzer()` était construit **sans tracker** sur les
  deux chemins → le coût d'**analyse** valait toujours 0. Corrigé des deux côtés. 10 tests, dont
  8 vérifiés comme échouant avant. ⚠️ **Bug réel commis** : l'index dans `schema.sql` (qui
  s'exécute avant les migrations) faisait planter **toute ouverture d'une base existante** — 416
  tests verts ne l'ont pas vu, la vraie base l'a attrapé.
- [x] 🎉 **Le §9 est tenu, et mesuré sur le VRAI chemin** — *fait le 2026-07-17* (`7938b7b`).
  Mesure réelle (route HTTP, vraie base, vraie instance Odoo, spec `demande_materiel`) :
  **analyse $0,0157 + génération $0,1050 = $0,1207 = 11 % du §9** ; avec 2 réparations au tarif
  mesuré : **$0,6997 = 65 %**.
  ⚠️ **Le $0,4529 n'est PAS « le coût de la génération » : c'est le coût d'AVANT les garde-fous.**
  Même spec, l'agent écrit aujourd'hui **1 973 car. de steps contre 15 312** (7,8× moins) et couvre
  **plus** (4 scénarios / 44 assertions contre 3) : il réutilise la bibliothèque. Le travail de
  prompt (catalogue `0003`, notes `0012`, contrat `0007` A1) a coûté **0 €** et divisé la
  génération par ~4. **Ne jamais moyenner les deux régimes** ($0,22 n'est jamais arrivé).
  `COST_LIMIT_PER_RUN_USD` recalibré **$2,00 → $0,50** (il valait 16,6× le réel) : 4,8× le coût
  actuel **et** au-dessus du pire jamais mesuré — il n'aurait fait échouer aucune génération connue.
  ⚠️ **Les plafonds ne délivrent pas le §9** : $0,50 + $0,62 = $1,12 = 104 % si les deux
  saturaient ensemble. Ce sont des filets anti-emballement ; c'est le travail de garde-fous qui
  tient le §9. Les serrer ferait échouer des créations légitimes.
- [x] **Re-mesurer le coût d'une réparation** — *fait au rejeu du 2026-07-17 (soir)*. **$0,2065/
  tentative** contre $0,2895 avant le fix P0 : **−29 %**, le dry-run supprime un appel LLM perdu.
  ⚠️ **2 échantillons très dispersés** ($0,3088 vs $0,1041) : le coût suit le **nombre de tours
  ReAct**, pas un tarif fixe — ne pas le traiter comme une constante. Le plafond $0,62 reste bon.
- [ ] 🔴 **La boucle rachète les mêmes correctifs à chaque rejeu** (`0018` — **note écrite, À
  ARBITRER, PRIORITÉ 1 — aucun code avant arbitrage**). `v7` fait passer **1 scénario sur 3** (v1 :
  0/3), délègue l'auth, ne réinvente aucun transport — **et elle est jetée**, disque rembobiné sur
  `v1`. Cause : `est_executable` exige que **TOUS** les scénarios tournent ; 2/3 en
  `technical_error` ⇒ verdict global `technical_error` ⇒ non adoptée.
  **`0016` a corrigé « passe au vert » → « tourne », mais « tourne » est resté du tout-ou-rien.**
  Conséquence chiffrée : chaque rejeu repart de `v1`, dépense son budget à **re-corriger ce qui
  l'était déjà** (~$0,41 de travail racheté), et jette tout. **La boucle ne peut pas converger** :
  elle a besoin de ~4 tentatives, elle en a 2, et ne garde rien entre sessions.
  Recommandation : **`A` + garde de couverture** — ⚠️ **`A` seule a un trou MESURÉ** : supprimer
  les scénarios **en échec** fait baisser le compteur, et le principe 5 ne surveille que les
  scénarios **verts** (vérifié : `regressions()` rend `[]`). Sans garde de couverture, `A` fait de
  « supprimer la couverture » une stratégie gagnante.
  → `decisions/0018-la-boucle-rachete-les-memes-correctifs-a-chaque-rejeu-inc2.md`.
- [ ] **Le §9 mesure-t-il une CRÉATION ou une VIE ?** (question 2 de `0018`) —
  `total_for_case_usd(1)` = **$1,1552 = 107 % du §9**, ce qui **alarme à tort** : c'est le cumul de
  5 sessions de débogage et 7 versions. Une **création** réelle vaut **$0,1207 = 11 %**. Le brief
  §9 dit « nouveau cas de test (génération + exécution + rapport) » — donc une création. **Décision
  produit à trancher**, pas un bug.
- [ ] **Artefacts de mesure à arbitrer** — les cas **7** et **8** ont été créés dans la vraie base
  pour mesurer le coût réel du chemin écran (c'est ce qui rend la mesure réelle, et ça laisse des
  déchets — leçon du ménage du 2026-07-16). À nettoyer ou à assumer : **décision du porteur**.
  Backups : `data/testpilot.db.pre-migration12.bak`, `…pre-mesure-generation.bak`.

## Incrément 1 (suite de l'interface / robustesse)

- [x] **Parser d'exécution — steps « errored »** — *fait*. Formatter maison
  (`behave_runtime/tp_json_formatter.py`) qui sérialise le message que Behave ≥1.3 omettait
  pour les statuts `error`/`hook_error` ; normalisation `error_text()` d'un `error_message`
  en liste (qui **crashait** le parser et masquait un vrai bug en « erreur technique ») ;
  symptôme `http_error` → `WRONG_NAVIGATION` pour ne pas confondre une route 404 avec un
  sélecteur introuvable. → `decisions/0002-parser-message-erreur-steps-errored-inc1.md`.
- [x] **Fiabilité de la génération — réutilisation des steps partagés** — *fait (A+B)*. Le
  catalogue des 43 steps est désormais **montré** à l'agent (il n'en voyait qu'1 : on lui
  demandait de réutiliser sans jamais lui montrer) ; extraction par AST (la regex tronquait les
  libellés multi-lignes et en ratait 12) ; `write_steps_file` refuse le transport réinventé
  (`requests`/`/web/dataset`) en indiquant l'alternative `context.odoo`/`context.page`.
  → `decisions/0003-agent-reutiliser-steps-partages-inc1.md`.
- [ ] **Quasi-doublons sémantiques (volet C de 0003)** — *en observation*. Détecter un libellé
  généré « proche » d'un step partagé (même comportement sous un autre nom). Écarté pour
  l'instant : à reconsidérer avec des exemples concrets après plusieurs runs réels.
- [x] **Mesurer 0003 en run réel** — *fait, concluant*. Génération réelle via
  `POST /api/modules/1/cases` : **16/37** steps partagés réutilisés, **les 3 steps de comptage
  réutilisés**, 4 steps custom seulement (tous légitimes), **aucun transport brut**.
  Voir `CONTINUITE.md` §6.
- [x] **Confirmer l'écart par exécution réelle** — *fait, écart CONFIRMÉ*. Version 2 approuvée
  délibérément (geste de test assumé, tracé en base), exécution 2 → `technical_error /
  indetermine`. Traceback complet : `TimeoutError … waiting for locator("[name='Raison de la
  demande']")`. Sonde du formulaire : le champ existe sous `name='name'` (libellé affiché
  « Raison de la demande * ») → erreur de **paramétrage**, pas un bug applicatif. La taxonomie
  0002 (`ui_timeout` → `wrong_field_name` → `test_a_reparer`) est validée de bout en bout.
  Voir `CONTINUITE.md` §6.1.
- [x] **Assertion tautologique → faux « conforme »** (écart 2, **`0008` — A + C FAITS**) —
  *fait*. L'agent générait un `assert error_visible or "<chemin>" not in current_url` dans une
  branche `else` où le second opérande est **toujours vrai** → step infalsifiable, `conforme`
  déclaratif (viole §4.2 et §4.4).
  - **A** — prompt : Règle 4 (falsifiabilité) + `[Limite]` en **disjonction falsifiable** (pas
    « attendu unique » : la spec peut être légitimement multi-issues). Prouvé par re-génération
    réelle (cas 3).
  - **C** — lint pur `generation/assertion_lint.py` (motifs triviaux **+ extension contextuelle**,
    motif exact de l'écart 2 ; `@then`-sans-assert filtré par décorateur) → `GateOut.lint_warnings`
    (non-bloquant, n'affecte jamais `allowed`) + bandeau `ReviewGate.vue`. Tests dont
    anti-faux-positif étendu aux variantes légitimes + preuve sur le contenu exact de l'écart 2,
    plus preuve API « signalée au gate ». Preuve réelle : cas 2 signalé, cas 3 propre.
  → `decisions/0008-generation-assertion-infalsifiable-faux-conforme-inc1.md`.
- [x] **Message d'erreur détruit avant l'écran** (écart 3) — *fait*. Nouveau helper
  `meaningful_error()` (`execution/behave_result.py`) : repart de la dernière ligne d'exception
  jusqu'à la fin (message + `Call log` avec le sélecteur), au lieu de la tête du traceback. Le
  résumé de `classify_failure` ne suffisait pas (il s'arrête à la 1re ligne, avant le `Call
  log`). `failure_type`/`raw` inchangés. Prouvé sur l'exécution 3 (le sélecteur
  `[name='Raison de la demande']` est enfin en base) ; 3 tests de non-régression, **168 verts**.
  *Reste* : visibilité complète à l'écran (dépend de l'écart 4 pour `ReportView` ; le dépliage
  `CaseRow` n'affiche pas la cause — choix de design 0006 à trancher). Voir `CONTINUITE.md` §6.1.
- [x] **Sémantique des paramètres de steps** (écart 1, **`0007` — CLOS** : B, B+ et A1 livrés et
  prouvés en conditions réelles, capture d'écran à l'appui) —
  l'agent passe le **libellé humain** au step UI là où le helper attend le **nom technique**
  (`[name=…]`) → `TimeoutError`. **Bug déterministe** (reproduit cas 2 **et** cas 3). Racine de
  **famille commune** avec `0008`/`0003` (le catalogue montre le libellé, pas la sémantique de
  `{field}`), **mais** remède **technique** possible (un champ est résoluble par `name` *et* par
  libellé). **Verdict** :
  - **B porteur** — ✅ *fait*. Helpers UI tolérants (`_base_helpers` : `name` d'abord,
    `get_by_label` en repli). **Repli TRACÉ** et visible en mode dev (§5), **jamais silencieux** —
    sinon une vraie régression Odoo (champ renommé) serait absorbée.
  - **B+** — ✅ *fait, au 2ᵉ essai*. Surfaçage du repli **REQUIS**, pas optionnel (arbitrage
    complémentaire du verdict `0007` n°2) : Behave masque les logs d'un scénario **vert**, or le
    pire cas de l'exigence (champ renommé → repli le retrouve → run vert) est justement un succès.
    Le log seul a donc un **angle mort** que seul le surfaçage ferme. Chaîne : repli consigné dans
    un **fichier sidecar** (`TP_FIELD_FALLBACK_FILE`) → `execution.field_fallbacks` (migration 4) →
    API → bandeau `FieldFallbackNotice` + pastille d'historique dans `CaseDetail` (uniquement sur
    les runs concernés). ⚠️ **Le 1ᵉʳ jet lisait le marqueur dans la sortie de Behave et était
    AVEUGLE en run réel** — et son test de garde partageait l'angle mort du code (il omettait
    `environment.py`). Démasqué par le re-run réel, pas par la suite de tests. Sidecar retenu pour
    **supprimer** la dépendance au routage de capture de Behave. Détail complet dans la note.
  - **A1** — ✅ *fait*. Contrat écrit dans l'en-tête de `as_prompt_section` : `{field}` = **nom
    technique, jamais le libellé affiché** (attribut HTML `name` côté interface, champ du modèle
    côté vérification Odoo) — formulation **corrigée** à l'implémentation : `{field}` sert dans
    deux registres, et `{name}` (onglet/produit) désigne au contraire un **libellé visible**, donc
    l'annotation exclut explicitement boutons/onglets pour ne pas casser `click_button` par
    surcorrection. ✅ **Mesure d'obéissance faite et concluante** : re-génération réelle → l'agent
    écrit `champ "name"` là où les cas 2 et 3 écrivaient `champ "Raison de la demande"`, sans
    surcorriger les steps RPC. Réserve : **1 échantillon**, LLM non déterministe. A2 (par step)
    différée.
  → `decisions/0007-agent-parametre-steps-libelle-vs-nom-technique-inc1.md`.
- [x] **Runs API sans rapport** (écart 4) — ❌ **DIAGNOSTIC FAUX, classé (2026-07-16)**. Le bug
  n'existait pas. Mesuré : la CLI ne persiste pas ces chemins non plus (son `finalize()` ne les
  passe pas), et le rapport d'un run API répond **200** — il est reconstruit depuis la base par
  `build_report_for_execution`, sans fichier. Le vrai défaut était l'inverse :
  `report_json_path`/`report_html_path` étaient des **colonnes mortes**, jamais alimentées **ni
  lues** — le `position` décoratif de §2.4. **Supprimées** (migration 7), plutôt qu'écrire du code
  pour alimenter ce que personne ne lit. 3ᵉ diagnostic corrigé après vérification (après `0002`,
  `0007`). 5 tests.
- [x] **Step partagé infalsifiable** (`0010`) — *fait*. `@then("aucun enregistrement inattendu …
  effet de bord")` faisait `pass` : une **vérification qui ne vérifiait rien**, donc un
  « conforme » déclaratif (§4.2) et un faux-négatif (§4.4) — **au catalogue**, donc proposé à
  l'agent (`0003`). Même famille que `0008` mais dans la **bibliothèque partagée** : sa portée
  était **tout cas futur**, pas un cas. Trouvé en effet de bord de l'audit d'import. **Supprimé**
  (promesse « aucun modèle Odoo » intenable ; besoin déjà couvert par les steps ciblés par
  modèle). Dégât nul à ce jour (aucun cas ne l'utilisait). 5 tests de garde du **motif**.
  → `decisions/0010-step-partage-infalsifiable-bibliotheque-inc1.md`.
- [x] **Comptage sans point de comparaison** (`0011`) — *fait, avant l'import (décision du
  porteur)*. Chaîne de faux-négatif **muette aux deux bouts** : `memorize_record_count` avalait
  son exception (`warn`) → aucun snapshot ; `check_count_*` faisait `warn` + `return` → aucune
  assertion ; le `@then` passait → **scénario vert qui n'avait rien vérifié** (§4.2/§4.4, et le
  motif de `0007` : un repli ne doit jamais être silencieux). Portée : les helpers les **plus
  réutilisés** (c'est le succès de `0003` qui la donnait). Correctif : **échec explicite** nommant
  le step manquant (libellé vérifié comme présent au catalogue). 9 tests dont un garde AST du
  motif `warn`+`return`, **vérifié comme échouant sur l'ancien code**.
  → `decisions/0011-comptage-sans-snapshot-faux-negatif-inc1.md`.
- [x] **Catalogue : note par step** (`0012`, = A2 de `0007` activée) — *fait*. **3ᵉ occurrence
  du motif `0007`** : le libellé ne dit pas le comportement. « je suis **authentifié** … »
  (vérifie le RPC, ne connecte rien) vs « je me **connecte** … » (connecte le navigateur) —
  l'agent a pris le premier pour ouvrir une page du portail : session anonyme, **5 scénarios
  en échec**. Remède : la 1ʳᵉ ligne de la **docstring** devient la note du catalogue (le code
  reste la source de vérité ; 0/36 steps en avaient une, donc aucun effet de bord ; on
  n'annote que les pièges). **Prouvé par régénération** : l'agent emploie désormais les deux
  steps, dans le bon ordre. Protège les 3 modules restants à importer. 5 tests.
  → `decisions/0012-catalogue-note-par-step-inc1.md`.
- [x] **Taxonomie : classer sur le SIGNAL, pas sur le texte de l'agent** (`0015` — **arbitré et
  LIVRÉ le 2026-07-17**). La classification lisait `step_text` (le libellé Gherkin **écrit par
  l'agent**) par mots-clés prioritaires : le **même** `TypeError` recevait **4 classements** selon
  le seul nom du step, et un **vrai bug** sur un step `…"team_id"…` devenait `test_a_reparer` — la
  boucle `0014` aurait réparé un test correct contre une application cassée (faux négatif, §4.4).
  Livré : ordre **SIGNAL → SYMPTÔME → INDICE**, catégorie **`broken_test_code`** → `test_a_reparer`
  déterministe, mots-clés de domaine retirés, `missing_server_context` en **voie dégradée**
  (`indetermine`), **migration 10** (`step_text` persisté pour l'audit).
  **Découvert au passage** : Behave n'écrit **jamais** « AssertionError » (`model.py:1888` →
  `ASSERT FAILED:`) — la clé de signal ET la regex du parser étaient **mortes en run réel**, et
  les assertions retombaient sur les mots-clés. Corrigé : le rendu de Behave est reconnu comme
  signal, testé en premier. Mesuré sur 20 échecs réels : **14/20 décidés par un signal, 9/20
  reclassés**, le faux `missing_role` du cas 6 (`0012`) corrigé.
  → `decisions/0015-…md`, `scripts/prove_0015_signal_vs_texte.py`, `tests/test_taxonomy_signal.py`.
- [ ] **DETTE — Principe 3 : édition ciblée plutôt que réécriture complète** (`docs/PRINCIPES.md`
  — *dette assumée, arbitrée le 2026-07-17 : à noter, pas à ouvrir*). Chaque réparation réécrit
  ~14 000 car. de code **qui marchait** pour corriger un step (`write_steps_file` REMPLACE, et le
  contrat l'exige — correctif du bug 2 de `0014`). C'est la cause de `0017`.
  ⚠️ **CORRIGÉ le 2026-07-17 — mon chiffrage était 10× trop bas.** J'avais estimé $0,015/tentative
  en raisonnant sur la SORTIE. Mesuré sur une réparation réelle : **$0,2895**. Le coût est dominé
  par l'**entrée répétée** (la boucle ReAct renvoie le catalogue de 42 steps + le fichier de
  14 000 car. à chaque tour), pas par la sortie. ~~Conséquence : **génération + 2 réparations =
  $1,0319 = 96 % du budget §9**.~~
  🔄 **RÉVISÉ le 2026-07-17 (soir) — ce 96 % est faux.** Il reposait sur une génération à $0,4529,
  mesurée **avant les garde-fous**. Mesure réelle du chemin écran : création $0,1207, et
  **$0,6997 = 65 % du §9** avec 2 réparations. **L'urgence coût du principe 3 tombe** : il reste
  un sujet de **rayon d'explosion** (une réparation réécrit du code qui marchait), pas de budget.
  Un diff réduirait quand même l'entrée réinjectée à chaque tour — **à chiffrer si on rouvre**,
  jamais à supposer (je me suis trompé deux fois sur ce chiffre : d'abord 10× trop bas, puis sur
  le mauvais régime).
  **Pourquoi ça attend** : le principe 5 (garde de non-régression, livré, coût nul) couvre le même
  risque **en pratique** — une réparation qui casse ce qui marchait n'est plus adoptée. Mais voir
  la correction de coût ci-dessus : l'argument « ça n'attend que pour le rayon d'explosion » ne
  tient plus tel quel. Le
  principe 3 réduirait le risque *à la source* plutôt qu'en aval, mais il **rouvre le bug 2 de
  `0014`** (l'agent rendait 1 step sur 4) : chantier de conception, pas de budget.
  À rouvrir si le principe 5 se met à refuser des réparations trop souvent — ce serait le signal
  que le rayon d'explosion coûte vraiment.
- [x] **L'agent réinvente l'authentification que la bibliothèque résout déjà** (`0017` —
  **ARBITRÉ ET LIVRÉ**, cf. `c1ee857`). *(Révisé le 2026-07-17 : cette entrée disait « note écrite,
  à arbitrer » — périmé.)* **Livré** : **A** (annotation du catalogue, vérifiée jusqu'au prompt de
  réparation) + **B′** (`generation/repair_diff.py`, garde **détective** du rayon d'explosion —
  signale au gate les steps réécrits/supprimés, `allowed` jamais touché, 12 tests dont 6
  anti-faux-positifs). **L'option B — garde BLOQUANTE à l'écriture — n'a PAS été retenue** : elle
  aurait rejeté un cas testant légitimement la page de login, et retiré à l'agent un droit que le
  **§6 du brief** lui accorde. Voir la borne du principe 2 (`PRINCIPES.md`).
  ⚠️ **Le rejeu réel qui a suivi a ÉCHOUÉ, et la cause est trouvée depuis** : l'annotation a porté
  (v12 ne réimplémente plus l'auth), mais l'agent a **supprimé** son step d'auth sans mettre à
  jour le `.feature` → `undefined` → `RUN_FAILED`. **Le dry-run de la session n'était branché sur
  rien** (`dry_runner=None`) : c'est lui qui aurait rendu la liste des steps undefined à l'agent
  pour qu'il corrige dans le même appel. **Fix P0 livré** (`3a744a4`) → **à rejouer**.
  Historique du diagnostic initial, conservé : mesuré au rejeu du cas 1
  (exec 20-22) : les deux réparations corrigent bien le `HTTPError 404` (le garde-fou transport de
  `0003` les y **force**) mais écrivent leur **propre** step d'auth avec un `fill` nu → timeout
  Playwright sur `[name="login"]`, « element is not visible ». Le step partagé gère ce piège
  (`state="attached"` + `force=True`) ; `v9` réussissait parce qu'elle lui **déléguait**.
  Ce n'est pas de l'aléa : `reserved_steps` bloque la **collision de libellés**, pas la
  **duplication de comportement**, et rien n'oblige à réutiliser le step d'auth. Racine : le
  contrat « rends le fichier ENTIER » (correctif du bug 2 de `0014`) force l'agent à réécrire
  ~14 000 car. de code **qui marchait** pour corriger un step.
  Bloquant pour `0016` : mesuré, ni le cas 2 (passe → 0 tentative) ni le cas 6 (tourne déjà →
  circuit arrêté sur `vrai_bug`, 0 tentative) ne peuvent déclencher une réparation.
  → `decisions/0017-agent-reinvente-l-authentification-inc1.md`.
- [ ] 🔴 **« Réparée » veut dire « passe au vert » — les deux axes fusionnés dans la boucle**
  (`0016` — **A + (iii) ARBITRÉS et LIVRÉS le 2026-07-17 ; preuve réelle PARTIELLE**). Chemin
  négatif prouvé en réel (deux réparations non exécutables → aucune adoption → disque rembobiné
  sur `v1`). **Chemin positif NON prouvé.**
  ➡️ **Prochaine action (tâche 3.3) : rejouer le cas 1.** *(Révisé le 2026-07-17 : ce point était
  dit « bloqué par `0017` ». `0017` est livré, et la vraie cause du dernier échec — le dry-run non
  branché — est corrigée par le fix P0 `3a744a4`. Le rejeu est donc **débloqué**, et il fera
  d'une pierre deux coups : prouver le chemin positif **et** re-mesurer le coût d'une réparation,
  dont le chiffre en vigueur est périmé.)* Sur les données
  réelles de l'exec 17 (`v9`) : `execution_status=success` → `A` adopte, là où l'ancien critère
  (2 échecs) jetait — analyse reproductible, pas un bout-en-bout. Mesuré au rejeu réel du 2026-07-17 : la
  réparation du cas 1 (`v9`) a transformé une cécité technique (`HTTPError 404`, 0/3, l'outil ne
  juge rien) en **verdict fonctionnel** (`success/non_conforme`, 1/3) — puis **la version a été
  jetée** parce que `resolved` exige **zéro échec**. Le disque est rembobiné sur `v1` (`import
  requests` de retour), `current_version_id` vaut `v1` : **un nouveau run refera le 404**.
  Le critère d'adoption fusionne « le test **tourne** » (axe exécution) et « le test **passe** »
  (axe fonctionnel) — c'est **§4.1** violé au cœur de `0014`, et dans la direction la plus
  coûteuse : **un test réparé qui détecte un vrai bug ne peut jamais être adopté**. Le §5 dit
  pourtant déjà la bonne règle (`validation_status_after_run`).
  Effet de bord visible : le cas 1 affiche `validated` + `success/non_conforme` obtenus sur `v9`,
  alors que sa version courante est `v1` — un statut **orphelin** de la version qui l'a produit.
  → `decisions/0016-reparee-veut-dire-passe-au-vert-inc1.md`.
- [ ] **Exploiter le STATUT de step de Behave** (`failed` = assertion, `error` = exception) —
  *ouvert par `0015`, non urgent*. C'est un signal plus sûr que le rendu textuel, et il est déjà
  dans le JSON : le parser met aujourd'hui tous les statuts d'échec dans un même sac
  (`_FAILING_STEP_STATUSES`) et ne s'en sert jamais pour classer. À reprendre si le rendu textuel
  montre une autre faille.
- [ ] **Teardown : résidus du cas 2 non nettoyés** — *constat (2026-07-16), pas urgent mais ça
  s'accumule*. Mesuré : **9** tickets `AAAAA…` (chaîne de 300 car. du scénario `[Limite]`) et
  **6** « Demande test BDD » restants — un de plus par run. Cause : le teardown ne supprime que
  ce qui passe par `register_created()`, or le cas 2 crée ses tickets **via le formulaire UI**
  (ID inconnu). Il s'en sort par un nettoyage **en amont**, qui ne couvre pas les `AAAAA…`
  (leur nom EST la chaîne de test). Le cas 6 fait mieux (préfixe `[TEST]`, 0 résidu). Pollue
  l'accueil du portail.
- [ ] **Angle mort du lint : la bibliothèque partagée n'est jamais lintée** — le lint `0008` ne
  regarde que les steps de la **version d'un cas**, au gate. `0010` et `0011` ont été trouvés
  **à la main**. Le brancher sur la bibliothèque suppose d'abord de lui apprendre la
  **délégation** (un `@then` qui appelle un helper qui assertit **est** falsifiable), sinon
  4 faux positifs. À arbitrer.
- [x] **Navigation en arborescence + vue Modules** — *fait (2026-07-16)*. L'onglet « Gestion
  des cas » devient un EXPLORATEUR : arbre `Modules → Cas` en colonne permanente
  (`ModuleTree`, repliable, tout déplier/replier, état persistant par projet) rendu dans la
  BARRE LATÉRALE par `AppShell`, sous les onglets — pas de seconde colonne (arbitrage du
  porteur), donc routes à plat et contenu pleine largeur ; état partagé `useProjectTree`.
  Première vue du projet = `ModulesOverview` (la structure, pas un mur de cas), table plate
  conservée en « Tous les cas ». Arbre à 2 niveaux, non récursif (pas de sous-module,
  `0004`) ; aucun statut fusionné dans l'arbre (`4.1`) ; masqué hors gestion (`4.8`).
  8 vitest + captures. **Bug serveur trouvé au passage** : HTTP 500 intermittent
  (connexion SQLite passée entre threads du pool FastAPI) → `check_same_thread=False`,
  3 tests. Voir `CONTINUITE` §2.8.
- [x] **Unicité des noms** — *fait (2026-07-16, migration 5)*. Projet unique globalement,
  module unique par projet, titre de cas unique par module, `feature_slug` unique globalement
  (bug latent : deux cas au même slug écriraient dans le même `.feature`). Deux couches :
  garde applicative `casefold` (Unicode) → 409 + message clair, et index UNIQUE `COLLATE
  NOCASE` (ASCII seulement) en filet. Couvre création, renommage et ajout par spec (validé
  avant l'appel LLM). Audit préalable : **zéro doublon** — les « doublons » vus à l'écran
  étaient des titres tronqués + des artefacts de scripts de preuve, nettoyés sur décision du
  porteur. 19 tests. Voir `CONTINUITE` §2.9.
- [x] **Ordre d'affichage manuel des cas (glisser-déposer)** — *fait (2026-07-16, `0009`,
  migration 6)*. ⚠️ **Amende `0006`/§2.4** (« pas de colonne `position` ») : 0006 refusait une
  position DÉCORATIVE (jamais alimentée, promettant un ordre d'exécution) ; celle-ci est
  RÉELLEMENT honorée par le tri et ne promet rien sur l'exécution — gardé par un test qui
  échoue si `position` fuit vers `execution/`, `verdict/`, `reporting/` ou `behave_runtime/`.
  `PUT /api/modules/{id}/cases/order` en lot transactionnel (liste stricte, 409 sinon) ;
  poignée + drag HTML5 natif dans la liste du module uniquement ; infobulle d'honnêteté.
  Conséquence assumée : **la priorité n'ordonne plus la liste**. 13 tests + preuve navigateur
  (glissement réel, ordre persisté). → `decisions/0009-ordre-affichage-manuel-des-cas-inc1.md`.
- [x] **Vue liste des modules** — *fait*. Bascule Grille/Liste sur `ModulesOverview`,
  préférence retenue par utilisateur (localStorage). Purement visuel.
- [ ] **Déplacer un cas entre modules (drag)** — hors périmètre de `0009` (change `module_id`,
  le rangement métier, pas l'ordre). Chantier séparé, arbitré avec le porteur.
- [x] **Arbitrage humain des diagnostics** (`0013`, **remplace `0001`**) — *fait*. `0001` était
  trop étroit : il parlait des `pending_human`, or un **`not_required` faux était IRRÉVOCABLE**.
  Constat mesuré : **aucun** diagnostic n'était jamais tranché (8/8 avec `confirmed_by = NULL`) —
  aucun endpoint, aucun écran, alors que l'UI affichait « En attente de validation humaine »
  (§4.6). §4.4 dit « faux-positif acceptable », pas « **irréversible** » : il l'est parce qu'un
  humain le corrige. Livré : couche **distincte** (migration 8) qui **n'écrase jamais**
  `defect_origin` — sinon on perdrait l'écart machine/humain, seul matériau de l'audit de la
  taxonomie ; `GET /api/repairs` (dont `status=all` pour infirmer un `not_required`) +
  `POST /api/repairs/{id}/verdict` (409 si déjà tranché) ; onglet **Confirmations** sous Exécution
  avec compteur ; infobulle sur `vrai_bug` disant que c'est une **déduction**. Jamais de blocage,
  jamais de recalcul des deux axes (§4.2, gardé par test). 15 tests.
  → `decisions/0013-arbitrage-humain-des-diagnostics-inc1.md`.
- [x] **Réparation automatique** (`0014`) — ✅ **LIVRÉE et PROUVÉE sur les deux chemins.**
  Le pilier était **annoncé mais inexistant** : `evaluate()` écrit/testé/**jamais appelé**,
  `what_was_tried` vide partout, **aucun cas n'avait de v2**, et le prompt promettait un
  `run_behave` qui n'existait pas. Nœud résolu : réparer exige d'exécuter, exécuter exige le
  gate → **option C**, le gate **autorise N tentatives** (défaut 2, migration 9). Design **(b)** :
  le circuit décide, l'agent propose (aucun outil d'exécution). **Modèle B** : une exécution =
  un run. **Option (i)** : une version réparée n'est **jamais** approuvée d'office → ratification.
  **Preuve réelle** : cas 6 → `vrai_bug` → aucune réparation (0 appel LLM) ; cas 2 → 1 tentative →
  `success/conforme` **3/3** — **première exécution verte du projet**, v8 ratifiée, cas
  **`validated`**. ⚠️ Le run réel a sorti **3 bugs** que 10 tests avaient laissés passer, dont
  « pas de run » pris pour « ça passe » — **et le gate a tenu pendant que le circuit se
  trompait**. → `decisions/0014-reparation-automatique-bornee-par-le-gate-inc1.md`.
- [ ] **`_finalize_error` n'est pas un filet** — *trouvé le 2026-07-16, non corrigé*. Il est censé
  clore un run planté en `technical_error / indetermine` (§4.5), mais il **appelle lui-même
  `finalize()`** : si `finalize()` est la cause du plantage, le filet tombe avec. Constaté sur
  l'**exécution 10** — restée `not_executed` alors qu'elle a réellement tourné (ses 5
  `scenario_result` sont en base, corrects). L'écran affiche donc « Pas lancé » pour un run qui a
  tourné (§4.6). Déclencheur ici : une migration appliquée pendant qu'un serveur tournait avec
  l'ancien code — mais toute panne pendant `finalize()` produirait le même état menteur.
- [x] **Runtime branché sur la connexion du projet** — *fait*. L'exécution (run UI et CLI) et
  l'exploration de génération tapent désormais l'application du projet, plus la config globale :
  `connectors/runtime_env.py` (projet → variables d'env), injection dans le sous-processus
  behave, `OdooConnector.from_project`. Repli sur la config si le projet n'a pas de connexion
  saisie. → `decisions/0005-connecteur-au-niveau-projet.md`.
- [ ] **Sélection explicite du projet en CLI** : `testpilot run` utilise le *premier* projet
  (même règle que le rattachement automatique). Ajouter `--project` pour lever l'implicite dès
  qu'il y aura plusieurs applications réellement testées.
- [ ] **Édition de la connexion d'un projet** : `PATCH /api/projects/{id}` ne gère que
  nom/description ; permettre d'éditer connecteur + connexion. → `decisions/0005-...`.

## Incrément 1+ (structure §7 non encore implémentée)

- [ ] **Exécution nommée transverse** (« Test Suite » ad hoc) : regroupement libre de cas de
  plusieurs modules, avec nom et but propres, et rapport attaché à l'exécution. Classé JTBD
  essentiel (régression transverse, §3 du brief). L'UI de l'onglet Exécution laisse la porte
  ouverte (badge mono/multi-module + nom d'exécution prévus dans les tuiles).
  **Contrainte actée (porteur, 2026-07-16)** : référencer les cas **par ID**, via une table de
  liaison **many-to-many** entre l'exécution nommée et `test_case` — **jamais** de duplication
  de cas. Un cas dupliqué divergerait de son original dès la première régénération (c'est
  exactement le référentiel scindé de l'ancien prototype, §2.6).
  ⚠️ **En attente, volontairement** : le porteur a arbitré le focus sur *création → exécution →
  réparation* (« ça ne sert à rien de rajouter plusieurs modules qui ne marchent pas »). À
  reprendre quand un cas passe au vert et que `0014` est livré — grouper des cas qui échouent
  tous ne prouverait rien.
