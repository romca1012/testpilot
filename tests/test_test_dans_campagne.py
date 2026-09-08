"""**UN CAS DANS UNE CAMPAGNE** — l'objet « test », et ce qui le distingue du cas (2026-08-05).

⚠️ **Le défaut que ce fichier empêche : confondre le cas et le test.** Le cas (`C…`) vit dans le
référentiel et sert à toutes les campagnes ; le test (`T…`) est ce cas DANS UNE campagne, et c'est
lui qui porte un statut, des résultats et des commentaires. La confusion n'est pas théorique : elle
produit exactement deux bugs, et ce sont les deux qui sont testés ici —

1. **montrer à l'écran d'une campagne les résultats obtenus dans une AUTRE** (un cas rouge en
   recette apparaîtrait rouge dans la campagne de non-régression où il n'a jamais été joué) ;
2. **enchaîner, avec les flèches précédent/suivant, des cas qui ne font pas partie de la
   campagne** — on note alors un cas qu'on croit être dedans, et le résultat part dans le vide.

S'y ajoute la promesse centrale du produit : **le MODE d'exécution accompagne chaque résultat**,
ici comme partout. Un « Passed » saisi à la main ne doit jamais pouvoir passer pour un « Passed »
mesuré par la machine, y compris dans la vue « ce cas dans les autres campagnes ».

Le fil d'ACTIVITÉ d'une campagne est testé dans le même fichier parce qu'il répond à la même
question sous un autre angle : « qu'est-ce qui s'est passé ICI, et seulement ici ».
"""
import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import app as app_mod


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "tests_de_campagne.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return TestClient(app_mod.app)


@pytest.fixture
def decor(client):
    """Trois cas dans un module, DEUX campagnes manuelles :

    - `recette` contient les cas A et C — **pas** le cas B, qui est pourtant leur voisin de module ;
    - `regression` contient le cas A, pour qu'il ait une histoire ailleurs.
    """
    pid = client.post("/api/projects", json={"name": "Portail"}).json()["id"]
    mid = client.post(f"/api/projects/{pid}/modules", json={"name": "Demandes"}).json()["id"]

    def cas(titre):
        return client.post(f"/api/modules/{mid}/cases/manual", json={
            "title": titre, "test_steps": ["ouvrir"], "expected_result": "ok"}).json()["id"]

    a, b, c = cas("Cas A"), cas("Cas B — hors campagne"), cas("Cas C")
    recette = client.post(f"/api/projects/{pid}/runs", json={
        "name": "Recette de juillet", "selection_mode": "frozen",
        "case_ids": [a, c], "mode": "manuelle"}).json()["id"]
    regression = client.post(f"/api/projects/{pid}/runs", json={
        "name": "Non-régression", "selection_mode": "frozen",
        "case_ids": [a], "mode": "manuelle"}).json()["id"]
    return {"projet": pid, "a": a, "b": b, "c": c,
            "recette": recette, "regression": regression}


def _saisir(client, run, cas, statut, commentaire=""):
    r = client.post(f"/api/runs/{run}/cases/{cas}/results",
                    json={"statut": statut, "comment": commentaire})
    assert r.status_code == 201, r.text
    return r.json()


# ── 1. Les résultats affichés sont ceux de CETTE campagne ────────────────────

def test_un_test_ne_montre_que_les_resultats_de_SA_campagne(client, decor):
    """🔴 Sans ce cloisonnement, un cas échoué en recette s'afficherait échoué dans la campagne de
    non-régression où personne ne l'a joué — et on chercherait un bug qui n'a pas été constaté là.
    """
    _saisir(client, decor["recette"], decor["a"], "failed", "constaté en recette")
    _saisir(client, decor["regression"], decor["a"], "passed", "vert en non-régression")

    recette = client.get(f"/api/runs/{decor['recette']}/tests/{decor['a']}").json()
    regression = client.get(f"/api/runs/{decor['regression']}/tests/{decor['a']}").json()

    assert [r["statut"] for r in recette["results"]] == ["failed"]
    assert recette["statut"] == "failed"
    assert [r["statut"] for r in regression["results"]] == ["passed"]
    assert regression["statut"] == "passed"
    # Le MÊME cas, deux verdicts : c'est précisément ce que l'objet « test » rend représentable.
    assert recette["case_id"] == regression["case_id"] == decor["a"]


def test_un_cas_jamais_joue_ici_est_untested_et_n_invente_aucun_resultat(client, decor):
    """« Untested » n'est pas un verdict : c'est l'absence de résultat. Fabriquer une ligne pour
    remplir l'écran ferait croire que quelqu'un a constaté quelque chose."""
    _saisir(client, decor["regression"], decor["a"], "passed")

    vu = client.get(f"/api/runs/{decor['recette']}/tests/{decor['a']}").json()
    assert vu["statut"] == "untested"
    assert vu["results"] == []


def test_corriger_c_est_ajouter_l_ancien_resultat_reste_lisible(client, decor):
    """L'historique du test est ce qui rend une correction honnête plutôt que silencieuse — même
    discipline que la suppression douce : on empile, on n'écrase pas."""
    _saisir(client, decor["recette"], decor["a"], "failed", "erreur de manip")
    _saisir(client, decor["recette"], decor["a"], "passed", "en fait ça marche")

    vu = client.get(f"/api/runs/{decor['recette']}/tests/{decor['a']}").json()
    assert [r["statut"] for r in vu["results"]] == ["failed", "passed"]
    assert vu["statut"] == "passed"   # le DERNIER inscrit fait foi


# ── 2. Le MODE d'exécution reste visible partout ─────────────────────────────

def test_chaque_resultat_dit_COMMENT_il_a_ete_obtenu(client, decor):
    """🔴 La promesse centrale du produit : on ne dit jamais « ça marche » sans pouvoir dire par
    quel moyen on l'a su. Un résultat sans mode redeviendrait une case cochée."""
    _saisir(client, decor["recette"], decor["a"], "passed")

    vu = client.get(f"/api/runs/{decor['recette']}/tests/{decor['a']}").json()
    assert [r["mode"] for r in vu["results"]] == ["manuelle"]
    # …et les deux axes restent VIDES : aucune machine n'a rien mesuré.
    assert vu["results"][0]["execution_status"] is None
    assert vu["results"][0]["functional_status"] is None
    # Le mode voyage aussi dans « ce cas dans les autres campagnes » : c'est là qu'un « Passed »
    # manuel pourrait le plus facilement se faire passer pour une mesure.
    assert {r["mode"] for r in vu["historique_du_cas"]} == {"manuelle"}


# ── 3. Les flèches précédent / suivant restent DANS la campagne ──────────────

def test_les_voisins_sont_ceux_de_la_CAMPAGNE_jamais_ceux_du_module(client, decor):
    """🔴 Le cas B est le voisin de A dans le module, mais ne fait PAS partie de la recette.
    Des flèches bornées au module y mèneraient — on noterait un cas absent de la campagne, et son
    résultat serait refusé (ou pire, accepté ailleurs)."""
    premier = client.get(f"/api/runs/{decor['recette']}/tests/{decor['a']}").json()
    dernier = client.get(f"/api/runs/{decor['recette']}/tests/{decor['c']}").json()

    assert premier["prev_case_id"] is None          # A ouvre la campagne
    assert premier["next_case_id"] == decor["c"]    # …et enjambe B, qui n'en fait pas partie
    assert dernier["prev_case_id"] == decor["a"]
    assert dernier["next_case_id"] is None


def test_un_cas_hors_campagne_n_a_pas_de_page_dans_cette_campagne(client, decor):
    """Une adresse forgée à la main ne doit pas ouvrir un écran de saisie sur un cas que la
    campagne ne contient pas : l'objet « test » n'existe pas là."""
    r = client.get(f"/api/runs/{decor['recette']}/tests/{decor['b']}")
    assert r.status_code == 404
    assert "ne fait pas partie" in r.json()["detail"]


# ── 4. Le même cas AILLEURS, et la lecture d'une campagne close ──────────────

def test_l_historique_du_cas_traverse_les_campagnes_et_les_nomme(client, decor):
    """C'est la question qu'une campagne seule ne peut pas poser : « ce cas échoue-t-il partout,
    ou seulement ici ? ». Sans le NOM de la campagne, la réponse serait illisible."""
    _saisir(client, decor["recette"], decor["a"], "failed")
    _saisir(client, decor["regression"], decor["a"], "passed")

    vu = client.get(f"/api/runs/{decor['recette']}/tests/{decor['a']}").json()
    par_campagne = {r["run_name"]: r["statut"] for r in vu["historique_du_cas"]}
    assert par_campagne == {"Recette de juillet": "failed", "Non-régression": "passed"}


def test_une_campagne_ARCHIVEE_reste_consultable(client, decor):
    """🔴 Archiver, c'est passer en lecture seule — pas rendre illisible. Refuser la lecture d'un
    test clôturé rendrait inconsultable exactement ce qu'on archive pour garder."""
    _saisir(client, decor["recette"], decor["a"], "passed")
    client.post(f"/api/runs/{decor['recette']}/archive", json={"archived": True})

    vu = client.get(f"/api/runs/{decor['recette']}/tests/{decor['a']}")
    assert vu.status_code == 200
    assert vu.json()["run_archived"] is True
    assert [r["statut"] for r in vu.json()["results"]] == ["passed"]


# ── 5. Le fil d'ACTIVITÉ d'une campagne ──────────────────────────────────────

def test_l_activite_ne_raconte_que_CETTE_campagne(client, decor):
    """🔴 Un fil d'activité qui mélangerait deux campagnes ferait croire à une recette active
    alors que le travail a eu lieu ailleurs — le pire mensonge possible sur un écran de suivi."""
    _saisir(client, decor["recette"], decor["a"], "passed")
    _saisir(client, decor["recette"], decor["c"], "blocked")
    _saisir(client, decor["regression"], decor["a"], "failed")

    fil = client.get(f"/api/runs/{decor['recette']}/activite").json()
    assert fil["run_name"] == "Recette de juillet"
    assert {e["statut"] for e in fil["events"]} == {"passed", "blocked"}
    assert {e["case_id"] for e in fil["events"]} == {decor["a"], decor["c"]}
    # Chaque ligne dit COMMENT, et sur quel cas — un fil sans titre de cas serait illisible.
    assert all(e["mode"] == "manuelle" and e["case_title"] for e in fil["events"])


def test_l_activite_porte_le_TOTAL_des_cas_ce_qui_fait_la_progression(client, decor):
    """La Progression se calcule sur cette réponse et pas sur une seconde route : deux comptages
    de la même chose finiraient par diverger sans que personne le voie."""
    _saisir(client, decor["recette"], decor["a"], "passed")

    fil = client.get(f"/api/runs/{decor['recette']}/activite").json()
    assert fil["case_count"] == 2            # A et C
    assert len(fil["events"]) == 1           # un seul a été joué


def test_un_cas_mis_a_la_corbeille_disparait_du_fil_d_activite(client, decor):
    """🔴 Le fil serait sinon le seul écran où un cas supprimé continuerait de vivre — alors qu'un
    cas à la corbeille ne fait plus partie d'aucune campagne (invariant de `RunRepo.case_ids`)."""
    _saisir(client, decor["recette"], decor["a"], "passed")
    _saisir(client, decor["recette"], decor["c"], "failed")
    assert client.delete(f"/api/cases/{decor['c']}").status_code in (200, 204)

    fil = client.get(f"/api/runs/{decor['recette']}/activite").json()
    assert [e["case_id"] for e in fil["events"]] == [decor["a"]]
    assert fil["case_count"] == 1
