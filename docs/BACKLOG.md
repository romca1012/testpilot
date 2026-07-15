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
- [ ] **Sémantique des paramètres de steps** (écart trouvé au run réel, priorité haute) :
  l'agent réutilise le bon step mais lui passe le **libellé humain** (« Raison de la demande »)
  là où le helper attend le **nom technique HTML** (`name`) → `TimeoutError` à l'exécution.
  Le catalogue montre les libellés mais **rien sur la sémantique des placeholders**. À confirmer
  par une exécution réelle, puis décision `0007` + plan avant de coder.
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
