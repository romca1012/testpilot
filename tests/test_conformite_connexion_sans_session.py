"""« j'accède à la page de connexion sans me connecter » ouvre RÉELLEMENT une page sans session (2026-10-07).

Défaut trouvé par le PREMIER essai réel du banc d'agents : depuis le lot 07b-2, le run se connecte UNE fois avant le
premier scénario (`storage_state.json`) et réutilise cette session pour chaque scénario. Le step « … sans me connecter »
ouvrait donc un navigateur DÉJÀ connecté : une application qui redirige l'utilisateur connecté (ici `/connexion` →
`/produits`) n'affichait jamais son formulaire, et tout test de connexion négative sortait `technical_error`
(« Champ 'username' introuvable sur …/produits ») — le test était juste, c'est l'outil qui mentait sur l'état du navigateur.

Preuve de bout en bout : vrai Behave + vrai Chromium + l'application locale du banc (`banc/app_web/`), avec les identifiants
du projet (donc une connexion initiale et une session mémorisée). Exclue de `pytest -q` (marker `conformance`).
"""

from __future__ import annotations

import sys
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path

import pytest

from banc.app_web import serveur
from testpilot.execution.behave_runner import BehaveRunner
from testpilot.execution.executor import Executor
from testpilot.verdict import status as st

_STEPS_LIB = Path(__file__).resolve().parent.parent / "behave_runtime" / "steps_library"
sys.path.insert(0, str(_STEPS_LIB))

pytestmark = pytest.mark.conformance

_FEATURE = """Fonctionnalité: Connexion sans session
  Scénario: {titre}
    Soit j'accède à la page de connexion sans me connecter
    Alors la page affiche le texte "Connexion"
    Et la page affiche le texte "Se connecter"
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


def _rejouer(url: str, titre: str):
    dossier = Path(tempfile.mkdtemp(prefix="sans_session_"))
    module = "sans_session"
    (dossier / f"{module}.feature").write_text(_FEATURE.format(titre=titre), encoding="utf-8")
    (dossier / f"{module}_steps.py").write_text("from behave import given, when, then\n", encoding="utf-8")
    runner = BehaveRunner(
        connection={"WEB_URL": url, "WEB_USER": "testeur", "WEB_PASSWORD": "motdepasse-test"},
        connector_type="web", generated_dir=dossier)
    outcome = Executor(runner, max_retries=0).execute(module)
    return outcome, st.derive_verdict(outcome, connector_type="web")


def test_la_page_de_connexion_s_affiche_meme_quand_le_run_a_une_session_memorisee():
    with _application() as url:
        outcome, verdict = _rejouer(url, "formulaire visible malgré la session du run")

    assert outcome.real_run.scenarios[0].status == "passed", (
        f"le formulaire de connexion n'était pas affiché : {outcome.real_run.scenarios[0].error!r}")
    assert (verdict.execution_status, verdict.functional_status) == (st.EXEC_SUCCESS, st.FUNC_CONFORME)
