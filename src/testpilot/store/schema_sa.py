"""Modèle de schéma PORTABLE (SQLAlchemy Core), cible des migrations Alembic PostgreSQL.

Le runtime PostgreSQL est réellement branché via `store/portable_connection.py`. Les repositories
conservent leur API SQL historique et l'adaptateur traduit les particularités nécessaires ; ce
module reste la source déclarative utilisée par Alembic et par les contrôles de migration.

**Origine des tables ci-dessous : l'INTROSPECTION, pas une relecture des 41 migrations.** Chaque
table/colonne/CHECK/index a été vérifié contre la sortie réelle de
``python scripts/introspect_schema.py`` — lui-même construit en appelant
``testpilot.store.db.get_initialized_db()`` (donc `schema.sql` PUIS les migrations, dans
l'ordre réel) et en interrogeant SQLite (`sqlite_master`, `PRAGMA table_info`, etc.). Retranscrire
les migrations à l'œil, une par une, est exactement le mode de défaillance que ce lot évite — voir
la leçon de la migration 19 dans `db.py` (« mes tests exerçaient la dérivation du verdict, jamais
la persistance de la nouvelle valeur »). Le garde-fou anti-dérive
(`tests/test_schema_sa_portable.py`) vérifie que ce fichier reste synchronisé : toute migration
future (42, 43…) ajoutée à `db.py` SANS son équivalent ici fait échouer ce test.

**Conventions reprises de `schema.sql`** (elles ne sont pas réinventées ici) :
- Timestamps en `Text` (ISO-8601 UTC), jamais un type date/heure natif du moteur.
- Booléens en `Integer` 0/1 (`is_active`, `is_archived`, `auto_enveloppe`…), jamais `Boolean` —
  `schema.sql` ne les traite jamais autrement, et changer de convention ici romprait la promesse
  « le modèle portable EST le schéma réel », pas une réinterprétation « plus propre ».
- Enums en `Text` + `CheckConstraint`, jamais un type ENUM natif (Postgres en a un, SQLite non) :
  un administrateur peut ajouter une valeur `type`/`etat` sans migration (cf. `test_case`), et un
  ENUM natif recréerait la rigidité que le projet a explicitement refusée à ces deux colonnes.

**La preuve AUTOINCREMENT.** Chaque clé primaire entière auto-incrémentée est déclarée
``Integer`` + ``primary_key=True`` + ``autoincrement=True`` — SANS jamais écrire ``AUTOINCREMENT``
ni ``SERIAL``/``IDENTITY`` à la main. C'est SQLAlchemy qui choisit le DDL propre à chaque moteur
au moment du ``CREATE TABLE`` (voir `docs/ARCHITECTURE.md` §4 pour l'extrait exact observé sur
les deux moteurs). C'est tout l'intérêt de ce module : ne plus jamais retaper un dialecte SQL.

**Compléments PostgreSQL.** Les index d'unicité insensibles à la casse et le trigger
`trg_resultat_suit_le_mode_de_sa_campagne` ne sont pas exprimés de façon portable ici : ils sont
installés par la migration PostgreSQL dédiée `c4a1e95d7820`, puis vérifiés par les tests runtime.
"""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    Table,
    Text,
    UniqueConstraint,
)

# Version de `_SCHEMA_VERSION` (store/db.py) à laquelle ce modèle a été aligné pour la dernière
# fois. Le garde-fou anti-dérive (`tests/test_schema_sa_portable.py`) échoue bruyamment si la
# vraie base avance sans que ce fichier ne suive.
ALIGNED_WITH_SCHEMA_VERSION = 50

metadata = MetaData()


# ── Projet (racine de la hiérarchie §7) ──────────────────────────────────────
project = Table(
    "project",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", Text, nullable=False),
    Column("description", Text, nullable=False, server_default=""),
    # Migration 44 : seul `'odoo'` est traité spécialement (`connectors/factory.py`) — tout le
    # reste tombe déjà dans le connecteur générique. Le CHECK rend cette réalité explicite plutôt
    # que de laisser une faute de frappe s'y glisser sans le moindre signal.
    Column("connector_type", Text, nullable=False, server_default="odoo"),
    # Migration 38 : version DÉCLARÉE de cette instance — vide = indéterminée.
    Column("connector_version", Text, nullable=False, server_default=""),
    Column("base_url", Text, nullable=False, server_default=""),
    Column("database", Text, nullable=False, server_default=""),
    Column("username", Text, nullable=False, server_default=""),
    Column("password", Text, nullable=False, server_default=""),
    # Migration 45 : calibration en ÉCRITURE pendant la génération (RPC create+delete, Odoo
    # seulement) — ÉTEINTE par défaut, activée projet par projet par son porteur.
    Column("calibration_writes_enabled", Integer, nullable=False, server_default="0"),
    # Migration 50 (lot 07c) : contexte navigateur FIGÉ — vide = le défaut (fr-FR, Europe/Paris, 1440x900).
    Column("browser_locale", Text, nullable=False, server_default=""),
    Column("browser_timezone", Text, nullable=False, server_default=""),
    Column("browser_viewport", Text, nullable=False, server_default=""),
    Column("deleted_at", Text, nullable=False, server_default=""),
    Column("deleted_by", Text, nullable=False, server_default=""),
    Column("created_at", Text, nullable=False),
    # Migration 31 : '' = rôle global (comportement d'avant), sinon `no_access` ou un rôle forcé.
    Column("default_access", Text, nullable=False, server_default=""),
    CheckConstraint("connector_type IN ('odoo', 'web')", name="ck_project_connector_type"),
    # Partiel (vivants seulement) + NOCASE sur SQLite — voir la limite documentée en tête de
    # fichier : la collation n'est PAS reproduite ici, seule la clause `WHERE` l'est.
    Index("uq_project_name", "name", unique=True,
          sqlite_where=Column("deleted_at") == "",
          postgresql_where=Column("deleted_at") == ""),
    sqlite_autoincrement=True,
)


# ── Module / Fonctionnalité (appartient à un projet) ─────────────────────────
module = Table(
    "module",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("project_id", Integer, ForeignKey("project.id"), nullable=False),
    Column("name", Text, nullable=False),
    Column("description", Text, nullable=False, server_default=""),
    Column("deleted_at", Text, nullable=False, server_default=""),
    Column("deleted_by", Text, nullable=False, server_default=""),
    Column("created_at", Text, nullable=False),
    Index("idx_module_project", "project_id"),
    Index("uq_module_project_name", "project_id", "name", unique=True,
          sqlite_where=Column("deleted_at") == "",
          postgresql_where=Column("deleted_at") == ""),
    sqlite_autoincrement=True,
)


# ── Spécification : conteneur d'un GROUPE de cas testant la même fonctionnalité ─
case_group = Table(
    "case_group",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("module_id", Integer, ForeignKey("module.id"), nullable=False),
    Column("title", Text, nullable=False),
    Column("description", Text, nullable=False, server_default=""),
    Column("spec_content", Text, nullable=False, server_default=""),
    Column("spec_hash", Text, nullable=False, server_default=""),
    Column("position", Integer, nullable=False, server_default="0"),
    # Booléen INTEGER 0/1 (convention `schema.sql`) : 1 = enveloppe automatique (migration 17/18).
    Column("auto_enveloppe", Integer, nullable=False, server_default="0"),
    Column("deleted_at", Text, nullable=False, server_default=""),
    Column("deleted_by", Text, nullable=False, server_default=""),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    # Sous-section (migration 28) : NULL = Section de premier niveau.
    Column("parent_group_id", Integer, ForeignKey("case_group.id"), nullable=True),
    Index("idx_group_module", "module_id"),
    Index("idx_case_group_parent", "parent_group_id"),
    Index("uq_group_module_title", "module_id", "title", unique=True,
          sqlite_where=Column("deleted_at") == "",
          postgresql_where=Column("deleted_at") == ""),
    sqlite_autoincrement=True,
)


# ── Cas de test (socle commun §7) ────────────────────────────────────────────
test_case = Table(
    "test_case",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("title", Text, nullable=False),
    Column("module_id", Integer, ForeignKey("module.id"), nullable=True),
    Column("group_id", Integer, ForeignKey("case_group.id"), nullable=True),
    Column("feature_slug", Text, nullable=False, server_default=""),
    Column("description", Text, nullable=False, server_default=""),
    Column("origin", Text, nullable=False, server_default="ia_generated"),
    # `type`/`etat` : TEXTE LIBRE SANS CHECK, délibérément (précédent : `angle`, retiré migration
    # 26) — un administrateur peut ajouter une valeur sans migration de schéma.
    Column("type", Text, nullable=False, server_default="fonctionnel"),
    Column("etat", Text, nullable=False, server_default="new"),
    Column("priority", Text, nullable=False, server_default="medium"),
    Column("position", Integer, nullable=False, server_default="0"),
    Column("refs", Text, nullable=False, server_default=""),
    Column("estimate", Text, nullable=False, server_default=""),
    # Référence LOGIQUE vers la version courante — pas de FK dure (cycle case<->version), comme
    # dans `schema.sql`.
    Column("current_version_id", Integer, nullable=True),
    Column("last_execution_status", Text, nullable=True),
    Column("last_functional_status", Text, nullable=True),
    Column("last_executed_at", Text, nullable=True),
    Column("last_statut_manuel", Text, nullable=False, server_default=""),
    Column("last_result_mode", Text, nullable=False, server_default=""),
    Column("last_result_at", Text, nullable=False, server_default=""),
    Column("author", Text, nullable=False, server_default=""),
    Column("deleted_at", Text, nullable=False, server_default=""),
    Column("deleted_by", Text, nullable=False, server_default=""),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    CheckConstraint("origin IN ('ia_generated', 'manual_converted')", name="ck_test_case_origin"),
    CheckConstraint("priority IN ('low', 'medium', 'high')", name="ck_test_case_priority"),
    CheckConstraint(
        "last_execution_status IN ('success', 'technical_error', 'not_executed', 'blocked')",
        name="ck_test_case_last_execution_status",
    ),
    CheckConstraint(
        "last_functional_status IN ('conforme', 'non_conforme', 'indetermine',"
        " 'not_evaluated', 'donnee_invalide')",
        name="ck_test_case_last_functional_status",
    ),
    Index("idx_case_module", "module_id"),
    Index("idx_case_group", "group_id"),
    Index("uq_case_feature_slug", "feature_slug", unique=True,
          sqlite_where=(Column("feature_slug") != "") & (Column("deleted_at") == ""),
          postgresql_where=(Column("feature_slug") != "") & (Column("deleted_at") == "")),
    Index("uq_case_group_title", "group_id", "title", unique=True,
          sqlite_where=Column("deleted_at") == "",
          postgresql_where=Column("deleted_at") == ""),
    sqlite_autoincrement=True,
)


# ── Historisation des versions (gherkin + script) §7 §4 ──────────────────────
test_case_version = Table(
    "test_case_version",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("test_case_id", Integer, ForeignKey("test_case.id"), nullable=False),
    Column("version_number", Integer, nullable=False),
    # Dette explicite héritée de `schema.sql` (sursis technique jusqu'à la génération multi-cas) :
    # reprise TELLE QUELLE, ce module ne tranche pas une dette qui ne lui appartient pas.
    Column("spec_content", Text, nullable=False, server_default=""),
    Column("spec_hash", Text, nullable=False, server_default=""),
    Column("title", Text, nullable=False, server_default=""),
    Column("preconditions", Text, nullable=False, server_default=""),
    Column("test_steps", Text, nullable=False, server_default=""),
    Column("expected_result", Text, nullable=False, server_default=""),
    Column("feature_content", Text, nullable=False, server_default=""),
    Column("steps_content", Text, nullable=False, server_default=""),
    Column("verified_fields", Text, nullable=False, server_default=""),
    Column("observation_evidence", Text, nullable=False, server_default=""),
    Column("generation_provenance", Text, nullable=False, server_default=""),
    Column("technical_plan", Text, nullable=False, server_default=""),
    Column("feature_path", Text, nullable=False, server_default=""),
    Column("steps_path", Text, nullable=False, server_default=""),
    Column("change_summary", Text, nullable=False, server_default=""),
    Column("created_at", Text, nullable=False),
    Column("created_by", Text, nullable=False, server_default=""),
    Index("idx_version_case", "test_case_id"),
    sqlite_autoincrement=True,
)


# ── Décisions de relecture humaine (gate §4) ─────────────────────────────────
review_decision = Table(
    "review_decision",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("test_case_id", Integer, ForeignKey("test_case.id"), nullable=False),
    Column("version_id", Integer, ForeignKey("test_case_version.id"), nullable=False),
    Column("decision", Text, nullable=False),
    Column("reviewer", Text, nullable=False, server_default=""),
    Column("comment", Text, nullable=False, server_default=""),
    Column("repair_budget", Integer, nullable=False, server_default="2"),
    Column("decided_at", Text, nullable=False),
    CheckConstraint("decision IN ('approved', 'rejected')", name="ck_review_decision_decision"),
    Index("idx_review_version", "version_id"),
    sqlite_autoincrement=True,
)


# ── Exécution (TestRun) — deux axes de statut indépendants §5 ─────────────────
execution = Table(
    "execution",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("test_case_id", Integer, ForeignKey("test_case.id"), nullable=False),
    Column("version_id", Integer, ForeignKey("test_case_version.id"), nullable=False),
    Column("execution_status", Text, nullable=False, server_default="not_executed"),
    Column("functional_status", Text, nullable=False, server_default="not_evaluated"),
    Column("scenarios_total", Integer, nullable=False, server_default="0"),
    Column("scenarios_passed", Integer, nullable=False, server_default="0"),
    Column("scenarios_failed", Integer, nullable=False, server_default="0"),
    Column("cost_usd", Float, nullable=False, server_default="0"),
    Column("iterations", Integer, nullable=False, server_default="0"),
    Column("duration_seconds", Float, nullable=False, server_default="0"),
    Column("field_fallbacks", Text, nullable=False, server_default=""),
    Column("error_message", Text, nullable=False, server_default=""),
    Column("trigger", Text, nullable=False, server_default="first_run"),
    Column("target_url", Text, nullable=False, server_default=""),
    Column("target_database", Text, nullable=False, server_default=""),
    Column("target_username", Text, nullable=False, server_default=""),
    Column("artifacts_path", Text, nullable=False, server_default=""),
    Column("triggered_by", Text, nullable=False, server_default=""),
    Column("started_at", Text, nullable=False),
    # Lot 05 (D5, migration 49) : comment le verdict a été obtenu. `nominale` PAR DÉFAUT pour l'historique — ce n'est pas
    # une mesure (la confiance n'était pas calculée avant ce lot).
    Column("confiance", Text, nullable=False, server_default="nominale"),
    # `run_id` (migration 15) : PAS de FK dure dans `db.py` (`ALTER TABLE … ADD COLUMN run_id
    # INTEGER` sans REFERENCES) — repris à l'identique, NULL = exécutions mono-cas héritées.
    Column("run_id", Integer, nullable=True),
    CheckConstraint(
        "execution_status IN ('success', 'technical_error', 'not_executed', 'blocked')",
        name="ck_execution_execution_status",
    ),
    CheckConstraint(
        "functional_status IN ('conforme', 'non_conforme', 'indetermine',"
        " 'not_evaluated', 'donnee_invalide')",
        name="ck_execution_functional_status",
    ),
    CheckConstraint("trigger IN ('first_run', 'rerun')", name="ck_execution_trigger"),
    CheckConstraint("confiance IN ('nominale', 'auto_resolue', 'apres_retry')", name="ck_execution_confiance"),
    Index("idx_execution_case", "test_case_id"),
    Index("idx_execution_run", "run_id"),
    sqlite_autoincrement=True,
)


# ── Résultat par scénario (source des deux axes) ─────────────────────────────
scenario_result = Table(
    "scenario_result",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("execution_id", Integer, ForeignKey("execution.id"), nullable=False),
    Column("scenario_name", Text, nullable=False),
    Column("execution_status", Text, nullable=False),
    Column("functional_status", Text, nullable=False),
    Column("failure_type", Text, nullable=False, server_default=""),
    Column("cause_category", Text, nullable=False, server_default=""),
    Column("error_summary", Text, nullable=False, server_default=""),
    Column("step_text", Text, nullable=False, server_default=""),
    CheckConstraint(
        "execution_status IN ('success', 'technical_error', 'blocked')",
        name="ck_scenario_result_execution_status",
    ),
    CheckConstraint(
        "functional_status IN ('conforme', 'non_conforme', 'indetermine', 'donnee_invalide')",
        name="ck_scenario_result_functional_status",
    ),
    Index("idx_scenario_execution", "execution_id"),
    sqlite_autoincrement=True,
)


# ── Tentatives de réparation + origine du défaut (§5 asymétrique / §7) ────────
repair_attempt = Table(
    "repair_attempt",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("execution_id", Integer, ForeignKey("execution.id"), nullable=False),
    Column("attempt_number", Integer, nullable=False),
    Column("failure_signature", Text, nullable=False, server_default=""),
    Column("cause_category", Text, nullable=False, server_default=""),
    Column("defect_origin", Text, nullable=False, server_default="indetermine"),
    Column("confirmation_status", Text, nullable=False, server_default="not_required"),
    Column("confirmed_by", Text, nullable=True),
    Column("confirmed_at", Text, nullable=True),
    Column("what_was_tried", Text, nullable=False, server_default=""),
    Column("human_verdict", Text, nullable=False, server_default=""),
    Column("human_origin", Text, nullable=False, server_default=""),
    Column("human_comment", Text, nullable=False, server_default=""),
    Column("created_at", Text, nullable=False),
    CheckConstraint(
        "defect_origin IN ('test_a_reparer', 'vrai_bug', 'indetermine')",
        name="ck_repair_attempt_defect_origin",
    ),
    CheckConstraint(
        "confirmation_status IN ('pending_human', 'confirmed', 'rejected', 'not_required')",
        name="ck_repair_attempt_confirmation_status",
    ),
    CheckConstraint(
        "human_verdict IN ('', 'confirmed', 'overturned')",
        name="ck_repair_attempt_human_verdict",
    ),
    CheckConstraint(
        "human_origin IN ('', 'test_a_reparer', 'vrai_bug', 'indetermine')",
        name="ck_repair_attempt_human_origin",
    ),
    Index("idx_repair_execution", "execution_id"),
    sqlite_autoincrement=True,
)


# ── Journal des coûts (budget mensuel cumulé §5/§6) ──────────────────────────
cost_ledger = Table(
    "cost_ledger",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("period_month", Text, nullable=False),
    Column("test_case_id", Integer, ForeignKey("test_case.id"), nullable=True),
    Column("execution_id", Integer, ForeignKey("execution.id"), nullable=True),
    Column("phase", Text, nullable=False, server_default=""),
    Column("model", Text, nullable=False, server_default=""),
    Column("cost_usd", Float, nullable=False, server_default="0"),
    Column("source", Text, nullable=False, server_default="estimated"),
    Column("created_at", Text, nullable=False),
    CheckConstraint("source IN ('estimated', 'anthropic_api')", name="ck_cost_ledger_source"),
    Index("idx_cost_period", "period_month"),
    Index("idx_cost_case", "test_case_id"),
    sqlite_autoincrement=True,
)


# ── Campagne (migration 15, incrément 1) ─────────────────────────────────────
test_run = Table(
    "test_run",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("project_id", Integer, ForeignKey("project.id"), nullable=False),
    Column("name", Text, nullable=False),
    Column("description", Text, nullable=False, server_default=""),
    Column("refs", Text, nullable=False, server_default=""),
    Column("selection_mode", Text, nullable=False, server_default="frozen"),
    Column("status", Text, nullable=False, server_default="draft"),
    # `plan_id` : colonne simple, sans FK dure — le conteneur `test_plan` n'existe pas encore
    # (repris à l'identique de `db.py`).
    Column("plan_id", Integer, nullable=True),
    Column("created_at", Text, nullable=False),
    Column("launched_at", Text, nullable=True),
    Column("completed_at", Text, nullable=True),
    Column("is_archived", Integer, nullable=False, server_default="0"),
    Column("mode", Text, nullable=False, server_default="automatique"),
    # Lot 05 (D5, migration 49) : campagne STRICTE — ni résolution adaptative ni retry pendant l'exécution.
    Column("strict", Integer, nullable=False, server_default="0"),
    CheckConstraint("strict IN (0, 1)", name="ck_test_run_strict"),
    CheckConstraint("selection_mode IN ('all', 'frozen')", name="ck_test_run_selection_mode"),
    CheckConstraint("status IN ('draft', 'running', 'completed')", name="ck_test_run_status"),
    CheckConstraint("mode IN ('manuelle', 'automatique')", name="ck_test_run_mode"),
    Index("idx_run_project", "project_id"),
    sqlite_autoincrement=True,
)


# ── Liaison campagne <-> cas, par ID (jamais de copie de cas) ────────────────
test_run_case = Table(
    "test_run_case",
    metadata,
    Column("run_id", Integer, ForeignKey("test_run.id"), nullable=False),
    Column("case_id", Integer, ForeignKey("test_case.id"), nullable=False),
    PrimaryKeyConstraint("run_id", "case_id"),
    Index("idx_runcase_run", "run_id"),
)


# ── Plans de test — regroupement de campagnes (migration 43) ─────────────────
# `test_run.plan_id` (ci-dessus) reste SANS FK dure vers cette table — même convention que
# `execution.run_id` : une référence logique, jamais un verrou d'intégrité qui forcerait un
# reconstruire-la-table SQLite au prochain changement.
test_plan = Table(
    "test_plan",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("project_id", Integer, ForeignKey("project.id"), nullable=False),
    Column("name", Text, nullable=False),
    Column("description", Text, nullable=False, server_default=""),
    Column("refs", Text, nullable=False, server_default=""),
    Column("created_by", Text, nullable=False, server_default=""),
    Column("created_at", Text, nullable=False),
    Index("idx_plan_project", "project_id"),
    sqlite_autoincrement=True,
)


# ── Planifications récurrentes (migration 43) ────────────────────────────────
# ⚠️ AUCUNE colonne `mode` : une planification est TOUJOURS automatique (voir la docstring de
# `_migrate_43_plans_et_planifications` dans `db.py` — personne n'est présent à 2h du matin pour
# saisir un résultat manuel, donc ce choix n'existe même pas ici, pas seulement caché à l'écran).
scheduled_run = Table(
    "scheduled_run",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("project_id", Integer, ForeignKey("project.id"), nullable=False),
    Column("name", Text, nullable=False),
    Column("selection_mode", Text, nullable=False, server_default="frozen"),
    Column("frequency", Text, nullable=False),
    Column("hour", Integer, nullable=False),
    Column("minute", Integer, nullable=False),
    Column("weekday", Integer, nullable=True),
    Column("is_active", Integer, nullable=False, server_default="1"),
    Column("created_by", Text, nullable=False, server_default=""),
    Column("created_at", Text, nullable=False),
    Column("last_run_id", Integer, nullable=True),
    Column("last_triggered_at", Text, nullable=True),
    CheckConstraint("selection_mode IN ('all', 'frozen')",
                     name="ck_scheduled_run_selection_mode"),
    CheckConstraint("frequency IN ('daily', 'weekly')", name="ck_scheduled_run_frequency"),
    CheckConstraint("hour BETWEEN 0 AND 23", name="ck_scheduled_run_hour"),
    CheckConstraint("minute BETWEEN 0 AND 59", name="ck_scheduled_run_minute"),
    CheckConstraint("weekday IS NULL OR weekday BETWEEN 0 AND 6",
                     name="ck_scheduled_run_weekday"),
    Index("idx_scheduled_run_project", "project_id"),
    Index("idx_scheduled_run_active", "is_active"),
    sqlite_autoincrement=True,
)

scheduled_run_case = Table(
    "scheduled_run_case",
    metadata,
    Column("scheduled_run_id", Integer, ForeignKey("scheduled_run.id"), nullable=False),
    Column("case_id", Integer, nullable=False),
    PrimaryKeyConstraint("scheduled_run_id", "case_id"),
)


# ── Le registre des résultats (migration 25, renommé migration 27) ───────────
test_result = Table(
    "test_result",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", Integer, ForeignKey("test_run.id"), nullable=False),
    Column("case_id", Integer, ForeignKey("test_case.id"), nullable=False),
    # STOCKÉ, jamais déduit : c'est la colonne qui empêche le produit de mentir (cf. `db.py`).
    Column("mode", Text, nullable=False),
    Column("execution_id", Integer, ForeignKey("execution.id"), nullable=True),
    Column("statut_manuel", Text, nullable=False, server_default=""),
    Column("comment", Text, nullable=False, server_default=""),
    Column("created_by", Text, nullable=False, server_default=""),
    Column("attachments_path", Text, nullable=False, server_default=""),
    Column("created_at", Text, nullable=False),
    CheckConstraint("mode IN ('manuelle', 'automatique')", name="ck_test_result_mode"),
    CheckConstraint(
        "statut_manuel IN ('', 'passed', 'failed', 'retest', 'blocked')",
        name="ck_test_result_statut_manuel",
    ),
    # LE CHECK QUI PORTE LA PROMESSE (repris mot pour mot de `db.py`, migration 27) : un résultat
    # automatique a une exécution et aucun statut saisi ; un manuel a un statut saisi et aucune
    # exécution. ⚠️ Le TRIGGER qui vérifie la concordance avec le mode de la campagne n'est PAS
    # reproduit ici (voir la limite documentée en tête de fichier).
    CheckConstraint(
        "(mode = 'automatique' AND execution_id IS NOT NULL AND statut_manuel = '')"
        " OR (mode = 'manuelle' AND execution_id IS NULL AND statut_manuel <> '')",
        name="ck_test_result_mode_coherence",
    ),
    Index("uq_result_execution", "execution_id", unique=True,
          sqlite_where=Column("execution_id").isnot(None),
          postgresql_where=Column("execution_id").isnot(None)),
    Index("idx_result_case", "case_id"),
    Index("idx_result_run_case", "run_id", "case_id"),
    sqlite_autoincrement=True,
)


# ── À qui un cas est CONFIÉ dans une campagne ────────────────────────────────
run_case_assignment = Table(
    "run_case_assignment",
    metadata,
    Column("run_id", Integer, ForeignKey("test_run.id"), nullable=False),
    Column("case_id", Integer, ForeignKey("test_case.id"), nullable=False),
    Column("assigned_to", Text, nullable=False, server_default=""),
    Column("assigned_by", Text, nullable=False, server_default=""),
    Column("assigned_at", Text, nullable=False),
    PrimaryKeyConstraint("run_id", "case_id"),
)


# ── Pièces jointes d'un résultat ─────────────────────────────────────────────
result_attachment = Table(
    "result_attachment",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("result_id", Integer, ForeignKey("test_result.id"), nullable=False),
    Column("filename", Text, nullable=False),
    Column("stored_name", Text, nullable=False),
    Column("content_type", Text, nullable=False, server_default=""),
    Column("size_bytes", Integer, nullable=False, server_default="0"),
    Column("created_at", Text, nullable=False),
    Index("idx_attachment_result", "result_id"),
    sqlite_autoincrement=True,
)


# ── Réglages d'instance ──────────────────────────────────────────────────────
# Clé PRIMAIRE TEXTE, pas d'auto-incrément : `SettingRepo` refuse toute clé absente de son
# `CLES_CONNUES`, la clé porte donc déjà tout le sens (pas besoin d'un id numérique).
app_setting = Table(
    "app_setting",
    metadata,
    Column("key", Text, primary_key=True, autoincrement=False),
    Column("value", Text, nullable=False, server_default=""),
    Column("updated_at", Text, nullable=False),
    Column("updated_by", Text, nullable=False, server_default=""),
)


# ── Job de génération PERSISTÉ (migration 29, incident réel du 07/08) ────────
# id TEXTE (uuid côté application), pas d'auto-incrément — repris à l'identique de `db.py`.
generation_job = Table(
    "generation_job",
    metadata,
    Column("id", Text, primary_key=True, autoincrement=False),
    Column("status", Text, nullable=False),
    Column("error", Text, nullable=False, server_default=""),
    Column("case_ids", Text, nullable=False, server_default="[]"),
    # Pas de FK dure vers `module` dans `db.py` : repris à l'identique.
    Column("module_id", Integer, nullable=False),
    Column("payload", Text, nullable=False, server_default="{}"),
    Column("cost_usd", Float, nullable=False, server_default="0.0"),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    Index("idx_generation_job_status", "status"),
)


# ── Comptes utilisateurs (migration 30) ──────────────────────────────────────
user = Table(
    "user",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("username", Text, nullable=False),
    Column("password_hash", Text, nullable=False),
    Column("role", Text, nullable=False),
    Column("is_active", Integer, nullable=False, server_default="1"),
    Column("created_at", Text, nullable=False),
    Column("email", Text, nullable=False, server_default=""),
    Column("session_version", Integer, nullable=False, server_default="1"),
    Column("must_change_password", Integer, nullable=False, server_default="0"),
    Column("password_expires_at", Integer, nullable=False, server_default="0"),
    CheckConstraint(
        "role IN ('lecture_seule', 'testeur', 'dev', 'admin')", name="ck_user_role"
    ),
    UniqueConstraint("username", name="uq_user_username"),
    sqlite_autoincrement=True,
)


background_job = Table(
    "background_job",
    metadata,
    Column("id", Text, primary_key=True, autoincrement=False),
    Column("kind", Text, nullable=False),
    Column("queue_label", Text, nullable=False),
    Column("payload", Text, nullable=False, server_default="{}"),
    Column("status", Text, nullable=False),
    Column("error", Text, nullable=False, server_default=""),
    Column("created_at", Text, nullable=False),
    Column("started_at", Text, nullable=False, server_default=""),
    Column("finished_at", Text, nullable=False, server_default=""),
    CheckConstraint(
        "status IN ('queued','running','completed','failed')",
        name="ck_background_job_status",
    ),
    Index("idx_background_job_status_created", "status", "created_at"),
)


login_failure = Table(
    "login_failure",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("attempt_key", Text, nullable=False),
    Column("occurred_at", Float, nullable=False),
    Index("idx_login_failure_key_time", "attempt_key", "occurred_at"),
    sqlite_autoincrement=True,
)


# ── Surcharge du rôle global, PAR PROJET (migration 31) ──────────────────────
# Pas de FK dure ici (repris à l'identique de `db.py` — `project_access` a été créée sans
# REFERENCES, contrairement à `project_member`, née plus tard avec la discipline FK).
project_access = Table(
    "project_access",
    metadata,
    Column("project_id", Integer, nullable=False),
    Column("user_id", Integer, nullable=False),
    Column("role", Text, nullable=False),
    CheckConstraint(
        "role IN ('no_access', 'lecture_seule', 'testeur', 'dev', 'admin')",
        name="ck_project_access_role",
    ),
    PrimaryKeyConstraint("project_id", "user_id"),
)


# ── Appartenance projet matérialisée (migration 34) ──────────────────────────
project_member = Table(
    "project_member",
    metadata,
    Column("project_id", Integer, ForeignKey("project.id"), nullable=False),
    Column("user_id", Integer, ForeignKey("user.id"), nullable=False),
    Column("role", Text, nullable=False),
    Column("status", Text, nullable=False, server_default="active"),
    Column("created_at", Text, nullable=False),
    CheckConstraint(
        "role IN ('lecture_seule', 'testeur', 'dev', 'admin')", name="ck_project_member_role"
    ),
    CheckConstraint(
        "status IN ('active', 'suspended', 'removed')", name="ck_project_member_status"
    ),
    PrimaryKeyConstraint("project_id", "user_id"),
    Index("idx_project_member_user", "user_id", "status"),
)


# ── Journal des mutations d'accès (migration 35) ─────────────────────────────
# Pas de FK dure sur `project_id`/`actor_user_id`/`target_user_id` : repris à l'identique de
# `db.py` — un journal d'audit doit survivre à la suppression de ce qu'il journalise.
access_audit = Table(
    "access_audit",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("occurred_at", Text, nullable=False),
    Column("actor_user_id", Integer, nullable=True),
    Column("project_id", Integer, nullable=False),
    Column("action", Text, nullable=False),
    Column("target_user_id", Integer, nullable=True),
    Column("result", Text, nullable=False),
    Column("detail", Text, nullable=False, server_default=""),
    CheckConstraint("result IN ('allowed', 'denied')", name="ck_access_audit_result"),
    Index("idx_access_audit_project_time", "project_id", "occurred_at"),
    sqlite_autoincrement=True,
)


# ── Groupes d'utilisateurs façon TestRail (migration 36) ─────────────────────
user_group = Table(
    "user_group",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", Text, nullable=False),
    Column("created_at", Text, nullable=False),
    UniqueConstraint("name", name="uq_user_group_name"),
    sqlite_autoincrement=True,
)


user_group_member = Table(
    "user_group_member",
    metadata,
    Column("group_id", Integer, ForeignKey("user_group.id", ondelete="CASCADE"), nullable=False),
    Column("user_id", Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
    PrimaryKeyConstraint("group_id", "user_id"),
    Index("idx_user_group_member_user", "user_id"),
)


# ── Surcharge d'accès par groupe et par projet (migration 37) ────────────────
project_group_access = Table(
    "project_group_access",
    metadata,
    Column("project_id", Integer, ForeignKey("project.id", ondelete="CASCADE"), nullable=False),
    Column("group_id", Integer, ForeignKey("user_group.id", ondelete="CASCADE"), nullable=False),
    Column("role", Text, nullable=False),
    CheckConstraint(
        "role IN ('', 'no_access', 'lecture_seule', 'testeur', 'dev', 'admin')",
        name="ck_project_group_access_role",
    ),
    PrimaryKeyConstraint("project_id", "group_id"),
)

# Tentatives physiques : un rejeu ne remplace jamais son premier résultat.
execution_attempt = Table(
    'execution_attempt', metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('execution_id', Integer, ForeignKey('execution.id', ondelete='CASCADE'), nullable=False),
    Column('attempt_number', Integer, nullable=False),
    Column('reason', Text, nullable=False),
    Column('started_at', Text, nullable=False),
    Column('finished_at', Text, nullable=False, server_default=''),
    Column('execution_status', Text, nullable=False, server_default='pending'),
    Column('functional_status', Text, nullable=False, server_default='indetermine'),
    Column('duration_seconds', Float, nullable=False, server_default='0'),
    Column('artifacts_path', Text, nullable=False, server_default=''),
    Column('provenance', Text, nullable=False, server_default='{}'),
    Column('result_json', Text, nullable=False, server_default='{}'),
    CheckConstraint('attempt_number > 0', name='ck_execution_attempt_number'),
    UniqueConstraint('execution_id', 'attempt_number', name='uq_execution_attempt_number'),
    sqlite_autoincrement=True,
)
