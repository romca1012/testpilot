"""GET /api/steps-library — le catalogue de steps partagés, jusqu'ici visible SEULEMENT du prompt
système de l'agent de génération, jamais d'un humain sans lire `behave_runtime/steps_library/`
(2026-08-11).

Un seul invariant à figer : la route rend EXACTEMENT ce que `steps_library.catalogue()` extrait
par AST, dédupliqué comme `as_prompt_section` (une fonction à double décorateur `@when`+`@then`
n'apparaît pas deux fois pour le même mot-clé), triée pour un affichage stable.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import app as app_mod

_LIB = '''
from behave import given, when, then

@given('le nombre d\\'enregistrements dans le modele "{model}" est enregistre')
def s1(context, model):
    """-> compte les enregistrements AVANT l'action, pour comparaison ensuite."""
    pass

@when('je clique sur le bouton "{label}"')
@then('je clique sur le bouton "{label}"')
def s2(context, label):
    pass
'''


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "a.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    steps_dir = tmp_path / "steps_library"
    steps_dir.mkdir()
    (steps_dir / "_test_steps.py").write_text(_LIB, encoding="utf-8")
    monkeypatch.setattr(config, "STEPS_LIBRARY_DIR", steps_dir)
    return TestClient(app_mod.app)


def test_le_catalogue_est_consultable_sans_role_particulier(client):
    r = client.get("/api/steps-library")
    assert r.status_code == 200
    libelles = {(s["keyword"], s["label"]) for s in r.json()}
    assert ("given", "le nombre d'enregistrements dans le modele \"{model}\" est enregistre") in libelles
    assert ("when", 'je clique sur le bouton "{label}"') in libelles


def test_la_note_est_la_premiere_ligne_de_la_docstring(client):
    r = client.get("/api/steps-library")
    step = next(s for s in r.json() if s["keyword"] == "given")
    assert step["note"] == "-> compte les enregistrements AVANT l'action, pour comparaison ensuite."


def test_une_fonction_a_double_decorateur_n_apparait_pas_deux_fois_PAR_MOT_CLE(client):
    """`@when` + `@then` sur le MÊME libellé — une entrée par mot-clé, jamais deux fois dans le
    même mot-clé (même règle que `steps_library.as_prompt_section`)."""
    r = client.get("/api/steps-library")
    steps = r.json()
    whens = [s for s in steps if s["keyword"] == "when" and s["label"] == 'je clique sur le bouton "{label}"']
    thens = [s for s in steps if s["keyword"] == "then" and s["label"] == 'je clique sur le bouton "{label}"']
    assert len(whens) == 1
    assert len(thens) == 1


def test_sans_bibliotheque_rend_une_liste_vide(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "b.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "STEPS_LIBRARY_DIR", tmp_path / "absent")
    client = TestClient(app_mod.app)
    assert client.get("/api/steps-library").json() == []


@pytest.mark.sans_bouchon_auth
def test_sans_session_401(client):
    assert client.get("/api/steps-library").status_code == 401
