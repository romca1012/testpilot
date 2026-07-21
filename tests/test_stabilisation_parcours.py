"""Stabilisation du parcours par l'interface : création manuelle, suppressions, import fichier.

Les deux boutons ont des rôles DISTINCTS (correction du porteur, 2026-07-21) :
- « Ajouter un cas de test » = créer un cas À LA MAIN (métier, sans IA) → `create_manual` ;
- « Générer des cas de test » = l'IA depuis une spec (texte OU fichier).

Et le parcours doit inclure la SUPPRESSION de projet / module / cas si l'utilisateur le veut.
"""

import io
import json

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import app as app_mod
from testpilot.api.services import spec_extract
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import (
    CaseRepo,
    ExecutionRepo,
    ModuleRepo,
    VersionRepo,
    ensure_default_module,
)


@pytest.fixture
def conn(tmp_path):
    c = get_initialized_db(tmp_path / "s.db")
    yield c
    c.close()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    return TestClient(app_mod.app)


def _module(client) -> tuple[int, int]:
    pid = client.post("/api/projects", json={"name": "P"}).json()["id"]
    mid = client.post(f"/api/projects/{pid}/modules", json={"name": "M"}).json()["id"]
    return pid, mid


# ── Création MANUELLE (bouton « Ajouter ») ────────────────────────────────────

def test_creer_un_cas_a_la_main_SANS_ia(conn):
    """Le cas naît avec son métier mais SANS Gherkin — non exécutable tant qu'aucun test
    technique n'est généré. Ce n'est PAS le cas fantôme de `0006` : il décrit une intention."""
    mid = ensure_default_module(conn, "m")
    cid = CaseRepo(conn).create_manual(
        module_id=mid, title="Connexion avec un mot de passe valide",
        preconditions="Un compte actif existe.",
        test_steps=json.dumps(["Ouvrir la page de connexion", "Saisir les identifiants",
                               "Valider"]),
        expected_result="L'utilisateur accède à son tableau de bord.")

    case = CaseRepo(conn).get(cid)
    assert case["origin"] == "manual_converted", "origine humaine, pas ia_generated"
    version = VersionRepo(conn).get(case["current_version_id"])
    assert version["preconditions"] == "Un compte actif existe."
    assert json.loads(version["test_steps"])[0] == "Ouvrir la page de connexion"
    assert version["feature_content"] == "", "pas de Gherkin : le cas manuel n'est pas exécutable"


def test_api_ajouter_cas_manuel(client):
    _, mid = _module(client)

    r = client.post(f"/api/modules/{mid}/cases/manual", json={
        "title": "Cas manuel", "preconditions": "P",
        "test_steps": ["étape 1", "étape 2"], "expected_result": "Le résultat attendu."})

    assert r.status_code == 201
    assert r.json()["title"] == "Cas manuel"
    # Il apparaît dans la liste du module comme n'importe quel cas.
    assert any(c["title"] == "Cas manuel" for c in client.get(f"/api/cases?module_id={mid}").json())


def test_api_cas_manuel_exige_titre_etapes_resultat(client):
    _, mid = _module(client)

    r = client.post(f"/api/modules/{mid}/cases/manual", json={
        "title": "Sans étapes", "test_steps": [], "expected_result": "x"})

    assert r.status_code == 422
    assert "obligatoires" in r.json()["detail"]


# ── Suppressions (projet / module / cas) ──────────────────────────────────────

def test_supprimer_un_cas_emporte_sa_descendance(client):
    _, mid = _module(client)
    cid = client.post(f"/api/modules/{mid}/cases/manual", json={
        "title": "À supprimer", "test_steps": ["a"], "expected_result": "r"}).json()["id"]

    assert client.delete(f"/api/cases/{cid}").status_code == 204
    assert client.get(f"/api/cases/{cid}").status_code == 404


def test_supprimer_un_cas_emporte_sa_specification_AUTO(conn):
    """⚠️ Défaut réel (2026-07-21) : `create()` auto-enveloppe un cas dans sa propre Spécification
    1:1, mais `delete()` laissait cette enveloppe VIDE derrière lui. Résultat : des Spécifications
    fantômes à 0 cas (8 dans la vraie base), visibles dans l'arbre, et qui **bloquaient la
    regénération du même titre** (unicité par module). Le banc de mesure l'a fait tomber."""
    from testpilot.store.repositories import CaseGroupRepo

    mid = ensure_default_module(conn, "m")
    cid = CaseRepo(conn).create_manual(module_id=mid, title="Jetable",
                                       test_steps=json.dumps(["a"]), expected_result="r")
    gid = CaseRepo(conn).get(cid)["group_id"]
    assert CaseGroupRepo(conn).get(gid) is not None

    CaseRepo(conn).delete(cid)

    assert CaseGroupRepo(conn).get(gid) is None, "l'enveloppe automatique part avec son cas"
    # …et le titre redevient disponible : c'est ce qui débloquait la regénération.
    CaseRepo(conn).create_manual(module_id=mid, title="Jetable",
                                 test_steps=json.dumps(["a"]), expected_result="r")


def test_une_specification_AVEC_DOCUMENT_survit_a_ses_cas(conn):
    """Règle prudente : une Spécification rédigée par un humain est un ACTIF — on peut vouloir
    regénérer depuis elle. Seule l'enveloppe technique vide est un résidu."""
    from testpilot.store.repositories import CaseGroupRepo

    mid = ensure_default_module(conn, "m")
    gid = CaseGroupRepo(conn).create(module_id=mid, title="Spec rédigée",
                                     spec_content="Le document complet de la spec")
    cid = CaseRepo(conn).create(title="Cas", module_id=mid, group_id=gid, feature_slug="c")

    CaseRepo(conn).delete(cid)

    assert CaseGroupRepo(conn).get(gid) is not None, "un document rédigé ne se perd pas"


def test_supprimer_un_module_emporte_ses_cas(client):
    _, mid = _module(client)
    client.post(f"/api/modules/{mid}/cases/manual", json={
        "title": "C1", "test_steps": ["a"], "expected_result": "r"})
    client.post(f"/api/modules/{mid}/cases/manual", json={
        "title": "C2", "test_steps": ["a"], "expected_result": "r"})

    assert client.delete(f"/api/modules/{mid}").status_code == 204

    conn = get_initialized_db(config.DB_PATH)
    assert conn.execute("SELECT COUNT(*) FROM test_case").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM case_group").fetchone()[0] == 0
    conn.close()


def test_supprimer_un_module_avec_des_RUNS_les_emporte_aussi(conn):
    """La cascade doit atteindre exécutions et résultats, pas seulement les cas."""
    mid = ensure_default_module(conn, "m")
    cid = CaseRepo(conn).create_manual(module_id=mid, title="C", test_steps=json.dumps(["a"]),
                                       expected_result="r")
    vid = CaseRepo(conn).get(cid)["current_version_id"]
    eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid)
    ExecutionRepo(conn).finalize(eid, execution_status="success", functional_status="conforme",
                                 scenarios_total=1, scenarios_passed=1, scenarios_failed=0,
                                 duration_seconds=1.0, iterations=0, cost_usd=0.0)

    ModuleRepo(conn).delete(mid)

    assert conn.execute("SELECT COUNT(*) FROM execution").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM module WHERE id=?", (mid,)).fetchone()[0] == 0


def test_supprimer_module_ou_cas_inconnu_404(client):
    assert client.delete("/api/modules/999").status_code == 404
    assert client.delete("/api/cases/999").status_code == 404


# ── Renommer un module (« Éditer la section ») ────────────────────────────────

def test_renommer_un_module(client):
    _, mid = _module(client)

    r = client.patch(f"/api/modules/{mid}", json={"name": "Nouveau nom"})

    assert r.status_code == 200
    assert r.json()["name"] == "Nouveau nom"
    assert client.get(f"/api/modules/{mid}").json()["module"]["name"] == "Nouveau nom"


def test_renommer_vers_un_nom_deja_pris_dans_le_projet_409(client):
    pid = client.post("/api/projects", json={"name": "P"}).json()["id"]
    client.post(f"/api/projects/{pid}/modules", json={"name": "Alpha"})
    m2 = client.post(f"/api/projects/{pid}/modules", json={"name": "Beta"}).json()["id"]

    r = client.patch(f"/api/modules/{m2}", json={"name": "alpha"})

    assert r.status_code == 409


def test_renommer_module_inconnu_404_et_nom_vide_422(client):
    _, mid = _module(client)
    assert client.patch("/api/modules/999", json={"name": "X"}).status_code == 404
    assert client.patch(f"/api/modules/{mid}", json={"name": "  "}).status_code == 422


# ── Import de fichier (bouton « Générer ») ────────────────────────────────────

def test_extraction_txt_et_md():
    assert spec_extract.extract_text("spec.txt", "bonjour".encode()) == "bonjour"
    assert "titre" in spec_extract.extract_text("spec.md", "# titre\ncorps".encode())


def test_extraction_latin1_ne_plante_pas():
    """Un fichier non-UTF-8 ne doit pas casser l'import : repli Latin-1 documenté."""
    txt = spec_extract.extract_text("v.txt", "café résumé".encode("latin-1"))
    assert "caf" in txt


def test_extraction_pdf_REFUSEE_avec_message_clair():
    """Pas de dépendance PDF : on le dit, on ne rend pas un texte vide silencieux (§4.6)."""
    with pytest.raises(spec_extract.UnsupportedFormat) as exc:
        spec_extract.extract_text("doc.pdf", b"%PDF-1.4 ...")
    assert "PDF" in str(exc.value)


def test_api_extract_upload(client):
    _, mid = _module(client)

    r = client.post(f"/api/modules/{mid}/cases/extract",
                    files={"file": ("ma_spec.md", io.BytesIO("# Ma spec\nDétails".encode()),
                                    "text/markdown")})

    assert r.status_code == 200
    assert "Ma spec" in r.json()["text"]
    assert r.json()["filename"] == "ma_spec.md"


def test_api_extract_pdf_renvoie_422(client):
    _, mid = _module(client)

    r = client.post(f"/api/modules/{mid}/cases/extract",
                    files={"file": ("doc.pdf", io.BytesIO(b"%PDF"), "application/pdf")})

    assert r.status_code == 422
    assert "PDF" in r.json()["detail"]
