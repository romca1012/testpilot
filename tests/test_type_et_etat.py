"""Type et État d'un cas — et l'invariant qui les distingue de l'ancien statut de validation.

⚠️ **Ce que ce fichier empêche de revenir.** `validation_status` prétendait être un cycle de vie
alors qu'il était *dérivé* : cinq endroits du code l'écrivaient automatiquement (une exécution,
une génération, une réparation, un rejet de relecture…), et **aucun humain ne pouvait le poser**.
Résultat : l'écran affichait un champ « État » sur lequel l'utilisateur n'avait aucune prise, et
qui ne répondait pas à la question qu'il pose — *où en est la rédaction de ce cas ?*

`etat` est son remplaçant, et il n'est un remplaçant qu'à une condition : **que rien d'autre que
l'utilisateur ne l'écrive**. C'est l'invariant testé ici, sur les trois chemins qui touchaient
l'ancien champ. Le jour où quelqu'un rebranche un automatisme « par commodité », un de ces tests
tombe — et c'est tout l'intérêt.

Le Type suit la même logique, avec un piège en moins : personne n'a jamais tenté de le dériver.
Il est testé ici pour son vocabulaire, refusé côté **API** et non côté base (les colonnes sont du
texte libre, pour qu'un administrateur puisse l'étendre sans migration).
"""
import pytest
from fastapi.testclient import TestClient

from testpilot.api.app import app
from testpilot.api.deps import get_conn
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, ModuleRepo, ProjectRepo, VersionRepo


@pytest.fixture
def conn(tmp_path):
    c = get_initialized_db(tmp_path / "etat.db")
    yield c
    c.close()


@pytest.fixture
def client(conn):
    app.dependency_overrides[get_conn] = lambda: conn
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _cas(conn, titre: str = "Nominal") -> int:
    pid = ProjectRepo(conn).create(name=f"P-{titre}")
    mid = ModuleRepo(conn).create(project_id=pid, name=f"M-{titre}")
    return CaseRepo(conn).create(title=titre, module_id=mid)


# ── Les défauts ──────────────────────────────────────────────────────────────

def test_un_cas_naît_fonctionnel_et_nouveau(conn):
    cas = CaseRepo(conn).get(_cas(conn))
    assert cas["type"] == "fonctionnel"
    assert cas["etat"] == "new"


# ── L'invariant : l'État appartient à l'humain ───────────────────────────────

def test_generer_une_version_ne_touche_pas_a_l_etat(conn):
    """Chemin n°1 : la génération. Elle repositionnait le cas (`never_executed`/`to_review`).

    Ce que la relecture doit rouvrir, c'est le GATE — et il porte sur la version, qui vient de
    naître non approuvée. L'État du document, lui, n'a aucune raison de bouger : le cas n'a pas
    été moins bien rédigé parce qu'on a régénéré son Gherkin.
    """
    cid = _cas(conn)
    cases = CaseRepo(conn)
    cases.set_metadonnees(cid, etat="ready")

    VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="",
                             feature_content="# language: fr", steps_content="x")
    assert cases.get(cid)["etat"] == "ready"


def test_une_execution_ne_touche_pas_a_l_etat(conn):
    """Chemin n°2 : l'exécution, qui « validait » le cas dès qu'un run passait au vert.

    Un test qui tourne ne dit rien de la qualité de sa RÉDACTION — il dit que l'application se
    comporte (ou non) comme attendu. Confondre les deux, c'est ce que faisait l'ancien champ.
    """
    cid = _cas(conn)
    cases = CaseRepo(conn)
    cases.set_metadonnees(cid, etat="design")

    cases.update_last_outcome(cid, execution_status="success", functional_status="conforme",
                              executed_at="2026-08-04T10:00:00+00:00")
    apres = cases.get(cid)
    assert apres["etat"] == "design", "une exécution verte ne 'valide' plus le document"
    assert apres["last_execution_status"] == "success", "…mais le résultat, lui, est bien inscrit"


def test_l_api_refuse_une_valeur_hors_vocabulaire(client, conn):
    """Chemin n°3 : l'écriture volontaire. Elle est la seule autorisée — et elle est contrôlée.

    ⚠️ Le refus vit dans l'API, pas dans un `CHECK` de la base : `type` et `etat` sont du texte
    libre en base, exprès, pour qu'ajouter « Sécurité » plus tard ne demande pas de migration.
    La contrepartie, c'est que ce test est le SEUL garde-fou — d'où sa présence ici.
    """
    cid = _cas(conn)
    assert client.patch(f"/api/cases/{cid}", json={"etat": "ready"}).json()["etat"] == "ready"
    assert client.patch(f"/api/cases/{cid}", json={"type": "non_fonctionnel"}
                        ).json()["type"] == "non_fonctionnel"

    refus = client.patch(f"/api/cases/{cid}", json={"etat": "validated"})
    assert refus.status_code == 422
    assert client.patch(f"/api/cases/{cid}", json={"type": "automatise"}).status_code == 422
    # …et le refus n'a rien écrit au passage.
    cas = CaseRepo(conn).get(cid)
    assert (cas["etat"], cas["type"]) == ("ready", "non_fonctionnel")


def test_modifier_un_seul_champ_n_ecrase_pas_les_autres(client, conn):
    """Un PATCH partiel est partiel. Sans ça, l'écran qui change l'État renverrait aussi une
    priorité — celle qu'il avait chargée — et écraserait en silence celle qu'un autre onglet
    vient de modifier."""
    cid = _cas(conn)
    CaseRepo(conn).set_metadonnees(cid, priority="high", type="non_fonctionnel", etat="design")

    client.patch(f"/api/cases/{cid}", json={"etat": "ready"})
    cas = CaseRepo(conn).get(cid)
    assert (cas["etat"], cas["priority"], cas["type"]) == ("ready", "high", "non_fonctionnel")


def test_le_depot_refuse_un_champ_qu_il_ne_connait_pas(conn):
    """`set_metadonnees` est générique : sans cette garde, une faute de frappe (`etats=…`) serait
    silencieusement ignorée, et l'écran afficherait l'ancienne valeur sans que rien n'ait échoué."""
    cid = _cas(conn)
    with pytest.raises(ValueError):
        CaseRepo(conn).set_metadonnees(cid, statut="ready")
