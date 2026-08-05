"""Migration 25 — le registre des résultats, et le cas qui gagne un cycle de vie.

⚠️ **Ce que ce fichier empêche de revenir.** Trois défauts déjà payés dans ce dépôt :

1. **Un CHECK désynchronisé de la règle Python** — le défaut EXACT de la migration 19 : le 4ᵉ
   verdict avait été branché partout côté Python, mais la base le refusait, et un cas correctement
   jugé retombait en « erreur technique ». Ici, la liste des statuts saisissables existe en Python
   (`STATUTS_MANUELS`), en SQL (le `CHECK`) et à l'écran : un test les compare, sinon elles
   divergeront un jour en silence. (Ce test-là vit désormais dans `test_migration_27.py`, qui
   possède le vocabulaire du schéma final ; la migration 25, elle, n'est jamais réécrite.)
2. **Une reprise de données qui perd l'ORDRE** — l'ordre des lignes du registre porte le « dernier
   résultat » d'un cas dans une campagne. Insérées dans le désordre, elles inverseraient des
   verdicts sur des campagnes existantes, sans rien casser de visible.
3. **Une reconstruction de table qui décale les colonnes** — supprimer `validation_status` exige de
   reconstruire `test_case` (la colonne porte un `CHECK`). Un `INSERT … SELECT *` y écrirait chaque
   valeur dans la colonne voisine, en silence, sur la table la plus centrale du produit.

Et l'invariant que la migration installe : **un résultat déclaré ne peut pas se déguiser en
résultat exécuté** — pas par convention, mais parce que la base refuse la ligne.
"""
import sqlite3

import pytest

from testpilot.store.db import (
    _SCHEMA_VERSION,
    _migrate_25_resultats_et_cycle_de_vie,
    _sql_sans_colonne,
    get_initialized_db,
)

# Une base « pré-25 » réaliste : la forme des tables au schéma 24, réduite à ce que la migration
# touche. Écrite en SQL BRUT (jamais via les dépôts) — c'est le seul moyen de tester une migration
# sur l'état qu'elle est censée rencontrer, et non sur celui d'aujourd'hui.
_PRE_25 = """
CREATE TABLE project (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
    deleted_at TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT '');
CREATE TABLE module (
    id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, name TEXT NOT NULL,
    deleted_at TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (project_id) REFERENCES project(id));
CREATE TABLE case_group (
    id INTEGER PRIMARY KEY AUTOINCREMENT, module_id INTEGER NOT NULL, title TEXT NOT NULL,
    spec_content TEXT NOT NULL DEFAULT '', deleted_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (module_id) REFERENCES module(id));
CREATE TABLE test_case (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    title                  TEXT    NOT NULL,
    module_id              INTEGER REFERENCES module(id),
    group_id               INTEGER REFERENCES case_group(id),
    angle                  TEXT    NOT NULL DEFAULT '',
    feature_slug           TEXT    NOT NULL DEFAULT '',
    description            TEXT    NOT NULL DEFAULT '',
    origin                 TEXT    NOT NULL DEFAULT 'ia_generated'
                                     CHECK (origin IN ('ia_generated', 'manual_converted')),
    validation_status      TEXT    NOT NULL DEFAULT 'never_executed'
                                     CHECK (validation_status IN ('never_executed', 'validated', 'to_review')),
    priority               TEXT    NOT NULL DEFAULT 'medium'
                                     CHECK (priority IN ('low', 'medium', 'high')),
    position               INTEGER NOT NULL DEFAULT 0,
    refs                   TEXT    NOT NULL DEFAULT '',
    estimate               TEXT    NOT NULL DEFAULT '',
    current_version_id     INTEGER,
    last_execution_status  TEXT    CHECK (last_execution_status IN ('success', 'technical_error', 'not_executed')),
    last_functional_status TEXT    CHECK (last_functional_status IN ('conforme', 'non_conforme', 'indetermine', 'not_evaluated', 'donnee_invalide')),
    last_executed_at       TEXT,
    author                 TEXT    NOT NULL DEFAULT '',
    deleted_at             TEXT    NOT NULL DEFAULT '',
    deleted_by             TEXT    NOT NULL DEFAULT '',
    created_at             TEXT    NOT NULL,
    updated_at             TEXT    NOT NULL);
CREATE UNIQUE INDEX uq_case_group_title ON test_case(group_id, title COLLATE NOCASE)
    WHERE deleted_at = '';
CREATE INDEX idx_case_module ON test_case(module_id);
CREATE TABLE test_run (
    id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, name TEXT NOT NULL,
    selection_mode TEXT NOT NULL DEFAULT 'frozen', status TEXT NOT NULL DEFAULT 'draft',
    is_archived INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (project_id) REFERENCES project(id));
CREATE TABLE execution (
    id INTEGER PRIMARY KEY AUTOINCREMENT, test_case_id INTEGER NOT NULL, version_id INTEGER NOT NULL,
    execution_status TEXT NOT NULL DEFAULT 'not_executed',
    functional_status TEXT NOT NULL DEFAULT 'not_evaluated',
    run_id INTEGER, artifacts_path TEXT NOT NULL DEFAULT '', started_at TEXT NOT NULL,
    FOREIGN KEY (test_case_id) REFERENCES test_case(id));

INSERT INTO project (id, name) VALUES (1, 'Portail Sapian');
INSERT INTO module (id, project_id, name) VALUES (1, 1, 'Demandes');
INSERT INTO case_group (id, module_id, title) VALUES (1, 1, 'Demande de matériel');
INSERT INTO test_case (id, title, module_id, group_id, priority, validation_status,
                       last_execution_status, last_functional_status, last_executed_at,
                       created_at, updated_at)
    VALUES (1, 'Nominal', 1, 1, 'high', 'validated',
            'success', 'conforme', '2026-07-30T10:00:00+00:00', '2026-07-01', '2026-07-30');
INSERT INTO test_case (id, title, module_id, group_id, priority, validation_status,
                       created_at, updated_at)
    VALUES (2, 'Champ requis', 1, 1, 'low', 'never_executed', '2026-07-01', '2026-07-01');
INSERT INTO test_run (id, project_id, name) VALUES (7, 1, 'Recette juillet');
-- Deux exécutions du MÊME cas dans la MÊME campagne : c'est leur ordre qui dit laquelle fait foi.
INSERT INTO execution (id, test_case_id, version_id, execution_status, functional_status,
                       run_id, started_at)
    VALUES (10, 1, 1, 'technical_error', 'indetermine', 7, '2026-07-30T09:00:00+00:00');
INSERT INTO execution (id, test_case_id, version_id, execution_status, functional_status,
                       run_id, started_at)
    VALUES (11, 1, 1, 'success', 'conforme', 7, '2026-07-30T10:00:00+00:00');
-- Exécution HORS campagne (l'ancien modèle mono-cas) : elle n'a rien à faire dans le registre,
-- qui répond à « résultat du cas C dans la campagne R » — sans campagne, il n'y a pas de question.
INSERT INTO execution (id, test_case_id, version_id, execution_status, functional_status,
                       run_id, started_at)
    VALUES (12, 2, 1, 'success', 'conforme', NULL, '2026-07-31T08:00:00+00:00');
"""


@pytest.fixture
def pre25(tmp_path):
    raw = sqlite3.connect(str(tmp_path / "pre25.db"))
    raw.row_factory = sqlite3.Row
    raw.executescript(_PRE_25)
    raw.commit()
    yield raw
    raw.close()


def _colonnes(conn, table: str) -> set[str]:
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}


# ── Ce que la migration installe ─────────────────────────────────────────────

def test_les_quatre_tables_et_les_cinq_colonnes_apparaissent(pre25):
    _migrate_25_resultats_et_cycle_de_vie(pre25)
    pre25.commit()

    tables = {r["name"] for r in pre25.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"test_result", "run_case_assignment", "result_attachment", "app_setting"} <= tables

    cols = _colonnes(pre25, "test_case")
    assert {"type", "etat", "last_declared_status", "last_result_source", "last_result_at"} <= cols
    # Le cycle de vie remplace le statut dérivé : garder les deux, c'est laisser deux réponses à
    # la même question, et laisser un écran afficher la mauvaise.
    assert "validation_status" not in cols


def test_les_defauts_sont_fonctionnel_et_new(pre25):
    """Un cas existant ne naît pas « sans type » : il devient fonctionnel/Nouveau, ce qu'il est."""
    _migrate_25_resultats_et_cycle_de_vie(pre25)
    ligne = pre25.execute("SELECT type, etat FROM test_case WHERE id=1").fetchone()
    assert ligne["type"] == "fonctionnel"
    assert ligne["etat"] == "new"


def test_la_reconstruction_ne_decale_ni_ne_perd_aucune_donnee(pre25):
    """Le défaut n°3 du docstring : une reconstruction qui écrit chaque valeur d'une colonne dans
    sa voisine ne lève rien — elle se voit uniquement en RELISANT les données."""
    avant = [dict(r) for r in pre25.execute("SELECT * FROM test_case ORDER BY id")]
    _migrate_25_resultats_et_cycle_de_vie(pre25)
    pre25.commit()
    apres = {r["id"]: dict(r) for r in pre25.execute("SELECT * FROM test_case ORDER BY id")}

    assert len(apres) == len(avant)
    for ligne in avant:
        cible = apres[ligne["id"]]
        for champ, valeur in ligne.items():
            if champ == "validation_status":
                continue  # la seule colonne que la migration retire
            assert cible[champ] == valeur, f"{champ} a bougé sur le cas {ligne['id']}"


def test_les_index_survivent_a_la_reconstruction(pre25):
    """`DROP TABLE` emporte les index avec lui : oubliés à la recréation, l'unicité des titres
    disparaîtrait sans le moindre message — et les doublons reviendraient un par un."""
    _migrate_25_resultats_et_cycle_de_vie(pre25)
    pre25.commit()
    index = {r["name"] for r in pre25.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='test_case'")}
    assert {"uq_case_group_title", "idx_case_module"} <= index

    # Et l'unicité est réellement APPLIQUÉE (l'index existe ≠ l'index mord).
    with pytest.raises(sqlite3.IntegrityError):
        pre25.execute("INSERT INTO test_case (title, group_id, created_at, updated_at)"
                      " VALUES ('nominal', 1, '', '')")   # même titre, casse différente


# ── La reprise des exécutions existantes ─────────────────────────────────────

def test_chaque_execution_de_campagne_devient_une_ligne_du_registre(pre25):
    _migrate_25_resultats_et_cycle_de_vie(pre25)
    pre25.commit()
    lignes = [dict(r) for r in pre25.execute("SELECT * FROM test_result ORDER BY id")]

    # 2 lignes : les deux exécutions rattachées à la campagne. Celle SANS `run_id` est ignorée.
    assert [l["execution_id"] for l in lignes] == [10, 11]
    assert all(l["source"] == "executed" for l in lignes)
    assert all(l["declared_status"] == "" for l in lignes)
    # `created_by` VIDE : ces runs précèdent le compte de service. Y écrire le nom du jour
    # prétendrait mesurer ce qu'on n'a pas mesuré.
    assert all(l["created_by"] == "" for l in lignes)


def test_l_ordre_du_registre_suit_l_ordre_des_executions(pre25):
    """Défaut n°2 du docstring. Le cas 1 a d'abord ÉCHOUÉ puis RÉUSSI : si la reprise inversait
    les deux lignes, la campagne afficherait « erreur technique » sur un cas passé au vert."""
    _migrate_25_resultats_et_cycle_de_vie(pre25)
    pre25.commit()
    dernier = pre25.execute(
        "SELECT execution_id FROM test_result WHERE run_id=7 AND case_id=1"
        " ORDER BY id DESC LIMIT 1").fetchone()
    assert dernier["execution_id"] == 11


def test_la_provenance_du_dernier_resultat_est_inscrite_sur_les_cas_deja_testes(pre25):
    _migrate_25_resultats_et_cycle_de_vie(pre25)
    cas = {r["id"]: dict(r) for r in pre25.execute(
        "SELECT id, last_result_source, last_result_at, last_declared_status FROM test_case")}
    assert cas[1]["last_result_source"] == "executed"
    assert cas[1]["last_result_at"] == "2026-07-30T10:00:00+00:00"
    assert cas[1]["last_declared_status"] == ""
    # Un cas jamais mesuré reste SANS provenance : « on ne sait pas » est la vérité, et une
    # provenance inventée serait le mensonge que la migration 20 sert déjà à empêcher.
    assert cas[2]["last_result_source"] == ""


def test_une_table_DEJA_reconstruite_une_fois_se_reconstruit_encore(pre25):
    """⚠️ **Trouvé en rejouant la migration sur une copie de la VRAIE base, pas ici.**

    `ALTER TABLE … RENAME TO test_case` — la dernière étape de toute reconstruction, celle de la
    migration 19 comprise — réécrit le schéma stocké en `CREATE TABLE "test_case"`, **avec des
    guillemets**. La reconstruction suivante cherchait `CREATE TABLE test_case` sans guillemets,
    ne trouvait rien, et créait sa table temporaire sous le nom d'origine : « table already
    exists », à l'ouverture de la base, sur la table la plus centrale du produit.

    La base synthétique de ce fichier n'était jamais passée par une reconstruction — elle ne
    pouvait pas voir le défaut. Ce test reproduit l'état que la migration 19 laisse derrière elle.
    """
    pre25.execute("ALTER TABLE test_case RENAME TO test_case_tmp")
    pre25.execute("ALTER TABLE test_case_tmp RENAME TO test_case")
    pre25.commit()
    assert '"test_case"' in pre25.execute(
        "SELECT sql FROM sqlite_master WHERE name='test_case'").fetchone()["sql"]

    _migrate_25_resultats_et_cycle_de_vie(pre25)
    pre25.commit()

    assert "validation_status" not in _colonnes(pre25, "test_case")
    assert pre25.execute("SELECT COUNT(*) AS n FROM test_case").fetchone()["n"] == 2


def test_rejouer_la_migration_ne_duplique_rien(pre25):
    """Toute migration de ce dépôt est rejouable : une reprise interrompue doit se rattraper
    seule, sans jamais compter deux fois ce qu'elle a déjà repris."""
    _migrate_25_resultats_et_cycle_de_vie(pre25)
    pre25.commit()
    _migrate_25_resultats_et_cycle_de_vie(pre25)
    pre25.commit()

    assert pre25.execute("SELECT COUNT(*) AS n FROM test_result").fetchone()["n"] == 2
    assert "validation_status" not in _colonnes(pre25, "test_case")
    assert pre25.execute("SELECT COUNT(*) AS n FROM test_case").fetchone()["n"] == 2


# ── Ce que la migration laisse derrière elle, vu d'une base neuve ────────────
# ⚠️ Les invariants du REGISTRE (le `CHECK` XOR, la liste des statuts saisissables) ne sont plus
# testés ici : ils portent sur le schéma FINAL, que la migration 27 réécrit en vocabulaire « mode
# d'exécution » (`mode` / `statut_manuel`). Ils vivent donc dans `test_migration_27.py`, où leur
# vocabulaire est le bon. Ce fichier garde ce qui concerne bien la 25 : le statut dérivé retiré.

def _base_neuve(tmp_path):
    return get_initialized_db(tmp_path / "neuve.db")


def test_une_base_neuve_est_a_la_version_cible_et_sans_statut_derive(tmp_path):
    conn = _base_neuve(tmp_path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == _SCHEMA_VERSION
    assert "validation_status" not in _colonnes(conn, "test_case")
    assert {"type", "etat"} <= _colonnes(conn, "test_case")
    conn.close()


# ── L'outil de reconstruction, testé pour lui-même ───────────────────────────

def test_sql_sans_colonne_ne_coupe_pas_sur_une_virgule_de_contrainte():
    """Une regex naïve couperait à la première virgule — celle du `IN (…)` — et produirait un
    `CREATE TABLE` invalide. C'est la raison d'être du parcours à profondeur de parenthèses."""
    sql = ("CREATE TABLE t (id INTEGER PRIMARY KEY,"
           " statut TEXT NOT NULL DEFAULT 'a' CHECK (statut IN ('a', 'b', 'c')),"
           " titre TEXT NOT NULL)")
    obtenu = _sql_sans_colonne(sql, "statut")
    # Espaces normalisés : retirer une définition laisse une espace en trop, sans conséquence
    # pour SQLite. C'est la STRUCTURE qui compte ici, pas la mise en forme.
    assert " ".join(obtenu.split()) == "CREATE TABLE t (id INTEGER PRIMARY KEY, titre TEXT NOT NULL)"


def test_sql_sans_colonne_ignore_une_colonne_absente():
    """Rendre le SQL inchangé est ce qui permet à l'appelant de DÉTECTER qu'il n'a rien fait,
    au lieu de reconstruire une table amputée au hasard."""
    sql = "CREATE TABLE t (id INTEGER PRIMARY KEY, titre TEXT NOT NULL)"
    assert _sql_sans_colonne(sql, "statut") == sql
