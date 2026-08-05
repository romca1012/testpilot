"""L'exécution MANUELLE d'un cas — le geste « Add Result » de TestRail, et ses refus.

⚠️ **Ce que ce fichier protège.** Ouvrir l'exécution manuelle est le moment où ce produit peut
cesser d'être ce qu'il promet. Dans la plupart des outils de test management, « Passed » est une
case qu'un humain coche, et plus rien ne distingue un test qui a tourné d'un test qu'on a dit bon.
Ici la saisie existe, mais sous quatre conditions — et ce sont ces quatre-là qui sont testées :

1. le résultat est **étiqueté « manuelle »**, et n'écrit AUCUN des deux axes ;
2. **`untested` ne se saisit pas** : l'absence de résultat n'est pas un choix ;
3. la saisie n'existe **que dans une campagne manuelle**, et seulement pour un cas qui en fait
   partie — une campagne **clôturée** la refuse, une campagne **automatique** aussi ;
4. rien ne s'écrase : **corriger, c'est ajouter**, et l'historique le montre.

Le cinquième point est ailleurs (`test_resultat_du_dernier.py`) : qu'une exécution automatique
ultérieure reprenne la main sur une saisie manuelle. Et la concordance des modes entre un résultat
et sa campagne a son propre fichier (`test_mode_de_campagne.py`).
"""
import pytest
from fastapi.testclient import TestClient

from testpilot.api.app import app
from testpilot.api.deps import get_conn
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, ModuleRepo, ProjectRepo, RunRepo
from testpilot.verdict.status import MODE_MANUELLE, STATUTS_MANUELS


@pytest.fixture
def conn(tmp_path):
    c = get_initialized_db(tmp_path / "saisie.db")
    yield c
    c.close()


@pytest.fixture
def client(conn):
    app.dependency_overrides[get_conn] = lambda: conn
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def campagne(conn):
    """Une campagne MANUELLE — le mode se choisit à la création, plus résultat par résultat."""
    pid = ProjectRepo(conn).create(name="Portail")
    mid = ModuleRepo(conn).create(project_id=pid, name="Demandes")
    cid = CaseRepo(conn).create(title="Nominal", module_id=mid, feature_slug="nominal")
    hors = CaseRepo(conn).create(title="Hors campagne", module_id=mid, feature_slug="hors")
    rid = RunRepo(conn).create(project_id=pid, name="Recette", case_ids=[cid],
                               mode=MODE_MANUELLE)
    return {"run": rid, "cas": cid, "hors": hors, "projet": pid}


# ── Le geste nominal ─────────────────────────────────────────────────────────

def test_saisir_un_resultat_l_etiquette_MANUELLE_et_n_invente_aucun_axe(client, campagne):
    r = client.post(f"/api/runs/{campagne['run']}/cases/{campagne['cas']}/results",
                    json={"statut": "passed", "comment": "vérifié à la main sur la recette"})

    assert r.status_code == 201
    corps = r.json()
    assert corps["mode"] == "manuelle"
    assert corps["statut"] == "passed"
    assert corps["comment"] == "vérifié à la main sur la recette"
    # ⚠️ Les deux axes restent VIDES : saisir « passed » ne doit jamais produire
    # « exécution=succès / fonctionnel=conforme », qui prétendrait qu'une MACHINE a constaté.
    assert corps["execution_status"] is None
    assert corps["functional_status"] is None
    assert corps["execution_id"] is None


def test_la_campagne_affiche_le_resultat_avec_son_MODE(client, campagne):
    client.post(f"/api/runs/{campagne['run']}/cases/{campagne['cas']}/results",
                json={"statut": "blocked", "comment": "environnement indisponible"})

    cas = client.get(f"/api/runs/{campagne['run']}").json()["cases"][0]
    assert cas["result_mode"] == "manuelle"
    assert cas["statut"] == "blocked"
    assert cas["statut_manuel"] == "blocked"


def test_les_statuts_saisissables_viennent_du_SERVEUR(client, campagne):
    """⚠️ L'écran ITÈRE cette liste, il ne la retape pas. Elle vit déjà en Python et dans un
    `CHECK` de la base ; une troisième copie en TypeScript divergerait un jour en silence — le
    défaut qu'on a déjà payé une fois ici avec le statut de lecture."""
    detail = client.get(f"/api/runs/{campagne['run']}").json()

    assert detail["statuts_manuels"] == list(STATUTS_MANUELS)
    assert "untested" not in detail["statuts_manuels"]


# ── Les refus ────────────────────────────────────────────────────────────────

def test_untested_est_REFUSE_avec_un_message_qui_dit_pourquoi(client, campagne):
    """Sans explication, l'utilisateur cherche l'option manquante dans la liste — et conclut à
    un bug de l'outil plutôt qu'à une règle."""
    r = client.post(f"/api/runs/{campagne['run']}/cases/{campagne['cas']}/results",
                    json={"statut": "untested"})

    assert r.status_code == 422
    assert r.json()["code"] == "statut_invalide"
    assert "absence de résultat" in r.json()["detail"]


def test_un_statut_inconnu_est_refuse(client, campagne):
    r = client.post(f"/api/runs/{campagne['run']}/cases/{campagne['cas']}/results",
                    json={"statut": "presque_bon"})
    assert r.status_code == 422
    assert r.json()["code"] == "statut_invalide"


def test_un_cas_hors_campagne_est_refuse(client, campagne):
    """La saisie n'a de sens que DANS une campagne : « ce cas passe » ne veut rien dire sans
    contexte de test. C'est aussi la règle de TestRail."""
    r = client.post(f"/api/runs/{campagne['run']}/cases/{campagne['hors']}/results",
                    json={"statut": "passed"})
    assert r.status_code == 409
    assert r.json()["code"] == "cas_hors_campagne"


def test_une_campagne_ARCHIVEE_refuse_la_saisie(client, campagne, conn):
    """Archivée = lecture seule. Réversible : le message doit dire qu'on peut la rouvrir, sinon
    le refus ressemble à une porte fermée définitivement."""
    RunRepo(conn).archive(campagne["run"], True)

    r = client.post(f"/api/runs/{campagne['run']}/cases/{campagne['cas']}/results",
                    json={"statut": "passed"})
    assert r.status_code == 409
    assert r.json()["code"] == "campagne_archivee"
    assert "rouvrez" in r.json()["detail"].lower()


def test_un_cas_SUPPRIME_ne_recoit_plus_de_resultat(client, campagne, conn):
    """⚠️ L'appartenance passe par `RunRepo.case_ids`, qui porte l'invariant de suppression
    douce. Un cas à la corbeille ne fait plus partie d'aucune campagne — lui écrire un résultat
    ressusciterait une donnée que l'utilisateur croit supprimée."""
    CaseRepo(conn).delete(campagne["cas"], par="qa")

    r = client.post(f"/api/runs/{campagne['run']}/cases/{campagne['cas']}/results",
                    json={"statut": "passed"})
    assert r.status_code == 409
    assert r.json()["code"] == "cas_hors_campagne"


# ── L'historique ─────────────────────────────────────────────────────────────

def test_corriger_c_est_AJOUTER_et_l_historique_garde_tout(client, campagne):
    base = f"/api/runs/{campagne['run']}/cases/{campagne['cas']}/results"
    client.post(base, json={"statut": "failed", "comment": "je me suis trompé"})
    client.post(base, json={"statut": "passed", "comment": "correction : c'était ma donnée"})

    historique = client.get(base).json()
    assert [h["statut_manuel"] for h in historique] == ["failed", "passed"]
    assert [h["mode"] for h in historique] == ["manuelle", "manuelle"]
    # Le dernier fait foi pour la campagne, mais le premier reste LISIBLE.
    assert client.get(f"/api/runs/{campagne['run']}").json()["cases"][0]["statut"] == "passed"
