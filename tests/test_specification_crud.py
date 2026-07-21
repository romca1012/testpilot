"""CRUD de la SPÉCIFICATION (`case_group`) — chantier 1 du plan validé (2026-07-20).

La Spécification est LE DOCUMENT source (décision `0022`) : elle produit **1 à N cas** selon les
angles que l'humain retient — jamais une découpe automatique. Avant ce chantier, seule la LECTURE
existait (`GET /projects/{id}/groups`) : on ne pouvait ni créer, ni éditer, ni supprimer une
spécification, donc l'étape 3 (génération « un angle par appel ») n'avait aucun document à lire.

Ce que ces tests figent :
- créer une spécification ne génère AUCUN cas et ne dépense RIEN (elle nomme un document) ;
- `spec_hash` est RECALCULÉ, jamais reçu — une empreinte ne doit pas pouvoir mentir ;
- éditer le document ne crée aucune version et ne rebloque aucun gate (ils vivent sur le CAS) ;
- supprimer une spécification qui porte des cas est REFUSÉ (pas de cascade sur de l'historique).
"""

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.analysis.spec_analyzer import spec_hash
from testpilot.api import app as app_mod
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import (
    CaseGroupRepo,
    CaseRepo,
    NotEmpty,
    ensure_default_module,
)


@pytest.fixture
def conn(tmp_path):
    c = get_initialized_db(tmp_path / "spec.db")
    yield c
    c.close()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    return TestClient(app_mod.app)


def _module(client) -> int:
    """Un module réel via l'API, pour y accrocher des spécifications."""
    pid = client.post("/api/projects", json={"name": "Portail Sapian"}).json()["id"]
    return client.post(f"/api/projects/{pid}/modules",
                       json={"name": "Demande matériel"}).json()["id"]


# ── Repo : édition ────────────────────────────────────────────────────────────

def test_update_partiel_ne_touche_que_ce_qui_est_fourni(conn):
    """`None` veut dire « ne touche pas », jamais « vide-le » — sinon éditer le titre effacerait
    le document."""
    mid = ensure_default_module(conn, "demande_materiel")
    repo = CaseGroupRepo(conn)
    gid = repo.create(module_id=mid, title="Demande", description="résumé court")
    repo.update(gid, spec_content="Le document complet")

    repo.update(gid, title="Demande de matériel")

    g = repo.get(gid)
    assert g["title"] == "Demande de matériel"
    assert g["spec_content"] == "Le document complet", "le document survit à un renommage"
    assert g["description"] == "résumé court"


def test_le_hash_est_RECALCULE_a_chaque_changement_de_document(conn):
    """⚠️ Invariant : `spec_hash` décrit TOUJOURS le `spec_content` qu'il accompagne.

    C'est ce hash qui détectera « ce cas est né d'une spec dépassée » (`0022` n°6). Une empreinte
    qui ne correspond pas à son document est un champ qui ment — le `position` décoratif de
    `0006`, appliqué à la traçabilité. Le repo ne l'accepte donc PAS en entrée : il le calcule.
    """
    mid = ensure_default_module(conn, "demande_materiel")
    repo = CaseGroupRepo(conn)
    gid = repo.create(module_id=mid, title="Demande")

    repo.update(gid, spec_content="version 1 du document")
    h1 = repo.get(gid)["spec_hash"]
    assert h1 == spec_hash("version 1 du document")

    repo.update(gid, spec_content="version 2 du document")
    h2 = repo.get(gid)["spec_hash"]
    assert h2 == spec_hash("version 2 du document")
    assert h1 != h2, "un document modifié change d'empreinte — c'est le signal de « dépassée »"


def test_renommer_vers_un_titre_deja_pris_dans_le_module_est_refuse(conn):
    from testpilot.store.repositories import DuplicateName
    mid = ensure_default_module(conn, "demande_materiel")
    repo = CaseGroupRepo(conn)
    repo.create(module_id=mid, title="Demande")
    g2 = repo.create(module_id=mid, title="Retour")

    with pytest.raises(DuplicateName):
        repo.update(g2, title="  demande ")  # même clé Unicode/espaces


def test_se_renommer_a_l_identique_ne_se_bloque_pas_soi_meme(conn):
    """Le garde d'unicité doit s'exclure lui-même : sinon renommer « Demande » → « Demande »
    (ou changer sa casse) échouerait contre sa PROPRE ligne."""
    mid = ensure_default_module(conn, "demande_materiel")
    repo = CaseGroupRepo(conn)
    gid = repo.create(module_id=mid, title="Demande")

    repo.update(gid, title="DEMANDE")

    assert repo.get(gid)["title"] == "DEMANDE"


# ── Repo : suppression ────────────────────────────────────────────────────────

def test_supprimer_une_specification_qui_porte_des_cas_est_REFUSE(conn):
    """Pas de cascade, délibérément (§2.10 : on ne détruit pas d'historique en silence).

    Un cas porte des versions, des exécutions et des lignes de coût. Les emporter parce qu'on
    supprime leur conteneur détruirait ce que le projet passe son temps à préserver.
    """
    mid = ensure_default_module(conn, "demande_materiel")
    repo = CaseGroupRepo(conn)
    gid = repo.create(module_id=mid, title="Demande")
    CaseRepo(conn).create(title="Nominal", module_id=mid, group_id=gid, feature_slug="n")

    with pytest.raises(NotEmpty):
        repo.delete(gid)

    assert repo.get(gid) is not None, "la spécification est INTACTE après un refus"
    assert conn.execute("SELECT COUNT(*) FROM test_case").fetchone()[0] == 1, "le cas aussi"


def test_supprimer_une_specification_vide_fonctionne(conn):
    mid = ensure_default_module(conn, "demande_materiel")
    repo = CaseGroupRepo(conn)
    gid = repo.create(module_id=mid, title="Brouillon abandonné")

    repo.delete(gid)

    assert repo.get(gid) is None


# ── API ───────────────────────────────────────────────────────────────────────

def test_api_cycle_complet_creer_lire_editer_supprimer(client):
    mid = _module(client)

    created = client.post(f"/api/modules/{mid}/groups",
                          json={"title": "Demande de matériel",
                                "spec_content": "Le document source complet"})
    assert created.status_code == 201
    gid = created.json()["id"]
    assert created.json()["spec_hash"] == spec_hash("Le document source complet")

    assert client.get(f"/api/modules/{mid}/groups").json()[0]["title"] == "Demande de matériel"

    detail = client.get(f"/api/groups/{gid}")
    assert detail.status_code == 200
    assert detail.json()["spec_content"] == "Le document source complet"

    patched = client.patch(f"/api/groups/{gid}", json={"spec_content": "Document révisé"})
    assert patched.status_code == 200
    assert patched.json()["spec_content"] == "Document révisé"
    assert patched.json()["spec_hash"] == spec_hash("Document révisé")

    assert client.delete(f"/api/groups/{gid}").status_code == 204
    assert client.get(f"/api/groups/{gid}").status_code == 404


def test_api_creer_une_specification_ne_genere_AUCUN_cas(client):
    """⚠️ Créer une spécification nomme un DOCUMENT — ça ne lance pas la génération.

    C'est l'étape 3 qui lira ce document, APRÈS que l'humain aura confirmé les angles voulus
    (§4bis du brief). Créer un conteneur ne doit engager aucune dépense LLM non demandée — même
    principe que le lancement explicite d'un run (`0022` n°8.c.1). Ce test échouerait si
    quelqu'un rebranchait la génération sur la création.
    """
    mid = _module(client)

    r = client.post(f"/api/modules/{mid}/groups", json={"title": "Demande", "spec_content": "doc"})

    assert r.status_code == 201
    assert r.json()["case_count"] == 0
    assert client.get(f"/api/cases?module_id={mid}").json() == []


def test_api_une_specification_peut_naitre_SANS_document(client):
    """On nomme la spécification d'abord, on la rédige ensuite. C'est la GÉNÉRATION qui exigera
    un document non vide, pas le conteneur — le refuser ici interdirait le brouillon."""
    mid = _module(client)

    r = client.post(f"/api/modules/{mid}/groups", json={"title": "À rédiger"})

    assert r.status_code == 201
    assert r.json()["spec_content"] == ""
    assert r.json()["spec_hash"] == "", "pas de document ⇒ pas d'empreinte fabriquée"


def test_api_titre_vide_refuse_et_doublon_en_409(client):
    mid = _module(client)
    client.post(f"/api/modules/{mid}/groups", json={"title": "Demande"})

    assert client.post(f"/api/modules/{mid}/groups", json={"title": "   "}).status_code == 422
    dup = client.post(f"/api/modules/{mid}/groups", json={"title": "demande"})
    assert dup.status_code == 409
    assert "demande" in dup.json()["detail"].lower(), "le message NOMME le conflit"


def test_api_supprimer_une_specification_peuplee_renvoie_409_et_dit_combien(client):
    mid = _module(client)
    gid = client.post(f"/api/modules/{mid}/groups", json={"title": "Demande"}).json()["id"]
    conn = get_initialized_db(config.DB_PATH)
    CaseRepo(conn).create(title="Nominal", module_id=mid, group_id=gid, feature_slug="n")
    conn.close()

    r = client.delete(f"/api/groups/{gid}")

    assert r.status_code == 409
    assert "1 cas" in r.json()["detail"], "le refus dit ce qui bloque, il ne se contente pas de refuser"
    assert client.get(f"/api/groups/{gid}").status_code == 200, "rien n'a été supprimé"


def test_api_404_sur_module_et_specification_inconnus(client):
    assert client.post("/api/modules/999/groups", json={"title": "X"}).status_code == 404
    assert client.get("/api/modules/999/groups").status_code == 404
    assert client.get("/api/groups/999").status_code == 404
    assert client.patch("/api/groups/999", json={"title": "X"}).status_code == 404
    assert client.delete("/api/groups/999").status_code == 404


def test_api_la_liste_ne_transporte_PAS_les_documents(client):
    """`GroupSummary` volontairement sans `spec_content` : une liste de 40 spécifications ne doit
    pas charger 40 documents complets. L'écran d'édition les prend un par un."""
    mid = _module(client)
    client.post(f"/api/modules/{mid}/groups", json={"title": "Demande", "spec_content": "x" * 5000})

    row = client.get(f"/api/modules/{mid}/groups").json()[0]

    assert "spec_content" not in row
