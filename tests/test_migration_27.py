"""Migration 27 — « provenance : exécuté / déclaré » devient le MODE D'EXÉCUTION.

⚠️ **Ce que ce fichier empêche de revenir.** Un renommage de colonnes est le genre de changement
qui « marche » jusqu'au jour où on relit les données. Trois défauts précis sont visés :

1. **Le `CHECK` XOR perdu dans la reconstruction.** C'est LUI qui rend un résultat manuel incapable
   de se réclamer d'une exécution machine — la promesse centrale du produit, tenue en base et non
   par convention. SQLite ne sait pas modifier un `CHECK` : il faut reconstruire la table, et une
   reconstruction bâclée laisse une table sans contrainte, qui accepte tout, en silence.
2. **Une recopie qui décale les colonnes.** L'ancienne table et la nouvelle n'ont ni les mêmes
   noms ni le même ordre implicite : un `INSERT … SELECT *` écrirait chaque valeur dans la colonne
   voisine, sur la table qui porte les résultats du produit.
3. **Une reprise qui perd des lignes ou invente un mode.** Les campagnes existantes ont été jouées
   par la machine — sauf celles dont TOUT l'historique est humain, que les dire automatiques
   rendrait impossibles à continuer (l'écran ne proposerait plus la saisie).

Et l'invariant que la migration fait NAÎTRE, parce que le mode remonte à la campagne : **le mode
d'un résultat concorde toujours avec celui de sa campagne.** Un `CHECK` ne sait pas lire une autre
table ; c'est donc un TRIGGER, et sans lui la règle ne vivrait que dans les routes — donc nulle
part le jour où un script écrit directement en base.
"""
import sqlite3

import pytest

from testpilot.store.db import (
    _SCHEMA_VERSION,
    _migrate_27_mode_d_execution,
    get_initialized_db,
)
from testpilot.verdict.status import MODE_AUTOMATIQUE, MODE_MANUELLE, STATUTS_MANUELS

# Une base « pré-27 » réaliste : la forme laissée par la migration 25, réduite à ce que la 27
# touche. Écrite en SQL BRUT — c'est le seul moyen de tester une migration sur l'état qu'elle est
# censée rencontrer (l'ancien vocabulaire), et non sur celui d'aujourd'hui.
_PRE_27 = """
CREATE TABLE project (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT '');
CREATE TABLE test_case (
    id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
    last_executed_at TEXT, last_declared_status TEXT NOT NULL DEFAULT '',
    last_result_source TEXT NOT NULL DEFAULT '', last_result_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL DEFAULT '');
CREATE TABLE test_run (
    id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, name TEXT NOT NULL,
    selection_mode TEXT NOT NULL DEFAULT 'frozen', status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL DEFAULT '', FOREIGN KEY (project_id) REFERENCES project(id));
CREATE TABLE execution (
    id INTEGER PRIMARY KEY AUTOINCREMENT, test_case_id INTEGER NOT NULL, version_id INTEGER NOT NULL,
    run_id INTEGER, started_at TEXT NOT NULL,
    FOREIGN KEY (test_case_id) REFERENCES test_case(id));
CREATE TABLE test_result (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    case_id INTEGER NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('executed', 'declared')),
    execution_id INTEGER,
    declared_status TEXT NOT NULL DEFAULT ''
        CHECK (declared_status IN ('', 'passed', 'failed', 'retest', 'blocked')),
    comment TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL DEFAULT '',
    attachments_path TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    CHECK ((source = 'executed' AND execution_id IS NOT NULL AND declared_status = '')
        OR (source = 'declared' AND execution_id IS NULL AND declared_status <> '')),
    FOREIGN KEY (run_id) REFERENCES test_run(id),
    FOREIGN KEY (case_id) REFERENCES test_case(id),
    FOREIGN KEY (execution_id) REFERENCES execution(id));
CREATE INDEX idx_result_run_case ON test_result(run_id, case_id);
CREATE UNIQUE INDEX uq_result_execution ON test_result(execution_id) WHERE execution_id IS NOT NULL;

INSERT INTO project (id, name) VALUES (1, 'Portail Sapian');
INSERT INTO test_case (id, title, last_result_source, last_declared_status, last_result_at)
    VALUES (1, 'Nominal', 'executed', '', '2026-07-30T10:00:00+00:00');
INSERT INTO test_case (id, title, last_result_source, last_declared_status, last_result_at)
    VALUES (2, 'Non automatisable', 'declared', 'blocked', '2026-08-01T09:00:00+00:00');
INSERT INTO test_case (id, title) VALUES (3, 'Jamais testé');
-- Campagne 7 : jouée par la machine. Campagne 8 : entièrement saisie à la main.
INSERT INTO test_run (id, project_id, name) VALUES (7, 1, 'Recette juillet');
INSERT INTO test_run (id, project_id, name) VALUES (8, 1, 'Recette manuelle');
INSERT INTO execution (id, test_case_id, version_id, run_id, started_at)
    VALUES (10, 1, 1, 7, '2026-07-30T10:00:00+00:00');
INSERT INTO test_result (id, run_id, case_id, source, execution_id, declared_status, comment,
                         created_by, created_at)
    VALUES (100, 7, 1, 'executed', 10, '', '', 'TestPilot', '2026-07-30T10:00:00+00:00');
INSERT INTO test_result (id, run_id, case_id, source, execution_id, declared_status, comment,
                         created_by, created_at)
    VALUES (101, 8, 2, 'declared', NULL, 'blocked', 'environnement KO', 'Romaric',
            '2026-08-01T09:00:00+00:00');
"""


@pytest.fixture
def pre27(tmp_path):
    raw = sqlite3.connect(str(tmp_path / "pre27.db"))
    raw.row_factory = sqlite3.Row
    raw.executescript(_PRE_27)
    raw.commit()
    yield raw
    raw.close()


def _colonnes(conn, table: str) -> set[str]:
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}


# ── Le vocabulaire change, les données restent ───────────────────────────────

def test_les_colonnes_prennent_le_vocabulaire_du_mode(pre27):
    _migrate_27_mode_d_execution(pre27)
    pre27.commit()

    assert "mode" in _colonnes(pre27, "test_run")
    assert {"mode", "statut_manuel"} <= _colonnes(pre27, "test_result")
    assert {"source", "declared_status"} & _colonnes(pre27, "test_result") == set()
    assert {"last_result_mode", "last_statut_manuel"} <= _colonnes(pre27, "test_case")
    assert {"last_result_source", "last_declared_status"} & _colonnes(pre27, "test_case") == set()


def test_la_recopie_ne_decale_ni_ne_perd_aucun_resultat(pre27):
    """Défaut n°2 du docstring : une recopie qui écrit chaque valeur dans la colonne voisine ne
    lève rien — elle ne se voit qu'en RELISANT les données."""
    _migrate_27_mode_d_execution(pre27)
    pre27.commit()
    lignes = {r["id"]: dict(r) for r in pre27.execute("SELECT * FROM test_result")}

    assert set(lignes) == {100, 101}
    auto = lignes[100]
    assert (auto["mode"], auto["execution_id"], auto["statut_manuel"]) == (MODE_AUTOMATIQUE, 10, "")
    assert (auto["run_id"], auto["case_id"], auto["created_by"]) == (7, 1, "TestPilot")
    manuel = lignes[101]
    assert (manuel["mode"], manuel["execution_id"]) == (MODE_MANUELLE, None)
    assert (manuel["statut_manuel"], manuel["comment"]) == ("blocked", "environnement KO")
    assert manuel["created_at"] == "2026-08-01T09:00:00+00:00"


def test_les_index_survivent_a_la_reconstruction(pre27):
    """`DROP TABLE` emporte les index avec lui : oubliés à la recréation, l'unicité qui empêche
    une exécution d'entrer deux fois au registre disparaîtrait sans le moindre message."""
    _migrate_27_mode_d_execution(pre27)
    pre27.commit()
    index = {r["name"] for r in pre27.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='test_result'")}
    assert {"idx_result_run_case", "uq_result_execution"} <= index


def test_les_raccourcis_du_cas_sont_TRADUITS_pas_seulement_renommes(pre27):
    """Renommer la colonne sans convertir ses valeurs laisserait `executed` / `declared` dans une
    colonne qui s'appelle `mode` : l'écran afficherait une pastille vide, ou l'enum brut."""
    _migrate_27_mode_d_execution(pre27)
    pre27.commit()
    cas = {r["id"]: dict(r) for r in pre27.execute(
        "SELECT id, last_result_mode, last_statut_manuel, last_result_at FROM test_case")}

    assert cas[1]["last_result_mode"] == MODE_AUTOMATIQUE
    assert cas[2]["last_result_mode"] == MODE_MANUELLE
    assert cas[2]["last_statut_manuel"] == "blocked"
    # Un cas jamais mesuré reste SANS mode : « on ne sait pas » est la vérité, et un mode inventé
    # serait exactement le mensonge que la migration 20 sert déjà à empêcher.
    assert cas[3]["last_result_mode"] == ""


# ── La reprise : le mode des campagnes existantes ────────────────────────────

def test_les_campagnes_existantes_sont_automatiques_sauf_les_entierement_manuelles(pre27):
    """Défaut n°3 du docstring. Dire « automatique » d'une campagne dont tout l'historique est
    humain lui retirerait le bouton de saisie : son histoire deviendrait impossible à continuer."""
    _migrate_27_mode_d_execution(pre27)
    pre27.commit()
    modes = {r["id"]: r["mode"] for r in pre27.execute("SELECT id, mode FROM test_run")}

    assert modes[7] == MODE_AUTOMATIQUE
    assert modes[8] == MODE_MANUELLE


def test_rejouer_la_migration_ne_change_plus_rien(pre27):
    """Toute migration de ce dépôt est rejouable : une reprise interrompue doit se rattraper
    seule, sans jamais recopier deux fois ce qu'elle a déjà converti."""
    _migrate_27_mode_d_execution(pre27)
    pre27.commit()
    avant = [dict(r) for r in pre27.execute("SELECT * FROM test_result ORDER BY id")]
    modes_avant = {r["id"]: r["mode"] for r in pre27.execute("SELECT id, mode FROM test_run")}

    _migrate_27_mode_d_execution(pre27)
    pre27.commit()

    assert [dict(r) for r in pre27.execute("SELECT * FROM test_result ORDER BY id")] == avant
    assert {r["id"]: r["mode"] for r in pre27.execute("SELECT id, mode FROM test_run")} == modes_avant


# ── Les invariants portés par la base ────────────────────────────────────────

def _base_neuve(tmp_path, mode=MODE_MANUELLE):
    """Une base neuve avec un projet, un cas et une campagne — le décor minimal d'un résultat."""
    conn = get_initialized_db(tmp_path / "neuve.db")
    conn.execute("INSERT INTO project (id, name, created_at) VALUES (1, 'P', '')")
    conn.execute("INSERT INTO test_case (id, title, created_at, updated_at) VALUES (1, 'C', '', '')")
    conn.execute("INSERT INTO test_run (id, project_id, name, mode, created_at)"
                 " VALUES (7, 1, 'R', ?, '')", (mode,))
    return conn


def test_un_resultat_manuel_ne_peut_pas_se_reclamer_d_une_execution(tmp_path):
    """⚠️ **Le cœur du chantier, et le `CHECK` qui a survécu au renommage.** La promesse « on sait
    toujours COMMENT un statut a été obtenu » ne tient pas parce que le code est discipliné : elle
    tient parce que la ligne est INSÉRABLE ou non."""
    conn = _base_neuve(tmp_path)

    def inserer(**champs):
        base = {"run_id": 7, "case_id": 1, "mode": MODE_MANUELLE, "execution_id": None,
                "statut_manuel": "passed", "created_at": "2026-08-04"}
        base.update(champs)
        conn.execute(
            "INSERT INTO test_result (run_id, case_id, mode, execution_id, statut_manuel,"
            " created_at) VALUES (:run_id, :case_id, :mode, :execution_id, :statut_manuel,"
            " :created_at)", base)

    inserer()  # une exécution manuelle honnête passe

    with pytest.raises(sqlite3.IntegrityError):
        inserer(statut_manuel="")           # manuel sans statut : n'affirme rien
    with pytest.raises(sqlite3.IntegrityError):
        inserer(statut_manuel="untested")   # « non testé » ne se saisit pas, il s'observe
    with pytest.raises(sqlite3.IntegrityError):
        inserer(mode="inconnu")
    conn.close()


def test_un_resultat_automatique_sans_execution_est_refuse(tmp_path):
    """L'autre moitié du XOR : `automatique` affirme qu'une MACHINE a produit ce résultat. Sans
    `execution_id`, il n'y a rien à montrer — et la promesse redeviendrait une convention."""
    conn = _base_neuve(tmp_path, mode=MODE_AUTOMATIQUE)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO test_result (run_id, case_id, mode, execution_id, statut_manuel,"
                     " created_at) VALUES (7, 1, ?, NULL, '', '2026-08-04')", (MODE_AUTOMATIQUE,))
    with pytest.raises(sqlite3.IntegrityError):
        # …et un automatique qui porterait AUSSI un statut saisi mélangerait les deux moitiés.
        conn.execute("INSERT INTO test_result (run_id, case_id, mode, execution_id, statut_manuel,"
                     " created_at) VALUES (7, 1, ?, NULL, 'passed', '2026-08-04')",
                     (MODE_AUTOMATIQUE,))
    conn.close()


def test_le_mode_d_un_resultat_CONCORDE_avec_celui_de_sa_campagne(tmp_path):
    """⚠️ **L'invariant que le mode au niveau campagne fait naître.** Une campagne manuelle qui
    contiendrait un résultat machine (ou l'inverse) donnerait un écran incohérent : il propose le
    geste d'un mode et affiche les résultats de l'autre. Un `CHECK` ne sait pas lire `test_run` —
    c'est donc un TRIGGER, et sans lui la règle ne vivrait que dans les routes, c'est-à-dire nulle
    part le jour où un script ou un import écrit directement en base."""
    conn = _base_neuve(tmp_path, mode=MODE_MANUELLE)
    conn.execute("INSERT INTO test_case_version (id, test_case_id, version_number, spec_content,"
                 " spec_hash, feature_content, steps_content, created_at)"
                 " VALUES (1, 1, 1, '', '', '', '', '')")
    conn.execute("INSERT INTO execution (id, test_case_id, version_id, run_id, started_at)"
                 " VALUES (10, 1, 1, 7, '')")

    with pytest.raises(sqlite3.IntegrityError, match="concorde"):
        conn.execute("INSERT INTO test_result (run_id, case_id, mode, execution_id, statut_manuel,"
                     " created_at) VALUES (7, 1, ?, 10, '', '2026-08-04')", (MODE_AUTOMATIQUE,))

    # Et l'inverse : une saisie humaine dans une campagne automatique.
    conn.execute("INSERT INTO test_run (id, project_id, name, mode, created_at)"
                 " VALUES (8, 1, 'Auto', ?, '')", (MODE_AUTOMATIQUE,))
    with pytest.raises(sqlite3.IntegrityError, match="concorde"):
        conn.execute("INSERT INTO test_result (run_id, case_id, mode, execution_id, statut_manuel,"
                     " created_at) VALUES (8, 1, ?, NULL, 'passed', '2026-08-04')", (MODE_MANUELLE,))
    conn.close()


def test_le_CHECK_de_la_base_dit_exactement_ce_que_dit_python(tmp_path):
    """⚠️ Le défaut de la migration 19, rejoué mot pour mot : la liste des statuts saisissables vit
    en Python ET en SQL. Sans cette comparaison, ajouter une valeur d'un seul côté produirait un
    statut que le produit propose et que la base refuse."""
    conn = get_initialized_db(tmp_path / "neuve.db")
    sql = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='test_result'"
                       ).fetchone()["sql"]
    conn.close()

    debut = sql.index("statut_manuel IN (")
    liste = sql[debut + len("statut_manuel IN ("):sql.index(")", debut)]
    valeurs = {v.strip().strip("'") for v in liste.split(",")}
    # '' en plus : l'absence de statut saisi, qui n'est pas une valeur saisissable.
    assert valeurs == {""} | set(STATUTS_MANUELS)


def test_une_base_neuve_est_a_la_version_cible_et_parle_de_mode(tmp_path):
    conn = get_initialized_db(tmp_path / "neuve.db")
    assert conn.execute("PRAGMA user_version").fetchone()[0] == _SCHEMA_VERSION
    assert "mode" in _colonnes(conn, "test_run")
    assert {"mode", "statut_manuel"} <= _colonnes(conn, "test_result")
    # ⚠️ Sur une base NEUVE, la migration 25 crée l'ancien vocabulaire puis la 27 le convertit :
    # c'est correct et voulu (on n'édite jamais l'histoire des migrations). Ce qui ne doit pas
    # survivre, c'est l'ancien nom — sinon deux colonnes répondraient à la même question.
    assert {"last_result_source", "last_declared_status"} & _colonnes(conn, "test_case") == set()
    conn.close()
