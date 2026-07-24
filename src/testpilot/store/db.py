"""Accès SQLite bas niveau : connexion, initialisation du schéma et migrations.

Le schéma CIBLE vit dans ``schema.sql`` (SQL portable, ``CREATE IF NOT EXISTS``). Les bases
DÉJÀ existantes sont amenées à la cible par des migrations versionnées via ``PRAGMA
user_version`` — chaque migration est idempotente (gardée par introspection). Aucune logique
métier ici.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from testpilot import config

logger = logging.getLogger(__name__)

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")

# Version cible du schéma. Incrémentée à chaque migration ajoutée ci-dessous.
_SCHEMA_VERSION = 22


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
    vcols = _column_names(conn, "test_case_version")
    for col in ("title", "preconditions", "test_steps", "expected_result", "angle"):
        if col not in vcols:
            conn.execute(f"ALTER TABLE test_case_version ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")

    ccols = _column_names(conn, "test_case")
    for col in ("refs", "estimate"):
        if col not in ccols:
            conn.execute(f"ALTER TABLE test_case ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")

    # Reprise MINIMALE et non inventée : le titre et l'angle des versions existantes sont ceux
    # du cas (on ne les connaît pas autrement — aucune version n'a jamais porté de titre).
    # Les champs de CONTENU (préconditions/étapes/résultat) restent vides : les dériver ici
    # reviendrait à fabriquer du texte, ce que A.1 a explicitement écarté.
    conn.execute(
        "UPDATE test_case_version SET title = ("
        "  SELECT tc.title FROM test_case tc WHERE tc.id = test_case_version.test_case_id)"
        " WHERE title = ''")
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
