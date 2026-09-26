"""Lot 07b-1 (D8) — « je me connecte en tant que "<libellé>" », prouvé de bout en bout : Behave + Chromium RÉELS, application locale.

Une petite application à DEUX comptes qui ne voient pas la même chose (`admin` → « Menu : Administration », `banc_commercial` → « Menu :
Ventes »), sans réseau. Les vrais scénarios sont rejoués dans le sous-processus complet (`BehaveRunner`), avec les comptes secondaires
transmis par l'environnement (`TESTPILOT_COMPTES`), exactement comme en production.

Ce que ça prouve, et surtout ce que ça REFUSE de laisser passer (falsifiabilité, CLAUDE.md §4) :
- le changement de compte repart d'un contexte NEUF : le nouveau compte ne voit rien de la session de l'ancien ;
- SANS le step, le scénario reste sur le compte principal et l'assertion « Ventes » échoue (`non_conforme`) ;
- un libellé inconnu, un mot de passe refusé, une liste de comptes illisible → `blocked` (le test n'a pas pu entrer), jamais un vert.
"""

from __future__ import annotations

import json
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

import pytest

from testpilot.connectors.runtime_env import ENV_COMPTES
from testpilot.execution.behave_runner import BehaveRunner
from testpilot.execution.executor import Executor
from testpilot.verdict import status as st

pytestmark = pytest.mark.conformance

UTILISATEURS = {"admin": ("pw-admin", "Administration"), "banc_commercial": ("pw-commercial", "Ventes")}
COMPTES = [{"label": "Commercial", "username": "banc_commercial", "password": "pw-commercial"},
           {"label": "Mauvais mot de passe", "username": "banc_commercial", "password": "pas-le-bon"}]

_LOGIN = """<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Connexion</title></head><body>
<h1>Connexion</h1>{erreur}
<form method="post" action="/connexion">
<label>Identifiant <input type="text" name="username"></label>
<label>Mot de passe <input type="password" name="password"></label>
<button type="submit">Se connecter</button></form></body></html>"""


class _Application(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _envoyer(self, code, corps: str, entetes=None):
        octets = corps.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(octets)))
        for cle, valeur in (entetes or {}).items():
            self.send_header(cle, valeur)
        self.end_headers()
        self.wfile.write(octets)

    def _utilisateur(self):
        for morceau in (self.headers.get("Cookie") or "").split(";"):
            cle, _, valeur = morceau.strip().partition("=")
            if cle == "u" and valeur in UTILISATEURS:
                return valeur
        return None

    def do_GET(self):
        utilisateur = self._utilisateur()
        if utilisateur is None:
            return self._envoyer(200, _LOGIN.format(erreur=""))
        if self.path.split("?")[0] == "/":   # déjà connecté : l'accueil vit à une AUTRE URL (le critère de connexion exige que l'URL change)
            return self._envoyer(303, "", {"Location": "/accueil"})
        self._envoyer(200, f"<!doctype html><html><head><meta charset='utf-8'><title>Accueil</title></head><body>"
                           f"<h1>Bonjour {utilisateur}</h1><p>Menu : {UTILISATEURS[utilisateur][1]}</p></body></html>")

    def do_POST(self):
        champs = parse_qs(self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode())
        nom, mdp = champs.get("username", [""])[0], champs.get("password", [""])[0]
        if nom in UTILISATEURS and UTILISATEURS[nom][0] == mdp:
            return self._envoyer(303, "", {"Location": "/accueil", "Set-Cookie": f"u={nom}; Path=/"})
        self._envoyer(200, _LOGIN.format(erreur="<p role='alert'>Identifiant ou mot de passe incorrect</p>"))


@pytest.fixture(scope="module")
def application():
    serveur = ThreadingHTTPServer(("127.0.0.1", 0), _Application)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{serveur.server_address[1]}"
    serveur.shutdown()


def _rejouer(application: str, scenarios: dict[str, list[str]], *, comptes=None) -> dict:
    lignes = ["Fonctionnalité: Comptes multiples", ""]
    for titre, etapes in scenarios.items():
        lignes += [f"  Scénario: {titre}", "    Soit j'accède à la page d'accueil de l'application", *[f"    {e}" for e in etapes], ""]
    dossier = Path(tempfile.mkdtemp(prefix="l07b_"))
    (dossier / "vu.feature").write_text("\n".join(lignes), encoding="utf-8")
    connexion = {"WEB_URL": application, "WEB_USER": "admin", "WEB_PASSWORD": "pw-admin"}
    connexion[ENV_COMPTES] = comptes if isinstance(comptes, str) else json.dumps(COMPTES if comptes is None else comptes)
    runner = BehaveRunner(connection=connexion, connector_type="web", generated_dir=dossier)
    outcome = Executor(runner, max_retries=0).execute("vu")
    assert outcome.dry_run_passed, f"les steps ne se résolvent pas (non définis / ambigus) : {outcome.error}"
    return {v.name: v for v in st.derive_verdict(outcome, connector_type="web").scenarios}


def test_changer_de_compte_repart_d_un_contexte_neuf_et_chaque_compte_voit_ses_propres_droits(application):
    v = _rejouer(application, {"admin, puis le commercial, puis retour": [
        'Alors la page affiche le texte "Menu : Administration"',
        'Quand je me connecte en tant que "Commercial"',
        'Alors la page affiche le texte "Menu : Ventes"',
        'Et la page affiche le texte "Bonjour banc_commercial"',
        'Et la page n\'affiche pas le texte "Menu : Administration"',
        'Quand je me connecte en tant que "principal"',
        'Alors la page affiche le texte "Menu : Administration"',
        'Et la page n\'affiche pas le texte "Menu : Ventes"']})["admin, puis le commercial, puis retour"]

    assert (v.execution_status, v.functional_status) == (st.EXEC_SUCCESS, st.FUNC_CONFORME), v.error[:400]


def test_falsifiable_sans_le_step_le_scenario_reste_sur_le_compte_principal(application):
    """Le contrôle qui rend le test vert du dessus significatif : sans changement de compte, « Ventes » n'est PAS affiché."""
    v = _rejouer(application, {"sans changer": ['Alors la page affiche le texte "Menu : Ventes"']})["sans changer"]

    assert v.functional_status == st.FUNC_NON_CONFORME, (v.execution_status, v.functional_status)


def test_falsifiable_la_session_de_l_ancien_compte_ne_survit_pas(application):
    """Si le contexte n'était pas remplacé, le commercial verrait encore « Administration » (cookie de l'admin)."""
    v = _rejouer(application, {"isolation": [
        'Quand je me connecte en tant que "Commercial"',
        'Alors la page affiche le texte "Menu : Administration"']})["isolation"]

    assert v.functional_status == st.FUNC_NON_CONFORME


@pytest.mark.parametrize("etapes,comptes,attendu", [
    (['Quand je me connecte en tant que "Comptable"'], None, "compte inconnu"),
    (['Quand je me connecte en tant que "Mauvais mot de passe"'], None, "mot de passe refusé"),
    (['Quand je me connecte en tant que "Commercial"'], "pas du json", "liste de comptes illisible"),
    (['Quand je me connecte en tant que "Commercial"'], [], "aucun compte secondaire déclaré"),
])
def test_falsifiable_un_compte_inconnu_refuse_ou_illisible_bloque_jamais_un_vert(application, etapes, comptes, attendu):
    v = _rejouer(application, {attendu: [*etapes, 'Alors la page affiche le texte "Menu : Ventes"']}, comptes=comptes)[attendu]

    assert v.execution_status == st.EXEC_BLOCKED, (attendu, v.execution_status, v.functional_status, v.error[:300])
    assert v.functional_status != st.FUNC_CONFORME
    assert "pw-commercial" not in v.error and "pas-le-bon" not in v.error, "un message d'erreur ne porte jamais un secret"
