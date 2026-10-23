"""Étape 7 (A110) — les fiches de calcul choisies sur l'écran de validation des cas.

Ce que ces tests gardent :
1. sans choix, pas de calcul : rien n'est retenu (le défaut) ;
2. une fiche choisie qui ne retrouve pas ses exemples, ou mal formée, est refusée À LA VALIDATION, en le disant — avant toute
   dépense de génération (falsifiabilité) ;
3. une fiche retenue est enregistrée avec le nom de la personne qui l'a choisie (choisir vaut validation, V10) ; les
   propositions de l'IA non choisies sont gardées « proposées », jamais utilisées.
"""

from __future__ import annotations

import pytest

from testpilot import config
from testpilot.api.services import fiches_de_calcul_service
from testpilot.store.repositories import FicheDeCalculRepo

FICHE = {"nom": "Total", "resultat": "total",
         "elements": [{"nom": "quantite", "source": "variable {{quantite}}"}, {"nom": "prix", "source": "variable {{prix}}"}],
         "etapes": [{"resultat": "total", "operation": "multiplier", "termes": ["quantite", "prix"]}],
         "exemples": [{"entrees": {"quantite": "3", "prix": "10"}, "attendu": "30"}]}


@pytest.fixture
def projet(tmp_path, monkeypatch):
    from testpilot.store.db import get_initialized_db
    from testpilot.store.repositories import CaseRepo, GenerationJobRepo, ModuleRepo, ProjectRepo, TestDataRepo

    db = tmp_path / "db.sqlite"
    monkeypatch.setattr(config, "DB_PATH", db)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    conn = get_initialized_db(db)
    pid = ProjectRepo(conn).create(name="Boutique", connector_type="web", base_url="http://app")
    mid = ModuleRepo(conn).create(project_id=pid, name="M")
    for nom in ("quantite", "prix"):
        TestDataRepo(conn).creer_variable(pid, nom=nom)
    GenerationJobRepo(conn).creer("j", module_id=mid, payload={"title": "T", "spec_content": "spec", "author": "a"})
    conn.execute("UPDATE generation_job SET status='awaiting_metier' WHERE id='j'")
    conn.commit()
    cid = CaseRepo(conn).create(title="Commande", module_id=mid, feature_slug="commande")
    yield conn, pid, cid
    conn.close()


def _cas(**plus):
    return {"title": "Commande", "steps": ["Commander"], "expected_result": "Le total s'affiche", **plus}


def test_sans_choix_pas_de_calcul(projet):
    from testpilot.api.services import generation_service

    conn, *_ = projet
    sortie = generation_service.validate_metier(conn, "j", [_cas(calcul_detecte="le total dépend du prix",
                                                                  fiches_proposees=[FICHE])], par="marie")
    cas = sortie["cases"][0]
    assert "fiches_retenues" not in cas and "valide_par" not in cas
    assert cas["fiches_proposees"][0]["nom"] == "Total", "la proposition est gardée, pas utilisée"


@pytest.mark.parametrize("fiche, motif", [
    ({**FICHE, "exemples": [{"entrees": {"quantite": "3", "prix": "10"}, "attendu": "31"}]}, "attend 31, le calcul donne 30"),
    ({**FICHE, "elements": [{"nom": "quantite"}, {"nom": "prix", "source": "x"}]}, "source manque"),
])
def test_falsifiable_une_fiche_fausse_est_refusee_a_la_validation(projet, fiche, motif):
    from testpilot.api.services import generation_service

    conn, *_ = projet
    with pytest.raises(generation_service.GenerationError, match=motif):
        generation_service.validate_metier(conn, "j", [_cas(fiches_retenues=[{"origine": "ia", "contenu": fiche}])],
                                           par="marie")


def test_choisir_une_fiche_vaut_validation_par_cette_personne(projet):
    from testpilot.api.services import generation_service

    conn, pid, cid = projet
    sortie = generation_service.validate_metier(conn, "j", [_cas(
        calcul_detecte="le total dépend du prix", fiches_retenues=[{"origine": "personne", "contenu": FICHE}])],
        par="marie")
    cas = sortie["cases"][0]
    assert cas["valide_par"] == "marie"

    fiches_de_calcul_service.enregistrer(conn, case_id=cid, project_id=pid, cas=cas, par=cas["valide_par"])
    (fiche,) = FicheDeCalculRepo(conn).du_cas(cid)
    assert (fiche["statut"], fiche["origine"], fiche["retenue_par"], fiche["nom"]) == ("retenue", "personne", "marie", "Total")
    assert fiche["retenue_le"]
    assert conn.execute("SELECT calcul_detecte FROM test_case WHERE id=?", (cid,)).fetchone()[0] == "le total dépend du prix"


def test_falsifiable_une_fiche_ne_peut_pas_etre_retenue_sans_nom(projet):
    conn, pid, cid = projet
    with pytest.raises(ValueError, match="nom de la personne"):
        FicheDeCalculRepo(conn).creer(project_id=pid, case_id=cid, contenu=FICHE, origine="ia", statut="retenue")


def test_deux_calculs_du_meme_nom_sont_refuses():
    fautes = fiches_de_calcul_service.fautes_des_fiches({"fiches_retenues": [
        {"origine": "ia", "contenu": FICHE}, {"origine": "personne", "contenu": FICHE}]})
    assert any("s'appellent « Total »" in f for f in fautes)


def test_falsifiable_une_entree_sans_donnee_de_test_est_refusee(projet):
    """L'entrée « remise » n'a pas de variable dans le projet : le test serait bloqué à chaque exécution."""
    from testpilot.api.services import generation_service

    conn, *_ = projet
    fiche = {**FICHE, "elements": [*FICHE["elements"], {"nom": "remise", "source": "variable {{remise}}"}]}
    with pytest.raises(generation_service.GenerationError, match="l'entrée « remise » n'est pas une donnée de test"):
        generation_service.validate_metier(conn, "j", [_cas(fiches_retenues=[{"origine": "ia", "contenu": fiche}])],
                                           par="marie")


# ── Vérifier une fiche depuis l'écran, sans rien enregistrer ──────────────────────────────────────────────────────────────

def test_falsifiable_l_ecran_voit_l_ecart_d_un_exemple_et_le_detail(projet):
    from fastapi.testclient import TestClient

    from testpilot.api import app as app_mod

    client = TestClient(app_mod.app)
    bonne = client.post("/api/calculs/verifier", json={"fiche": FICHE}).json()
    assert bonne["utilisable"] and bonne["entrees"] == ["quantite", "prix"]
    assert bonne["exemples"][0]["retrouve"] and bonne["exemples"][0]["detail"][-1] == "total = quantite × prix = 30"

    fausse = client.post("/api/calculs/verifier", json={"fiche": {**FICHE, "exemples": [
        {"entrees": {"quantite": "3", "prix": "10"}, "attendu": "31"}]}}).json()
    assert not fausse["utilisable"] and fausse["exemples"][0] | {"detail": []} == {
        "numero": 1, "attendu": "31", "obtenu": "30", "retrouve": False, "detail": []}

    sans_source = client.post("/api/calculs/verifier", json={"fiche": {**FICHE, "elements": [{"nom": "quantite"}]}}).json()
    assert not sans_source["utilisable"] and "source manque" in sans_source["erreur"]
    assert not client.post("/api/calculs/verifier", json={"fiche": FICHE, "proposition": True}).json()["utilisable"], \
        "une proposition n'est jamais « utilisable » telle quelle : une personne la choisit"
    assert FicheDeCalculRepo(projet[0]).du_cas(projet[2]) == [], "rien n'est enregistré"


def test_falsifiable_choisir_un_calcul_sans_compte_nomme_est_refuse(projet):
    from testpilot.api.services import generation_service

    conn, *_ = projet
    with pytest.raises(generation_service.GenerationError, match="compte nommé"):
        generation_service.validate_metier(conn, "j", [_cas(fiches_retenues=[{"origine": "ia", "contenu": FICHE}])], par="")
