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
- [ ] **Assertion tautologique → faux « conforme »** (écart 2, **priorité 1 — DÉCIDÉ `0008`,
  à implémenter**) : l'agent génère un `assert error_visible or "<chemin>" not in current_url`
  dans une branche `else` où le second opérande est **toujours vrai** → le step ne peut
  **jamais** échouer, le scénario est déclaré `conforme` quoi que fasse l'application. Viole les
  invariants §4.2 (statut jamais déclaratif) et §4.4 (faux-négatif inacceptable). Défaut du
  **code généré**. **Verdict** : **A** (prompt — falsifiabilité + `[Limite]` à attendu défini)
  **+ C** (lint non-bloquant au gate), **B** non-bloquante en entrée de C (jamais de blocage auto
  de la génération, brief §11.2). Ordre **A puis C**, plan avant code.
  → `decisions/0008-generation-assertion-infalsifiable-faux-conforme-inc1.md`.
- [x] **Message d'erreur détruit avant l'écran** (écart 3) — *fait*. Nouveau helper
  `meaningful_error()` (`execution/behave_result.py`) : repart de la dernière ligne d'exception
  jusqu'à la fin (message + `Call log` avec le sélecteur), au lieu de la tête du traceback. Le
  résumé de `classify_failure` ne suffisait pas (il s'arrête à la 1re ligne, avant le `Call
  log`). `failure_type`/`raw` inchangés. Prouvé sur l'exécution 3 (le sélecteur
  `[name='Raison de la demande']` est enfin en base) ; 3 tests de non-régression, **168 verts**.
  *Reste* : visibilité complète à l'écran (dépend de l'écart 4 pour `ReportView` ; le dépliage
  `CaseRow` n'affiche pas la cause — choix de design 0006 à trancher). Voir `CONTINUITE.md` §6.1.
- [ ] **Sémantique des paramètres de steps** — écart **CONFIRMÉ**, décision `0007` + plan avant
  de coder. ⚠️ Le diagnostic initial (« incohérence interne de l'agent ») était **faux** : le
  step custom de l'agent utilise `page.get_by_label(field)`, qui résout le libellé humain. Son
  modèle est **cohérent** (libellé pour l'UI, nom technique pour le RPC) ; c'est le placeholder
  `{field}` de la bibliothèque qui signifie « attribut HTML `name` » **sans le dire**. Désaccord
  de **convention**, pas confusion. Deux options ouvertes : **(A)** annoter la sémantique des
  placeholders dans le catalogue ; **(B)** rendre le step tolérant (repli `get_by_label`). Non
  exclusives, **rien n'est tranché**. Voir `CONTINUITE.md` §6.1.
- [ ] **Runs API sans rapport** (écart 4) : `run_service._persist` n'écrit ni `report_json_path`
  ni `report_html_path` (vides pour l'exécution 2), alors que la CLI les produit. L'UI promet un
  rapport que le runtime ne fournit pas → invariant §4.6 (« jamais affiché ≠ réel »).
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
