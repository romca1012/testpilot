"""Adresse de la page au moment d'un step en échec : consignée par le runtime, donnée à l'agent de réparation (2026-10-08).

Origine : mesure « après réparation » du banc d'agents. `panier_total_tva` échouait sur « Locator introuvable » alors que le
navigateur n'était plus sur la page du formulaire (l'application avait changé de page après le premier ajout). Le message
d'échec ne disait pas OÙ était le navigateur ; l'agent accusait donc le sélecteur. L'adresse est un FAIT mesuré par le
navigateur (jamais un texte de l'agent), consigné par un sidecar comme les autres signaux du runtime.
"""

from __future__ import annotations

import importlib.util
import json
import threading
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from testpilot import config
from testpilot.execution import behave_result as br
from testpilot.execution.behave_runner import BehaveRunner
from testpilot.generation import repair_agent

_ENV_PATH = config.BEHAVE_RUNTIME_DIR / "environment.py"


def _environment():
    spec = importlib.util.spec_from_file_location("environment_page_echec", _ENV_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _echec(scenario="S", step="Quand je clique", url=""):
    return br.BehaveFailure(scenario_name=scenario, step_text=step, failure_type="x", traceback_summary="", raw="boom", page_url=url)


# ── Lecture et rattachement (purs) ───────────────────────────────────────────────────────────────────────


def test_l_adresse_est_rattachee_au_bon_echec_par_scenario_et_texte_du_step(tmp_path):
    chemin = tmp_path / "p.jsonl"
    chemin.write_text("\n".join([
        json.dumps({"scenario": "S1", "step": "Quand a", "url": "http://h/a"}),
        json.dumps({"scenario": "S2", "step": "Quand a", "url": "http://h/b"}),
    ]), encoding="utf-8")
    resultat = br.BehaveResult(success=False, returncode=1, dry_run=False)
    resultat.failures = [_echec("S2", "Quand a"), _echec("S1", "Quand a"), _echec("S3", "Quand z")]

    br.rattacher_pages_au_echec(resultat, br.read_pages_au_echec(chemin))

    assert [f.page_url for f in resultat.failures] == ["http://h/b", "http://h/a", ""]


def test_un_echec_de_fixture_sans_step_n_a_pas_de_page_et_deux_echecs_identiques_consomment_chacun_leur_ligne():
    resultat = br.BehaveResult(success=False, returncode=1, dry_run=False)
    resultat.failures = [_echec("S", ""), _echec("S", "Quand a"), _echec("S", "Quand a")]
    lignes = [{"scenario": "S", "step": "Quand a", "url": "http://h/1"}, {"scenario": "S", "step": "Quand a", "url": "http://h/2"}]

    br.rattacher_pages_au_echec(resultat, lignes)

    assert [f.page_url for f in resultat.failures] == ["", "http://h/1", "http://h/2"]


def test_fichier_absent_ou_lignes_illisibles_ne_donnent_rien_jamais_une_erreur(tmp_path):
    assert br.read_pages_au_echec(tmp_path / "absent.jsonl") == []
    chemin = tmp_path / "p.jsonl"
    chemin.write_text("pas du json\n{\"url\": 3}\n[1]\n" + json.dumps({"scenario": "S", "step": "x", "url": "http://h"}) + "\n",
                      encoding="utf-8")

    assert br.read_pages_au_echec(chemin) == [{"scenario": "S", "step": "x", "url": "http://h"}]


def test_le_runner_designe_le_sidecar_et_les_deux_copies_des_noms_s_accordent(tmp_path):
    env = BehaveRunner()._subprocess_env(tmp_path)
    harnais = _environment()

    assert env[br.PAGE_ECHEC_FILE_ENV] == str(tmp_path / br.PAGE_ECHEC_FILENAME)
    assert harnais.PAGE_ECHEC_FILE_ENV == br.PAGE_ECHEC_FILE_ENV


# ── Le crochet du harnais ────────────────────────────────────────────────────────────────────────────────


def _step(statut="failed", keyword="Quand", name="je clique sur le bouton \"X\""):
    return SimpleNamespace(status=SimpleNamespace(name=statut), keyword=keyword, name=name)


def _contexte(url="http://h/panier", scenario="Mon scénario"):
    return SimpleNamespace(page=SimpleNamespace(url=url), scenario=SimpleNamespace(name=scenario))


def test_un_step_en_echec_consigne_l_adresse_de_la_page(tmp_path, monkeypatch):
    harnais = _environment()
    chemin = tmp_path / "p.jsonl"
    monkeypatch.setenv(harnais.PAGE_ECHEC_FILE_ENV, str(chemin))

    for statut in ("failed", "error"):
        harnais._consigner_page_au_echec(_contexte(), _step(statut))

    lignes = [json.loads(ligne) for ligne in chemin.read_text(encoding="utf-8").splitlines()]
    assert lignes == [{"scenario": "Mon scénario", "step": "Quand je clique sur le bouton \"X\"", "url": "http://h/panier"}] * 2


def test_falsifiable_un_step_reussi_ou_ignore_ne_consigne_rien(tmp_path, monkeypatch):
    harnais = _environment()
    chemin = tmp_path / "p.jsonl"
    monkeypatch.setenv(harnais.PAGE_ECHEC_FILE_ENV, str(chemin))

    for statut in ("passed", "skipped", "undefined", "untested"):
        harnais._consigner_page_au_echec(_contexte(), _step(statut))

    assert not chemin.exists()


def test_sans_page_sans_sidecar_ou_page_illisible_aucune_exception_ne_masque_l_echec(tmp_path, monkeypatch):
    harnais = _environment()
    chemin = tmp_path / "p.jsonl"

    monkeypatch.delenv(harnais.PAGE_ECHEC_FILE_ENV, raising=False)
    harnais._consigner_page_au_echec(_contexte(), _step())  # pas de sidecar désigné

    monkeypatch.setenv(harnais.PAGE_ECHEC_FILE_ENV, str(chemin))
    harnais._consigner_page_au_echec(SimpleNamespace(scenario=SimpleNamespace(name="S")), _step())  # connecteur sans navigateur

    class PageFermee:
        @property
        def url(self):
            raise RuntimeError("Target page, context or browser has been closed")

    harnais._consigner_page_au_echec(SimpleNamespace(page=PageFermee(), scenario=SimpleNamespace(name="S")), _step())
    harnais._consigner_page_au_echec(_contexte(url=""), _step())  # adresse vide : rien à dire

    assert not chemin.exists()


# ── Ce que reçoit l'agent de réparation ──────────────────────────────────────────────────────────────────


def _rapport(url):
    return repair_agent._failure_report([], [_echec(url=url)])


def test_l_agent_de_reparation_recoit_la_page_ou_se_trouvait_le_navigateur():
    rapport = _rapport("http://127.0.0.1:5000/panier")

    assert "Page du navigateur au moment de l'échec : http://127.0.0.1:5000/panier" in rapport


def test_sans_adresse_connue_le_rapport_ne_change_pas():
    assert "Page du navigateur" not in _rapport("")
    assert _rapport("") == repair_agent._failure_report([], [_echec()])


@pytest.mark.parametrize("url", [
    "https://admin:motdepasse-secret@app.exemple.fr/compte?token=abc123SECRET&q=chaise#ancre-secrete",
    "https://app.exemple.fr/compte?session=s3cr3t-valeur",
])
def test_falsifiable_aucun_secret_de_l_adresse_ne_part_chez_le_fournisseur_du_modele(url):
    """Identifiants, VALEURS de paramètres et fragment ne sont jamais transmis : seul le chemin et le NOM des paramètres."""
    rapport = _rapport(url)

    for secret in ("motdepasse-secret", "abc123SECRET", "s3cr3t-valeur", "ancre-secrete", "admin:"):
        assert secret not in rapport
    assert "https://app.exemple.fr/compte" in rapport and "paramètres" in rapport


# ── Vrai Behave + vrai Chromium (exclu de `pytest -q`) ───────────────────────────────────────────────────

_FEATURE = """Fonctionnalité: Adresse au moment de l'échec
  Scénario: un bouton absent
    Soit j'accède à la page de connexion sans me connecter
    Quand je clique sur le bouton "Bouton qui n'existe pas"
"""


@contextmanager
def _application():
    from banc.app_web import serveur

    srv = serveur.creer_serveur("127.0.0.1", 0, "")
    fil = threading.Thread(target=srv.serve_forever, daemon=True)
    fil.start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}"
    finally:
        srv.shutdown()
        srv.server_close()
        fil.join(timeout=5)


@pytest.mark.conformance
def test_vrai_run_l_echec_porte_l_adresse_de_la_page_ou_il_a_eu_lieu(tmp_path):
    from testpilot.execution.executor import Executor

    (tmp_path / "m.feature").write_text(_FEATURE, encoding="utf-8")
    (tmp_path / "m_steps.py").write_text("from behave import given, when, then\n", encoding="utf-8")
    with _application() as url:
        runner = BehaveRunner(connection={"WEB_URL": url, "WEB_USER": "testeur", "WEB_PASSWORD": "motdepasse-test"},
                              connector_type="web", generated_dir=tmp_path)
        outcome = Executor(runner, max_retries=0).execute("m")

    echecs = outcome.real_run.failures
    assert echecs and echecs[0].page_url.endswith("/connexion"), [f.page_url for f in echecs]
