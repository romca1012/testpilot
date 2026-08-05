"""Le contenu MÉTIER d'un cas — champs de première classe, VERSIONNÉS (décision `0022`, n°3 et 10).

CE QUI EXISTAIT AVANT. Préconditions / étapes / résultat attendu n'existaient nulle part : l'écran
les **dérivait du Gherkin à la volée**. Mesuré sur le cas 9 : la ligne technique
« le champ "partner_id" de cet enregistrement n'est pas vide » s'affichait comme une **étape
métier**. C'est pourquoi la migration ne remplit RIEN (arbitrage A.1) : stocker ce texte dérivé lui
donnerait l'air rédigé, alors qu'il vient d'une conversion automatique.

L'INVARIANT CENTRAL ICI : **une édition CRÉE une version, elle n'écrase jamais.** Écraser
détruirait l'historique que l'onglet Historique doit differ, et modifierait sous ses pieds un
contenu que le gate a peut-être déjà approuvé.
"""
import json
import sqlite3

import pytest

from testpilot.store.db import _migrate_14_champs_metier, get_initialized_db
from testpilot.store.repositories import CaseRepo, ReviewRepo, VersionRepo, ensure_default_module


@pytest.fixture
def conn(tmp_path):
    c = get_initialized_db(tmp_path / "metier.db")
    yield c
    c.close()


def _cas(conn, *, title="Demande de matériel"):
    mid = ensure_default_module(conn, "demande_materiel")
    cid = CaseRepo(conn).create(title=title, module_id=mid, feature_slug="dm")
    vid = VersionRepo(conn).create(
        test_case_id=cid, spec_content="spec", spec_hash="h",
        feature_content="# language: fr\nFonctionnalité: F\n", steps_content="from behave import when\n",
        title=title)
    CaseRepo(conn).set_current_version(cid, vid)
    return cid, vid


# ── Le schéma ─────────────────────────────────────────────────────────────────

def test_les_champs_metier_sont_sur_la_VERSION_et_les_metadonnees_sur_le_cas(conn):
    """Décision 10 : une version = le cas entier. Les métadonnées, elles, ne versionnent pas."""
    vcols = {r["name"] for r in conn.execute("PRAGMA table_info(test_case_version)")}
    assert {"title", "preconditions", "test_steps", "expected_result"} <= vcols
    # `angle` a quitté la version avec la migration 26 (TestRail n'a pas ce champ).
    assert "angle" not in vcols

    ccols = {r["name"] for r in conn.execute("PRAGMA table_info(test_case)")}
    assert {"refs", "estimate"} <= ccols
    # ⚠️ `refs` et non `references` : REFERENCES est un mot-clé SQL réservé.
    assert "references" not in ccols


def test_migration_14_ne_FABRIQUE_aucun_contenu(tmp_path):
    """Arbitrage A.1 : la migration reprend le titre/l'angle (connus du cas), mais laisse les
    champs de CONTENU vides. Les dériver du Gherkin reviendrait à stocker du texte machine qui
    aurait ensuite l'air rédigé par un humain."""
    db = tmp_path / "pre14.db"
    raw = sqlite3.connect(str(db))
    raw.row_factory = sqlite3.Row
    raw.execute("CREATE TABLE test_case (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT,"
                " angle TEXT DEFAULT '')")
    raw.execute("CREATE TABLE test_case_version (id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " test_case_id INTEGER, feature_content TEXT DEFAULT '')")
    raw.execute("INSERT INTO test_case (id, title, angle) VALUES (1, 'Demande', 'nominal')")
    raw.execute("INSERT INTO test_case_version (test_case_id, feature_content)"
                " VALUES (1, 'Quand je clique…')")
    raw.commit()

    _migrate_14_champs_metier(raw)
    raw.commit()

    v = dict(raw.execute("SELECT * FROM test_case_version WHERE test_case_id=1").fetchone())
    assert v["title"] == "Demande", "le titre est repris du cas (il n'existait pas sur la version)"
    assert v["angle"] == "nominal"
    assert v["preconditions"] == "" and v["test_steps"] == "" and v["expected_result"] == "", \
        "le CONTENU reste vide : la migration ne dérive rien du Gherkin"
    raw.close()


def test_migration_14_est_idempotente(conn):
    _migrate_14_champs_metier(conn)
    _migrate_14_champs_metier(conn)   # rejouée : aucune erreur, aucune colonne en double
    vcols = [r["name"] for r in conn.execute("PRAGMA table_info(test_case_version)")]
    assert vcols.count("preconditions") == 1


# ── L'invariant : éditer CRÉE une version ─────────────────────────────────────

def test_editer_le_metier_CREE_une_version_et_n_ecrase_jamais(conn):
    cid, vid = _cas(conn)
    cases = CaseRepo(conn)

    steps = json.dumps(["Se connecter", "Ouvrir la page des services"])
    new_vid = cases.update_metier(cid, preconditions="Un employé connecté.", test_steps=steps,
                                  expected_result="La demande est enregistrée.", editor="romaric")

    assert new_vid is not None and new_vid != vid, "une édition doit créer une NOUVELLE version"
    # L'ancienne version est INTACTE — c'est ce qui rend l'historique diffable.
    ancienne = VersionRepo(conn).get(vid)
    assert ancienne["preconditions"] == "" and ancienne["test_steps"] == ""
    nouvelle = VersionRepo(conn).get(new_vid)
    assert nouvelle["preconditions"] == "Un employé connecté."
    assert json.loads(nouvelle["test_steps"]) == ["Se connecter", "Ouvrir la page des services"]
    assert nouvelle["created_by"] == "romaric"
    # Le cas pointe désormais sur la nouvelle version.
    assert cases.get(cid)["current_version_id"] == new_vid


def test_le_technique_est_RECOPIE_tel_quel_lors_d_une_edition_metier(conn):
    """Décision 6 : éditer le métier ne régénère PAS le Gherkin — on signale la divergence,
    l'humain régénère quand il veut."""
    cid, vid = _cas(conn)
    avant = VersionRepo(conn).get(vid)

    new_vid = CaseRepo(conn).update_metier(cid, expected_result="Un ticket est créé.")

    apres = VersionRepo(conn).get(new_vid)
    assert apres["feature_content"] == avant["feature_content"]
    assert apres["steps_content"] == avant["steps_content"]


def test_une_edition_SANS_changement_ne_cree_pas_de_version_fantome(conn):
    cid, vid = _cas(conn)
    cases = CaseRepo(conn)
    cases.update_metier(cid, preconditions="Un employé connecté.")

    # Re-soumettre exactement la même valeur ne doit rien créer.
    assert cases.update_metier(cid, preconditions="Un employé connecté.") is None
    assert len(VersionRepo(conn).list_for_case(cid)) == 2   # v1 + la seule édition réelle


def test_les_metadonnees_ne_creent_PAS_de_version(conn):
    """`refs`/`estimate` ne changent pas ce que le test vérifie : les versionner gonflerait
    l'historique pour rien (décision 3b)."""
    cid, _vid = _cas(conn)
    cases = CaseRepo(conn)

    assert cases.update_metier(cid, refs="JIRA-42", estimate="15m") is None
    assert len(VersionRepo(conn).list_for_case(cid)) == 1
    case = cases.get(cid)
    assert case["refs"] == "JIRA-42" and case["estimate"] == "15m"


def test_le_cas_porte_une_COPIE_du_titre_la_version_fait_foi(conn):
    """Le cas garde les valeurs courantes pour les listes/filtres ; la version reste la vérité."""
    cid, _vid = _cas(conn)
    cases = CaseRepo(conn)

    new_vid = cases.update_metier(cid, title="Demande de matériel informatique")

    assert cases.get(cid)["title"] == "Demande de matériel informatique"   # la copie suit
    assert VersionRepo(conn).get(new_vid)["title"] == "Demande de matériel informatique"


# ── Conséquence sur le gate ───────────────────────────────────────────────────

def test_une_edition_metier_REBLOQUE_le_gate(conn):
    """La nouvelle version n'est pas approuvée → l'exécution est bloquée jusqu'à relecture.
    L'invariant §4.3 s'applique tout seul, sans règle supplémentaire."""
    from testpilot.verdict import review_gate

    cid, vid = _cas(conn)
    ReviewRepo(conn).create(test_case_id=cid, version_id=vid, decision="approved", reviewer="qa")
    assert review_gate.evaluate_gate(ReviewRepo(conn), vid).allowed is True

    new_vid = CaseRepo(conn).update_metier(cid, expected_result="Un ticket est créé.")

    assert review_gate.evaluate_gate(ReviewRepo(conn), new_vid).allowed is False


# ── L'API ─────────────────────────────────────────────────────────────────────

def test_api_patch_metier_expose_la_version_creee(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from testpilot import config
    from testpilot.api import app as app_mod

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    c = get_initialized_db(config.DB_PATH)
    cid, _vid = _cas(c)
    c.close()

    client = TestClient(app_mod.app)
    r = client.patch(f"/api/cases/{cid}/metier",
                     json={"preconditions": "Un employé connecté.", "editor": "qa"})

    assert r.status_code == 200
    assert r.json()["version_created"] is True
    detail = client.get(f"/api/cases/{cid}").json()
    courante = next(v for v in detail["versions"] if v["id"] == detail["current_version_id"])
    assert courante["preconditions"] == "Un employé connecté."
