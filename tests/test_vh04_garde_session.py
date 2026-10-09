"""Lot VH-04, étape 2 (audit V8, garantie G4) — une session perdue avant un `Alors` bloque le test, jamais un verdict.

Prouvé de bout en bout : vrai Behave, vrai Chromium, contre une petite application à session (formulaire de connexion,
cookie de session, expiration côté serveur, déconnexion). Avant ce lot, après une expiration de session :
- « la page n'affiche pas le texte … » passait sur la page de connexion → `conforme` sans avoir rien regardé (FAUX VERT) ;
- « la page affiche le texte … » échouait → `non_conforme`, une accusation de l'application pour un problème d'environnement.
Et les parcours légitimes qui finissent sur la page de connexion (déconnexion voulue, test de connexion refusée, page de
connexion ouverte par le test) restent jugés normalement.
"""

from __future__ import annotations

import secrets
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

import pytest

from testpilot.execution.behave_runner import BehaveRunner
from testpilot.execution.executor import Executor
from testpilot.verdict import status as st

pytestmark = pytest.mark.conformance

_SESSIONS: set[str] = set()

_FORMULAIRE = """<html><body><h1>Connexion</h1>{erreur}
<form method="post" action="/connexion">
<label for="id">Identifiant</label><input id="id" name="identifiant" type="text">
<label for="mdp">Mot de passe</label><input id="mdp" name="mot_de_passe" type="password">
<button type="submit">Se connecter</button></form></body></html>"""

_APP = """<html><body><h1>Tableau de bord</h1><p>Bienvenue testeur</p>
<form method="get" action="/deconnexion"><button type="submit">Se déconnecter</button></form></body></html>"""


class _Application(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _html(self, corps: str, code=200, entetes=None):
        donnees = corps.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(donnees)))
        for cle, valeur in (entetes or {}).items():
            self.send_header(cle, valeur)
        self.end_headers()
        self.wfile.write(donnees)

    def _rediriger(self, cible, entetes=None):
        self.send_response(302)
        self.send_header("Location", cible)
        self.send_header("Content-Length", "0")
        for cle, valeur in (entetes or {}).items():
            self.send_header(cle, valeur)
        self.end_headers()

    def _sid(self):
        for morceau in (self.headers.get("Cookie") or "").split(";"):
            nom, _, valeur = morceau.strip().partition("=")
            if nom == "sid":
                return valeur
        return ""

    def do_GET(self):
        chemin, _, requete = self.path.partition("?")
        if chemin == "/":
            return self._rediriger("/app")
        if chemin == "/connexion":
            erreur = "<p>Identifiants invalides</p>" if "erreur=1" in requete else ""
            return self._html(_FORMULAIRE.format(erreur=erreur))
        if chemin == "/app":
            return self._html(_APP) if self._sid() in _SESSIONS else self._rediriger("/connexion")
        if chemin == "/expirer":  # le SERVEUR invalide la session ; le cookie reste dans le navigateur
            _SESSIONS.discard(self._sid())
            return self._rediriger("/app")
        if chemin == "/deconnexion":  # déconnexion voulue : l'application SUPPRIME son cookie
            _SESSIONS.discard(self._sid())
            return self._rediriger("/connexion", {"Set-Cookie": "sid=; Max-Age=0; Path=/"})
        self._html("absent", 404)

    def do_POST(self):
        champs = parse_qs(self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode())
        if champs.get("identifiant") == ["testeur"] and champs.get("mot_de_passe") == ["secret"]:
            jeton = secrets.token_hex(8)
            _SESSIONS.add(jeton)
            return self._rediriger("/app", {"Set-Cookie": f"sid={jeton}; Path=/"})
        self._rediriger("/connexion?erreur=1")


@pytest.fixture(scope="module")
def application():
    serveur = ThreadingHTTPServer(("127.0.0.1", 0), _Application)
    fil = threading.Thread(target=serveur.serve_forever, daemon=True)
    fil.start()
    yield f"http://127.0.0.1:{serveur.server_address[1]}"
    serveur.shutdown()


def _rejouer(application: str, scenarios: dict[str, list[str]]) -> dict:
    lignes = ["Fonctionnalité: Garde de session", ""]
    for titre, etapes in scenarios.items():
        lignes += [f"  Scénario: {titre}", "    Soit j'accède à la page d'accueil de l'application",
                   *[f"    {e}" for e in etapes], ""]
    dossier = Path(tempfile.mkdtemp(prefix="vh04_session_"))
    (dossier / "gs.feature").write_text("\n".join(lignes), encoding="utf-8")
    runner = BehaveRunner(connection={"WEB_URL": application, "WEB_USER": "testeur", "WEB_PASSWORD": "secret",
                                      "TESTPILOT_AUTH_STRATEGIE": "formulaire"},
                          connector_type="web", generated_dir=dossier)
    outcome = Executor(runner, max_retries=0).execute("gs")
    assert outcome.dry_run_passed, outcome.error
    return {v.name: v for v in st.derive_verdict(outcome, connector_type="web").scenarios}


SESSION_PERDUE = {
    "absence constatée après une expiration de session": [
        'Quand j\'ouvre la page "/expirer"', 'Alors la page n\'affiche pas le texte "Erreur"'],
    "présence constatée après une expiration de session": [
        'Quand j\'ouvre la page "/expirer"', 'Alors la page affiche le texte "Tableau de bord"'],
}

LEGITIMES = {
    "page de l'application, session valide": ['Quand j\'ouvre la page "/app"', 'Alors la page affiche le texte "Tableau de bord"'],
    "déconnexion voulue par le test": [
        'Quand j\'ouvre la page "/app"', 'Et je clique sur le bouton "Se déconnecter"',
        'Alors la page affiche le texte "Connexion"'],
    "test de connexion refusée (le test saisit un mot de passe)": [
        'Quand j\'accède à la page de connexion sans me connecter',
        'Et je renseigne le champ "Identifiant" avec la valeur "testeur"',
        'Et je renseigne le champ "Mot de passe" avec la valeur "faux"', 'Et je clique sur le bouton "Se connecter"',
        'Alors la page affiche le texte "Identifiants invalides"',
        'Et la page n\'affiche pas le texte "Tableau de bord"'],
    "page de connexion ouverte par le test": [
        'Quand j\'accède à la page de connexion sans me connecter', 'Alors la page affiche le texte "Connexion"'],
}


def test_falsifiable_une_session_perdue_avant_un_alors_bloque_le_test(application):
    verdicts = _rejouer(application, SESSION_PERDUE)

    for titre, v in verdicts.items():
        assert (v.execution_status, v.functional_status) == (st.EXEC_BLOCKED, st.FUNC_INDETERMINE), (
            f"« {titre} » : {v.execution_status}/{v.functional_status} — {v.error[:300]}")
        assert "session a été perdue" in v.error


def test_les_parcours_qui_finissent_legitimement_sur_la_connexion_restent_juges(application):
    verdicts = _rejouer(application, LEGITIMES)

    for titre, v in verdicts.items():
        assert (v.execution_status, v.functional_status) == (st.EXEC_SUCCESS, st.FUNC_CONFORME), (
            f"« {titre} » : {v.execution_status}/{v.functional_status} — {v.error[:300]}")
