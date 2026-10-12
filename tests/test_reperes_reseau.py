"""Rattachement d'une réponse réseau à l'ACTION qui a émis sa requête — sans navigateur (vrais gestionnaires, faux contexte).

CI du 2026-10-11 (PR #80) : « je clique "Ping" » puis « j'ouvre la page » ; la réponse de Ping, arrivée après le début du second
step, lui était attribuée et « la requête "GET /api/ping" répond 200 » sortait `conforme` une fois sur deux. La preuve en vrai
navigateur est dans `tests/test_vocabulaire_universel.py` ; ce fichier-ci couvre la même règle dans la suite par défaut.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from testpilot import config

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "behave_runtime" / "steps_library"))
import _base_helpers as H  # noqa: E402


class _FauxNavigateur:
    def __init__(self):
        self.gestionnaires = {}

    def on(self, evenement, gestionnaire):
        self.gestionnaires[evenement] = gestionnaire


@pytest.fixture
def scene(monkeypatch):
    """`(context, gestionnaires)` : les observateurs RÉELS du socle, branchés sur un faux contexte de navigateur."""
    monkeypatch.setattr(H, "_ATTENDRE_UNIVERSELLE_MS", 50)
    navigateur = _FauxNavigateur()
    context = SimpleNamespace(_browser_context=navigateur,
                              page=SimpleNamespace(wait_for_timeout=lambda ms: None, url="http://app.test/"))
    H.installer_les_observateurs(context)
    return context, navigateur.gestionnaires


def _requete(methode="GET"):
    return SimpleNamespace(resource_type="fetch", method=methode, redirected_from=None)


def _reponse(requete, url, statut=200):
    return SimpleNamespace(request=requete, url=url, status=statut, frame=SimpleNamespace(parent_frame=None, page=object()))


def test_falsifiable_une_reponse_tardive_n_est_pas_attribuee_a_l_action_suivante(scene):
    """Le cas de la CI : émission pendant l'action 1, réponse après le repère de l'action 2 — l'action 2 n'a rien émis."""
    context, g = scene
    H.poser_repere_action(context)
    ping = _requete()
    g["request"](ping)                                          # action 1 : le clic émet la requête
    H.poser_repere_action(context)                              # action 2 : n'émet rien
    g["response"](_reponse(ping, "http://app.test/api/ping"))   # la réponse n'arrive que maintenant

    with pytest.raises(AssertionError, match="Aucune requête"):
        H.requete_repond(context, "GET /api/ping", 200)


def test_la_reponse_a_la_derniere_action_est_retenue_meme_si_elle_arrive_tard(scene):
    """Témoin : la même réponse, quand c'est bien la dernière action qui a émis la requête, est retenue."""
    context, g = scene
    H.poser_repere_action(context)
    H.poser_repere_action(context)
    ping = _requete()
    g["request"](ping)
    g["response"](_reponse(ping, "http://app.test/api/ping"))

    H.requete_repond(context, "GET /api/ping", 200)             # ne lève pas


def test_falsifiable_une_reponse_dont_l_emission_est_inconnue_n_est_attribuable_a_aucune_action(scene):
    """Sans événement d'émission observé, pas de repli sur l'instant d'arrivée : il refaisait le faux vert."""
    context, g = scene
    H.poser_repere_action(context)
    g["response"](_reponse(_requete(), "http://app.test/api/ping"))

    assert [r["n"] for r in context.reponses_reseau] == [0]
    with pytest.raises(AssertionError, match="Aucune requête"):
        H.requete_repond(context, "GET /api/ping", 200)


def test_falsifiable_un_envoi_emis_avant_le_releve_ne_vaut_pas_soumission(scene):
    """`_soumission_observee` (comptage « n'a pas augmenté ») : un POST parti AVANT le relevé et répondu après n'est pas
    la soumission de l'action jugée."""
    context, g = scene
    envoi = _requete("POST")
    g["request"](envoi)
    context._tp_releve_sequence = context._tp_sequence
    g["response"](_reponse(envoi, "http://app.test/api/creer", 201))

    assert H._soumission_observee(context) is False


def test_un_envoi_emis_apres_le_releve_vaut_soumission(scene):
    """Témoin du précédent : l'envoi parti après le relevé est bien la soumission observée."""
    context, g = scene
    context._tp_releve_sequence = getattr(context, "_tp_sequence", 0)
    envoi = _requete("POST")
    g["request"](envoi)
    g["response"](_reponse(envoi, "http://app.test/api/creer", 201))

    assert H._soumission_observee(context) is True


def _environment():
    spec = importlib.util.spec_from_file_location("environment_reperes", config.BEHAVE_RUNTIME_DIR / "environment.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["environment_reperes"] = module
    spec.loader.exec_module(module)
    return module


def _step(type_, fonction):
    return SimpleNamespace(step_type=type_, name="un step", match=SimpleNamespace(func=fonction))


def _fonction_dans(fichier: str, *, non_assertive: bool):
    """Une fonction dont le code « vient » de `fichier` — c'est l'ORIGINE que le runtime regarde, pas le marqueur seul."""
    espace: dict = {}
    exec(compile("def f(context):\n    pass\n", fichier, "exec"), espace)
    if non_assertive:
        espace["f"]._tp_non_assertif = True
    return espace["f"]


@pytest.mark.parametrize("fichier, non_assertive, repere_deplace", [
    ("_generic_steps.py", True, False),    # pure attente du socle : le repère reste sur la vraie action
    ("_generic_steps.py", False, True),    # action du socle
    ("cas_genere_steps.py", True, True),   # le fichier GÉNÉRÉ ne peut pas se déclarer « pure attente »
])
def test_falsifiable_seule_une_pure_attente_du_socle_ne_deplace_pas_le_repere(monkeypatch, fichier, non_assertive,
                                                                              repere_deplace):
    env = _environment()
    monkeypatch.setenv("TP_GENERATED_STEPS_FILE", "cas_genere_steps.py")
    context = SimpleNamespace(page=SimpleNamespace(), _tp_sequence=7, _tp_reperes=(0, 3))

    env.before_step(context, _step("when", _fonction_dans(fichier, non_assertive=non_assertive)))

    assert context._tp_reperes == ((3, 7) if repere_deplace else (0, 3))
