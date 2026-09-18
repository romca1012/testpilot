"""Accès SQLite bas niveau : connexion, initialisation du schéma et migrations.

Le schéma CIBLE vit dans ``schema.sql`` (SQL portable, ``CREATE IF NOT EXISTS``). Les bases
DÉJÀ existantes sont amenées à la cible par des migrations versionnées via ``PRAGMA
user_version`` — chaque migration est idempotente (gardée par introspection). Aucune logique
métier ici.
"""

from __future__ import annotations

import logging
import re
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from testpilot import config
from testpilot.store.portable_connection import PostgresConnection

logger = logging.getLogger(__name__)

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")

# Version cible du schéma. Incrémentée à chaque migration ajoutée ci-dessous.
_SCHEMA_VERSION = 46

# Horodatage des sauvegardes automatiques — même granularité que les copies manuelles déjà vues
# dans ce dépôt (`testpilot.db.avant-nettoyage-20260805-104308`).
_HORODATAGE_SAUVEGARDE = "%Y%m%d-%H%M%S"


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Ouvre une connexion SQLite avec les lignes indexables par nom et les FK actives.

    ``check_same_thread=False`` : FastAPI exécute une dépendance ``yield`` SYNCHRONE dans un
    thread du pool et l'endpoint dans un AUTRE thread du même pool. La connexion d'``api.deps``
    est donc *passée* d'un thread à l'autre — jamais partagée par deux threads en même temps
    (une connexion PAR requête, fermée à la fin). Sans ce drapeau, SQLite refuse ce simple
    passage de main et la requête tombe en HTTP 500 — de façon **intermittente**, au gré de
    l'ordonnancement du pool, donc invisible tant qu'aucune requête ne se chevauche.

    ⚠️ Ce drapeau ne rend PAS une connexion partageable entre threads concurrents : il lève le
    contrôle de propriété, il n'ajoute aucun verrou. L'invariant à tenir reste « une connexion
    par requête / par tâche », jamais une connexion globale partagée.
    """
    path = Path(db_path) if db_path else config.DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Crée les tables manquantes (idempotent) puis applique les migrations en attente."""
    conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()
    _run_migrations(conn)


def _sauvegarder_avant_migration(path: Path, version_avant: int) -> Path:
    """Copie `path` À CÔTÉ d'elle-même, AVANT qu'une migration n'y écrive quoi que ce soit.

    Convention de nom cohérente avec les copies manuelles déjà vues dans ce dépôt
    (`testpilot.db.avant-nettoyage-20260805-104308`) : `{nom}.avant-migration-{version}-{horodatage}`,
    où `version` est le schéma DE DÉPART (celui qu'on peut retrouver en cas de retour arrière), pas
    la cible. `shutil.copy2` (pas `copy`) : préserve les métadonnées, sans intérêt fonctionnel ici
    mais sans coût non plus.

    Ne touche PAS aux fichiers `-wal`/`-shm` : `connect()` n'active aucun `PRAGMA journal_mode=WAL`
    (le mode par défaut de sqlite3 est le journal `DELETE`, purgé à la fermeture de la connexion
    précédente) — il n'y a donc rien de cohérent à recopier en plus du fichier principal.
    """
    horodatage = datetime.now(timezone.utc).strftime(_HORODATAGE_SAUVEGARDE)
    cible = path.with_name(f"{path.name}.avant-migration-{version_avant}-{horodatage}")
    shutil.copy2(path, cible)
    return cible


def get_initialized_db(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Raccourci : connexion + schéma prêt à l'emploi (migrations incluses).

    ⚠️ **Sauvegarde AVANT toute migration qui va RÉELLEMENT écrire la base** — dans ce code, pas
    seulement documentée (`docs/DEPLOIEMENT*`) : une consigne humaine s'oublie, un appel au
    démarrage du serveur non. Trois cas, tous mesurés par le test qui accompagne cette fonction :

    - **base neuve** (le fichier n'existe pas encore) : rien à perdre, aucune copie — le schéma se
      crée directement. Copier un fichier qui n'existe pas planterait pour rien.
    - **base déjà à jour** (`user_version == _SCHEMA_VERSION`) : aucune migration ne va s'exécuter,
      donc aucune sauvegarde à CHAQUE redémarrage du serveur — ça grossirait sans fin pour un
      bénéfice nul (le même écart que `data/executions/`, que ce lot ne veut pas répéter).
    - **base ancienne** (`user_version < _SCHEMA_VERSION`) : une migration va écrire. On sauvegarde
      D'ABORD. Si la copie ÉCHOUE (disque plein, permission refusée), on **refuse de migrer** et on
      relève l'exception plutôt que de continuer sans filet — mieux vaut un démarrage bloqué,
      bruyamment journalisé, qu'une migration qu'on ne pourrait pas défaire si elle tournait mal.

    L'existence du fichier est testée **avant** `connect()` : ouvrir une connexion SQLite sur un
    chemin absent CRÉE le fichier (vide, sans schéma) — après quoi `path.exists()` mentirait.
    """
    if db_path is None and config.DB_URL.startswith(("postgresql://", "postgresql+psycopg://")):
        # Le schéma PostgreSQL est géré par Alembic au déploiement, jamais recréé à chaque requête.
        return PostgresConnection(config.DB_URL)  # type: ignore[return-value]

    # `Path(...)` dans les DEUX branches : `config.DB_PATH` est un `Path` par défaut (`config.py`),
    # mais un test peut légitimement le monkeypatcher avec une chaîne (ex. `PRAGMA database_list`
    # renvoie le chemin en `str`, jamais en `Path`) — trouvé en pratique (2026-09-03) sur l'appel
    # sans argument (`get_initialized_db()`), qui empruntait ce repli sans jamais passer par
    # `Path(db_path)` comme le fait la branche explicite juste au-dessus.
    path = Path(db_path) if db_path else Path(config.DB_PATH)
    existait_deja = path.exists()
    conn = connect(path)
    if existait_deja:
        version_avant = conn.execute("PRAGMA user_version").fetchone()[0]
        if version_avant < _SCHEMA_VERSION:
            try:
                cible = _sauvegarder_avant_migration(path, version_avant)
            except OSError:
                conn.close()
                logger.critical(
                    "[sauvegarde pré-migration] ÉCHEC de la copie de %s avant la migration"
                    " (schéma %s -> %s) : migration REFUSÉE, le serveur ne démarre pas sur cette"
                    " base. Vérifiez l'espace disque et les droits d'écriture sur %s, puis relancez.",
                    path, version_avant, _SCHEMA_VERSION, path.parent, exc_info=True)
                raise
            logger.info(
                "[sauvegarde pré-migration] %s -> %s (schéma %s -> %s)",
                path, cible, version_avant, _SCHEMA_VERSION)
    init_db(conn)
    return conn


# ── Migrations ────────────────────────────────────────────────────────────────
def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}


def _colonnes_ordonnees(conn: sqlite3.Connection, table: str) -> list[str]:
    """Les colonnes DANS L'ORDRE de la table — nécessaire pour recopier une table à l'identique."""
    return [r["name"] for r in conn.execute(f"PRAGMA table_info({table})")]


def _run_migrations(conn: sqlite3.Connection) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version < 1:
        _migrate_1_project_module(conn)
    if version < 2:
        _migrate_2_project_connector(conn)
    if version < 3:
        _migrate_3_case_priority(conn)
    if version < 4:
        _migrate_4_execution_field_fallbacks(conn)
    if version < 5:
        _migrate_5_unicite_noms(conn)
    if version < 6:
        _migrate_6_case_position(conn)
    if version < 7:
        _migrate_7_drop_report_paths(conn)
    if version < 8:
        _migrate_8_verdict_humain(conn)
    if version < 9:
        _migrate_9_repair_budget(conn)
    if version < 10:
        _migrate_10_step_text(conn)
    if version < 11:
        _migrate_11_execution_error(conn)
    if version < 12:
        _migrate_12_cost_case_id(conn)
    if version < 13:
        _migrate_13_case_group(conn)
    if version < 14:
        _migrate_14_champs_metier(conn)
    if version < 15:
        _migrate_15_test_run(conn)
    if version < 16:
        _migrate_16_run_archive(conn)
    if version < 17:
        _migrate_17_specification_auto_enveloppe(conn)
    if version < 18:
        _migrate_18_corriger_provenance_enveloppes(conn)
    if version < 19:
        _migrate_19_verdict_donnee_invalide(conn)
    if version < 20:
        _migrate_20_execution_cible(conn)
    if version < 21:
        _migrate_21_chiffrer_secrets(conn)
    if version < 22:
        _migrate_22_execution_artefacts(conn)
    if version < 23:
        _migrate_23_suppression_douce(conn)
    if version < 24:
        _migrate_24_unicite_parmi_les_vivants(conn)
    if version < 25:
        _migrate_25_resultats_et_cycle_de_vie(conn)
    if version < 26:
        _migrate_26_retrait_de_l_angle(conn)
    if version < 27:
        _migrate_27_mode_d_execution(conn)
    if version < 28:
        _migrate_28_sous_sections(conn)
    if version < 29:
        _migrate_29_generation_job(conn)
    if version < 30:
        _migrate_30_utilisateurs(conn)
    if version < 31:
        _migrate_31_acces_par_projet(conn)
    if version < 32:
        _migrate_32_triggered_by(conn)
    if version < 33:
        _migrate_33_email_utilisateur(conn)
    if version < 34:
        _migrate_34_project_members(conn)
    if version < 35:
        _migrate_35_access_audit(conn)
    if version < 36:
        _migrate_36_user_groups(conn)
    if version < 37:
        _migrate_37_project_group_access(conn)
    if version < 38:
        _migrate_38_connector_version(conn)
    if version < 39:
        _migrate_39_session_version(conn)
    if version < 40:
        _migrate_40_login_failure(conn)
    if version < 41:
        _migrate_41_background_job(conn)
    if version < 42:
        _migrate_42_password_ownership(conn)
    if version < 43:
        _migrate_43_plans_et_planifications(conn)
    if version < 44:
        _migrate_44_connector_type_valide(conn)
    if version < 45:
        _migrate_45_calibration_writes(conn)
    if version < 46:
        _migrate_46_verified_fields(conn)
    conn.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
    conn.commit()


def _migrate_42_password_ownership(conn: sqlite3.Connection) -> None:
    import time
    if "must_change_password" not in _column_names(conn, "user"):
        conn.execute("ALTER TABLE user ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0")
        conn.execute("ALTER TABLE user ADD COLUMN password_expires_at INTEGER NOT NULL DEFAULT 0")
        conn.execute("UPDATE user SET must_change_password=1, password_expires_at=?, "
                     "session_version=session_version+1", (int(time.time()) + 7 * 86400,))
        # Fige l'accès implicite ACTUEL en overrides explicites AVANT de fermer les projets :
        # sans ça, `default_access='no_access'` couperait immédiatement tout compte qui n'a
        # jamais eu besoin d'une exception — soit tout le monde, puisque c'est précisément le
        # trou que ce correctif comble pour l'avenir. Idempotent : ne touche que les projets
        # encore ouverts (`default_access=''`) et ne recrée jamais une ligne déjà présente.
        conn.execute(
            "INSERT INTO project_access (project_id, user_id, role) "
            "SELECT p.id, u.id, u.role FROM project p CROSS JOIN user u "
            "WHERE p.default_access='' AND NOT EXISTS ("
            "  SELECT 1 FROM project_access pa WHERE pa.project_id=p.id AND pa.user_id=u.id)")
        conn.execute("UPDATE project SET default_access='no_access' WHERE default_access=''")
        from testpilot.store.repositories import ProjectMemberRepo
        for project in conn.execute("SELECT id FROM project").fetchall():
            ProjectMemberRepo(conn).sync_project(project["id"])


def _migrate_43_plans_et_planifications(conn: sqlite3.Connection) -> None:
    """Plans de test (regroupement de campagnes) + planifications récurrentes (2026-09-10).

    ⚠️ **Aucune colonne `mode` sur `scheduled_run`** : une planification est TOUJOURS automatique
    — personne n'est présent à 2h du matin pour saisir un résultat manuel. `scheduler_service.tick()`
    force `MODE_AUTOMATIQUE` à la création de chaque `test_run` qu'elle engendre ; le lire depuis
    une entrée utilisateur serait la seule façon de se tromper ici, donc la colonne n'existe pas.

    `test_run.plan_id` (colonne déjà présente depuis la migration 15, jamais FK dure « pour ne pas
    dépendre d'une table encore absente ») reste SANS FK dure même maintenant que `test_plan`
    existe — cohérent avec la même convention déjà appliquée à `execution.run_id` : une référence
    logique, pas un verrou d'intégrité, pour ne jamais bloquer une migration future sur un
    reconstruire-la-table SQLite.
    """
    conn.execute(
        "CREATE TABLE IF NOT EXISTS test_plan ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " project_id INTEGER NOT NULL REFERENCES project(id),"
        " name TEXT NOT NULL,"
        " description TEXT NOT NULL DEFAULT '',"
        " refs TEXT NOT NULL DEFAULT '',"
        " created_by TEXT NOT NULL DEFAULT '',"
        " created_at TEXT NOT NULL)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_plan_project ON test_plan(project_id)")

    conn.execute(
        "CREATE TABLE IF NOT EXISTS scheduled_run ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " project_id INTEGER NOT NULL REFERENCES project(id),"
        " name TEXT NOT NULL,"
        " selection_mode TEXT NOT NULL DEFAULT 'frozen'"
        "     CHECK (selection_mode IN ('all', 'frozen')),"
        " frequency TEXT NOT NULL CHECK (frequency IN ('daily', 'weekly')),"
        " hour INTEGER NOT NULL CHECK (hour BETWEEN 0 AND 23),"
        " minute INTEGER NOT NULL CHECK (minute BETWEEN 0 AND 59),"
        " weekday INTEGER CHECK (weekday IS NULL OR weekday BETWEEN 0 AND 6),"
        " is_active INTEGER NOT NULL DEFAULT 1,"
        " created_by TEXT NOT NULL DEFAULT '',"
        " created_at TEXT NOT NULL,"
        " last_run_id INTEGER,"
        " last_triggered_at TEXT)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_scheduled_run_project ON scheduled_run(project_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_scheduled_run_active ON scheduled_run(is_active)")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS scheduled_run_case ("
        " scheduled_run_id INTEGER NOT NULL REFERENCES scheduled_run(id) ON DELETE CASCADE,"
        " case_id INTEGER NOT NULL,"
        " PRIMARY KEY (scheduled_run_id, case_id))")


def _migrate_44_connector_type_valide(conn: sqlite3.Connection) -> None:
    """`project.connector_type` gagne un CHECK — audit « Le pari Mabl/Testim » (2026-09-15, P2).

    ⚠️ **Avant ce correctif, une faute de frappe ne levait rien.** Seule la valeur `'odoo'` est
    traitée spécialement (`connectors/factory.py::build_connector`) ; tout le reste — y compris
    un typo — tombait déjà, en silence, dans le connecteur générique. Le CHECK ne CHANGE donc
    aucun comportement d'exécution : il rend visible, dès l'écriture, ce qui était déjà vrai à la
    lecture.

    **Normalisation AVANT le CHECK, pas après.** Un projet existant dont `connector_type` porterait
    déjà une valeur ni `'odoo'` ni `'web'` (improbable — rien ne l'a jamais écrit — mais possible
    par une manipulation directe de la base) ferait échouer la reconstruction de table sur une
    violation de contrainte, à l'ouverture du serveur. Le ramener à `'web'` PRÉSERVE exactement le
    comportement déjà en vigueur pour cette ligne (`build_connector` la traite déjà comme
    générique) — ce n'est pas une correction de donnée, c'est la même vérité écrite explicitement.

    SQLite ne sait pas ajouter un CHECK par `ALTER TABLE` : reconstruction de `project`, même
    procédé qu'à la migration 19, robuste à `IF NOT EXISTS` (présent dans `schema.sql` pour cette
    table, contrairement aux tables ciblées par la 19 à l'époque) et à un nom déjà entre guillemets
    (`project` n'a encore jamais été reconstruite, mais le motif protège une reconstruction future).

    ⚠️ **`PRAGMA foreign_key_check` SANS argument (le choix de la migration 19) est le mauvais
    garde ici — trouvé en rejouant CETTE migration sur une copie de la VRAIE base.** Sans argument,
    la PRAGMA vérifie TOUTES les tables de la base, pas seulement celle qu'on reconstruit — et la
    vraie base porte une ligne `project_member` orpheline (un `user` supprimé), un défaut de
    donnée PRÉEXISTANT et SANS AUCUN RAPPORT avec `project`/`connector_type`. Un check global
    aurait fait échouer cette migration (et donc bloqué le démarrage du serveur) sur un problème
    qu'elle n'a ni créé ni le pouvoir de corriger. `PRAGMA foreign_key_check(project)` restreint le
    contrôle aux clés étrangères SORTANTES de `project` elle-même (il n'y en a aucune : c'est une
    table racine) — le risque réel de CETTE reconstruction, un nombre de lignes qui changerait,
    est vérifié explicitement juste après, plutôt que délégué à une PRAGMA qui regarde ailleurs.
    """
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='project'").fetchone()
    sql = row["sql"] if row else ""
    if not sql or re.search(r"connector_type\s+IN\s*\(", sql, re.IGNORECASE):
        return  # table absente, ou déjà migrée → idempotent

    conn.execute(
        "UPDATE project SET connector_type='web' WHERE connector_type NOT IN ('odoo', 'web')")

    new_sql, remplace = re.subn(
        r"(connector_type\s+TEXT\s+NOT\s+NULL\s+DEFAULT\s+'odoo')",
        r"\1 CHECK (connector_type IN ('odoo', 'web'))", sql, count=1, flags=re.IGNORECASE)
    if not remplace:
        logger.critical("[migration 44] définition de project.connector_type non reconnue dans le "
                        "schéma stocké : la colonne reste SANS validation (sans effet fonctionnel, "
                        "le comportement d'exécution ne dépendait déjà pas de ce CHECK).")
        return

    tmp = "project__migr44"
    # Guillemets appariés par RÉFÉRENCE ARRIÈRE (`\2`), pas deux `?` indépendants : deux quantifieurs
    # optionnels laisseraient passer un texte avec SEULEMENT la guillemet fermante (ex. après une
    # première reconstruction, `CREATE TABLE "project" (` — repli sur `\b` cassé, testé et corrigé
    # ici avant tout commit). Même motif que `_reconstruire_sans_colonne` (migration 25).
    create_tmp, renomme = re.subn(
        r'^(\s*CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?)("?)project\2',
        lambda m: f"{m.group(1)}{tmp}", new_sql, count=1, flags=re.IGNORECASE)
    if not renomme:
        logger.critical("[migration 44] en-tête CREATE TABLE de project non reconnue : la colonne "
                        "reste SANS validation (sans effet fonctionnel).")
        return

    aux = conn.execute(
        "SELECT sql FROM sqlite_master WHERE tbl_name='project' AND type IN ('index','trigger')"
        " AND sql IS NOT NULL AND name NOT LIKE 'sqlite_%'").fetchall()
    avant = conn.execute("SELECT COUNT(*) AS n FROM project").fetchone()["n"]

    conn.commit()  # aucune transaction ouverte : PRAGMA foreign_keys est un no-op en transaction
    old_iso = conn.isolation_level
    conn.isolation_level = None  # autocommit : on gère BEGIN/COMMIT nous-mêmes (DDL+DML atomique)
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("BEGIN")
        try:
            conn.execute(f"DROP TABLE IF EXISTS {tmp}")
            conn.execute(create_tmp)
            conn.execute(f"INSERT INTO {tmp} SELECT * FROM project")
            apres = conn.execute(f"SELECT COUNT(*) AS n FROM {tmp}").fetchone()["n"]
            if apres != avant:
                raise RuntimeError(
                    f"reconstruction de project : {avant} lignes avant, {apres} après — abandon")
            conn.execute("DROP TABLE project")
            conn.execute(f"ALTER TABLE {tmp} RENAME TO project")
            for a in aux:
                conn.execute(a["sql"])  # index/triggers recréés (dropés avec l'ancienne table)
            violations = conn.execute("PRAGMA foreign_key_check(project)").fetchall()
            if violations:
                raise RuntimeError(f"FK sortantes cassées sur project : {violations}")
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        conn.execute("PRAGMA foreign_keys = ON")
    finally:
        conn.isolation_level = old_iso


def _migrate_45_calibration_writes(conn: sqlite3.Connection) -> None:
    """`project.calibration_writes_enabled` — amendement §4.3-bis étendu (2026-09-16).

    Autorise l'agent de génération à soumettre un VRAI formulaire (au-delà de la connexion,
    `attempt_login`) pour observer le message réel avant d'écrire une assertion dessus, puis à
    nettoyer ce qu'il crée (Odoo, RPC delete — cf. `OdooConnector.attempt_form_submission`).
    ÉTEINT par défaut sur tout projet existant : soumettre un formulaire quelconque pourrait créer
    une vraie donnée, seul le porteur du projet sait si l'application configurée le tolère.

    Simple `ADD COLUMN` (pas de CHECK ajouté) : contrairement à la migration 44, aucune
    reconstruction de table n'est nécessaire ici.
    """
    if "calibration_writes_enabled" not in _column_names(conn, "project"):
        conn.execute(
            "ALTER TABLE project ADD COLUMN calibration_writes_enabled INTEGER NOT NULL DEFAULT 0")


def _migrate_1_project_module(conn: sqlite3.Connection) -> None:
    """Hiérarchie Projet → Module → Cas (§7) + séparation feature_slug / module_id.

    Amène une base d'avant la hiérarchie (colonne texte ``test_case.module``) à la cible :
    tables project/module, colonnes ``module_id`` + ``feature_slug`` sur test_case, backfill
    des cas existants sous un projet « Odoo », puis suppression de la colonne ``module``.
    Idempotent : sur une base déjà à la cible, chaque étape est ignorée. Voir décision 0004.
    """
    now = datetime.now(timezone.utc).isoformat()
    cols = _column_names(conn, "test_case")

    # 1. Colonnes ajoutées seulement si absentes (base neuve : déjà présentes via schema.sql).
    if "module_id" not in cols:
        conn.execute("ALTER TABLE test_case ADD COLUMN module_id INTEGER REFERENCES module(id)")
    if "feature_slug" not in cols:
        conn.execute("ALTER TABLE test_case ADD COLUMN feature_slug TEXT NOT NULL DEFAULT ''")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_case_module ON test_case(module_id)")

    # 2. Backfill : uniquement si l'ancienne colonne texte ``module`` existe encore.
    if "module" in cols:
        rows = conn.execute(
            "SELECT DISTINCT module FROM test_case WHERE module IS NOT NULL AND module <> ''"
        ).fetchall()
        if rows:
            project_id = _ensure_project(conn, "Odoo", now)
            for row in rows:
                slug = row["module"]
                module_id = _ensure_module(conn, project_id, _prettify(slug), now)
                conn.execute(
                    "UPDATE test_case SET module_id=?, feature_slug=? WHERE module=?",
                    (module_id, slug, slug),
                )
        # 3. Suppression de la colonne obsolète (double rôle éliminé — décision 0004).
        conn.execute("ALTER TABLE test_case DROP COLUMN module")


def _migrate_2_project_connector(conn: sqlite3.Connection) -> None:
    """Le connecteur remonte au PROJET, et quitte le cas de test (décision 0005).

    Ajoute connector_type + paramètres de connexion sur ``project`` ; renomme le projet
    par défaut « Odoo » (nom de connecteur, erroné) en « Portail Sapian » avec sa connexion
    reprise de la config ; supprime ``test_case.connector_type``. Idempotent.
    """
    pcols = _column_names(conn, "project")
    for col in ("connector_type", "base_url", "database", "username", "password"):
        if col not in pcols:
            default = "'odoo'" if col == "connector_type" else "''"
            conn.execute(f"ALTER TABLE project ADD COLUMN {col} TEXT NOT NULL DEFAULT {default}")

    # Reprise de la connexion existante (config env) pour le projet par défaut mal nommé.
    odoo = conn.execute("SELECT id FROM project WHERE name='Odoo'").fetchone()
    if odoo:
        conn.execute(
            "UPDATE project SET name='Portail Sapian', connector_type='odoo',"
            " base_url=?, database=?, username=?, password=? WHERE id=?",
            (config.ODOO_URL, config.ODOO_DB, config.ODOO_USER, config.ODOO_PASSWORD, odoo["id"]))

    if "connector_type" in _column_names(conn, "test_case"):
        conn.execute("ALTER TABLE test_case DROP COLUMN connector_type")


def _migrate_3_case_priority(conn: sqlite3.Connection) -> None:
    """Priorité de lecture sur le cas (décision 0006). Idempotent.

    Étiquette assumée (low|medium|high) : elle ne promet AUCUN ordre d'exécution — celui-ci
    est dicté par l'ordre des scénarios dans le .feature. On n'ajoute donc pas de colonne
    ``position`` décorative (l'ancien prototype en avait une, jamais alimentée).
    """
    if "priority" not in _column_names(conn, "test_case"):
        conn.execute("ALTER TABLE test_case ADD COLUMN priority TEXT NOT NULL DEFAULT 'medium'")


def _migrate_4_execution_field_fallbacks(conn: sqlite3.Connection) -> None:
    """Replis « libellé → nom technique » attachés à l'exécution (décision 0007, phase B+).
    Idempotent.

    Liste JSON des replis tracés par les helpers UI pendant le run. Attachée à l'EXÉCUTION (pas
    au scénario) : le repli doit rester lisible a posteriori, y compris sur un run vert, sinon
    un champ réellement renommé côté application serait absorbé sans que personne ne le voie.
    """
    if "field_fallbacks" not in _column_names(conn, "execution"):
        conn.execute("ALTER TABLE execution ADD COLUMN field_fallbacks TEXT NOT NULL DEFAULT ''")


def _migrate_5_unicite_noms(conn: sqlite3.Connection) -> None:
    """Unicité des noms : projet (global), module (par projet), cas (par module), et
    `feature_slug` (global). Idempotent (`IF NOT EXISTS`).

    Des INDEX plutôt qu'une contrainte de table : SQLite ne sait pas ajouter un `UNIQUE` par
    `ALTER TABLE`, et recréer les tables coûterait bien plus cher pour le même effet.

    ⚠️ `COLLATE NOCASE` ne replie que l'**ASCII** : « CAFÉ » et « Café » passeraient cet index.
    C'est pourquoi la garde applicative des repos (`_key`/`casefold`, qui gère l'Unicode) est
    la **première** ligne de défense — cet index est le filet de dernier recours, notamment
    contre une écriture directe en base.

    `feature_slug` : index **partiel** (`WHERE feature_slug != ''`). Le slug nomme le fichier
    `{slug}.feature` d'un répertoire commun — deux cas au même slug écriraient dans le MÊME
    fichier. Un slug vide ne produit aucun fichier, donc aucune collision : l'exclure évite de
    faire échouer des cas légitimement sans `.feature`.
    """
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_project_name"
                 " ON project(name COLLATE NOCASE)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_module_project_name"
                 " ON module(project_id, name COLLATE NOCASE)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_case_module_title"
                 " ON test_case(module_id, title COLLATE NOCASE)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_case_feature_slug"
                 " ON test_case(feature_slug) WHERE feature_slug != ''")


def _migrate_6_case_position(conn: sqlite3.Connection) -> None:
    """Ordre d'affichage manuel des cas dans leur module (décision 0009). Idempotent.

    ⚠️ **Amende la décision 0006/§2.4** (« pas de colonne `position` »). Ce que 0006 refusait :
    une position **décorative**, jamais alimentée, laissant croire à un ordre d'exécution — le
    `position` de l'ancien prototype. Celui-ci est **réellement honoré** par le tri
    (`ORDER BY position, id`) et ne promet **rien** sur l'exécution, qui reste dictée par l'ordre
    des scénarios dans le `.feature`. C'est ce qui le rend honnête, et distinct du précédent.

    **PAS de contrainte UNIQUE(module_id, position)** : un glissement décale N voisins, et un
    index unique ferait échouer les états intermédiaires (il faudrait des positions négatives
    temporaires ou un ordre d'UPDATE savant, pour aucun bénéfice). Les ex æquo sont départagés
    par `id` au tri — l'affichage reste donc déterministe, ce qui est le seul invariant qui
    compte ici.

    **Backfill par le tri EXISTANT** (priorité puis titre) : à la migration, rien ne bouge à
    l'écran. Une position à 0 partout aurait resorti la liste par `id` — un réordonnancement
    surprise que personne n'a demandé.
    """
    if "position" in _column_names(conn, "test_case"):
        return
    conn.execute("ALTER TABLE test_case ADD COLUMN position INTEGER NOT NULL DEFAULT 0")
    modules = [r["module_id"] for r in conn.execute("SELECT DISTINCT module_id FROM test_case"
                                                    " WHERE module_id IS NOT NULL")]
    for module_id in modules:
        rows = conn.execute(
            "SELECT id FROM test_case WHERE module_id=?"
            " ORDER BY CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,"
            " title COLLATE NOCASE, id", (module_id,))
        for index, row in enumerate(rows.fetchall()):
            conn.execute("UPDATE test_case SET position=? WHERE id=?", (index, row["id"]))


def _migrate_7_drop_report_paths(conn: sqlite3.Connection) -> None:
    """Supprime `execution.report_json_path` / `report_html_path` — colonnes MORTES. Idempotent.

    ⚠️ **Corrige un diagnostic faux** (« écart 4 »), le 3ᵉ de ce projet après 0002 et 0007. La
    note affirmait que `run_service._persist` ne les écrivait pas « alors que la CLI le fait » et
    que l'UI promettait donc un rapport absent (§4.6). **Les deux points étaient inexacts**,
    mesuré : la CLI ne les persiste pas non plus (son `finalize()` ne les passe pas), et le
    rapport d'un run API répond bien (200) — `report_service.build_report_for_execution` le
    **reconstruit depuis la base**, sans jamais toucher un fichier. Rien n'était promis qui ne
    fût tenu.

    Le vrai défaut était l'inverse : ces colonnes n'étaient **jamais alimentées** (ni CLI ni API)
    **ni jamais lues** (aucun lecteur dans tout le code ; l'API ne les expose même pas). Un champ
    mort — exactement le `position` décoratif que §2.4 dénonce, et la colonne `module` que 0004 a
    **supprimée plutôt que laissée inerte**. On supprime donc, au lieu d'écrire du code pour
    alimenter ce que personne ne lit.

    La CLI continue d'écrire ses fichiers dans `data/reports/` et d'en afficher le chemin : utile
    là où il n'y a pas de HTTP, et indépendant de ces colonnes.
    """
    colonnes = _column_names(conn, "execution")
    for nom in ("report_json_path", "report_html_path"):
        if nom in colonnes:
            conn.execute(f"ALTER TABLE execution DROP COLUMN {nom}")


def _migrate_8_verdict_humain(conn: sqlite3.Connection) -> None:
    """Arbitrage humain d'un diagnostic — COUCHE DISTINCTE (décision 0013). Idempotent.

    ⚠️ `defect_origin` (ce que la MACHINE a déduit) n'est JAMAIS réécrit. L'humain ne corrige pas
    le diagnostic, il le JUGE : sans cette séparation, on perdrait ce que la machine avait conclu
    — donc toute possibilité de mesurer si la taxonomie s'améliore ou dérive. C'est précisément
    la donnée qui manque pour l'audit de la taxonomie (backlog).

    Pourquoi ce chantier : mesuré sur données réelles, **aucun** diagnostic n'était jamais tranché
    (les 8 produits avaient `confirmed_by = NULL`). Un `pending_human` attendait une confirmation
    qui ne pouvait pas arriver ; un `not_required` était définitif et IRRÉVOCABLE, même faux.
    Or §4.4 dit « faux-positif acceptable », pas « faux-positif irréversible » : il l'est parce
    qu'un humain le corrige.

    `confirmed_by` / `confirmed_at` existent déjà (jamais alimentés) : on les réutilise.
    """
    colonnes = _column_names(conn, "repair_attempt")
    if "human_verdict" not in colonnes:
        # confirmed = la machine avait raison ; overturned = elle s'est trompée.
        # '' = pas encore tranché (les lignes existantes, qui ne l'ont jamais été).
        conn.execute("ALTER TABLE repair_attempt ADD COLUMN human_verdict TEXT NOT NULL DEFAULT ''")
    if "human_origin" not in colonnes:
        # L'origine RÉELLE selon l'humain, quand il infirme. Vide sinon.
        conn.execute("ALTER TABLE repair_attempt ADD COLUMN human_origin TEXT NOT NULL DEFAULT ''")
    if "human_comment" not in colonnes:
        # Le POURQUOI — la seule chose qui vaudra encore quelque chose dans six mois.
        conn.execute("ALTER TABLE repair_attempt ADD COLUMN human_comment TEXT NOT NULL DEFAULT ''")


def _migrate_9_repair_budget(conn: sqlite3.Connection) -> None:
    """Budget de réparation autorisé à l'approbation (décision 0014, option C). Idempotent.

    **Pourquoi le budget vit sur la RELECTURE et pas ailleurs.** Réparer exige d'exécuter ; or
    §4.3 impose le gate humain avant la première exécution d'une version générée par IA. Une
    boucle de réparation exécuterait donc du code IA non relu (option A, écartée), ou imposerait
    un gate par itération (option B, écartée : ce n'est plus une boucle, c'est un ping-pong).
    Option C retenue : **le gate autorise explicitement N tentatives**. Le garde-fou reste
    souverain — il n'est pas contourné, il est *consulté* et il *décide*.

    Défaut = `config.REPAIR_BUDGET_DEFAULT` (2). Les approbations EXISTANTES héritent de ce
    défaut, et c'est voulu : le défaut est la **politique** appliquée à toute approbation qui ne
    dit rien du budget — un relecteur qui veut interdire la réparation descend à 0 explicitement.
    Rétro-appliquer 0 aurait prétendu que ces humains avaient refusé, ce qu'ils n'ont pas fait.
    """
    if "repair_budget" in _column_names(conn, "review_decision"):
        return
    conn.execute(
        "ALTER TABLE review_decision ADD COLUMN repair_budget INTEGER NOT NULL DEFAULT "
        f"{int(config.REPAIR_BUDGET_DEFAULT)}")


def _migrate_10_step_text(conn: sqlite3.Connection) -> None:
    """Persiste le step en échec — pour AUDITER la classification (décision 0015). Idempotent.

    ⚠️ **Traçabilité, pas fonctionnalité.** Depuis `0015`, `step_text` **ne sert plus à classer**
    (il est écrit par l'agent : le lire revenait à juger l'agent sur son propre texte). Mais il
    n'était pas stocké du tout — `scenario_result` ne gardait que `scenario_name` — et **aucune
    classification passée n'était donc auditable**. Sans lui, on ne pourra jamais mesurer si
    `0015` a réellement amélioré les choses, ni détecter une dérive de la taxonomie.

    C'est aussi le contexte le plus utile à un humain qui lit un rapport : *quel step* a lâché.
    """
    if "step_text" not in _column_names(conn, "scenario_result"):
        conn.execute("ALTER TABLE scenario_result ADD COLUMN step_text TEXT NOT NULL DEFAULT ''")


def _migrate_11_execution_error(conn: sqlite3.Connection) -> None:
    """Raison d'une exécution PLANTÉE, à l'écran plutôt que dans les logs. Idempotent.

    ``_finalize_error`` recevait le message de l'exception et ne l'écrivait **nulle part** — un
    paramètre mort. L'écran affichait donc « erreur technique » sans le moindre pourquoi, et la
    seule trace vivait dans les logs du serveur. Or c'est exactement ce qu'un humain doit lire
    pour décider si le défaut vient du test, de l'outil, ou de l'application.
    """
    if "error_message" not in _column_names(conn, "execution"):
        conn.execute("ALTER TABLE execution ADD COLUMN error_message TEXT NOT NULL DEFAULT ''")


def _migrate_12_cost_case_id(conn: sqlite3.Connection) -> None:
    """Le coût appartient au CAS ; l'exécution n'en est qu'un contexte. Idempotent.

    ⚠️ **Sans cette colonne, le §9 est structurellement inmesurable sur le chemin de l'écran.**
    `cost_ledger` ne reliait un coût à un cas qu'à TRAVERS `execution` (`total_for_case_usd`
    fait `JOIN execution`). Or la génération par l'API se produit **avant toute exécution** :
    un cas est généré, relu, puis exécuté plus tard — voire jamais. Le coût de génération
    n'avait donc **aucune exécution où s'accrocher**, et il était simplement perdu.

    La CLI masquait le défaut : elle génère et exécute dans le même pipeline, donc elle avait une
    exécution sous la main. C'est pour ça que la seule ligne `generation` du ledger vient d'un run
    CLI — et que le poste le plus lourd du §9 (42 % sur le cas 1) était invisible sur le chemin
    que les utilisateurs empruntent réellement.

    `test_case_id` devient donc le lien de référence ; `execution_id` reste, mais **facultatif**
    et purement contextuel (quel run a provoqué cette dépense). Les deux coexistent : le rattacher
    à l'exécution reste utile pour une réparation, ça ne l'est pas pour une génération.

    **Reprise des lignes existantes** : on remplit `test_case_id` depuis l'exécution liée. Aucune
    donnée n'est perdue, aucun total ne bouge — les deux lignes réelles (génération + réparation
    du cas 1) sont rattachées au cas 1, qu'elles décrivaient déjà par ce détour.
    """
    if "test_case_id" not in _column_names(conn, "cost_ledger"):
        conn.execute("ALTER TABLE cost_ledger ADD COLUMN test_case_id INTEGER "
                     "REFERENCES test_case(id)")
    # Reprise : ce que le JOIN déduisait, on l'inscrit. Idempotent (WHERE … IS NULL).
    conn.execute(
        "UPDATE cost_ledger SET test_case_id = ("
        "  SELECT e.test_case_id FROM execution e WHERE e.id = cost_ledger.execution_id)"
        " WHERE test_case_id IS NULL AND execution_id IS NOT NULL")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cost_case ON cost_ledger(test_case_id)")


def _migrate_13_case_group(conn: sqlite3.Connection) -> None:
    """La situation testée devient un cas indépendant, regroupé sous une SPÉCIFICATION (2026-07-19,
    décision du porteur — rouvre 0006). Idempotent, gardé par introspection.

    On introduit `case_group` (le regroupement) et deux colonnes sur `test_case` : `group_id`
    (propriétaire, RENDU obligatoire une fois les groupes créés) et `angle` (étiquette libre).
    **Rien ne bouge en aval** : `test_case` reste l'unité versionnée/gatée/exécutée/facturée, donc
    aucune FK de `test_case_version`/`review_decision`/`execution`/`cost_ledger` n'est repointée.

    LEGACY ENVELOPPÉ 1:1 (choix du porteur) : chaque cas existant reçoit SA PROPRE spécification
    (un groupe par cas), `angle='legacy'`. On ne fusionne rien, on ne devine rien — les cas 9/10
    sont des artefacts de débogage, pas un référentiel à réorganiser. Historique intact.

    UNICITÉ : le titre de cas devient unique PAR GROUPE (plus par module) — deux spécifications
    peuvent chacune avoir un « Nominal ». On retire donc `uq_case_module_title`. Les groupes legacy
    étant à un seul cas, aucun conflit possible à la reprise.
    """
    cols = _column_names(conn, "test_case")
    if "group_id" not in cols:
        conn.execute("ALTER TABLE test_case ADD COLUMN group_id INTEGER REFERENCES case_group(id)")
    if "angle" not in cols:
        conn.execute("ALTER TABLE test_case ADD COLUMN angle TEXT NOT NULL DEFAULT ''")

    # La spec (le DOCUMENT) vit sur le groupe (source unique, 2026-07-19). Guard-add : une base où
    # `case_group` existe déjà sans ces colonnes (schema.sql l'a créée avant qu'on les ajoute).
    gcols = _column_names(conn, "case_group")
    if "spec_content" not in gcols:
        conn.execute("ALTER TABLE case_group ADD COLUMN spec_content TEXT NOT NULL DEFAULT ''")
    if "spec_hash" not in gcols:
        conn.execute("ALTER TABLE case_group ADD COLUMN spec_hash TEXT NOT NULL DEFAULT ''")

    # Enveloppe 1:1 : un groupe par cas encore orphelin (idempotent via WHERE group_id IS NULL).
    # ⚠️ `module_id IS NOT NULL` : une spécification a besoin d'un module (FK NOT NULL). Un cas
    # SANS module n'a pas de place dans la hiérarchie — on le laisse sans groupe, comme le fait
    # `CaseRepo.create`. C'est un cas de bord (hors arbre), pas le chemin de production.
    #
    # REMONTÉE DE LA SPEC LEGACY : on copie la spec de la version COURANTE du cas dans son groupe
    # (source établie, rien de perdu). `version.spec_content` subsiste (déprécié) jusqu'à l'étape 3.
    now = datetime.now(timezone.utc).isoformat()
    orphelins = conn.execute(
        "SELECT id, module_id, title FROM test_case"
        " WHERE group_id IS NULL AND module_id IS NOT NULL").fetchall()
    has_versions = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='test_case_version'").fetchone()
    for cas in orphelins:
        spec = conn.execute(
            "SELECT spec_content, spec_hash FROM test_case_version"
            " WHERE test_case_id=? ORDER BY id DESC LIMIT 1", (cas["id"],)).fetchone() \
            if has_versions else None
        spec_content = spec["spec_content"] if spec else ""
        spec_hash = spec["spec_hash"] if spec else ""
        cur = conn.execute(
            "INSERT INTO case_group (module_id, title, description, spec_content, spec_hash,"
            " position, created_at, updated_at) VALUES (?,?,?,?,?,0,?,?)",
            (cas["module_id"], cas["title"], "Spécification (cas existant, migration 13)",
             spec_content, spec_hash, now, now))
        conn.execute("UPDATE test_case SET group_id=?, angle='legacy' WHERE id=?",
                     (cur.lastrowid, cas["id"]))

    # Unicité : par groupe désormais. On retire l'ancien index par module s'il existe.
    conn.execute("DROP INDEX IF EXISTS uq_case_module_title")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_group_module_title"
                 " ON case_group(module_id, title COLLATE NOCASE)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_case_group_title"
                 " ON test_case(group_id, title COLLATE NOCASE)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_case_group ON test_case(group_id)")


def _migrate_14_champs_metier(conn: sqlite3.Connection) -> None:
    """Le contenu MÉTIER d'un cas devient une donnée de première classe, VERSIONNÉE avec le
    technique (décision `0022`, n°3 et n°10). Idempotent, gardé par introspection.

    ⚠️ **Jusqu'ici, préconditions / étapes / résultat attendu n'existaient PAS.** L'écran les
    dérivait du Gherkin à la volée, en provisoire — ce qui rangeait parfois une vérification
    technique dans « Étapes » (mesuré sur le cas 9 : *« le champ partner_id … n'est pas vide »*
    affiché comme une étape métier). Ils deviennent de vrais champs, éditables.

    **Une version = LE CAS ENTIER** : le métier est figé dans `test_case_version` en même temps
    que le Gherkin. C'est ce qui permet l'historique à diffs, et ce que le gate approuve (5.c).
    `test_case.title`/`angle` restent des COPIES courantes pour les listes — **la version fait
    foi** en cas de divergence (même règle que le raccourci de résultat).

    **Aucun remplissage automatique** (arbitrage du porteur, A.1) : les versions existantes
    gardent leurs champs métier VIDES. L'écran continue d'afficher la dérivation provisoire tant
    qu'ils le sont — on ne stocke pas du texte machine qui aurait ensuite l'air rédigé.

    `refs` (et non `references`, mot-clé SQL) et `estimate` vivent sur le CAS : ce sont des
    métadonnées qui ne changent pas ce que le test vérifie, les versionner gonflerait l'historique.
    """
    ccols = _column_names(conn, "test_case")
    # ⚠️ `angle` n'est repris QUE si le cas le porte encore — c'est-à-dire sur une base
    # réellement antérieure à la migration 26, qui l'a supprimé. Sans cette garde, rejouer la 14
    # sur une base moderne RESSUSCITE une colonne qu'une migration ultérieure a retirée, puis
    # échoue sur `tc.angle`. Une migration doit rester rejouable, y compris hors de son époque.
    ancien = "angle" in ccols
    vcols = _column_names(conn, "test_case_version")
    for col in ("title", "preconditions", "test_steps", "expected_result",
                *(("angle",) if ancien else ())):
        if col not in vcols:
            conn.execute(f"ALTER TABLE test_case_version ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")

    for col in ("refs", "estimate"):
        if col not in ccols:
            conn.execute(f"ALTER TABLE test_case ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")

    # Reprise MINIMALE et non inventée : le titre des versions existantes est celui du cas (on ne
    # le connaît pas autrement — aucune version n'a jamais porté de titre). Les champs de CONTENU
    # (préconditions/étapes/résultat) restent vides : les dériver ici reviendrait à fabriquer du
    # texte, ce que A.1 a explicitement écarté.
    conn.execute(
        "UPDATE test_case_version SET title = ("
        "  SELECT tc.title FROM test_case tc WHERE tc.id = test_case_version.test_case_id)"
        " WHERE title = ''")
    if ancien:
        conn.execute(
            "UPDATE test_case_version SET angle = ("
            "  SELECT tc.angle FROM test_case tc WHERE tc.id = test_case_version.test_case_id)"
            " WHERE angle = ''")


def _migrate_15_test_run(conn: sqlite3.Connection) -> None:
    """Le RUN — une campagne de N cas (décision `0022` n°8, incrément 1). Idempotent.

    Jusqu'ici, une `execution` était un run **mono-cas** : un cas s'exécutait seul. La cible : un
    `test_run` est une **campagne nommée**, une liste de cas à jouer ensemble ; le résultat d'un
    cas DANS un run est une `execution` rattachée (`run_id`). `run_id` NULL = les exécutions
    mono-cas de l'ancien modèle, conservées telles quelles (aucune donnée perdue).

    - `test_run.selection_mode` : `all` (VIVANT — les cas du projet, recalculés) ou `frozen`
      (FIGÉ — matérialisé dans `test_run_case`). Le filtrage dynamique est REPORTÉ (`0022` 8.a).
    - `test_run_case` : liaison par **id** (contrainte §7 — jamais de copie de cas).
    - `plan_id` : colonne simple (le conteneur `test_plan` viendra à l'incrément 2), sans FK dure
      pour ne pas dépendre d'une table encore absente.

    Index dans la MIGRATION, jamais dans `schema.sql` : `run_id` n'existe pas sur une base
    antérieure, l'indexer avant la migration ferait planter l'ouverture (leçon du bug d'index).
    """
    conn.execute(
        "CREATE TABLE IF NOT EXISTS test_run ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " project_id INTEGER NOT NULL,"
        " name TEXT NOT NULL,"
        " description TEXT NOT NULL DEFAULT '',"
        " refs TEXT NOT NULL DEFAULT '',"
        " selection_mode TEXT NOT NULL DEFAULT 'frozen'"
        "     CHECK (selection_mode IN ('all', 'frozen')),"
        " status TEXT NOT NULL DEFAULT 'draft'"
        "     CHECK (status IN ('draft', 'running', 'completed')),"
        " plan_id INTEGER,"
        " created_at TEXT NOT NULL,"
        " launched_at TEXT,"
        " completed_at TEXT,"
        " FOREIGN KEY (project_id) REFERENCES project(id))")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS test_run_case ("
        " run_id INTEGER NOT NULL,"
        " case_id INTEGER NOT NULL,"
        " PRIMARY KEY (run_id, case_id),"
        " FOREIGN KEY (run_id) REFERENCES test_run(id),"
        " FOREIGN KEY (case_id) REFERENCES test_case(id))")
    if "run_id" not in _column_names(conn, "execution"):
        conn.execute("ALTER TABLE execution ADD COLUMN run_id INTEGER")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_run_project ON test_run(project_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_runcase_run ON test_run_case(run_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_execution_run ON execution(run_id)")


def _migrate_16_run_archive(conn: sqlite3.Connection) -> None:
    """Archivage d'une campagne : un run clos passe en LECTURE SEULE (note fonctionnelle).

    `is_archived` et non un statut de plus : le cycle `draft/running/completed` dit OÙ EN EST
    l'exécution, l'archivage dit si on a le droit d'y toucher. Les fondre ferait qu'un run
    terminé serait automatiquement gelé — or on veut pouvoir relancer une campagne terminée.

    ⚠️ Archivage ≠ suppression (§2.10) : rien n'est effacé, tout reste consultable. Le SNAPSHOT
    des cas à la clôture (décision n°2 de la note) reste REPORTÉ — un cas modifié après coup
    s'affichera dans son état actuel, écart connu et assumé.
    """
    if "is_archived" not in _column_names(conn, "test_run"):
        conn.execute("ALTER TABLE test_run ADD COLUMN is_archived INTEGER NOT NULL DEFAULT 0")


def _migrate_17_specification_auto_enveloppe(conn: sqlite3.Connection) -> None:
    """Distinguer une ENVELOPPE AUTOMATIQUE d'une Spécification voulue par un humain.

    ⚠️ **Le problème que ça tranche.** `CaseRepo.create` auto-enveloppe un cas sans spécification
    dans un conteneur 1:1. Quand le cas est supprimé, l'enveloppe doit partir avec lui — sinon
    elle devient un fantôme qui **bloque toute regénération du même titre** (§2.9). Le banc de
    mesure y a buté **trois fois**.

    Jusqu'ici le seul critère disponible était « vide » (ni cas ni document). Il est **faux** : une
    Spécification que l'utilisateur vient de créer depuis l'écran est vide elle aussi, et la traiter
    comme un déchet la ferait **effacer en silence** au profit d'un homonyme. Vide ne veut pas dire
    jetable ; c'est la PROVENANCE qui décide.

    ⚠️ **Reprise de l'existant.** On ne peut pas reconstituer la provenance après coup. On marque
    donc comme enveloppes automatiques exactement les résidus **constatés aujourd'hui** — ni cas
    ni document — car dans une base vécue, une Spécification restée vide et sans document est le
    reliquat d'un cas supprimé. Toutes les autres sont déclarées délibérées : en cas de doute, on
    protège. Une Spécification conservée à tort est un désordre ; supprimée à tort, une perte.
    """
    if "auto_enveloppe" in _column_names(conn, "case_group"):
        return
    conn.execute("ALTER TABLE case_group ADD COLUMN auto_enveloppe INTEGER NOT NULL DEFAULT 0")
    conn.execute(
        "UPDATE case_group SET auto_enveloppe = 1"
        " WHERE TRIM(COALESCE(spec_content, '')) = ''"
        "   AND NOT EXISTS (SELECT 1 FROM test_case tc WHERE tc.group_id = case_group.id)")


def _migrate_18_corriger_provenance_enveloppes(conn: sqlite3.Connection) -> None:
    """Rattrape la reprise FAUTIVE de la migration 17 — qui a cassé le nettoyage des fantômes.

    ⚠️ **Ce que la 17 a raté, et ce que ça a coûté.** Sa reprise ne marquait comme enveloppes que
    les spécifications **déjà vides** au moment où elle tournait. Or celles qui portaient encore un
    cas ont été déclarées « délibérées » — définitivement. Quand leur cas a été supprimé ensuite,
    le nettoyage automatique ne s'est plus déclenché : **6 fantômes d'un coup**, et la campagne de
    mesure suivante bloquée sur 6 spécifications au lieu de 1. J'ai aggravé le défaut que je
    corrigeais.

    ⚠️ **La leçon** : une reprise de données ne doit pas classer sur l'état INSTANTANÉ quand elle
    peut classer sur une SIGNATURE stable. `CaseRepo.create` fabrique une enveloppe 1:1 en lui
    donnant **le titre exact de son cas** — c'est ça, la signature, et elle reste vraie que le cas
    existe encore ou non.

    Deux règles, toutes deux bornées par « aucun document » (un document reste un actif) :

    1. **signature d'enveloppe** — le groupe n'a que des cas portant son propre titre ;
    2. **déjà vide** — la règle de la 17, réappliquée pour rattraper ceux qu'elle a manqués depuis.

    La règle 2 peut se tromper sur une spécification qu'un humain aurait créée et laissée vide au
    moment précis où cette migration passe. Le risque est borné : elle ne s'exécute **qu'une fois**,
    et rien n'est supprimé ici — le groupe devient seulement *récupérable* si un homonyme réclame
    son titre. Un fantôme qui bloque toute regénération coûte plus cher que ce risque-là.
    """
    conn.execute(
        "UPDATE case_group SET auto_enveloppe = 1"
        " WHERE auto_enveloppe = 0"
        "   AND TRIM(COALESCE(spec_content, '')) = ''"
        "   AND ("
        "        NOT EXISTS (SELECT 1 FROM test_case tc WHERE tc.group_id = case_group.id)"
        "     OR NOT EXISTS (SELECT 1 FROM test_case tc WHERE tc.group_id = case_group.id"
        "                      AND tc.title <> case_group.title)"
        "   )")


def _migrate_19_verdict_donnee_invalide(conn: sqlite3.Connection) -> None:
    """Ajoute la valeur `donnee_invalide` aux CHECK de `functional_status` (4ᵉ verdict, §2bis).

    ⚠️ **Le défaut, trouvé par le RÉEL** (re-rejeu du 2026-07-23). Le 4ᵉ verdict a été branché dans
    toute la couche Python (`status.FUNC_DONNEE_INVALIDE`), mais **les CHECK de la base n'ont pas
    été migrés** : `scenario_result`/`execution`/`test_case.last_functional_status` n'acceptaient que
    les anciennes valeurs. Résultat mesuré : un cas correctement jugé `donnee_invalide` (la
    classification marchait) **plantait à la persistance** (`IntegrityError`) → retombait en
    `technical_error`. Mes tests de statut exerçaient la DÉRIVATION du verdict, jamais la
    PERSISTANCE de la nouvelle valeur — l'angle mort §8.8, une fois de plus.

    SQLite ne sait pas modifier un CHECK par `ALTER TABLE` : on RECONSTRUIT chaque table (procédé
    en 12 étapes), en réutilisant son propre `CREATE TABLE` (lu depuis `sqlite_master`) avec un
    remplacement CIBLÉ de la liste `functional_status` — pas de re-transcription manuelle, source
    d'erreur. `foreign_keys=OFF` pendant le remplacement (les 3 tables ont des FK entrantes) ;
    `foreign_key_check` après ; **atomique et idempotent par table** (une table déjà migrée, ou
    dont aucune liste n'est reconnue, est sautée → une reprise partielle se rattrape seule).
    """
    tables = ("execution", "scenario_result", "test_case")
    conn.commit()  # aucune transaction ouverte : PRAGMA foreign_keys est un no-op en transaction
    old_iso = conn.isolation_level
    conn.isolation_level = None  # autocommit : on gère BEGIN/COMMIT nous-mêmes (DDL+DML atomique)
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        for tbl in tables:
            row = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (tbl,)).fetchone()
            sql = row["sql"] if row else ""
            if not sql or "donnee_invalide" in sql:
                continue  # table absente, ou déjà migrée → idempotent
            new_sql = sql.replace(
                "'indetermine', 'not_evaluated')",
                "'indetermine', 'not_evaluated', 'donnee_invalide')",
            ).replace(
                "'non_conforme', 'indetermine')",  # scenario_result n'a pas 'not_evaluated'
                "'non_conforme', 'indetermine', 'donnee_invalide')",
            )
            if new_sql == sql:
                continue  # aucune liste functional_status reconnue : ne rien casser en silence
            tmp = f"{tbl}__migr19"
            create_tmp = new_sql.replace(f"CREATE TABLE {tbl}", f"CREATE TABLE {tmp}", 1)
            aux = conn.execute(
                "SELECT sql FROM sqlite_master WHERE tbl_name=? AND type IN ('index','trigger')"
                " AND sql IS NOT NULL AND name NOT LIKE 'sqlite_%'", (tbl,)).fetchall()
            conn.execute("BEGIN")
            try:
                conn.execute(f"DROP TABLE IF EXISTS {tmp}")
                conn.execute(create_tmp)
                conn.execute(f"INSERT INTO {tmp} SELECT * FROM {tbl}")  # colonnes identiques (seul le CHECK change)
                conn.execute(f"DROP TABLE {tbl}")
                conn.execute(f"ALTER TABLE {tmp} RENAME TO {tbl}")
                for a in aux:
                    conn.execute(a["sql"])  # index/triggers recréés (dropés avec l'ancienne table)
                violations = conn.execute("PRAGMA foreign_key_check").fetchall()
                if violations:
                    raise RuntimeError(f"FK cassées après reconstruction de {tbl} : {violations}")
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        conn.execute("PRAGMA foreign_keys = ON")
    finally:
        conn.isolation_level = old_iso


def _migrate_20_execution_cible(conn: sqlite3.Connection) -> None:
    """Inscrit dans l'exécution **contre quoi** le test a tourné (2026-07-24).

    ⚠️ **Un rapport qui ne dit pas quelle application il a jugée ne prouve rien.** La table
    `execution` ne portait aucune trace de la cible : deux campagnes vertes du même cas, l'une
    contre la recette et l'autre contre une instance de démo, étaient **indiscernables** dans
    l'historique. Sur un serveur partagé par plusieurs testeurs, c'est le genre d'ambiguïté qui
    ruine la confiance dans l'ensemble du référentiel.

    Trois colonnes, jamais le **mot de passe** : un secret n'a rien à faire dans une ligne
    d'historique qu'on lit, exporte et affiche.

    Les exécutions ANTÉRIEURES restent vides — et c'est volontaire : on ne **reconstitue** pas une
    cible qu'on n'a pas mesurée. Un champ vide se lit « on ne sait pas » ; une valeur devinée
    depuis la configuration d'aujourd'hui se lirait « c'était ça », ce qui serait un mensonge —
    exactement le motif « affiché ≠ réel » que le projet refuse partout (et la leçon de la
    migration 17, qui avait classé sur l'état instantané au lieu d'une signature stable).
    """
    cols = _column_names(conn, "execution")
    for nom in ("target_url", "target_database", "target_username"):
        if nom not in cols:
            conn.execute(f"ALTER TABLE execution ADD COLUMN {nom} TEXT NOT NULL DEFAULT ''")


def _migrate_21_chiffrer_secrets(conn: sqlite3.Connection) -> None:
    """Chiffre les mots de passe de connexion déjà stockés **en clair** (2026-07-24).

    Le secret d'un projet partait tel quel dans les sauvegardes et les copies de la base. La
    migration le reprend une fois pour toutes ; les écritures suivantes chiffrent à la source
    (`ProjectRepo`).

    **Idempotente par ligne** : une valeur déjà préfixée `enc:v1:` est sautée, une chaîne vide
    aussi (l'absence de secret n'est pas un secret à protéger). Rejouable sans dégât.

    ⚠️ **Ne fait pas échouer l'ouverture de la base.** Si la clé est indisponible (bibliothèque
    absente, répertoire non inscriptible), on **journalise bruyamment** et on laisse les valeurs
    en clair : refuser de démarrer rendrait l'outil inutilisable pour un défaut de configuration,
    alors que le mot de passe en clair est le comportement qu'on avait la veille. Le silence,
    lui, serait inacceptable — on croirait la base protégée sans qu'elle le soit.
    """
    from testpilot.store import secrets as secrets_mod

    lignes = conn.execute("SELECT id, password FROM project").fetchall()
    a_chiffrer = [(r["id"], r["password"]) for r in lignes
                  if r["password"] and not secrets_mod.est_chiffre(r["password"])]
    if not a_chiffrer:
        return
    try:
        for pid, clair in a_chiffrer:
            conn.execute("UPDATE project SET password=? WHERE id=?",
                         (secrets_mod.chiffrer(clair), pid))
        logger.info("[migration 21] %s secret(s) de connexion chiffré(s) au repos", len(a_chiffrer))
    except Exception:
        logger.critical(
            "[migration 21] les secrets de connexion N'ONT PAS PU être chiffrés : ils restent EN "
            "CLAIR dans la base. Vérifiez `cryptography` et l'accès en écriture au répertoire de "
            "données, puis rouvrez la base.", exc_info=True)


def _migrate_22_execution_artefacts(conn: sqlite3.Connection) -> None:
    """Où sont rangés les ARTEFACTS BRUTS d'une exécution (2026-07-24).

    Le chemin est stocké plutôt que déduit de l'id : le répertoire de données est configurable
    (`TESTPILOT_DATA_DIR`), et une base déplacée entre deux machines ne doit pas se mettre à
    désigner des dossiers qui n'ont jamais existé. Vide = **aucun artefact conservé** — le cas de
    toutes les exécutions antérieures, et le seul honnête : on n'invente pas une trace qu'on n'a
    pas gardée.
    """
    if "artifacts_path" not in _column_names(conn, "execution"):
        conn.execute("ALTER TABLE execution ADD COLUMN artifacts_path TEXT NOT NULL DEFAULT ''")


def _migrate_23_suppression_douce(conn: sqlite3.Connection) -> None:
    """La suppression cesse de DÉTRUIRE (2026-07-24) — §7 du brief enfin tenu.

    Le §7 interdit qu'une purge soit une « suppression sèche » : tout nettoyage doit être précédé
    d'une sauvegarde récupérable. Or supprimer un projet exécutait **douze `DELETE FROM` en
    cascade** — projet, modules, spécifications, cas, versions, relectures, exécutions, résultats,
    réparations, coûts. Un clic, et des mois d'historique partaient sans retour. C'était le seul
    endroit du produit où son propre principe était violé.

    Quatre tables reçoivent `deleted_at` / `deleted_by` : les CONTENEURS et les cas. Les versions,
    exécutions et coûts n'en ont pas besoin — ils appartiennent à un cas, et masquer le cas les
    masque avec lui. Leur en donner un créerait deux façons d'être supprimé pour la même chose.

    `deleted_by` est le nom déclaré à la connexion (lot 2) : une signature, pas une identité
    vérifiée. Sur un serveur partagé, savoir QUI a supprimé vaut mieux que rien.

    Vide = vivant. On n'utilise pas NULL : `WHERE deleted_at = ''` se lit et s'indexe, là où
    `IS NULL` s'oublie plus facilement dans une condition composée.
    """
    for table in ("project", "module", "case_group", "test_case"):
        cols = _column_names(conn, table)
        if "deleted_at" not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN deleted_at TEXT NOT NULL DEFAULT ''")
        if "deleted_by" not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN deleted_by TEXT NOT NULL DEFAULT ''")


def _migrate_24_unicite_parmi_les_vivants(conn: sqlite3.Connection) -> None:
    """Les index UNIQUE cessent de compter les elements a la corbeille (2026-07-24).

    ⚠️ **Trouve par un test, pas a la relecture.** La suppression douce filtrait bien cote
    Python, mais les index UNIQUE de la base, eux, voyaient toujours les lignes supprimees : un
    nom restait pris par un module que plus personne ne voit. L'utilisateur butait sur « nom deja
    utilise » sans aucun moyen de comprendre pourquoi — le pire genre de blocage.

    SQLite gere les index PARTIELS : l'unicite ne s'applique qu'aux lignes vivantes. Deux modules
    « Facturation » peuvent donc coexister si l'un est a la corbeille — et si on restaure celui-ci
    alors qu'un homonyme vivant existe, l'index refusera la restauration. C'est le bon
    comportement : mieux vaut un refus explicite qu'un doublon silencieux dans l'arbre.
    """
    partiels = [
        ("uq_project_name", "project(name COLLATE NOCASE)"),
        ("uq_module_project_name", "module(project_id, name COLLATE NOCASE)"),
        ("uq_group_module_title", "case_group(module_id, title COLLATE NOCASE)"),
        ("uq_case_group_title", "test_case(group_id, title COLLATE NOCASE)"),
    ]
    for nom, colonnes in partiels:
        conn.execute(f"DROP INDEX IF EXISTS {nom}")
        conn.execute(f"CREATE UNIQUE INDEX {nom} ON {colonnes} WHERE deleted_at = ''")
    # Le slug technique suit la meme regle (il portait deja une condition partielle).
    conn.execute("DROP INDEX IF EXISTS uq_case_feature_slug")
    conn.execute("CREATE UNIQUE INDEX uq_case_feature_slug ON test_case(feature_slug)"
                 " WHERE feature_slug != '' AND deleted_at = ''")


def _sql_sans_colonne(create_sql: str, colonne: str) -> str:
    """Retire d'un `CREATE TABLE` la DÉFINITION d'une colonne — sa contrainte comprise.

    ⚠️ **Pourquoi un parcours de caractères et pas une expression régulière.** La définition à
    retirer se termine par une virgule, mais elle en CONTIENT (`CHECK (x IN ('a', 'b'))`). Une
    regex non parenthésée couperait à la première virgule venue et produirait un `CREATE TABLE`
    invalide — sur une reconstruction de table, donc au pire moment possible. On compte donc les
    parenthèses et on coupe à la première virgule de profondeur 0.

    Rend le SQL **inchangé** si la colonne n'est pas trouvée comme début de définition : mieux
    vaut une migration qui n'a rien fait (l'appelant le détecte et le dit) qu'une table amputée
    au hasard.
    """
    debut = None
    for m in re.finditer(rf"\b{re.escape(colonne)}\b", create_sql):
        avant = create_sql[:m.start()].rstrip()
        # Une DÉFINITION commence juste après la parenthèse ouvrante ou une virgule ; toute autre
        # occurrence du nom (dans un CHECK, un commentaire…) n'est pas un début de colonne.
        if avant.endswith("(") or avant.endswith(","):
            debut = m.start()
            break
    if debut is None:
        return create_sql

    profondeur, i = 0, debut
    while i < len(create_sql):
        c = create_sql[i]
        if c == "(":
            profondeur += 1
        elif c == ")":
            if profondeur == 0:
                break          # dernière colonne de la table : la définition finit ici
            profondeur -= 1
        elif c == "," and profondeur == 0:
            i += 1             # on emporte la virgule de séparation avec la définition
            break
        i += 1
    return create_sql[:debut] + create_sql[i:]


def _reconstruire_sans_colonne(conn: sqlite3.Connection, table: str, colonne: str) -> None:
    """Supprime une colonne que `ALTER TABLE DROP COLUMN` REFUSE (elle porte un `CHECK`).

    Même procédé qu'à la migration 19 (reconstruction en 12 étapes), avec deux différences :
    la table cible est dérivée par `_sql_sans_colonne` plutôt que par un remplacement de texte,
    et la recopie NOMME ses colonnes — les deux tables n'ont plus la même forme, un
    `INSERT … SELECT *` insérerait tout décalé d'une colonne, en silence.

    Idempotent : une table dont la colonne est déjà partie n'est pas touchée.

    ⚠️ Ne lève pas si la définition n'est pas reconnue : une colonne survivante avec sa valeur
    par défaut ne casse aucune écriture, alors qu'une exception ici empêcherait d'OUVRIR la base.
    On journalise bruyamment — même arbitrage qu'à la migration 21.
    """
    if colonne not in _column_names(conn, table):
        return
    row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                       (table,)).fetchone()
    sql = row["sql"] if row else ""
    nouveau = _sql_sans_colonne(sql, colonne) if sql else ""
    if not sql or nouveau == sql:
        logger.critical("[migration 25] impossible de retirer %s.%s : définition non reconnue dans"
                        " le schéma stocké. La colonne SUBSISTE (sans effet fonctionnel).",
                        table, colonne)
        return

    colonnes = [c for c in _colonnes_ordonnees(conn, table) if c != colonne]
    liste = ", ".join(colonnes)
    tmp = f"{table}__migr25"
    # ⚠️ Le nom peut être ENTRE GUILLEMETS dans le schéma stocké — c'est le cas de toute table
    # déjà reconstruite une fois : `ALTER TABLE … RENAME TO x` réécrit `CREATE TABLE "x"`. Un
    # simple `replace("CREATE TABLE test_case", …)` ne matche alors PAS, la table temporaire garde
    # le nom d'origine, et la migration meurt sur « table already exists ». Trouvé en rejouant la
    # migration sur une COPIE de la vraie base — la base synthétique du test, elle, n'était jamais
    # passée par une reconstruction, donc ne portait pas de guillemets.
    create_tmp, remplace = re.subn(
        rf'^(\s*CREATE\s+TABLE\s+)("?){re.escape(table)}\2',
        lambda m: f"{m.group(1)}{tmp}", nouveau, count=1, flags=re.IGNORECASE)
    if not remplace:
        logger.critical("[migration 25] en-tête CREATE TABLE de %s non reconnue : la colonne %s "
                        "SUBSISTE (sans effet fonctionnel).", table, colonne)
        return
    aux = conn.execute(
        "SELECT sql FROM sqlite_master WHERE tbl_name=? AND type IN ('index','trigger')"
        " AND sql IS NOT NULL AND name NOT LIKE 'sqlite_%'", (table,)).fetchall()

    conn.commit()  # aucune transaction ouverte : PRAGMA foreign_keys est un no-op en transaction
    old_iso = conn.isolation_level
    conn.isolation_level = None  # autocommit : on gère BEGIN/COMMIT nous-mêmes (DDL+DML atomique)
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("BEGIN")
        try:
            conn.execute(f"DROP TABLE IF EXISTS {tmp}")
            conn.execute(create_tmp)
            conn.execute(f"INSERT INTO {tmp} ({liste}) SELECT {liste} FROM {table}")
            conn.execute(f"DROP TABLE {table}")
            conn.execute(f"ALTER TABLE {tmp} RENAME TO {table}")
            for a in aux:
                conn.execute(a["sql"])  # index/triggers recréés (dropés avec l'ancienne table)
            violations = conn.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise RuntimeError(f"FK cassées après reconstruction de {table} : {violations}")
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        conn.execute("PRAGMA foreign_keys = ON")
    finally:
        conn.isolation_level = old_iso


def _migrate_25_resultats_et_cycle_de_vie(conn: sqlite3.Connection) -> None:
    """L'exécution MANUELLE entre dans le modèle, et le cas gagne un cycle de vie (2026-08-04).

    ⚠️ **Le registre `test_result` porte la promesse du produit dans la BASE, pas dans le code.**
    Jusqu'ici, « quel est le résultat du cas C dans la campagne R ? » se répondait en cherchant la
    dernière `execution` rattachée — donc un résultat ne pouvait exister que si une machine avait
    tourné. Un humain qui teste à la main n'avait aucune place où écrire. Le registre lui en donne
    une, avec `source` **STOCKÉE** (`executed` / `declared`) et jamais déduite, et un `CHECK` qui
    rend un déclaré déguisé en exécuté **impossible à insérer** : l'invariant « on sait toujours
    d'où vient un statut » cesse d'être une convention que le code doit respecter.

    **Pourquoi une table et non des colonnes sur `execution`** (l'alternative évidente, écartée) :
    `execution.version_id` est `NOT NULL` avec FK, or un cas non automatisable — le cas d'usage
    central du manuel — n'a AUCUNE version ; et `ExecutionRepo.quality_summary` mesure la santé de
    la génération en comptant les `execution`, que des déclarations humaines fausseraient.

    **`run_case_assignment` est une table dédiée** et non une colonne sur `test_run_case` : en
    `selection_mode='all'` cette liaison est VIDE (la sélection est vivante), et y écrire une
    assignation gonflerait `frozen_count` — donc le nombre de cas affiché de la campagne.

    **Les trois raccourcis `last_*` sur `test_case`** : sans eux, un cas testé UNIQUEMENT à la main
    resterait « Non testé » dans les listes, qui lisent `last_execution_status`. Un statut qui ment
    — exactement ce que le produit combat. La vérité par campagne reste dans `test_result` ; ces
    colonnes ne sont qu'un raccourci global, et c'est assumé.

    **`validation_status` est SUPPRIMÉ** (reconstruction de table : il porte un `CHECK`). Il était
    dérivé des exécutions et non éditable — pas un cycle de vie de document. `etat` le remplace,
    librement modifiable. Vérifié avant d'écrire cette migration : il ne gate RIEN (le seul gate
    d'exécution est `review_decision`, lu par `review_gate.evaluate_gate`).

    ⚠️ **`test_case_version.spec_content` n'est PAS supprimé ici**, contrairement au plan de
    reprise : la génération et la réparation l'écrivent et le lisent encore. Le retirer avant de
    les avoir recâblées sur `case_group.spec_content` laisserait le dépôt rouge — la dette est
    soldée avec la génération multi-cas, qui est justement le chantier qui recâble ces appelants.

    Idempotente de bout en bout (introspection + `IF NOT EXISTS` + `NOT EXISTS` sur la reprise).
    """
    # La liste des statuts déclarables est GÉNÉRÉE depuis la règle Python, jamais retapée : c'est
    # exactement le défaut de la migration 19 (un CHECK oublié pendant que le code évoluait) qu'on
    # refuse de rejouer. Import local, comme à la migration 21 : `db` ne dépend pas de `verdict`.
    # (`STATUTS_MANUELS` s'appelait `STATUTS_DECLARABLES` le jour où cette migration a été écrite.
    #  Le symbole Python a été renommé le 2026-08-04 ; la liste de valeurs, elle, est la même —
    #  cette migration continue donc de produire EXACTEMENT le schéma qu'elle a déjà produit.)
    from testpilot.verdict.status import STATUTS_MANUELS

    declarables = ", ".join(f"'{s}'" for s in STATUTS_MANUELS)

    # ── Le registre des résultats ────────────────────────────────────────────
    conn.execute(
        "CREATE TABLE IF NOT EXISTS test_result ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " run_id INTEGER NOT NULL,"
        " case_id INTEGER NOT NULL,"
        # STOCKÉE, jamais déduite : c'est la colonne qui empêche le produit de mentir.
        " source TEXT NOT NULL CHECK (source IN ('executed', 'declared')),"
        # Exécuté : les DEUX AXES se lisent par jointure, on ne les recopie pas (une copie
        # divergerait ; et un axe recopié sur un résultat déclaré serait une mesure inventée).
        " execution_id INTEGER,"
        f" declared_status TEXT NOT NULL DEFAULT ''"
        f"     CHECK (declared_status IN ('', {declarables})),"
        " comment TEXT NOT NULL DEFAULT '',"
        " created_by TEXT NOT NULL DEFAULT '',"
        " attachments_path TEXT NOT NULL DEFAULT '',"
        " created_at TEXT NOT NULL,"
        # ⚠️ LE CHECK QUI PORTE LA PROMESSE : un exécuté a une exécution et aucun statut déclaré ;
        # un déclaré a un statut et aucune exécution. Les deux moitiés sont exclusives, en base.
        " CHECK ((source = 'executed' AND execution_id IS NOT NULL AND declared_status = '')"
        "     OR (source = 'declared' AND execution_id IS NULL AND declared_status <> '')),"
        " FOREIGN KEY (run_id) REFERENCES test_run(id),"
        " FOREIGN KEY (case_id) REFERENCES test_case(id),"
        " FOREIGN KEY (execution_id) REFERENCES execution(id))")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_result_run_case ON test_result(run_id, case_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_result_case ON test_result(case_id)")
    # Index unique PARTIEL : une exécution donne au plus UNE ligne de registre. C'est ce qui rend
    # la reprise ci-dessous rejouable sans doublon, même interrompue en plein milieu.
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_result_execution"
                 " ON test_result(execution_id) WHERE execution_id IS NOT NULL")

    # ── À qui un cas est CONFIÉ dans une campagne ────────────────────────────
    # `assigned_to` est du TEXTE LIBRE : testpilot n'a aucune notion de compte utilisateur, et
    # inventer une table d'utilisateurs pour ce seul champ promettrait une identité qu'on ne
    # vérifie pas (même raison que `deleted_by`, une signature déclarée).
    conn.execute(
        "CREATE TABLE IF NOT EXISTS run_case_assignment ("
        " run_id INTEGER NOT NULL,"
        " case_id INTEGER NOT NULL,"
        " assigned_to TEXT NOT NULL DEFAULT '',"
        " assigned_by TEXT NOT NULL DEFAULT '',"
        " assigned_at TEXT NOT NULL,"
        " PRIMARY KEY (run_id, case_id),"
        " FOREIGN KEY (run_id) REFERENCES test_run(id),"
        " FOREIGN KEY (case_id) REFERENCES test_case(id))")

    # ── Pièces jointes d'un résultat ─────────────────────────────────────────
    # `stored_name` (le nom SUR LE DISQUE) est distinct de `filename` (le nom de l'utilisateur) :
    # le téléchargement se fera par id numérique et lira `stored_name` en base, pour qu'aucune
    # chaîne venue du client ne touche jamais un chemin de fichier.
    conn.execute(
        "CREATE TABLE IF NOT EXISTS result_attachment ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " result_id INTEGER NOT NULL,"
        " filename TEXT NOT NULL,"
        " stored_name TEXT NOT NULL,"
        " content_type TEXT NOT NULL DEFAULT '',"
        " size_bytes INTEGER NOT NULL DEFAULT 0,"
        " created_at TEXT NOT NULL,"
        " FOREIGN KEY (result_id) REFERENCES test_result(id))")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_attachment_result"
                 " ON result_attachment(result_id)")

    # ── Réglages d'instance ──────────────────────────────────────────────────
    # Table volontairement générique, mais `SettingRepo` REFUSERA toute clé absente de son
    # `CLES_CONNUES` (même discipline que `erreurs.CATALOGUE`) : sans cette garde, une table
    # clé/valeur devient un dépotoir en six mois, et plus personne ne sait ce qui est lu.
    conn.execute(
        "CREATE TABLE IF NOT EXISTS app_setting ("
        " key TEXT PRIMARY KEY,"
        " value TEXT NOT NULL DEFAULT '',"
        " updated_at TEXT NOT NULL,"
        " updated_by TEXT NOT NULL DEFAULT '')")

    # ── Le cas : Type, État, et le raccourci du dernier résultat ─────────────
    # `type` et `etat` sont du TEXTE LIBRE SANS CHECK (précédent : `angle`) — un administrateur
    # pourra ajouter une valeur sans migration. Défauts : `fonctionnel` et `new`.
    ccols = _column_names(conn, "test_case")
    for nom, defaut in (("type", "'fonctionnel'"),
                        ("etat", "'new'"),
                        ("last_declared_status", "''"),
                        ("last_result_source", "''"),
                        ("last_result_at", "''")):
        if nom not in ccols:
            conn.execute(f"ALTER TABLE test_case ADD COLUMN {nom} TEXT NOT NULL DEFAULT {defaut}")

    _reconstruire_sans_colonne(conn, "test_case", "validation_status")

    # ── Reprise : chaque exécution DE CAMPAGNE devient une ligne de registre ──
    # ⚠️ `ORDER BY e.id` n'est pas décoratif : l'ordre des lignes PORTE le « dernier résultat ».
    # Insérées dans le désordre, elles inverseraient des verdicts sur des campagnes existantes.
    # `created_by` reste VIDE : ces exécutions précèdent le réglage du compte de service, et y
    # écrire le nom du jour prétendrait mesurer ce qu'on n'a pas mesuré (leçon de la migration 20).
    #
    # ⚠️ Les deux `EXISTS` ne sont pas de la prudence décorative : la vraie base porte une
    # exécution rattachée à une campagne DÉTRUITE (`run_id` orphelin, run purgé depuis). Sans
    # eux, la reprise insérait une ligne violant la clé étrangère — et l'ouverture de la base
    # échouait. Une exécution dont la campagne n'existe plus ne peut pas répondre à « résultat du
    # cas C dans la campagne R » : on la laisse hors du registre, elle reste dans `execution`.
    #
    # ⚠️ **`source` absente = la table a DÉJÀ été convertie par la migration 27**, qui l'a
    # renommée `mode`. On ne rejoue alors pas la reprise : elle a eu lieu, dans l'ancien
    # vocabulaire, et ses lignes ont été converties. Ce garde-fou ne change RIEN à ce que cette
    # migration produit sur une base pré-25 — il ne fait qu'éviter qu'elle plante en repassant sur
    # une base déjà arrivée plus loin (ce que font les tests des migrations antérieures, en
    # ramenant `user_version` en arrière sur une base moderne).
    if "source" in _column_names(conn, "test_result"):
        conn.execute(
            "INSERT INTO test_result (run_id, case_id, source, execution_id, declared_status,"
            " comment, created_by, attachments_path, created_at)"
            " SELECT e.run_id, e.test_case_id, 'executed', e.id, '', '', '', '', e.started_at"
            " FROM execution e"
            " WHERE e.run_id IS NOT NULL"
            "   AND EXISTS (SELECT 1 FROM test_run r WHERE r.id = e.run_id)"
            "   AND EXISTS (SELECT 1 FROM test_case c WHERE c.id = e.test_case_id)"
            "   AND NOT EXISTS (SELECT 1 FROM test_result tr WHERE tr.execution_id = e.id)"
            " ORDER BY e.id")

    # Un cas qui porte déjà un dernier résultat l'a forcément reçu d'une EXÉCUTION (rien d'autre
    # ne savait en écrire un avant aujourd'hui). On l'inscrit — sinon l'écran afficherait une
    # provenance vide sur tout l'historique, et laisserait croire que la question ne se posait pas.
    conn.execute(
        "UPDATE test_case SET last_result_source = 'executed', last_result_at = last_executed_at"
        " WHERE last_result_source = ''"
        "   AND last_executed_at IS NOT NULL AND last_executed_at <> ''")


def _migrate_26_retrait_de_l_angle(conn: sqlite3.Connection) -> None:
    """`angle` quitte le modèle (2026-08-04, décision du porteur) — **TestRail n'a pas ce champ**.

    L'angle (nominal / erreur / limite / autre) était une invention de TestPilot, arrêtée le
    2026-07-19 pour distinguer plusieurs cas nés d'une même spécification. Le cap produit étant la
    **parité TestRail**, un champ propriétaire de plus est une divergence qu'il faudrait expliquer
    à chaque utilisateur — et que rien ne réclamait : `type` (Fonctionnel / Non fonctionnel) et le
    **titre** portent déjà ce que l'angle prétendait dire.

    ⚠️ **Ce que ça coûte, et pourquoi c'est acceptable ici.** L'angle était le seul levier par
    lequel la génération pouvait demander autre chose qu'un cas nominal (`propose_metier(…,
    angle=…)`). Mais la génération ne produit **qu'un seul cas** aujourd'hui — le manque n°2 du
    chantier en cours — et le mécanisme qui la multipliera est le découpage en **user stories**,
    qui ne s'appuie pas sur l'angle. On ne retire donc pas une capacité : on retire une étiquette
    qui décrivait une capacité inexistante. (Vérifié sur la vraie base au moment du retrait : les
    8 cas portaient tous `nominal` — aucune information réelle n'y était rangée.)

    `ALTER TABLE … DROP COLUMN` suffit : `angle` ne porte ni `CHECK` ni index, contrairement à
    `validation_status` (migration 25) qui exigeait une reconstruction de table.
    """
    for table in ("test_case", "test_case_version"):
        if "angle" in _column_names(conn, table):
            conn.execute(f"ALTER TABLE {table} DROP COLUMN angle")


def _migrate_27_mode_d_execution(conn: sqlite3.Connection) -> None:
    """« provenance : exécuté / déclaré » devient le **MODE D'EXÉCUTION** : automatique / manuelle
    — et le mode remonte au niveau de la CAMPAGNE (2026-08-04, décision du porteur).

    ⚠️ **Ce n'est pas un renommage cosmétique.** « Déclaré » sous-entendait une affirmation sans
    preuve, une case cochée. Or un test joué à la main EST une exécution : un humain a suivi les
    étapes, contre la vraie application. Le mot faisait passer pour un aveu de faiblesse ce qui est
    **une autre façon d'exécuter** — et poussait à cacher la moitié manuelle du travail plutôt qu'à
    la tenir. `manuelle` dit ce qui s'est réellement passé.

    ⚠️ **Le mode monte sur `test_run`.** On ne le choisit plus résultat par résultat mais en créant
    la campagne, et c'est ce qui rend les écrans lisibles : une campagne automatique se **lance**
    (aucun bouton de saisie), une campagne manuelle se **saisit** (aucun bouton Lancer). Sans ce
    choix en amont, chaque ligne portait les deux gestes et aucun ne s'imposait.

    ⚠️ **Le `CHECK` XOR survit au renommage** — c'est la seule chose qui compte vraiment ici : un
    résultat manuel ne peut pas se réclamer d'une exécution machine, ni un automatique se passer
    d'exécution. Pas une convention que le code respecte : un refus d'insertion.

    Et un TRIGGER nouveau porte l'invariant que le mode fait naître : **le mode d'un résultat
    concorde avec celui de sa campagne**. Un `CHECK` ne sait pas lire une autre table ; sans le
    trigger, cette règle ne vivrait que dans les routes — donc nulle part le jour où un script
    écrit en base. Il gouverne ce qu'on ÉCRIT désormais, il ne rejuge pas l'histoire : une vieille
    campagne mixte reste telle quelle, mais ne peut plus recevoir de résultat du mauvais mode.

    **La reprise.** Les campagnes existantes ont toutes été jouées par la machine → `automatique`.
    Sauf celles dont TOUS les résultats sont des saisies humaines : les dire automatiques rendrait
    leur historique manuel impossible à continuer, l'écran ne proposant plus la saisie.

    `test_result` est RECONSTRUITE (ses deux colonnes portent des `CHECK`, que SQLite ne sait pas
    modifier autrement) ; `test_case` se contente d'un `RENAME COLUMN` — ses raccourcis n'ont
    aucun `CHECK`. Idempotente : chaque étape s'introspecte avant d'agir.
    """
    from testpilot.verdict.status import MODE_AUTOMATIQUE, MODE_MANUELLE, STATUTS_MANUELS

    manuels = ", ".join(f"'{s}'" for s in STATUTS_MANUELS)
    modes = ", ".join(f"'{m}'" for m in (MODE_MANUELLE, MODE_AUTOMATIQUE))

    # ── La campagne porte son mode ───────────────────────────────────────────
    # `ADD COLUMN … CHECK(…)` applique bien la contrainte (vérifié sur SQLite 3.35.5) ; c'est
    # seulement CHANGER un CHECK existant qui exige une reconstruction — cf. `test_result`.
    if "mode" not in _column_names(conn, "test_run"):
        conn.execute(f"ALTER TABLE test_run ADD COLUMN mode TEXT NOT NULL"
                     f" DEFAULT '{MODE_AUTOMATIQUE}' CHECK (mode IN ({modes}))")

    # ── Le registre : `source` devient `mode`, `declared_status` devient `statut_manuel` ─────
    if "mode" not in _column_names(conn, "test_result"):
        _reconstruire_test_result_en_mode(conn, manuels, modes)

    # Le trigger vient APRÈS la reconstruction (un `DROP TABLE` emporte ses triggers).
    conn.execute(
        "CREATE TRIGGER IF NOT EXISTS trg_resultat_suit_le_mode_de_sa_campagne"
        " BEFORE INSERT ON test_result FOR EACH ROW"
        " WHEN NEW.mode <> (SELECT mode FROM test_run WHERE id = NEW.run_id)"
        " BEGIN SELECT RAISE(ABORT,"
        " 'le mode du résultat ne concorde pas avec celui de sa campagne'); END")

    # ── Les raccourcis du cas suivent le même vocabulaire ────────────────────
    for ancien, nouveau in (("last_result_source", "last_result_mode"),
                            ("last_declared_status", "last_statut_manuel")):
        cols = _column_names(conn, "test_case")
        if ancien not in cols:
            continue
        if nouveau in cols:
            # Base NEUVE : `schema.sql` a créé la colonne cible, puis la migration 25 — qui ne
            # connaît que l'ancien nom — a rajouté l'ancienne à côté. Les deux sont vides (aucun
            # cas n'existe encore) : on retire l'intruse plutôt que d'inventer une fusion.
            conn.execute(f"ALTER TABLE test_case DROP COLUMN {ancien}")
        else:
            conn.execute(f"ALTER TABLE test_case RENAME COLUMN {ancien} TO {nouveau}")
    conn.execute(f"UPDATE test_case SET last_result_mode = '{MODE_AUTOMATIQUE}'"
                 f" WHERE last_result_mode = 'executed'")
    conn.execute(f"UPDATE test_case SET last_result_mode = '{MODE_MANUELLE}'"
                 f" WHERE last_result_mode = 'declared'")

    # ── Le mode des campagnes existantes ─────────────────────────────────────
    # Toutes automatiques (elles ont été jouées par la machine) SAUF celles dont aucun résultat ne
    # vient d'une exécution : leur histoire est entièrement manuelle, la dire automatique
    # empêcherait de la continuer.
    conn.execute(
        f"UPDATE test_run SET mode = '{MODE_MANUELLE}' WHERE id IN ("
        f" SELECT run_id FROM test_result GROUP BY run_id"
        f" HAVING SUM(mode = '{MODE_AUTOMATIQUE}') = 0)")


def _reconstruire_test_result_en_mode(conn: sqlite3.Connection, manuels: str, modes: str) -> None:
    """Reconstruit `test_result` avec le vocabulaire du mode d'exécution.

    ⚠️ La recopie **NOMME ses colonnes** (leçon de la migration 25) : les deux tables n'ont ni les
    mêmes noms ni le même ordre implicite, et un `INSERT … SELECT *` décalerait tout d'un cran,
    en silence, sur la table qui porte les résultats du produit.
    """
    from testpilot.verdict.status import MODE_AUTOMATIQUE, MODE_MANUELLE

    create_tmp = (
        "CREATE TABLE test_result__migr27 ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " run_id INTEGER NOT NULL,"
        " case_id INTEGER NOT NULL,"
        # STOCKÉ, jamais déduit : c'est la colonne qui empêche le produit de mentir.
        f" mode TEXT NOT NULL CHECK (mode IN ({modes})),"
        # Automatique : les DEUX AXES se lisent par jointure, on ne les recopie pas (une copie
        # divergerait ; et un axe recopié sur un résultat manuel serait une mesure inventée).
        " execution_id INTEGER,"
        f" statut_manuel TEXT NOT NULL DEFAULT ''"
        f"     CHECK (statut_manuel IN ('', {manuels})),"
        " comment TEXT NOT NULL DEFAULT '',"
        " created_by TEXT NOT NULL DEFAULT '',"
        " attachments_path TEXT NOT NULL DEFAULT '',"
        " created_at TEXT NOT NULL,"
        # ⚠️ LE CHECK QUI PORTE LA PROMESSE, repris mot pour mot de la migration 25 : un résultat
        # automatique a une exécution et aucun statut saisi ; un manuel a un statut saisi et
        # aucune exécution. Les deux moitiés restent exclusives, en base.
        f" CHECK ((mode = '{MODE_AUTOMATIQUE}' AND execution_id IS NOT NULL AND statut_manuel = '')"
        f"     OR (mode = '{MODE_MANUELLE}' AND execution_id IS NULL AND statut_manuel <> '')),"
        " FOREIGN KEY (run_id) REFERENCES test_run(id),"
        " FOREIGN KEY (case_id) REFERENCES test_case(id),"
        " FOREIGN KEY (execution_id) REFERENCES execution(id))")

    aux = conn.execute(
        "SELECT sql FROM sqlite_master WHERE tbl_name='test_result' AND type IN ('index','trigger')"
        " AND sql IS NOT NULL AND name NOT LIKE 'sqlite_%'").fetchall()

    conn.commit()  # aucune transaction ouverte : PRAGMA foreign_keys est un no-op en transaction
    old_iso = conn.isolation_level
    conn.isolation_level = None  # autocommit : on gère BEGIN/COMMIT nous-mêmes (DDL+DML atomique)
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("BEGIN")
        try:
            conn.execute("DROP TABLE IF EXISTS test_result__migr27")
            conn.execute(create_tmp)
            conn.execute(
                "INSERT INTO test_result__migr27 (id, run_id, case_id, mode, execution_id,"
                " statut_manuel, comment, created_by, attachments_path, created_at)"
                f" SELECT id, run_id, case_id,"
                f" CASE source WHEN 'executed' THEN '{MODE_AUTOMATIQUE}'"
                f"             ELSE '{MODE_MANUELLE}' END,"
                " execution_id, declared_status, comment, created_by, attachments_path, created_at"
                " FROM test_result ORDER BY id")
            conn.execute("DROP TABLE test_result")
            conn.execute("ALTER TABLE test_result__migr27 RENAME TO test_result")
            for a in aux:
                conn.execute(a["sql"])  # index recréés (dropés avec l'ancienne table)
            violations = conn.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise RuntimeError(f"FK cassées après reconstruction de test_result : {violations}")
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        conn.execute("PRAGMA foreign_keys = ON")
    finally:
        conn.isolation_level = old_iso


def _ensure_project(conn: sqlite3.Connection, name: str, now: str) -> int:
    row = conn.execute("SELECT id FROM project WHERE name=?", (name,)).fetchone()
    if row:
        return int(row["id"])
    cur = conn.execute(
        "INSERT INTO project (name, description, created_at) VALUES (?,?,?)", (name, "", now))
    return int(cur.lastrowid)


def _ensure_module(conn: sqlite3.Connection, project_id: int, name: str, now: str) -> int:
    row = conn.execute(
        "SELECT id FROM module WHERE project_id=? AND name=?", (project_id, name)).fetchone()
    if row:
        return int(row["id"])
    cur = conn.execute(
        "INSERT INTO module (project_id, name, description, created_at) VALUES (?,?,?,?)",
        (project_id, name, "", now))
    return int(cur.lastrowid)


def _prettify(slug: str) -> str:
    """'demande_materiel' → 'Demande materiel' (nom métier lisible depuis un slug technique)."""
    s = slug.replace("_", " ").replace("-", " ").strip()
    return s[:1].upper() + s[1:] if s else s


def _migrate_28_sous_sections(conn: sqlite3.Connection) -> None:
    """Sous-sections : une Section (`case_group`) peut désormais en contenir d'autres
    (2026-08-06, décision du porteur — parité TestRail, une vraie hiérarchie, pas un libellé).

    `parent_group_id` : NULL = Section de premier niveau, comme avant cette migration — aucune
    base existante ne change de comportement tant que personne ne crée de sous-section. Une seule
    profondeur : une sous-section ne porte jamais elle-même de `parent_group_id` renseigné, comme
    TestRail par défaut (pas de niveau 3).
    """
    if "parent_group_id" not in _column_names(conn, "case_group"):
        conn.execute("ALTER TABLE case_group ADD COLUMN parent_group_id"
                     " INTEGER REFERENCES case_group(id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_case_group_parent ON case_group(parent_group_id)")


def _migrate_29_generation_job(conn: sqlite3.Connection) -> None:
    """Le job de génération (multi-cas ou automatisation d'un cas manuel) devient PERSISTÉ —
    plus seulement un dict Python en mémoire (2026-08-07, incident réel).

    ⚠️ **Un job en mémoire ne survit pas à un redémarrage du serveur.** La génération est longue
    (plusieurs minutes de dry-run réel) ; si le serveur redémarre pendant qu'un job tourne, le job
    disparaît d'un coup, et l'écran continue d'interroger un `job_id` qui n'existe plus — bloqué
    sans jamais dire pourquoi. Vécu en conditions réelles le 07/08 : perçu comme un « timeout »,
    alors que la vraie cause était le redémarrage lui-même.

    Colonnes explicites pour ce qu'on filtre/affiche souvent (`status`, `error`, `case_ids`,
    `module_id`, `cost_usd`) ; le reste (Section ciblée, spécification, cas en attente de
    validation, ou `case_id`/`slug`/métier pour une automatisation) vit dans `payload`, en JSON —
    un job est un état de TRAVAIL EN COURS, pas une donnée métier durable, et cette table ne
    devrait pas s'élargir à chaque nouveau type de tâche de fond.
    """
    conn.execute(
        "CREATE TABLE IF NOT EXISTS generation_job ("
        " id           TEXT PRIMARY KEY,"
        " status       TEXT NOT NULL,"
        " error        TEXT NOT NULL DEFAULT '',"
        " case_ids     TEXT NOT NULL DEFAULT '[]',"
        " module_id    INTEGER NOT NULL,"
        " payload      TEXT NOT NULL DEFAULT '{}',"
        " cost_usd     REAL NOT NULL DEFAULT 0.0,"
        " created_at   TEXT NOT NULL,"
        " updated_at   TEXT NOT NULL)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_generation_job_status ON generation_job(status)")


def _migrate_30_utilisateurs(conn: sqlite3.Connection) -> None:
    """De vrais comptes utilisateurs, avec rôle — remplace le nom libre non vérifié de l'ancien
    verrou d'instance (2026-08-07, retour du porteur sur la V1 : « pas un système de comptes »
    devient un vrai système de comptes).

    Quatre rôles, en hiérarchie croissante de droits : `lecture_seule` (rien écrire) <
    `testeur` (usage courant) < `dev` (+ éditer les scripts générés à la main) < `admin`
    (+ gérer les comptes). Le `CHECK` porte la promesse en base, pas seulement côté Python — même
    discipline que partout ailleurs dans ce schéma.

    `is_active` plutôt qu'une suppression : désactiver un compte doit pouvoir se défaire (un
    départ temporaire n'est pas un départ définitif), et ne DÉTRUIT jamais l'auteur des cas/
    résultats qu'il a signés (cohérent avec la suppression douce déjà pratiquée ailleurs).
    """
    conn.execute(
        "CREATE TABLE IF NOT EXISTS user ("
        " id            INTEGER PRIMARY KEY AUTOINCREMENT,"
        " username      TEXT    NOT NULL UNIQUE,"
        " password_hash TEXT    NOT NULL,"
        " role          TEXT    NOT NULL"
        "     CHECK (role IN ('lecture_seule', 'testeur', 'dev', 'admin')),"
        " is_active     INTEGER NOT NULL DEFAULT 1,"
        " created_at    TEXT    NOT NULL)")


def _migrate_31_acces_par_projet(conn: sqlite3.Connection) -> None:
    """Surcharge du rôle global, PAR PROJET (2026-08-10 — parité TestRail partielle, portée
    validée par le porteur après vérification du vrai modèle TestRail : garder le rôle global,
    ajouter une surcharge par projet, pas de groupes, pas de droit Administrateur séparé).

    `project.default_access` : vide = rôle global (comportement d'AVANT cette migration,
    inchangé) ; sinon `no_access` (projet cache à tous sauf exception) ou un des 4 rôles (forcé
    pour tout le monde — ex. archiver un projet en lecture seule sans toucher à chaque compte).

    `project_access` : une exception PAR COMPTE, PAR PROJET — prime sur `default_access`, qui
    prime sur le rôle global (`access.role_effectif_projet`, ordre de résolution).

    ⚠️ `no_access` n'est PAS ajouté à la liste des rôles vérifiée par un `CHECK` ici : ce n'est
    pas un rôle qu'un COMPTE porte (la table `user` ne le connaît pas), seulement une valeur que
    `default_access`/`project_access.role` peuvent prendre — les valider ensemble aurait mélangé
    deux vocabulaires qui répondent à des questions différentes (« qui est ce compte » contre
    « que peut-il faire sur CE projet »).
    """
    if "default_access" not in _column_names(conn, "project"):
        conn.execute("ALTER TABLE project ADD COLUMN default_access TEXT NOT NULL DEFAULT ''")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS project_access ("
        " project_id INTEGER NOT NULL,"
        " user_id    INTEGER NOT NULL,"
        " role       TEXT    NOT NULL"
        "     CHECK (role IN ('no_access', 'lecture_seule', 'testeur', 'dev', 'admin')),"
        " PRIMARY KEY (project_id, user_id))")


def _migrate_32_triggered_by(conn: sqlite3.Connection) -> None:
    """Traçabilité des exécutions automatiques (2026-08-12) : QUI a déclenché ce run, pas
    seulement « Automatique ». Avant cette migration, `ExecutionRepo.finalize` signait
    systématiquement `test_result.created_by` avec le réglage `service_account_name` — l'humain
    qui avait cliqué « Lancer » n'était nulle part.

    Vide sur les exécutions antérieures à la migration : on ne sait pas qui les a déclenchées,
    et l'inventer serait un mensonge (même principe que `target_url`, migration 20).
    """
    if "triggered_by" not in _column_names(conn, "execution"):
        conn.execute("ALTER TABLE execution ADD COLUMN triggered_by TEXT NOT NULL DEFAULT ''")


def _migrate_33_email_utilisateur(conn: sqlite3.Connection) -> None:
    """L'email d'un compte (2026-08-12) — nécessaire pour le prévenir par email quand SA campagne
    ou SON automatisation se termine (`notification_service`). Vide par défaut : un compte
    existant n'a personne pour deviner son adresse."""
    if "email" not in _column_names(conn, "user"):
        conn.execute("ALTER TABLE user ADD COLUMN email TEXT NOT NULL DEFAULT ''")


def _migrate_34_project_members(conn: sqlite3.Connection) -> None:
    """Matérialise les appartenances projet sans changer les droits effectifs existants.

    La migration 31 exprimait les accès comme un défaut de projet et des exceptions. Cette table
    prépare le modèle V1 explicite : une ligne dit qu'un utilisateur est membre d'un projet, avec
    son rôle et son statut. Le backfill calcule exactement l'ancien rôle effectif
    (exception > défaut > rôle global) et n'insère pas les accès `no_access`.
    """
    conn.execute(
        "CREATE TABLE IF NOT EXISTS project_member ("
        " project_id INTEGER NOT NULL REFERENCES project(id),"
        " user_id    INTEGER NOT NULL REFERENCES user(id),"
        " role       TEXT NOT NULL"
        "   CHECK (role IN ('lecture_seule', 'testeur', 'dev', 'admin')) ,"
        " status     TEXT NOT NULL DEFAULT 'active'"
        "   CHECK (status IN ('active', 'suspended', 'removed')) ,"
        " created_at TEXT NOT NULL,"
        " PRIMARY KEY (project_id, user_id))")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_project_member_user"
        " ON project_member(user_id, status)")
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR IGNORE INTO project_member"
        " (project_id, user_id, role, status, created_at)"
        " SELECT p.id, u.id,"
        "   COALESCE(pa.role, NULLIF(p.default_access, ''), u.role),"
        "   CASE WHEN u.is_active=1 THEN 'active' ELSE 'suspended' END, ?"
        " FROM project p CROSS JOIN user u"
        " LEFT JOIN project_access pa"
        "   ON pa.project_id=p.id AND pa.user_id=u.id"
        " WHERE p.deleted_at=''"
        " AND COALESCE(pa.role, NULLIF(p.default_access, ''), u.role) <> 'no_access'",
        (now,),
    )


def _migrate_35_access_audit(conn: sqlite3.Connection) -> None:
    """Journal minimal et durable des mutations d'accès projet et de leurs refus."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS access_audit ("
        " id             INTEGER PRIMARY KEY AUTOINCREMENT,"
        " occurred_at    TEXT NOT NULL,"
        " actor_user_id  INTEGER,"
        " project_id     INTEGER NOT NULL,"
        " action         TEXT NOT NULL,"
        " target_user_id INTEGER,"
        " result         TEXT NOT NULL CHECK (result IN ('allowed','denied')),"
        " detail         TEXT NOT NULL DEFAULT '')")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_access_audit_project_time"
        " ON access_audit(project_id, occurred_at)")


def _migrate_36_user_groups(conn: sqlite3.Connection) -> None:
    """Groupes d'utilisateurs façon TestRail : un groupe nommé contient zéro à N comptes.

    Ce premier socle ne modifie pas encore la résolution des droits projet : il rend la gestion
    des équipes réelle et persistante avant d'ajouter, dans le lot suivant, les surcharges de
    rôle par groupe. Les FK empêchent de conserver un membre fantôme.
    """
    conn.execute(
        "CREATE TABLE IF NOT EXISTS user_group ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " name TEXT NOT NULL UNIQUE,"
        " created_at TEXT NOT NULL)")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS user_group_member ("
        " group_id INTEGER NOT NULL REFERENCES user_group(id) ON DELETE CASCADE,"
        " user_id INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,"
        " PRIMARY KEY (group_id, user_id))")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_group_member_user"
        " ON user_group_member(user_id)")


def _migrate_37_project_group_access(conn: sqlite3.Connection) -> None:
    """Surcharge d'accès par groupe et par projet, comme TestRail.

    Chaîne vide = utiliser le rôle global propre à chaque membre ; `no_access` = ce groupe
    n'accorde rien ; sinon l'un des quatre rôles V1. Les groupes d'un même utilisateur se
    cumulent ensuite en prenant le niveau le plus permissif.
    """
    conn.execute(
        "CREATE TABLE IF NOT EXISTS project_group_access ("
        " project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,"
        " group_id INTEGER NOT NULL REFERENCES user_group(id) ON DELETE CASCADE,"
        " role TEXT NOT NULL"
        "   CHECK (role IN ('', 'no_access', 'lecture_seule', 'testeur', 'dev', 'admin')) ,"
        " PRIMARY KEY (project_id, group_id))")


def _migrate_38_connector_version(conn: sqlite3.Connection) -> None:
    """La VERSION du connecteur, distincte du connecteur lui-même (ex. Odoo 17 vs Odoo 19).

    Un projet = une instance d'application (décision `0005`), mais rien jusqu'ici ne disait
    QUELLE version de cette application tourne derrière — deux projets Odoo peuvent avoir des
    comportements différents selon la version, sans que rien ne le documente. Chaîne libre,
    jamais une liste fermée : chaque connecteur a son propre format (un numéro Odoo, un tag SAP
    un jour, un build interne) — et le porteur doit pouvoir déclarer « indéterminée » (chaîne
    vide) quand l'application ne l'expose pas, sans que rien ne force une valeur inventée.
    """
    if "connector_version" not in _column_names(conn, "project"):
        conn.execute(
            "ALTER TABLE project ADD COLUMN connector_version TEXT NOT NULL DEFAULT ''")


def _migrate_39_session_version(conn: sqlite3.Connection) -> None:
    """Numéro de révocation des sessions d'un compte.

    Un changement de mot de passe, de rôle, d'état ou une déconnexion incrémente cette valeur :
    tous les jetons émis avec l'ancienne version deviennent immédiatement inutilisables.
    """
    if "session_version" not in _column_names(conn, "user"):
        conn.execute(
            "ALTER TABLE user ADD COLUMN session_version INTEGER NOT NULL DEFAULT 1")


def _migrate_40_login_failure(conn: sqlite3.Connection) -> None:
    """Tentatives de connexion partagées entre processus et persistantes aux redémarrages."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS login_failure ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " attempt_key TEXT NOT NULL,"
        " occurred_at REAL NOT NULL)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_login_failure_key_time"
        " ON login_failure(attempt_key, occurred_at)")


def _migrate_41_background_job(conn: sqlite3.Connection) -> None:
    """File durable des traitements longs acceptés par l'API."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS background_job ("
        " id TEXT PRIMARY KEY,"
        " kind TEXT NOT NULL,"
        " queue_label TEXT NOT NULL,"
        " payload TEXT NOT NULL DEFAULT '{}',"
        " status TEXT NOT NULL CHECK (status IN ('queued','running','completed','failed')),"
        " error TEXT NOT NULL DEFAULT '',"
        " created_at TEXT NOT NULL,"
        " started_at TEXT NOT NULL DEFAULT '',"
        " finished_at TEXT NOT NULL DEFAULT '')")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_background_job_status_created"
        " ON background_job(status, created_at)")


def _migrate_46_verified_fields(conn: sqlite3.Connection) -> None:
    if "verified_fields" not in _column_names(conn, "test_case_version"):
        conn.execute("ALTER TABLE test_case_version ADD COLUMN verified_fields TEXT NOT NULL DEFAULT ''")
