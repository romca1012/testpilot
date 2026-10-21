"""Étape 4 du plan unique (A72, A75 — porteur, 2026-10-20) : un projet qui a déclaré une adresse de remise à zéro y revient
avant CHAQUE exécution réelle d'un cas, puis le test est joué seul sur son application. Sans remise à zéro prouvée, le test
n'est pas joué (bloqué) — jamais un verdict sur un état hérité d'un autre test."""

from __future__ import annotations

import threading
import time

import pytest

from testpilot.guardrails import bac_a_sable

APP = "http://app:80"


@pytest.fixture(autouse=True)
def _propre(tmp_path, monkeypatch):
    from testpilot import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    bac_a_sable._marques_en_memoire.clear()
    bac_a_sable._verrous.clear()
    yield
    bac_a_sable._marques_en_memoire.clear()


def test_falsifiable_la_remise_a_zero_precede_le_test(monkeypatch):
    journal = []
    monkeypatch.setattr(bac_a_sable, "remettre_a_zero", lambda url, delai_s=0: journal.append(f"remise {url}"))
    with bac_a_sable.execution_remise_a_zero(APP, "http://app/__reset"):
        journal.append("test")
    assert journal == ["remise http://app/__reset", "test"]


def test_falsifiable_sans_remise_a_zero_prouvee_le_test_n_est_pas_joue(monkeypatch):
    def en_panne(url, delai_s=0):
        raise RuntimeError("la remise à zéro n'a pas confirmé")

    monkeypatch.setattr(bac_a_sable, "remettre_a_zero", en_panne)
    with pytest.raises(bac_a_sable.BacASableNonRemisAZero, match="avant le test"):
        with bac_a_sable.execution_remise_a_zero(APP, "http://app/__reset"):
            pytest.fail("le test ne doit pas être joué")
    with bac_a_sable.execution_reelle(APP):
        pass  # le verrou a été rendu : l'application n'est pas bloquée pour la suite


def test_falsifiable_deux_tests_de_la_meme_application_sont_joues_l_un_apres_l_autre(monkeypatch):
    monkeypatch.setattr(bac_a_sable, "remettre_a_zero", lambda url, delai_s=0: None)
    en_cours, chevauchements = [0], []

    def jouer():
        with bac_a_sable.execution_remise_a_zero(APP, "http://app/__reset"):
            en_cours[0] += 1
            chevauchements.append(en_cours[0])
            time.sleep(0.05)
            en_cours[0] -= 1

    fils = [threading.Thread(target=jouer) for _ in range(3)]
    for f in fils:
        f.start()
    for f in fils:
        f.join(5)
    assert chevauchements == [1, 1, 1], "jamais deux tests à la fois : une remise à zéro effacerait l'autre"


def test_une_execution_sans_remise_attend_le_test_remis_a_zero(monkeypatch):
    monkeypatch.setattr(bac_a_sable, "remettre_a_zero", lambda url, delai_s=0: None)
    ordre, tenu, relache = [], threading.Event(), threading.Event()

    def avec_remise():
        with bac_a_sable.execution_remise_a_zero(APP, "http://app/__reset"):
            tenu.set()
            relache.wait(5)
            ordre.append("test remis à zéro")

    fil = threading.Thread(target=avec_remise)
    fil.start()
    tenu.wait(5)
    autre = threading.Thread(target=lambda: (bac_a_sable.execution_reelle(APP).__enter__(), ordre.append("autre")))
    autre.start()
    time.sleep(0.1)
    relache.set()
    fil.join(5)
    autre.join(5)
    assert ordre == ["test remis à zéro", "autre"]


def test_falsifiable_le_lanceur_ne_lance_pas_behave_si_la_remise_echoue(tmp_path, monkeypatch):
    from testpilot.execution import behave_runner as br

    lances = []
    monkeypatch.setattr(br.subprocess, "run", lambda *a, **k: lances.append(a) or (_ for _ in ()).throw(AssertionError()))
    monkeypatch.setattr(bac_a_sable, "remettre_a_zero",
                        lambda url, delai_s=0: (_ for _ in ()).throw(RuntimeError("500")))
    (tmp_path / "gen").mkdir()
    (tmp_path / "gen" / "m.feature").write_text("# language: fr\nFonctionnalité: F\n", encoding="utf-8")
    (tmp_path / "gen" / "m_steps.py").write_text("", encoding="utf-8")
    runner = br.BehaveRunner(generated_dir=tmp_path / "gen", connection={"WEB_URL": "http://app"})
    runner.remise_a_zero_url = "http://app/__reset"
    resultat = runner.real_run("m")
    assert lances == [], "aucun sous-processus Behave"
    assert resultat.returncode == -3 and not resultat.success, "interruption technique, jamais un verdict"


def test_l_adresse_declaree_perimee_ne_remet_rien_a_zero(tmp_path, monkeypatch):
    from testpilot import config
    from testpilot.api.services import run_service
    from testpilot.store.db import get_initialized_db
    from testpilot.store.repositories import CaseRepo, ModuleRepo, ProjectRepo

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "a72.db")
    conn = get_initialized_db()
    pid = ProjectRepo(conn).create(name="P", connector_type="web", base_url="http://app")
    mid = ModuleRepo(conn).create(project_id=pid, name="m")
    cid = CaseRepo(conn).create(title="C", module_id=mid, feature_slug="c")
    assert run_service.adresse_de_remise_avant_test(conn, cid) == (None, ""), "aucune adresse : comportement d'avant"
    ProjectRepo(conn).set_bac_a_sable_reset(pid, "http://app/__reset")
    assert run_service.adresse_de_remise_avant_test(conn, cid) == ("http://app/__reset", "")
    conn.execute("UPDATE project SET base_url='http://production' WHERE id=?", (pid,))
    conn.commit()
    adresse, refus = run_service.adresse_de_remise_avant_test(conn, cid)
    assert adresse is None and "ne vaut plus" in refus, "périmée : jamais un POST vers une autre application, et dit"
    conn.close()


def test_falsifiable_l_execution_reelle_pose_l_adresse_sur_le_lanceur(monkeypatch):
    """Câblage : `run_execution` (environnement par défaut) pose l'adresse déclarée sur le runner — réparations comprises,
    puisqu'elles passent par le même runner."""
    from types import SimpleNamespace

    from testpilot.api.services import run_service

    vus = {}

    class _Runner:
        def __init__(self, **_kw):
            self.connection = {}
            self.remise_a_zero_url = None
            self.remise_a_zero_refus = ""

    monkeypatch.setattr(run_service, "BehaveRunner", _Runner)
    for nom in ("resolve_connection", "resolve_project_id", "resolve_connector_type", "resolve_profil_instance"):
        monkeypatch.setattr(run_service, nom, lambda *a, **k: None)
    monkeypatch.setattr(run_service, "_assurer_script_sur_disque", lambda *a, **k: None)
    monkeypatch.setattr(run_service, "get_initialized_db", lambda *a, **k: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(run_service, "adresse_de_remise_avant_test", lambda conn, cid: ("http://app/__reset", ""))
    monkeypatch.setattr(run_service, "_execute_and_persist",
                        lambda conn, eid, cid, module, runner, **o: vus.setdefault("url", runner.remise_a_zero_url))
    monkeypatch.setattr(run_service, "_maybe_repair", lambda *a, **k: None)

    run_service.run_execution(1, "m", 1, 1)
    assert vus["url"] == "http://app/__reset"



def test_falsifiable_un_echec_de_remise_a_zero_donne_bloque_jamais_une_erreur_technique():
    from testpilot.execution.behave_result import BehaveResult
    from testpilot.verdict.status import EXEC_BLOCKED, EXEC_TECHNICAL_ERROR, FUNC_INDETERMINE, derive_verdict

    class _Issue:
        dry_run_passed = True
        real_run = BehaveResult(success=False, returncode=-3, raw_stderr="PRÉREQUIS MANQUANT : x", prerequis_manquant="x")

    verdict = derive_verdict(_Issue())
    assert (verdict.execution_status, verdict.functional_status) == (EXEC_BLOCKED, FUNC_INDETERMINE)

    class _Plantage:
        dry_run_passed = True
        real_run = BehaveResult(success=False, returncode=-3)

    assert derive_verdict(_Plantage()).execution_status == EXEC_TECHNICAL_ERROR, "un vrai plantage reste technique"


def test_falsifiable_une_adresse_perimee_ne_lance_pas_behave(tmp_path, monkeypatch):
    from testpilot.execution import behave_runner as br

    lances = []
    monkeypatch.setattr(br.subprocess, "run", lambda *a, **k: lances.append(a))
    (tmp_path / "gen").mkdir()
    (tmp_path / "gen" / "m.feature").write_text("# language: fr\nFonctionnalité: F\n", encoding="utf-8")
    (tmp_path / "gen" / "m_steps.py").write_text("", encoding="utf-8")
    runner = br.BehaveRunner(generated_dir=tmp_path / "gen", connection={"WEB_URL": "http://app"})
    runner.remise_a_zero_refus = "l'adresse de remise à zéro déclarée ne vaut plus"
    resultat = runner.real_run("m")
    assert lances == [] and resultat.returncode == -3 and resultat.prerequis_manquant


def test_falsifiable_changer_la_base_odoo_retire_l_adresse_de_remise_a_zero(tmp_path, monkeypatch):
    """Revue : un projet Odoo passé de la base « test » à « client » sur le même hôte remettait « test » à zéro, puis jouait
    sur « client » non remise à zéro."""
    from fastapi.testclient import TestClient

    from testpilot import config
    from testpilot.api import app as app_mod
    from testpilot.store.db import get_initialized_db
    from testpilot.store.repositories import ProjectRepo

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "a72b.db")
    conn = get_initialized_db()
    pid = ProjectRepo(conn).create(name="O", connector_type="odoo", base_url="http://odoo:8069", database="test")
    ProjectRepo(conn).set_bac_a_sable_reset(pid, "http://odoo:8069/__reset")
    conn.close()
    client = TestClient(app_mod.app)
    reponse = client.patch(f"/api/projects/{pid}", json={"database": "client",
                                                         "bac_a_sable_reset": "http://odoo:8069/__reset"})
    assert reponse.status_code == 200, reponse.text
    conn = get_initialized_db()
    assert (ProjectRepo(conn).get(pid) or {}).get("bac_a_sable_reset") == "", "renvoyée telle qu'elle a été lue : tombe"
    conn.close()
