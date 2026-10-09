"""D32 (validée par le porteur le 2026-10-09) — un refus de ce que le métier demande n'est pas appris d'office.

Avant : tout refus mesuré devenait une règle apprise appliquée tout de suite (§5bis n°1) — le résolveur et l'agent évitaient
ensuite la valeur. Si l'application refusait à tort une valeur que la spec autorise (un bug), le test suivant prenait une
autre valeur et passait : le bug disparaissait des résultats sans qu'aucun humain l'ait vu. Ici : une valeur CITÉE par le
métier validé du cas donne une règle « à confirmer », qui ne s'applique pas tant qu'un humain n'a pas tranché (écran
« Cas à relire ») ; tout autre refus suit la règle d'origine, inchangée.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api.services import run_service
from testpilot.execution.behave_runner import BehaveRunner
from testpilot.generation import regles_apprises as ra
from testpilot.generation import valeur_conforme as vc
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, ExecutionRepo, ModuleRepo, ProjectRepo, VersionRepo

METIER = "Créer un fournisseur dont le contrat court jusqu'en 2027.\nRésultat attendu : le fournisseur est enregistré."


def _refus(valeur: str) -> dict:
    return {"route": "/fournisseur/creation", "champ": "annee_fin", "type_contrainte": "customError",
            "valeur_contrainte": "", "valeur_refusee": valeur, "origine": "navigateur", "preuve": "Année invalide"}


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(ra, "REGLES_DIR", tmp_path / "regles-apprises")
    return tmp_path


# ── Reconnaître une valeur citée ──────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("valeur, citee", [
    ("2027", True),
    ("FOURNISSEUR", True),            # sans casse
    ("enregistre", True),             # sans accents
    ("20270", False),                 # frontière de mot
    ("027", False),
    ("12", False),                    # trop courte pour conclure
    ("TestPilot", False),             # valeur fabriquée par le résolveur
])
def test_une_valeur_n_est_citee_que_telle_quelle_par_le_metier(valeur, citee):
    assert ra.valeur_citee(valeur, METIER) is citee


# ── Le registre ───────────────────────────────────────────────────────────────────────────────────────────


def _apprendre(valeur: str, metier: str = METIER, project_id: int = 1):
    runner = BehaveRunner(project_id=project_id)
    runner.cibler_metier(metier)
    runner._apprendre(SimpleNamespace(refus_mesures=[_refus(valeur)]), dry_run=False)


def test_falsifiable_un_refus_de_valeur_citee_n_est_pas_applique(store):
    _apprendre("2027")

    assert ra.charger(1) == []
    attente = ra.charger_tout(1)
    assert len(attente) == 1 and attente[0].a_confirmer and attente[0].decision == ""


def test_falsifiable_le_resolveur_ne_contourne_pas_une_valeur_citee_en_attente(store):
    """LE trou de D32 : le résolveur aurait écarté « 2027 » et rempli autre chose — le bug devenait invisible."""
    _apprendre("2027")
    champ = ra.fusionner({"name": "annee_fin", "options": ["2026", "2027", "2028"]},
                         ra.pour_champ(ra.charger(1), "/fournisseur/creation", "annee_fin"))

    assert "valeurs_interdites" not in champ


def test_un_refus_de_valeur_fabriquee_reste_appris_d_office(store):
    """Régime d'origine inchangé : la valeur venait de notre fabrication, l'éviter est sûr."""
    _apprendre("TestPilot")

    assert [r.valeur_refusee for r in ra.charger(1)] == ["TestPilot"]


def test_sans_metier_designe_le_comportement_d_avant_est_garde(store):
    runner = BehaveRunner(project_id=1)
    runner._apprendre(SimpleNamespace(refus_mesures=[_refus("2027")]), dry_run=False)

    assert [r.valeur_refusee for r in ra.charger(1)] == ["2027"]


def test_confirmer_applique_la_regle(store):
    _apprendre("2027")

    ra.decider(1, _refus("2027"), ra.DECISION_CONFIRMEE, auteur="qa")

    assert [r.valeur_refusee for r in ra.charger(1)] == ["2027"]
    champ = ra.fusionner({"name": "annee_fin", "options": ["2027", "2028"]},
                         ra.pour_champ(ra.charger(1), "/fournisseur/creation", "annee_fin"))
    assert vc.valeur_pour(champ) == "2028"


def test_rejeter_ne_l_applique_jamais_meme_si_le_refus_se_reproduit(store):
    _apprendre("2027")
    ra.decider(1, _refus("2027"), ra.DECISION_REJETEE, auteur="qa")

    _apprendre("2027")

    assert ra.charger(1) == []
    assert ra.charger_tout(1)[0].decision == ra.DECISION_REJETEE


def test_une_decision_inconnue_est_refusee(store):
    with pytest.raises(ValueError):
        ra.decider(1, _refus("2027"), "peut_etre")


# ── Le métier transmis au runner est le texte HUMAIN de la version jouée ──────────────────────────────────


def test_le_metier_transmis_est_celui_de_la_version_jamais_le_gherkin(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    conn = get_initialized_db(tmp_path / "d32.db")
    pid = ProjectRepo(conn).create(name="P")
    cid = CaseRepo(conn).create(title="C", module_id=ModuleRepo(conn).create(project_id=pid, name="M"), feature_slug="c")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="spec 2027", spec_hash="", feature_content="Alors 9999",
                                   steps_content="# 8888", expected_result="Enregistré")
    eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid)

    texte = run_service._texte_metier(conn, eid)
    conn.close()

    assert "2027" in texte and "Enregistré" in texte
    assert "9999" not in texte and "8888" not in texte


# ── L'API de l'écran « Cas à relire » ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def client(store, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    conn = get_initialized_db(tmp_path / "api.db")
    pid = ProjectRepo(conn).create(name="Projet D32")
    conn.close()
    from testpilot.api.app import app
    return TestClient(app), pid


def test_l_ecran_liste_les_refus_en_attente_et_enregistre_la_decision(client):
    http, pid = client
    _apprendre("2027", project_id=pid)
    _apprendre("TestPilot", project_id=pid)

    attente = http.get(f"/api/projects/{pid}/refus-a-confirmer").json()
    assert [r["valeur_refusee"] for r in attente] == ["2027"]

    corps = {k: attente[0][k] for k in ("route", "champ", "type_contrainte", "valeur_contrainte", "valeur_refusee")}
    reponse = http.post(f"/api/projects/{pid}/refus-a-confirmer", json={**corps, "decision": "confirmee"})

    assert reponse.status_code == 200 and reponse.json() == []
    assert "2027" in [r.valeur_refusee for r in ra.charger(pid)]


def test_l_ecran_refuse_une_regle_inconnue_ou_une_decision_invalide(client):
    http, pid = client
    _apprendre("2027", project_id=pid)
    corps = {"route": "/fournisseur/creation", "champ": "annee_fin", "type_contrainte": "customError",
             "valeur_contrainte": "", "valeur_refusee": "2027"}

    assert http.post(f"/api/projects/{pid}/refus-a-confirmer",
                     json={**corps, "valeur_refusee": "1999", "decision": "confirmee"}).status_code == 404
    assert http.post(f"/api/projects/{pid}/refus-a-confirmer", json={**corps, "decision": "bof"}).status_code == 422
    assert ra.charger(pid) == []
