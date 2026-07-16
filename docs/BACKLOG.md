# Backlog — reports assumés

Point d'entrée unique des travaux **différés et documentés** (chaque entrée renvoie à sa
décision détaillée dans `docs/decisions/`). Ordonné par incrément cible.

## Incrément 2 (avant tout déploiement client réel)

- [ ] **Secret de connexion en clair** — le mot de passe de connexion d'un projet est stocké
  en clair dans SQLite. Acceptable en dev local (instance Odoo neutralisée), **inacceptable
  avant le premier déploiement client**. À traiter : chiffrement au repos ou gestionnaire de
  secrets. Atténuation déjà en place : l'API ne renvoie jamais le mot de passe (write-only).
  → voir `decisions/0005-connecteur-au-niveau-projet.md`.

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
- [ ] **Exécution nommée transverse (groupée multi-modules)** — chantier suivant. Contrainte
  actée : référencer les cas **par ID** via une table de liaison **many-to-many** entre
  l'exécution nommée et `test_case` — **jamais** de duplication de cas.
- [ ] **Confirmations `pending_human`** : sous-commande / écran de traitement de la file de
  relecture des origines de défaut. → `decisions/0001-report-confirmations-pending-human-inc1.md`.
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
