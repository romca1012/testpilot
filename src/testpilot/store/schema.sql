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
CREATE TABLE IF NOT EXISTS project (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    description TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL
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

-- ── Cas de test (socle commun §7) ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS test_case (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    title                  TEXT    NOT NULL,
    module_id              INTEGER REFERENCES module(id),   -- rangement MÉTIER (§7)
    feature_slug           TEXT    NOT NULL DEFAULT '',      -- nom du .feature (technique)
    connector_type         TEXT    NOT NULL DEFAULT 'odoo',
    description            TEXT    NOT NULL DEFAULT '',
    origin                 TEXT    NOT NULL DEFAULT 'ia_generated'
                                     CHECK (origin IN ('ia_generated', 'manual_converted')),
    validation_status      TEXT    NOT NULL DEFAULT 'never_executed'
                                     CHECK (validation_status IN ('never_executed', 'validated', 'to_review')),
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
    spec_content    TEXT    NOT NULL DEFAULT '',
    spec_hash       TEXT    NOT NULL DEFAULT '',
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
    report_json_path  TEXT    NOT NULL DEFAULT '',
    report_html_path  TEXT    NOT NULL DEFAULT '',
    trigger           TEXT    NOT NULL DEFAULT 'first_run'
                                CHECK (trigger IN ('first_run', 'rerun')),
    started_at        TEXT    NOT NULL,
    FOREIGN KEY (test_case_id) REFERENCES test_case(id),
    FOREIGN KEY (version_id)   REFERENCES test_case_version(id)
);

CREATE INDEX IF NOT EXISTS idx_execution_case ON execution(test_case_id);

-- ── Résultat par scénario (source des deux axes) ─────────────────────────────
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
    created_at          TEXT    NOT NULL,
    FOREIGN KEY (execution_id) REFERENCES execution(id)
);

CREATE INDEX IF NOT EXISTS idx_repair_execution ON repair_attempt(execution_id);

-- ── Journal des coûts (budget mensuel cumulé §5/§6) ──────────────────────────
CREATE TABLE IF NOT EXISTS cost_ledger (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    period_month TEXT    NOT NULL,               -- 'YYYY-MM'
    execution_id INTEGER,                         -- NULL pour les appels hors run
    phase        TEXT    NOT NULL DEFAULT '',     -- analysis | generation | repair | report
    model        TEXT    NOT NULL DEFAULT '',
    cost_usd     REAL    NOT NULL DEFAULT 0,
    source       TEXT    NOT NULL DEFAULT 'estimated'
                           CHECK (source IN ('estimated', 'anthropic_api')),
    created_at   TEXT    NOT NULL,
    FOREIGN KEY (execution_id) REFERENCES execution(id)
);

CREATE INDEX IF NOT EXISTS idx_cost_period ON cost_ledger(period_month);
