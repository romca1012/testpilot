"""La SUPPRESSION DOUCE — aligner le produit sur son propre §7 (lot B, 2026-07-24).

**L'écart corrigé.** Le §7 du brief interdit qu'une purge soit une « suppression sèche » : tout
nettoyage doit être précédé d'une sauvegarde récupérable. Or `delete_project` exécutait **douze
`DELETE FROM` en cascade** — projet, modules, spécifications, cas, versions, relectures,
exécutions, résultats, réparations, coûts. Un clic, et des mois d'historique disparaissaient
sans retour possible. C'était le seul endroit du produit où le principe était violé.

**Ce que ces tests exigent** — et l'ordre compte :

  1. supprimer **cache** : l'élément ne doit apparaître dans AUCUNE liste, AUCUN compteur, AUCUN
     détail. ⚠️ C'est le vrai risque du chantier : un filtre oublié quelque part, et un élément
     supprimé réapparaît dans un compteur. Chaque surface est donc vérifiée nommément ;
  2. supprimer **ne détruit rien** : la ligne est toujours là, restaurable ;
  3. la **purge définitive** existe, mais c'est un geste distinct et explicite.
"""

import pytest

from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import (
    CaseGroupRepo,
    CaseRepo,
    ModuleRepo,
    ProjectRepo,
    VersionRepo,
)


@pytest.fixture
def conn(tmp_path):
    c = get_initialized_db(tmp_path / "douce.db")
    yield c
    c.close()


def _arbre(conn):
    """Un projet complet : 1 projet → 1 module → 1 spécification → 2 cas."""
    pid = ProjectRepo(conn).create(name="Recette", connector_type="odoo",
                                   base_url="http://x", database="db",
                                   username="qa", password="p")
    mid = ModuleRepo(conn).create(project_id=pid, name="Demandes")
    gid = CaseGroupRepo(conn).create(module_id=mid, title="Déclaration")
    c1 = CaseRepo(conn).create(title="Cas A", module_id=mid, group_id=gid, feature_slug="a")
    c2 = CaseRepo(conn).create(title="Cas B", module_id=mid, group_id=gid, feature_slug="b")
    return pid, mid, gid, c1, c2


# ── 1. Supprimer CACHE — toutes les surfaces ─────────────────────────────────

def test_un_cas_supprime_disparait_de_TOUTES_les_surfaces(conn):
    """⚠️ Le vrai risque du chantier : un filtre oublié, et le cas revient dans un compteur.

    On vérifie chaque surface NOMMÉMENT plutôt que « la liste est vide » : c'est la seule façon
    qu'un ajout futur de compteur ne passe pas silencieusement à travers.
    """
    pid, mid, gid, c1, c2 = _arbre(conn)
    CaseRepo(conn).delete(c1, par="Awa")

    assert CaseRepo(conn).get(c1) is None                                   # détail
    assert [c["id"] for c in CaseRepo(conn).list_all(project_id=pid)] == [c2]   # liste projet
    assert [c["id"] for c in CaseRepo(conn).list_all(module_id=mid)] == [c2]    # liste module
    assert ModuleRepo(conn).list_for_project(pid)[0]["case_count"] == 1      # compteur module
    assert CaseGroupRepo(conn).list_for_module(mid)[0]["case_count"] == 1    # compteur spec
    assert CaseGroupRepo(conn).case_count(gid) == 1                          # compteur direct
    assert ProjectRepo(conn).list_all()[0]["case_count"] == 1                # compteur projet


def test_un_module_supprime_emporte_ses_cas_DE_L_AFFICHAGE(conn):
    """Masquer le module sans masquer ses cas laisserait des orphelins visibles dans la liste
    des cas du projet — un état qui n'existe dans aucun écran."""
    pid, mid, gid, c1, c2 = _arbre(conn)
    ModuleRepo(conn).delete(mid, par="Awa")

    assert ModuleRepo(conn).get(mid) is None
    assert ModuleRepo(conn).list_for_project(pid) == []
    assert CaseRepo(conn).list_all(project_id=pid) == []
    assert CaseGroupRepo(conn).list_for_project(pid) == []
    assert ProjectRepo(conn).list_all()[0]["module_count"] == 0
    assert ProjectRepo(conn).list_all()[0]["case_count"] == 0


def test_un_projet_supprime_disparait_avec_toute_sa_descendance(conn):
    pid, mid, gid, c1, c2 = _arbre(conn)
    ProjectRepo(conn).delete(pid, par="Awa")

    assert ProjectRepo(conn).get(pid) is None
    assert ProjectRepo(conn).list_all() == []
    assert ProjectRepo(conn).first() is None
    assert ProjectRepo(conn).find_by_name("Recette") is None
    assert ModuleRepo(conn).list_for_project(pid) == []
    assert CaseRepo(conn).list_all(project_id=pid) == []


def test_le_nom_d_un_element_supprime_est_REUTILISABLE(conn):
    """Sinon un nom resterait pris par un élément que plus personne ne voit — l'utilisateur
    buterait sur « nom déjà utilisé » sans pouvoir comprendre pourquoi."""
    pid, mid, _, _, _ = _arbre(conn)
    ModuleRepo(conn).delete(mid, par="Awa")

    nouveau = ModuleRepo(conn).create(project_id=pid, name="Demandes")   # ne doit pas lever
    assert nouveau != mid


# ── 2. Supprimer NE DÉTRUIT RIEN ─────────────────────────────────────────────

def test_rien_n_est_detruit_et_l_historique_survit(conn):
    """La promesse du §7 : « nettoyer » signifie archiver, jamais détruire sans filet."""
    pid, mid, gid, c1, c2 = _arbre(conn)
    vid = VersionRepo(conn).create(test_case_id=c1, spec_content="", spec_hash="",
                                   feature_content="F", steps_content="S")
    ProjectRepo(conn).delete(pid, par="Awa")

    # Les lignes sont TOUJOURS là — c'est toute la différence avec la cascade d'avant.
    assert conn.execute("SELECT COUNT(*) AS n FROM test_case").fetchone()["n"] == 2
    assert conn.execute("SELECT COUNT(*) AS n FROM test_case_version").fetchone()["n"] == 1
    assert conn.execute("SELECT COUNT(*) AS n FROM project").fetchone()["n"] == 1


def test_la_suppression_trace_QUI_et_QUAND(conn):
    """Un historique qui ne dit pas qui a supprimé ne vaut pas grand-chose sur un serveur
    partagé (le nom vient de la session — signature déclarée, cf. lot 2)."""
    pid, _, _, _, _ = _arbre(conn)
    ProjectRepo(conn).delete(pid, par="Awa")

    ligne = conn.execute("SELECT deleted_at, deleted_by FROM project WHERE id=?", (pid,)).fetchone()
    assert ligne["deleted_by"] == "Awa"
    assert ligne["deleted_at"]          # horodaté


def test_la_corbeille_liste_ce_qui_a_ete_supprime(conn):
    pid, mid, gid, c1, c2 = _arbre(conn)
    CaseRepo(conn).delete(c1, par="Awa")
    ModuleRepo(conn).delete(mid, par="Bob")

    corbeille = ProjectRepo(conn).corbeille(pid)
    types = {(e["type"], e["titre"]) for e in corbeille}
    assert ("cas", "Cas A") in types
    assert ("module", "Demandes") in types
    # Le cas B n'a PAS été supprimé lui-même : il est masqué parce que son module l'est. Le faire
    # figurer dans la corbeille laisserait croire qu'on peut le restaurer seul — on ne peut pas.
    assert ("cas", "Cas B") not in types


# ── 3. Restaurer, et purger ──────────────────────────────────────────────────

def test_restaurer_rend_l_element_ET_sa_descendance(conn):
    pid, mid, gid, c1, c2 = _arbre(conn)
    ModuleRepo(conn).delete(mid, par="Awa")
    ModuleRepo(conn).restaurer(mid)

    assert ModuleRepo(conn).get(mid) is not None
    assert len(CaseRepo(conn).list_all(module_id=mid)) == 2   # les cas reviennent avec lui


def test_restaurer_un_cas_ne_ressuscite_PAS_son_module_supprime(conn):
    """Restaurer un enfant ne doit pas faire réapparaître un parent que personne n'a demandé :
    le cas resterait invisible (son module l'est), et l'écran mentirait sur ce qui a été fait."""
    pid, mid, gid, c1, c2 = _arbre(conn)
    CaseRepo(conn).delete(c1, par="Awa")
    ModuleRepo(conn).delete(mid, par="Awa")
    CaseRepo(conn).restaurer(c1)

    assert ModuleRepo(conn).get(mid) is None
    assert CaseRepo(conn).list_all(project_id=pid) == []   # toujours masqué par son module


def test_la_purge_definitive_existe_mais_est_un_geste_DISTINCT(conn):
    """Détruire reste possible — mais jamais comme effet de bord d'une suppression ordinaire."""
    pid, mid, gid, c1, c2 = _arbre(conn)
    ProjectRepo(conn).delete(pid, par="Awa")
    assert conn.execute("SELECT COUNT(*) AS n FROM project").fetchone()["n"] == 1

    ProjectRepo(conn).purger(pid)

    assert conn.execute("SELECT COUNT(*) AS n FROM project").fetchone()["n"] == 0
    assert conn.execute("SELECT COUNT(*) AS n FROM test_case").fetchone()["n"] == 0


def test_on_ne_purge_QUE_ce_qui_est_deja_dans_la_corbeille(conn):
    """Un garde-fou volontaire : purger directement un projet vivant contournerait la corbeille
    et rendrait la suppression douce décorative."""
    pid, _, _, _, _ = _arbre(conn)
    with pytest.raises(ValueError, match="corbeille"):
        ProjectRepo(conn).purger(pid)


# ── 4. La corbeille par l'API — sans elle, « restaurer » n'existe pas ────────

@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from testpilot import config
    from testpilot.api import app as app_mod

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "ACCESS_PASSWORD", "")
    return TestClient(app_mod.app)


def _projet_api(client) -> tuple[int, int, int]:
    pid = client.post("/api/projects", json={
        "name": "Recette", "base_url": "http://x", "database": "db",
        "username": "qa", "password": "p"}).json()["id"]
    mid = client.post(f"/api/projects/{pid}/modules", json={"name": "Demandes"}).json()["id"]
    cid = client.post(f"/api/modules/{mid}/cases/manual", json={
        "title": "Un cas", "test_steps": ["a"], "expected_result": "ok"}).json()["id"]
    return pid, mid, cid


def test_api_supprimer_puis_RESTAURER_un_cas(client):
    """Le cycle complet vu de l'écran : le cas s'en va, il revient, rien n'a été perdu."""
    pid, mid, cid = _projet_api(client)

    assert client.delete(f"/api/cases/{cid}").status_code == 204
    assert client.get(f"/api/cases?project_id={pid}").json()["items"] == []

    corbeille = client.get(f"/api/projects/{pid}/corbeille").json()
    assert [(e["type"], e["titre"]) for e in corbeille] == [("cas", "Un cas")]

    assert client.post(f"/api/corbeille/cas/{cid}/restaurer").status_code == 204
    assert [c["id"] for c in client.get(f"/api/cases?project_id={pid}").json()["items"]] == [cid]
    assert client.get(f"/api/projects/{pid}/corbeille").json() == []


def test_api_purger_est_REFUSE_tant_que_l_element_est_vivant(client):
    """Purger directement contournerait la corbeille et la rendrait décorative."""
    pid, _, _ = _projet_api(client)

    r = client.delete(f"/api/corbeille/projet/{pid}")

    assert r.status_code == 409
    assert r.json()["code"] == "etat_incompatible"


def test_api_un_type_inconnu_est_REFUSE_et_le_dit(client):
    """Un type non géré ne doit pas être traité « par défaut » — il doit être nommé."""
    r = client.post("/api/corbeille/licorne/1/restaurer")

    assert r.status_code == 422
    assert r.json()["code"] == "requete_invalide"
    assert "licorne" in r.json()["detail"]
