"""Accès SQLite bas niveau : connexion, initialisation du schéma et migrations.

Le schéma CIBLE vit dans ``schema.sql`` (SQL portable, ``CREATE IF NOT EXISTS``). Les bases
DÉJÀ existantes sont amenées à la cible par des migrations versionnées via ``PRAGMA
user_version`` — chaque migration est idempotente (gardée par introspection). Aucune logique
métier ici.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from testpilot import config

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")

# Version cible du schéma. Incrémentée à chaque migration ajoutée ci-dessous.
_SCHEMA_VERSION = 9


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


def get_initialized_db(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Raccourci : connexion + schéma prêt à l'emploi (migrations incluses)."""
    conn = connect(db_path)
    init_db(conn)
    return conn


# ── Migrations ────────────────────────────────────────────────────────────────
def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}


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
    conn.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
    conn.commit()


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
