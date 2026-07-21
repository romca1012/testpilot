-- TestPilot — schéma du référentiel (Incrément 0)
--
-- Écrit en SQL portable vers PostgreSQL (Incrément 1) : types INTEGER/TEXT/REAL,
-- timestamps en TEXT ISO-8601 UTC, booléens en INTEGER 0/1, enums en TEXT + CHECK,
-- JSON éventuel en TEXT. Aucune fonctionnalité propre à SQLite dans la logique métier.
--
-- Hiérarchie §7 : Projet → Module/Fonctionnalité → Cas de test (relations réelles).
-- Note : ``test_case.feature_slug`` est le nom TECHNIQUE du fichier .feature (pilotage
-- Behave), distinct de ``module_id`` qui porte le rangement MÉTIER. Les deux étaient
-- autrefois confondus dans un unique champ texte ``module`` (voir décision 0004).

-- ── Projet (racine de la hiérarchie §7) ──────────────────────────────────────
-- Un projet = une APPLICATION/ERP sous test. Il porte le CONNECTEUR et ses paramètres
-- de connexion (décision 0005). « odoo » est une valeur de connecteur, jamais un projet.
CREATE TABLE IF NOT EXISTS project (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT    NOT NULL,
    description    TEXT    NOT NULL DEFAULT '',
    connector_type TEXT    NOT NULL DEFAULT 'odoo',
    base_url       TEXT    NOT NULL DEFAULT '',
    database       TEXT    NOT NULL DEFAULT '',
    username       TEXT    NOT NULL DEFAULT '',
    password       TEXT    NOT NULL DEFAULT '',   -- secret : jamais renvoyé par l'API (write-only)
    created_at     TEXT    NOT NULL
);

-- ── Module / Fonctionnalité (appartient à un projet) ─────────────────────────
CREATE TABLE IF NOT EXISTS module (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL,
    name        TEXT    NOT NULL,
    description TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL,
    FOREIGN KEY (project_id) REFERENCES project(id)
);

CREATE INDEX IF NOT EXISTS idx_module_project ON module(project_id);

-- ── Spécification : conteneur d'un GROUPE de cas testant la même fonctionnalité ─
-- Rouvre 0006 (décision du porteur, 2026-07-19) : chaque situation testée (nominal/erreur/limite/
-- autre) devient un CAS indépendant. La spécification EST LE DOCUMENT fourni par l'utilisateur —
-- la spec complète du module/de la fonctionnalité, donnée UNE FOIS — à partir de laquelle plusieurs
-- cas indépendants sont générés (un par angle). Elle ne porte NI statut, NI version, NI gate, NI
-- coût (tout cela reste sur le cas), mais elle porte la SPEC : c'est la SOURCE UNIQUE, jamais
-- recopiée dans chaque version (un cas la RÉFÉRENCE par `spec_hash`). Libellé UI : « Spécification ».
CREATE TABLE IF NOT EXISTS case_group (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    module_id    INTEGER NOT NULL,
    title        TEXT    NOT NULL,
    description  TEXT    NOT NULL DEFAULT '',      -- résumé court affiché en liste (≠ la spec)
    spec_content TEXT    NOT NULL DEFAULT '',      -- LE DOCUMENT complet — source unique (2026-07-19)
    spec_hash    TEXT    NOT NULL DEFAULT '',      -- empreinte de la spec courante (détection « dépassée »)
    position     INTEGER NOT NULL DEFAULT 0,       -- ordre d'affichage dans le module (cf. 0009)
    created_at   TEXT    NOT NULL,
    updated_at   TEXT    NOT NULL,
    FOREIGN KEY (module_id) REFERENCES module(id)
);

CREATE INDEX IF NOT EXISTS idx_group_module ON case_group(module_id);

-- ── Cas de test (socle commun §7) ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS test_case (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    title                  TEXT    NOT NULL,
    module_id              INTEGER REFERENCES module(id),   -- rangement MÉTIER (§7)
    group_id               INTEGER REFERENCES case_group(id), -- Spécification propriétaire (2026-07-19)
    -- Angle testé : ÉTIQUETTE LIBRE (nominal/erreur/limite/autre/legacy…), PAS un triptyque imposé.
    angle                  TEXT    NOT NULL DEFAULT '',
    feature_slug           TEXT    NOT NULL DEFAULT '',      -- nom du .feature (technique)
    -- Le connecteur a quitté le cas : il vit sur le PROJET (décision 0005).
    description            TEXT    NOT NULL DEFAULT '',
    origin                 TEXT    NOT NULL DEFAULT 'ia_generated'
                                     CHECK (origin IN ('ia_generated', 'manual_converted')),
    validation_status      TEXT    NOT NULL DEFAULT 'never_executed'
                                     CHECK (validation_status IN ('never_executed', 'validated', 'to_review')),
    -- Priorité de LECTURE/traitement (étiquette). Volontairement PAS un ordre d'exécution :
    -- celui-ci est porté par l'ordre des scénarios du .feature (décision 0006).
    priority               TEXT    NOT NULL DEFAULT 'medium'
                                     CHECK (priority IN ('low', 'medium', 'high')),
    -- Ordre d'AFFICHAGE manuel dans le module (glisser-déposer, décision 0009). Réellement
    -- honoré par le tri (ORDER BY position, id) — c'est ce qui le distingue du `position`
    -- décoratif refusé en 0006. Ne promet RIEN sur l'ordre d'exécution. Pas de contrainte
    -- UNIQUE : un glissement décale N voisins, l'unicité ferait échouer les états
    -- intermédiaires ; les ex æquo sont départagés par `id`.
    position               INTEGER NOT NULL DEFAULT 0,
    -- ── Métadonnées NON versionnées (décision 0022 n°3b) ─────────────────────
    -- Elles ne changent pas ce que le test VÉRIFIE : les versionner gonflerait l'historique
    -- pour rien. `refs` et non `references` : REFERENCES est un mot-clé SQL.
    refs                   TEXT    NOT NULL DEFAULT '',   -- tickets externes (Jira, GitHub…)
    estimate               TEXT    NOT NULL DEFAULT '',   -- estimation de durée (alimente le burndown)
    -- Référence logique vers la version courante (pas de FK dure : cycle case<->version).
    current_version_id     INTEGER,
    last_execution_status  TEXT    CHECK (last_execution_status IN ('success', 'technical_error', 'not_executed')),
    last_functional_status TEXT    CHECK (last_functional_status IN ('conforme', 'non_conforme', 'indetermine', 'not_evaluated')),
    last_executed_at       TEXT,
    author                 TEXT    NOT NULL DEFAULT '',
    created_at             TEXT    NOT NULL,
    updated_at             TEXT    NOT NULL
);
-- (idx_case_module créé par la migration : la colonne module_id peut manquer sur une
--  base antérieure au moment où schema.sql s'exécute.)

-- ── Historisation des versions (gherkin + script) §7 §4 ──────────────────────
CREATE TABLE IF NOT EXISTS test_case_version (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    test_case_id    INTEGER NOT NULL,
    version_number  INTEGER NOT NULL,
    -- 🔴 DETTE EXPLICITE À SOLDER À L'ÉTAPE 3 (contractée le 2026-07-19). `spec_content` est un
    -- SURSIS TECHNIQUE, PAS une duplication permanente qu'on accepte : la spec est la SOURCE UNIQUE
    -- portée par `case_group`. Ce champ n'existe encore que parce que la génération/réparation
    -- l'écrivent/le lisent, et les recâbler est l'étape 3 (« un angle par appel »).
    -- ENGAGEMENT : à l'étape 3, la génération lira/écrira la spec sur `case_group.spec_content`,
    -- ce champ deviendra VIDE et INUTILISÉ, puis sera SUPPRIMÉ (migration dédiée). Il ne doit
    -- JAMAIS redevenir une source de vérité. Tant qu'il porte du texte, c'est une copie legacy.
    -- `spec_hash` RESTE : c'est la RÉFÉRENCE (quelle version de la spec a produit ce cas →
    -- détecter un cas généré depuis une spec dépassée, sans recopier le texte).
    spec_content    TEXT    NOT NULL DEFAULT '',
    spec_hash       TEXT    NOT NULL DEFAULT '',
    -- ── Contenu MÉTIER de cette version (décisions 0022 n°3 et n°10) ──────────
    -- Une version = LE CAS ENTIER : le métier est figé ici EN MÊME TEMPS que le technique.
    -- C'est ce qui rend possible l'historique à diffs (« titre : X → Y ») et permet au gate
    -- d'approuver un couple métier/technique cohérent.
    -- ⚠️ `test_case` porte des COPIES de `title`/`angle` (valeurs courantes, pour les listes) :
    -- en cas de divergence, C'EST LA VERSION QUI FAIT FOI — même règle que le raccourci de
    -- résultat sur le cas.
    title           TEXT    NOT NULL DEFAULT '',   -- le titre AU MOMENT de cette version
    preconditions   TEXT    NOT NULL DEFAULT '',   -- contexte nécessaire, en langage clair
    -- Étapes MÉTIER : liste JSON (`["Se connecter", "Aller sur …"]`), une entrée par étape.
    -- ⚠️ NE PAS confondre avec `steps_content` ci-dessous, qui est le FICHIER PYTHON technique.
    -- JSON et non texte multi-lignes : déplacer/supprimer une étape doit rester trivial, et un
    -- retour à la ligne parasite ne doit pas fabriquer une étape fantôme.
    test_steps      TEXT    NOT NULL DEFAULT '',
    expected_result TEXT    NOT NULL DEFAULT '',   -- UNE phrase de verdict global (décision 3.a)
    angle           TEXT    NOT NULL DEFAULT '',   -- snapshot de l'angle (l'historique le diffe)
    feature_content TEXT    NOT NULL DEFAULT '',
    steps_content   TEXT    NOT NULL DEFAULT '',
    feature_path    TEXT    NOT NULL DEFAULT '',
    steps_path      TEXT    NOT NULL DEFAULT '',
    change_summary  TEXT    NOT NULL DEFAULT '',
    created_at      TEXT    NOT NULL,
    created_by      TEXT    NOT NULL DEFAULT '',
    FOREIGN KEY (test_case_id) REFERENCES test_case(id)
);

CREATE INDEX IF NOT EXISTS idx_version_case ON test_case_version(test_case_id);

-- ── Décisions de relecture humaine (gate §4) ─────────────────────────────────
CREATE TABLE IF NOT EXISTS review_decision (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    test_case_id INTEGER NOT NULL,
    version_id   INTEGER NOT NULL,
    decision     TEXT    NOT NULL CHECK (decision IN ('approved', 'rejected')),
    reviewer     TEXT    NOT NULL DEFAULT '',
    comment      TEXT    NOT NULL DEFAULT '',
    -- Tentatives de réparation que CETTE approbation autorise (décision 0014, option C).
    -- Réparer exige d'exécuter, et §4.3 exige le gate avant toute exécution : le gate autorise
    -- donc explicitement un budget, plutôt que d'être contourné par la boucle. 0 = interdite.
    -- Le défaut réel vient de `config.REPAIR_BUDGET_DEFAULT` (migration 9) ; la valeur ci-dessous
    -- n'est qu'un filet pour une base créée hors migration.
    repair_budget INTEGER NOT NULL DEFAULT 2,
    decided_at   TEXT    NOT NULL,
    FOREIGN KEY (test_case_id) REFERENCES test_case(id),
    FOREIGN KEY (version_id)   REFERENCES test_case_version(id)
);

CREATE INDEX IF NOT EXISTS idx_review_version ON review_decision(version_id);

-- ── Exécution (TestRun) — deux axes de statut indépendants §5 ─────────────────
CREATE TABLE IF NOT EXISTS execution (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    test_case_id      INTEGER NOT NULL,
    version_id        INTEGER NOT NULL,
    execution_status  TEXT    NOT NULL DEFAULT 'not_executed'
                                CHECK (execution_status IN ('success', 'technical_error', 'not_executed')),
    functional_status TEXT    NOT NULL DEFAULT 'not_evaluated'
                                CHECK (functional_status IN ('conforme', 'non_conforme', 'indetermine', 'not_evaluated')),
    scenarios_total   INTEGER NOT NULL DEFAULT 0,
    scenarios_passed  INTEGER NOT NULL DEFAULT 0,
    scenarios_failed  INTEGER NOT NULL DEFAULT 0,
    cost_usd          REAL    NOT NULL DEFAULT 0,
    iterations        INTEGER NOT NULL DEFAULT 0,
    duration_seconds  REAL    NOT NULL DEFAULT 0,
    -- PAS de report_json_path / report_html_path : supprimés (migration 7). Ils n'étaient
    -- jamais alimentés (ni CLI ni API) ni jamais lus — un champ mort, comme le `position`
    -- décoratif que §2.4 dénonce. Le rapport est RECONSTRUIT à la demande depuis la base
    -- (report_service.build_report_for_execution) ; la CLI écrit ses fichiers dans data/reports/
    -- indépendamment de toute colonne.
    -- Replis « libellé → nom technique » tracés pendant le run (JSON, décision 0007 B+).
    -- Doit rester visible même sur un run VERT : un repli signale soit un step mal paramétré,
    -- soit un champ réellement renommé côté application.
    field_fallbacks   TEXT    NOT NULL DEFAULT '',
    -- Raison d'un plantage survenu AVANT tout scénario (migration 11) : `_finalize_error`
    -- recevait ce message et ne l'écrivait nulle part. L'écran disait « erreur technique » sans
    -- le pourquoi, seul le log du serveur le savait.
    error_message     TEXT    NOT NULL DEFAULT '',
    trigger           TEXT    NOT NULL DEFAULT 'first_run'
                                CHECK (trigger IN ('first_run', 'rerun')),
    started_at        TEXT    NOT NULL,
    FOREIGN KEY (test_case_id) REFERENCES test_case(id),
    FOREIGN KEY (version_id)   REFERENCES test_case_version(id)
);

CREATE INDEX IF NOT EXISTS idx_execution_case ON execution(test_case_id);

-- ── Résultat par scénario (source des deux axes) ─────────────────────────────
-- NB : `step_text` (le step en échec) est ajouté par la MIGRATION 10 — il sert à AUDITER la
-- classification (0015), jamais à classer : c'est un texte écrit par l'agent.
CREATE TABLE IF NOT EXISTS scenario_result (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id      INTEGER NOT NULL,
    scenario_name     TEXT    NOT NULL,
    execution_status  TEXT    NOT NULL
                                CHECK (execution_status IN ('success', 'technical_error')),
    functional_status TEXT    NOT NULL
                                CHECK (functional_status IN ('conforme', 'non_conforme', 'indetermine')),
    failure_type      TEXT    NOT NULL DEFAULT '',
    cause_category    TEXT    NOT NULL DEFAULT '',
    error_summary     TEXT    NOT NULL DEFAULT '',
    FOREIGN KEY (execution_id) REFERENCES execution(id)
);

CREATE INDEX IF NOT EXISTS idx_scenario_execution ON scenario_result(execution_id);

-- ── Tentatives de réparation + origine du défaut (§5 asymétrique / §7) ────────
CREATE TABLE IF NOT EXISTS repair_attempt (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id        INTEGER NOT NULL,
    attempt_number      INTEGER NOT NULL,
    failure_signature   TEXT    NOT NULL DEFAULT '',
    cause_category      TEXT    NOT NULL DEFAULT '',
    defect_origin       TEXT    NOT NULL DEFAULT 'indetermine'
                                  CHECK (defect_origin IN ('test_a_reparer', 'vrai_bug', 'indetermine')),
    confirmation_status TEXT    NOT NULL DEFAULT 'not_required'
                                  CHECK (confirmation_status IN ('pending_human', 'confirmed', 'rejected', 'not_required')),
    confirmed_by        TEXT,
    confirmed_at        TEXT,
    what_was_tried      TEXT    NOT NULL DEFAULT '',
    -- ── Arbitrage HUMAIN (décision 0013, migration 8) ────────────────────────
    -- Couche DISTINCTE : `defect_origin` ci-dessus (déduction de la MACHINE) n'est jamais
    -- réécrit. L'humain ne corrige pas le diagnostic, il le JUGE — sinon on perdrait ce que la
    -- machine avait conclu, donc toute mesure de sa justesse dans le temps.
    human_verdict       TEXT    NOT NULL DEFAULT ''      -- '' = pas encore tranché
                                  CHECK (human_verdict IN ('', 'confirmed', 'overturned')),
    -- L'origine RÉELLE selon l'humain. Obligatoire si `overturned` (contrainte applicative) :
    -- infirmer sans dire ce que c'était vraiment efface une information sans en produire.
    human_origin        TEXT    NOT NULL DEFAULT ''
                                  CHECK (human_origin IN ('', 'test_a_reparer', 'vrai_bug', 'indetermine')),
    human_comment       TEXT    NOT NULL DEFAULT '',     -- le POURQUOI
    created_at          TEXT    NOT NULL,
    FOREIGN KEY (execution_id) REFERENCES execution(id)
);

CREATE INDEX IF NOT EXISTS idx_repair_execution ON repair_attempt(execution_id);

-- ── Journal des coûts (budget mensuel cumulé §5/§6) ──────────────────────────
-- Le coût appartient au CAS (c'est l'unité du §9 : « moins de 1 € par nouveau cas de test »).
-- `execution_id` n'est qu'un CONTEXTE facultatif : une réparation naît d'un run, une génération
-- n'en a aucun (elle précède toute exécution — et le cas peut n'être jamais exécuté).
-- ⚠️ `test_case_id` est ajouté par la MIGRATION 12 sur les bases existantes : avant elle, le
-- lien passait par `JOIN execution`, et le coût de génération du chemin API — sans exécution où
-- s'accrocher — était tout simplement PERDU.
CREATE TABLE IF NOT EXISTS cost_ledger (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    period_month TEXT    NOT NULL,               -- 'YYYY-MM'
    test_case_id INTEGER,                         -- le CAS qui a coûté (lien de référence, §9)
    execution_id INTEGER,                         -- contexte : le run concerné, si c'en est un
    phase        TEXT    NOT NULL DEFAULT '',     -- analysis | generation | repair | report
    model        TEXT    NOT NULL DEFAULT '',
    cost_usd     REAL    NOT NULL DEFAULT 0,
    source       TEXT    NOT NULL DEFAULT 'estimated'
                           CHECK (source IN ('estimated', 'anthropic_api')),
    created_at   TEXT    NOT NULL,
    FOREIGN KEY (execution_id) REFERENCES execution(id),
    FOREIGN KEY (test_case_id) REFERENCES test_case(id)
);

CREATE INDEX IF NOT EXISTS idx_cost_period ON cost_ledger(period_month);
-- ⚠️ `idx_cost_case` vit dans la MIGRATION 12, PAS ici — même raison que les index d'unicité et
-- `idx_case_module` : ce fichier s'exécute AVANT les migrations, or `cost_ledger.test_case_id`
-- n'existe pas encore sur une base antérieure. L'indexer ici fait planter TOUTE ouverture d'une
-- base existante (`no such column: test_case_id`). Erreur réellement commise le 2026-07-17 :
-- 416 tests verts ne l'ont pas vue (ils partent tous d'un schéma neuf), la vraie base l'a
-- attrapée à la première ouverture. Gardé par `test_une_base_SANS_la_colonne_s_ouvre_toujours`.

-- ── Unicité des noms ─────────────────────────────────────────────────────────
-- Les index UNIQUE (uq_project_name, uq_module_project_name, uq_case_feature_slug, et depuis la
-- migration 13 uq_group_module_title + uq_case_group_title) sont créés par MIGRATION, pas ici : ce
-- fichier s'exécute AVANT les migrations, or `test_case.module_id`/`feature_slug`/`group_id`
-- peuvent manquer sur une base antérieure — les indexer ici la ferait planter à l'ouverture (même
-- raison que idx_case_module). Une base neuve les reçoit quand même (ses migrations tournent toutes).
-- ⚠️ Le titre de cas est unique PAR GROUPE (migration 13), plus par module : deux spécifications
-- peuvent chacune avoir un cas « Nominal ». L'ancien uq_case_module_title est donc RETIRÉ.
