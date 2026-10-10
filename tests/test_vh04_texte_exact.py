"""Lot VH-04, étape 3 (audit V7) — « la page affiche le texte » ne se satisfait plus d'un morceau de texte.

Avant : `get_by_text(texte)` de Playwright — sous-chaîne, sans casse. « 129,51 » était « affiché » sur une page qui affiche
« 1 129,51 € » (un total FAUX passait pour juste), « Command » dans « Commande », « commande validée » dans « Commande
validée ». Désormais : mot entier, casse respectée, un nombre n'est pas un morceau d'un plus grand nombre. Sans créer de faux
rouge : un texte mis en majuscules par la feuille de style se lit tel qu'AFFICHÉ (« COMMANDE VALIDÉE ») ou tel qu'ÉCRIT dans
la page (« Commande validée ») — mesuré le 2026-10-09 : Playwright compare le texte source, l'écran montre le texte rendu.

Prouvé de bout en bout : vrai Behave, vrai Chromium (marqueur `conformance`).
"""

from __future__ import annotations

import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from testpilot.execution.behave_runner import BehaveRunner
from testpilot.execution.executor import Executor
from testpilot.verdict import status as st

pytestmark = pytest.mark.conformance

_PAGES = Path(__file__).resolve().parent / "fixtures" / "torture_app"


class _Statique(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        page = _PAGES / ("accueil.html" if self.path in ("/", "") else self.path.split("?")[0].lstrip("/"))
        corps = page.read_bytes() if page.is_file() else b"absent"
        self.send_response(200 if page.is_file() else 404)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)


@pytest.fixture(scope="module")
def application():
    serveur = ThreadingHTTPServer(("127.0.0.1", 0), _Statique)
    fil = threading.Thread(target=serveur.serve_forever, daemon=True)
    fil.start()
    yield f"http://127.0.0.1:{serveur.server_address[1]}"
    serveur.shutdown()


def _verdicts(application: str, textes: list[str]) -> dict:
    lignes = ["Fonctionnalité: Texte exact", ""]
    for texte in textes:
        lignes += [f"  Scénario: {texte}", "    Soit j'accède à la page d'accueil de l'application",
                   '    Quand j\'ouvre la page "/textes.html"', f'    Alors la page affiche le texte "{texte}"', ""]
    dossier = Path(tempfile.mkdtemp(prefix="vh04_texte_"))
    (dossier / "tx.feature").write_text("\n".join(lignes), encoding="utf-8")
    runner = BehaveRunner(connection={"WEB_URL": application, "WEB_USER": "", "WEB_PASSWORD": ""},
                          connector_type="web", generated_dir=dossier)
    outcome = Executor(runner, max_retries=0).execute("tx")
    assert outcome.dry_run_passed, outcome.error
    return {v.name: v for v in st.derive_verdict(outcome, connector_type="web").scenarios}


AFFICHES = [
    "Commande validée",                       # tel qu'écrit dans la page
    "COMMANDE VALIDÉE",                       # tel qu'affiché (text-transform)
    "1 129,51 €",
    "12,50 €",
    "Le client « Dupont SARL » a été créé.",
    "Commandes en attente",
    "attente",                                # mot entier
]

# Chacun de ces textes était « affiché » avant le lot (sous-chaîne, sans casse) — sauf le texte caché.
NON_AFFICHES = [
    "129,51",            # morceau d'un plus grand nombre : un total faux passait pour juste
    "Command",           # morceau de mot
    "attent",
    "commande validée",  # mauvaise casse
    "Texte caché",       # présent dans la page mais invisible
    "Annulée",           # revue (B1) : option NON choisie d'une liste déroulante
    "Paiement accepté",  # revue (B1) : conteneur de hauteur nulle
    "12",                # revue : partie entière de « 12,50 € »
]


def test_les_textes_reellement_affiches_sont_trouves(application):
    for texte, v in _verdicts(application, AFFICHES).items():
        assert (v.execution_status, v.functional_status) == (st.EXEC_SUCCESS, st.FUNC_CONFORME), (
            f"« {texte} » : {v.execution_status}/{v.functional_status} — {v.error[:300]}")


def test_falsifiable_un_morceau_ou_une_autre_casse_n_est_pas_le_texte_affiche(application):
    for texte, v in _verdicts(application, NON_AFFICHES).items():
        assert v.functional_status == st.FUNC_NON_CONFORME, (
            f"« {texte} » : {v.execution_status}/{v.functional_status} — FAUX VERT si conforme")
