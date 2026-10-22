"""Étape 5 du plan unique (VH-04, reste 1) — « la page affiche le texte X » exige que X soit APPARU après la dernière action.

Avant : un texte déjà à l'écran (titre fixe, libellé de menu) suffisait. Un clic que l'application ignore laissait la page
inchangée, et « Alors la page affiche le texte "Nouveau client" » sortait « Passé » sans rien prouver de l'action. Désormais,
sur la MÊME page (même adresse, aucune page nouvellement demandée) : présent avant et pas davantage après → « non
concluant » (jamais « Passé », jamais « Échoué ») ; apparu → « Passé » ; absent → « Échoué », comme avant. Une action qui mène
à une autre page (adresse changée, page rouverte) : le texte de la page atteinte suffit — limite acceptée : un libellé de
menu présent sur la page d'arrivée la « prouve » encore.

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

_PAGES = {
    "/client.html": (
        "<html><body><nav><a href='/commandes.html'>Commandes</a></nav><h1>Nouveau client</h1>"
        "<button onclick=\"document.getElementById('z').textContent='Client enregistré'\">Enregistrer</button>"
        "<button onclick=\"\">Ignorer</button><div id='z'></div>"
        "<form method='post' action='/client.html'><button type='submit'>Renvoyer</button></form>"
        "<form method='post' action='/redirige'><button type='submit'>Envoyer puis rediriger</button></form>"
        "</body></html>"),
    "/commandes.html": "<html><body><nav><a href='/commandes.html'>Commandes</a></nav><h1>Commandes</h1></body></html>",
    "/vide.html": "<html><body><nav><a href='/commandes.html'>Commandes</a></nav><p>Rien</p></body></html>",
    # Revue (bloquant) : une notification qui s'efface seule pendant l'attente du constat.
    "/notification.html": (
        "<html><body><button onclick=\"var n=document.getElementById('n');n.textContent='Enregistré';"
        "setTimeout(function(){n.textContent='';},3000)\">Enregistrer</button><button onclick=\"\">Fermer</button>"
        "<div id='n'></div></body></html>"),
}


class _Statique(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if self.path == "/redirige":  # revue (seconde passe) : l'envoi est ignoré, 303 vers la même page (motif PRG)
            self.send_response(303)
            self.send_header("Location", "/client.html")
            self.send_header("Content-Length", "0")
            return self.end_headers()
        self.do_GET()  # l'application ignore l'envoi et réaffiche la même page, à la même adresse

    def do_GET(self):
        corps = _PAGES.get(self.path.split("?")[0], "<html><body>Accueil</body></html>").encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)


@pytest.fixture(scope="module")
def application():
    serveur = ThreadingHTTPServer(("127.0.0.1", 0), _Statique)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{serveur.server_address[1]}"
    serveur.shutdown()


def _verdicts(application: str, scenarios: dict[str, list[str]]) -> dict:
    lignes = ["Fonctionnalité: Texte apparu", ""]
    for nom, steps in scenarios.items():
        lignes += [f"  Scénario: {nom}"] + [f"    {s}" for s in steps] + [""]
    dossier = Path(tempfile.mkdtemp(prefix="texte_apparu_"))
    (dossier / "ta.feature").write_text("\n".join(lignes), encoding="utf-8")
    runner = BehaveRunner(connection={"WEB_URL": application, "WEB_USER": "", "WEB_PASSWORD": ""},
                          connector_type="web", generated_dir=dossier)
    outcome = Executor(runner, max_retries=0).execute("ta")
    assert outcome.dry_run_passed, outcome.error
    return {v.name: v for v in st.derive_verdict(outcome, connector_type="web").scenarios}


_SUR_LA_FICHE = ['Soit j\'ouvre la page "/client.html"']

SCENARIOS = {
    "apparu": _SUR_LA_FICHE + ['Quand je clique sur le bouton "Enregistrer"',
                               'Alors la page affiche le texte "Client enregistré"'],
    "clic ignoré": _SUR_LA_FICHE + ['Quand je clique sur le bouton "Ignorer"',
                                    'Alors la page affiche le texte "Nouveau client"'],
    "même page rouverte": _SUR_LA_FICHE + ['Quand j\'ouvre la page "/client.html"',
                                           'Alors la page affiche le texte "Nouveau client"'],
    "titre ajouté au menu": _SUR_LA_FICHE + ['Quand j\'ouvre la page "/commandes.html"',
                                             'Alors la page affiche le texte "Commandes"'],
    "seul le menu": _SUR_LA_FICHE + ['Quand j\'ouvre la page "/vide.html"', 'Alors la page affiche le texte "Commandes"'],
    "formulaire renvoyé sans effet": _SUR_LA_FICHE + ['Quand je clique sur le bouton "Renvoyer"',
                                                      'Alors la page affiche le texte "Nouveau client"'],
    "formulaire redirigé sans effet": _SUR_LA_FICHE + ['Quand je clique sur le bouton "Envoyer puis rediriger"',
                                                       'Alors la page affiche le texte "Nouveau client"'],
    "absent": _SUR_LA_FICHE + ['Quand je clique sur le bouton "Ignorer"',
                               'Alors la page affiche le texte "Client enregistré"'],
    "premier écran": ['Soit j\'ouvre la page "/client.html"', 'Alors la page affiche le texte "Nouveau client"'],
    "notification effacée pendant l'attente": [
        'Soit j\'ouvre la page "/notification.html"', 'Quand je clique sur le bouton "Enregistrer"',
        'Et je clique sur le bouton "Fermer"', 'Alors la page affiche le texte "Enregistré"'],
}


@pytest.fixture(scope="module")
def verdicts(application):
    return _verdicts(application, SCENARIOS)


def _paire(v):
    return v.execution_status, v.functional_status


def test_un_texte_apparu_apres_l_action_est_passe(verdicts):
    for nom in ("apparu", "titre ajouté au menu", "premier écran"):
        assert _paire(verdicts[nom]) == (st.EXEC_SUCCESS, st.FUNC_CONFORME), (nom, verdicts[nom].error[:300])


def test_falsifiable_un_texte_deja_la_avant_l_action_n_est_jamais_passe(verdicts):
    for nom in ("clic ignoré", "formulaire renvoyé sans effet", "formulaire redirigé sans effet",
                "notification effacée pendant l'attente"):
        assert verdicts[nom].functional_status == st.FUNC_INDETERMINE, (
            nom, _paire(verdicts[nom]), "FAUX VERT si conforme, faux rouge si non_conforme")


def test_un_texte_absent_reste_un_echec(verdicts):
    assert verdicts["absent"].functional_status == st.FUNC_NON_CONFORME


def test_limite_connue_a97_une_page_rouverte_ou_atteinte_se_prouve_par_son_texte(verdicts):
    """Limite CONNUE d'A97, pas un comportement voulu : quand l'action mène à une page (page rouverte, autre adresse), le texte
    de la page atteinte suffit — un libellé de menu présent sur la page d'arrivée la « prouve » encore. Si cette limite est
    fermée un jour, ce test changera avec elle (décision au registre)."""
    for nom in ("même page rouverte", "seul le menu"):
        assert _paire(verdicts[nom]) == (st.EXEC_SUCCESS, st.FUNC_CONFORME), (nom, verdicts[nom].error[:300])
