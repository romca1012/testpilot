"""Étape 4 (A70) : un cas « joué en tant que lecteur » l'est RÉELLEMENT — vrai Behave, vrai Chromium, application locale du banc
(`banc/app_web/`), qui affiche « Connecté en tant que <identifiant> ».

Falsifiable : le même test sort NON conforme quand le harnais joue le compte principal (ce que ferait un repli silencieux), et
BLOQUÉ quand le compte demandé n'existe pas — jamais joué avec un autre compte. Exclue de `pytest -q` (marker `conformance`).
"""

from __future__ import annotations

import json
import sys
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path

import pytest

from banc.app_web import serveur
from testpilot.connectors.runtime_env import ENV_COMPTE_DU_TEST, ENV_COMPTES
from testpilot.execution.behave_runner import BehaveRunner
from testpilot.execution.executor import Executor
from testpilot.verdict import status as st

_STEPS_LIB = Path(__file__).resolve().parent.parent / "behave_runtime" / "steps_library"
sys.path.insert(0, str(_STEPS_LIB))

pytestmark = pytest.mark.conformance

_FEATURE = """Fonctionnalité: Compte du cas
  Scénario: la page dit qui est connecté
    Soit j'ouvre la page "/produits"
    Alors la page affiche le texte "Connecté en tant que lecteur"
"""


@contextmanager
def _application():
    srv = serveur.creer_serveur("127.0.0.1", 0, "")
    fil = threading.Thread(target=srv.serve_forever, daemon=True)
    fil.start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}"
    finally:
        srv.shutdown()
        srv.server_close()
        fil.join(timeout=5)


def _jouer(url: str, compte_du_test: str | None, strategie: str = ""):
    dossier = Path(tempfile.mkdtemp(prefix="compte_du_cas_"))
    module = "compte_du_cas"
    (dossier / f"{module}.feature").write_text(_FEATURE, encoding="utf-8")
    (dossier / f"{module}_steps.py").write_text("from behave import given, when, then\n", encoding="utf-8")
    connexion = {"WEB_URL": url, "WEB_USER": serveur.IDENTIFIANT_TEST, "WEB_PASSWORD": serveur.MOT_DE_PASSE_TEST,
                 ENV_COMPTES: json.dumps([{"label": "Lecteur", "username": serveur.IDENTIFIANT_LECTEUR,
                                           "password": serveur.MOT_DE_PASSE_LECTEUR}])}
    if compte_du_test:
        connexion[ENV_COMPTE_DU_TEST] = compte_du_test
    if strategie:
        connexion["TESTPILOT_AUTH_STRATEGIE"] = strategie
    runner = BehaveRunner(connection=connexion, connector_type="web", generated_dir=dossier)
    outcome = Executor(runner, max_retries=0).execute(module)
    return st.derive_verdict(outcome, connector_type="web")


def test_falsifiable_le_cas_est_joue_avec_son_compte_et_jamais_un_autre():
    with _application() as url:
        avec_le_lecteur = _jouer(url, "Lecteur")
        avec_le_principal = _jouer(url, None)
        compte_inconnu = _jouer(url, "Gestionnaire")
        sans_connexion = _jouer(url, "Lecteur", strategie="aucune")

    assert (avec_le_lecteur.execution_status, avec_le_lecteur.functional_status) == (st.EXEC_SUCCESS, st.FUNC_CONFORME)
    assert avec_le_principal.functional_status == st.FUNC_NON_CONFORME, "joué avec le principal : la page dit « testeur »"
    assert compte_inconnu.execution_status == st.EXEC_BLOCKED, "un compte inconnu bloque, jamais un repli sur le principal"
    assert compte_inconnu.functional_status == st.FUNC_INDETERMINE
    assert (sans_connexion.execution_status, sans_connexion.functional_status) == (st.EXEC_BLOCKED, st.FUNC_INDETERMINE),         "un projet sans connexion ne joue jamais un cas « en tant que » : ce serait un run anonyme"
