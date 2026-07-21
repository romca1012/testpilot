"""Spécification (case_group) — la situation testée devient un cas indépendant (rouvre 0006).

Décision du porteur (2026-07-19) : chaque situation (nominal/erreur/limite/autre) est un CAS à
part entière, regroupé sous une SPÉCIFICATION (conteneur organisationnel simple). Le cas reste
l'unité versionnée/gatée/exécutée/facturée : aucune Fq en aval ne bouge. Étape 1 = SCHÉMA seul.
"""
import sqlite3

import pytest

from testpilot.store.db import get_initialized_db, _migrate_13_case_group
from testpilot.store.repositories import (
    CaseGroupRepo,
    CaseRepo,
    DuplicateName,
    ModuleRepo,
    ProjectRepo,
    ensure_default_module,
)


@pytest.fixture
def conn(tmp_path):
    c = get_initialized_db(tmp_path / "g.db")
    yield c
    c.close()


# ── Le schéma neuf porte la table + les colonnes ──────────────────────────────

def test_base_neuve_a_case_group_et_les_colonnes(conn):
    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "case_group" in tables
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(test_case)")}
    assert {"group_id", "angle"} <= cols
    # ⚠️ On compare à `_SCHEMA_VERSION`, jamais à un nombre en dur : figer « 13 » faisait échouer
    # ce test à chaque migration suivante, pour une raison sans rapport avec ce qu'il vérifie.
    from testpilot.store.db import _SCHEMA_VERSION
    assert conn.execute("PRAGMA user_version").fetchone()[0] == _SCHEMA_VERSION


# ── Migration 13 : legacy enveloppé 1:1, angle='legacy' ───────────────────────

def test_migration_13_enveloppe_chaque_cas_existant_dans_sa_propre_specification(tmp_path):
    """Une base d'AVANT la migration 13 : chaque cas existant reçoit SA PROPRE spécification
    (1:1), `angle='legacy'`, sans fusion ni perte."""
    db = tmp_path / "pre13.db"
    raw = sqlite3.connect(str(db))
    raw.row_factory = sqlite3.Row
    raw.execute("CREATE TABLE module (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER,"
                " name TEXT, description TEXT DEFAULT '', created_at TEXT DEFAULT '')")
    # test_case SANS group_id/angle (état pré-13), avec la table case_group encore absente.
    raw.execute("CREATE TABLE test_case (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,"
                " module_id INTEGER, feature_slug TEXT DEFAULT '', created_at TEXT DEFAULT '',"
                " updated_at TEXT DEFAULT '')")
    raw.execute("CREATE TABLE test_case_version (id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " test_case_id INTEGER, spec_content TEXT DEFAULT '', spec_hash TEXT DEFAULT '')")
    # case_group SANS les colonnes spec (état où schema.sql l'aurait créée avant l'ajout) — la
    # migration doit les guard-add.
    raw.execute("CREATE TABLE case_group (id INTEGER PRIMARY KEY AUTOINCREMENT, module_id INTEGER"
                " NOT NULL, title TEXT NOT NULL, description TEXT DEFAULT '', position INTEGER"
                " DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)")
    raw.execute("INSERT INTO module (id, name) VALUES (1, 'Demande materiel')")
    raw.execute("INSERT INTO test_case (title, module_id) VALUES ('Demande de matériel', 1)")
    raw.execute("INSERT INTO test_case (title, module_id) VALUES ('Validation champ requis', 1)")
    # Le cas 1 a une version portant sa spec — elle doit REMONTER au groupe.
    raw.execute("INSERT INTO test_case_version (test_case_id, spec_content, spec_hash)"
                " VALUES (1, 'La spec complète de la demande de matériel', 'abc123')")
    raw.commit()

    _migrate_13_case_group(raw)
    raw.commit()

    cases = list(raw.execute("SELECT id, title, group_id, angle FROM test_case ORDER BY id"))
    assert all(c["group_id"] is not None for c in cases), "tout cas est rattaché à une spécification"
    assert all(c["angle"] == "legacy" for c in cases)
    # 1:1 : deux cas → deux spécifications distinctes.
    groups = {c["group_id"] for c in cases}
    assert len(groups) == 2, "chaque cas legacy a SA PROPRE spécification (pas de fusion)"
    # La spécification porte le titre du cas qu'elle enveloppe ET la spec REMONTÉE de sa version.
    g0 = dict(raw.execute("SELECT title, spec_content, spec_hash FROM case_group WHERE id=?",
                          (cases[0]["group_id"],)).fetchone())
    assert g0["title"] == "Demande de matériel"
    assert g0["spec_content"] == "La spec complète de la demande de matériel", "la spec remonte au groupe"
    assert g0["spec_hash"] == "abc123", "l'empreinte de la spec remonte aussi (la référence)"
    raw.close()


def test_migration_13_est_idempotente(tmp_path):
    """Rejouer la migration ne recrée pas de groupes (WHERE group_id IS NULL)."""
    db = tmp_path / "idem.db"
    raw = sqlite3.connect(str(db))
    raw.row_factory = sqlite3.Row
    raw.execute("CREATE TABLE module (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)")
    raw.execute("CREATE TABLE test_case (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,"
                " module_id INTEGER, feature_slug TEXT DEFAULT '')")
    raw.execute("CREATE TABLE case_group (id INTEGER PRIMARY KEY AUTOINCREMENT, module_id INTEGER"
                " NOT NULL, title TEXT NOT NULL, description TEXT DEFAULT '', position INTEGER"
                " DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)")
    raw.execute("INSERT INTO module (id, name) VALUES (1, 'M')")
    raw.execute("INSERT INTO test_case (title, module_id) VALUES ('Cas', 1)")
    raw.commit()

    _migrate_13_case_group(raw)
    _migrate_13_case_group(raw)  # deuxième passage
    raw.commit()

    assert raw.execute("SELECT COUNT(*) FROM case_group").fetchone()[0] == 1
    raw.close()


# ── CaseGroupRepo ─────────────────────────────────────────────────────────────

def test_case_group_repo_cree_liste_et_refuse_les_doublons(conn):
    mid = ensure_default_module(conn, "demande_materiel")
    repo = CaseGroupRepo(conn)
    g1 = repo.create(module_id=mid, title="Demande de matériel")
    repo.create(module_id=mid, title="Retour de matériel")

    assert {g["title"] for g in repo.list_for_module(mid)} == {"Demande de matériel", "Retour de matériel"}
    with pytest.raises(DuplicateName):
        repo.create(module_id=mid, title="  demande de  matériel ")  # même clé Unicode/espaces


def test_la_specification_porte_le_document_source(conn):
    """La spec (le DOCUMENT) vit sur la spécification, pas dupliquée dans chaque version."""
    mid = ensure_default_module(conn, "demande_materiel")
    gid = CaseGroupRepo(conn).create(module_id=mid, title="Demande",
                                     spec_content="Document complet de la spec", spec_hash="h1")

    g = CaseGroupRepo(conn).get(gid)
    assert g["spec_content"] == "Document complet de la spec"
    assert g["spec_hash"] == "h1"


# ── CaseRepo : group_id, angle, unicité par groupe ────────────────────────────

def test_creer_un_cas_sans_group_id_l_auto_enveloppe(conn):
    """L'appelant historique (génération) ne passe pas de group_id : le cas est auto-enveloppé
    dans sa propre spécification — aucun cas orphelin, invariant « group_id obligatoire » tenu."""
    mid = ensure_default_module(conn, "demande_materiel")
    cid = CaseRepo(conn).create(title="Nominal", module_id=mid, feature_slug="nominal")

    case = CaseRepo(conn).get(cid)
    assert case["group_id"] is not None
    assert case["angle"] == ""  # étiquette libre, vide par défaut


def test_deux_specifications_peuvent_chacune_avoir_un_Nominal(conn):
    """Le titre est unique PAR GROUPE, plus par module (la décision). Deux spécifications du même
    module peuvent chacune avoir un cas « Nominal »."""
    mid = ensure_default_module(conn, "demande_materiel")
    g1 = CaseGroupRepo(conn).create(module_id=mid, title="Demande")
    g2 = CaseGroupRepo(conn).create(module_id=mid, title="Retour")

    CaseRepo(conn).create(title="Nominal", module_id=mid, group_id=g1, angle="nominal",
                          feature_slug="demande_nominal")
    # Même titre, AUTRE spécification → autorisé.
    CaseRepo(conn).create(title="Nominal", module_id=mid, group_id=g2, angle="nominal",
                          feature_slug="retour_nominal")

    # Mais deux « Nominal » dans la MÊME spécification → refusé.
    with pytest.raises(DuplicateName):
        CaseRepo(conn).create(title="Nominal", module_id=mid, group_id=g1, feature_slug="x")


def test_l_angle_est_une_etiquette_libre(conn):
    mid = ensure_default_module(conn, "demande_materiel")
    g = CaseGroupRepo(conn).create(module_id=mid, title="Demande")
    cid = CaseRepo(conn).create(title="Cas exotique", module_id=mid, group_id=g,
                                angle="charge_extreme", feature_slug="exo")

    assert CaseRepo(conn).get(cid)["angle"] == "charge_extreme"  # pas contraint à nominal/erreur/limite


# ── La cascade projet emporte les spécifications ──────────────────────────────

def test_supprimer_un_projet_emporte_ses_specifications(conn):
    """La cascade projet doit supprimer case_group AVANT module (FK case_group→module)."""
    mid = ensure_default_module(conn, "demande_materiel")
    pid = ModuleRepo(conn).get(mid)["project_id"]
    g = CaseGroupRepo(conn).create(module_id=mid, title="Demande")
    CaseRepo(conn).create(title="Nominal", module_id=mid, group_id=g, feature_slug="n")

    ProjectRepo(conn).delete(pid)

    assert conn.execute("SELECT COUNT(*) FROM case_group").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM test_case").fetchone()[0] == 0
