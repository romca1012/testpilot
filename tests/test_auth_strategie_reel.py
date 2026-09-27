"""Lot 07b-2 (C2) — la stratégie de connexion du compte principal, prouvée de bout en bout : Behave + Chromium RÉELS, une
petite application HTTP locale à sessions (aucun réseau tiers).

Chaque famille est un run COMPLET (avant_all inclus), comme le vivrait une vraie campagne :

- **réutilisée** : le compte principal se connecte UNE fois (`before_all`) ; ses scénarios n'ont PLUS à passer par le
  formulaire — vérifié en comptant les connexions RÉELLEMENT soumises au serveur ;
- **invalidée puis reconnectée** : une session tuée en cours de run est réparée UNE fois, jamais deux (falsifiable : une
  seconde invalidation dans le même scénario bloque plutôt que de retenter) ;
- **TOTP** : un vrai secret, un vrai code à usage unique généré et vérifié ;
- **session déjà ouverte** (session_injectee) : un `storage_state` fourni authentifie sans aucun formulaire ; expiré, TOUT
  le run est `blocked` (jamais un défaut applicatif présumé) — dès `before_all`, avant le premier scénario.
"""

from __future__ import annotations

import json
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs
from urllib.request import urlopen

import pyotp
import pytest

from testpilot.connectors.auth_strategie import ENV_INJECTED_SESSION, ENV_STRATEGIE, ENV_TOTP_SECRET
from testpilot.execution.behave_runner import BehaveRunner
from testpilot.execution.executor import Executor
from testpilot.verdict import status as st

pytestmark = pytest.mark.conformance

UTILISATEUR, MOT_DE_PASSE = "admin", "s3cret-pw"
_PAGE_LOGIN = """<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Connexion</title></head><body>
<h1>Connexion</h1>
<form method="post" action="/login">
<label>Identifiant <input type="text" name="username"></label>
<label>Mot de passe <input type="password" name="password"></label>
<button type="submit">Se connecter</button></form></body></html>"""
_PAGE_CODE = """<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Code</title></head><body>
<h1>Code de vérification</h1>
<form method="post" action="/code"><input type="text" name="code"><button type="submit">Valider</button></form>
</body></html>"""


def _fabriquer_application(mode: str, totp_secret: str = ""):
    """`(classe de handler, état partagé)` — `état` reste accessible au test (compteur de connexions, sessions injectées à la main
    pour `session_injectee`, sans passer par un navigateur)."""
    etat = {"sessions": {}, "connexions_reussies": 0}

    class _App(BaseHTTPRequestHandler):
        def log_message(self, *_a):
            pass

        def _cookie_sid(self):
            for morceau in (self.headers.get("Cookie") or "").split(";"):
                cle, _, valeur = morceau.strip().partition("=")
                if cle == "sid":
                    return valeur
            return None

        def _authentifie(self):
            return etat["sessions"].get(self._cookie_sid()) == "ok"

        def _envoyer(self, code, corps: str, entetes=None, type_="text/html; charset=utf-8"):
            octets = corps.encode()
            self.send_response(code)
            self.send_header("Content-Type", type_)
            self.send_header("Content-Length", str(len(octets)))
            for cle, valeur in (entetes or {}).items():
                self.send_header(cle, valeur)
            self.end_headers()
            self.wfile.write(octets)

        def do_GET(self):
            chemin = self.path.split("?")[0]
            if chemin == "/login":
                return self._envoyer(200, _PAGE_LOGIN)
            if chemin == "/code":
                if etat["sessions"].get(self._cookie_sid()) != "code_attendu":
                    return self._envoyer(303, "", {"Location": "/login"})
                return self._envoyer(200, _PAGE_CODE)
            if chemin == "/invalider-session":
                etat["sessions"].pop(self._cookie_sid(), None)
                return self._envoyer(200, "<html><body>Session invalidée</body></html>")
            if chemin == "/debug/compteur-connexions":
                return self._envoyer(200, json.dumps({"n": etat["connexions_reussies"]}), type_="application/json")
            if chemin == "/compte/mot-de-passe":
                # Une page METIER légitime, atteinte SANS redirection (jamais via /login) : affiche un champ mot de passe
                # sans que ce soit une invalidation de session (revue a posteriori, 2026-09-28).
                return self._envoyer(200, "<html><body><h1>Changer mon mot de passe</h1>"
                                          "<input type='password' name='ancien'></body></html>")
            if chemin == "/":
                if mode == "public" or self._authentifie():
                    return self._envoyer(200, "<html><body><h1>Bienvenue</h1></body></html>")
                return self._envoyer(303, "", {"Location": "/login"})
            self._envoyer(404, "absent")

        def do_POST(self):
            chemin = self.path.split("?")[0]
            champs = parse_qs(self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode())
            if chemin == "/login":
                if champs.get("username", [""])[0] == UTILISATEUR and champs.get("password", [""])[0] == MOT_DE_PASSE:
                    sid = f"sid-{len(etat['sessions']) + 1}-{time.time_ns()}"
                    if mode == "totp":
                        etat["sessions"][sid] = "code_attendu"
                        return self._envoyer(303, "", {"Location": "/code", "Set-Cookie": f"sid={sid}; Path=/"})
                    etat["sessions"][sid] = "ok"
                    etat["connexions_reussies"] += 1
                    return self._envoyer(303, "", {"Location": "/", "Set-Cookie": f"sid={sid}; Path=/"})
                return self._envoyer(200, _PAGE_LOGIN)
            if chemin == "/code":
                sid = self._cookie_sid()
                code = champs.get("code", [""])[0]
                if (etat["sessions"].get(sid) == "code_attendu"
                        and pyotp.TOTP(totp_secret).verify(code, valid_window=1)):
                    etat["sessions"][sid] = "ok"
                    etat["connexions_reussies"] += 1
                    return self._envoyer(303, "", {"Location": "/"})
                return self._envoyer(200, _PAGE_CODE)
            self._envoyer(404, "absent")

    return _App, etat


def _demarrer(mode: str, totp_secret: str = ""):
    classe, etat = _fabriquer_application(mode, totp_secret)
    serveur = ThreadingHTTPServer(("127.0.0.1", 0), classe)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    return serveur, f"http://127.0.0.1:{serveur.server_address[1]}", etat


def _compteur(base_url: str) -> int:
    with urlopen(f"{base_url}/debug/compteur-connexions") as r:
        return json.loads(r.read())["n"]


def _rejouer(base_url: str, scenarios: dict[str, list[str]], *, auth_strategie="formulaire", totp_secret="",
            injected_session="", identifiants=True) -> dict:
    lignes = ["Fonctionnalité: Stratégie de connexion", ""]
    for titre, etapes in scenarios.items():
        lignes += [f"  Scénario: {titre}", *[f"    {e}" for e in etapes], ""]
    dossier = Path(tempfile.mkdtemp(prefix="l07b2_"))
    (dossier / "vu.feature").write_text("\n".join(lignes), encoding="utf-8")
    connexion = {"WEB_URL": base_url,
                "WEB_USER": UTILISATEUR if identifiants else "", "WEB_PASSWORD": MOT_DE_PASSE if identifiants else "",
                ENV_STRATEGIE: auth_strategie}
    if totp_secret:
        connexion[ENV_TOTP_SECRET] = totp_secret
    if injected_session:
        connexion[ENV_INJECTED_SESSION] = injected_session
    runner = BehaveRunner(connection=connexion, connector_type="web", generated_dir=dossier)
    outcome = Executor(runner, max_retries=0).execute("vu")
    assert outcome.dry_run_passed, f"les steps ne se résolvent pas : {outcome.error}"
    verdict = st.derive_verdict(outcome, connector_type="web")
    return {v.name: v for v in verdict.scenarios}


# ── Réutilisée : une seule connexion pour DEUX scénarios du même run ───────────────────────────────────────────────────────


def test_la_session_du_compte_principal_est_reutilisee_entre_scenarios():
    serveur, base_url, etat = _demarrer("formulaire")
    try:
        verdicts = _rejouer(base_url, {
            "premier scénario": ['Soit j\'accède à la page d\'accueil de l\'application', 'Alors la page affiche le texte "Bienvenue"'],
            "second scénario": ['Soit j\'accède à la page d\'accueil de l\'application', 'Alors la page affiche le texte "Bienvenue"'],
        })

        for titre, v in verdicts.items():
            assert (v.execution_status, v.functional_status) == (st.EXEC_SUCCESS, st.FUNC_CONFORME), (titre, v.error[:300])
        assert _compteur(base_url) == 1, "une SEULE connexion (before_all) pour les deux scénarios : pas de formulaire refait"
    finally:
        serveur.shutdown()


def test_une_application_sans_aucun_formulaire_est_accessible_sans_identifiants():
    """Régression du commit qui a corrigé le lot 07b-2 initial (une application PUBLIQUE, sans aucun champ mot de passe,
    bloquait tout le run faute d'identifiants) — sans test de non-régression jusqu'ici (revue a posteriori, 2026-09-28)."""
    serveur, base_url, etat = _demarrer("public")
    try:
        v = _rejouer(base_url, {"application publique": [
            'Soit j\'accède à la page d\'accueil de l\'application',
            'Alors la page affiche le texte "Bienvenue"']}, identifiants=False)["application publique"]

        assert (v.execution_status, v.functional_status) == (st.EXEC_SUCCESS, st.FUNC_CONFORME), v.error[:400]
        assert _compteur(base_url) == 0, "aucun formulaire n'existe : aucune connexion n'a pu être comptée"
    finally:
        serveur.shutdown()


def test_falsifiable_un_champ_mot_de_passe_atteint_sans_redirection_ne_consomme_pas_la_reconnexion():
    """Une page métier légitime (« changer mon mot de passe »), atteinte SANS redirection vers /login, ne doit jamais
    être prise pour une session invalidée — sinon elle consommerait à tort l'unique reconnexion du scénario, et une VRAIE
    invalidation plus tard resterait sans recours (revue a posteriori, 2026-09-28)."""
    serveur, base_url, etat = _demarrer("formulaire")
    try:
        v = _rejouer(base_url, {"page mdp puis vraie invalidation": [
            'Soit j\'accède à la page d\'accueil de l\'application',
            'Quand j\'ouvre la page "/compte/mot-de-passe"',
            'Et j\'ouvre la page "/invalider-session"',
            'Et j\'ouvre la page "/"',
            'Alors la page affiche le texte "Bienvenue"']})["page mdp puis vraie invalidation"]

        assert (v.execution_status, v.functional_status) == (st.EXEC_SUCCESS, st.FUNC_CONFORME), v.error[:400]
        assert _compteur(base_url) == 2, "before_all (1) + UNE reconnexion réparatrice pour la VRAIE invalidation (2)"
    finally:
        serveur.shutdown()


# ── Invalidée puis reconnectée, une fois ────────────────────────────────────────────────────────────────────────────────────


def test_une_session_invalidee_en_cours_de_run_est_reconnectee_une_fois():
    serveur, base_url, etat = _demarrer("formulaire")
    try:
        v = _rejouer(base_url, {"invalidation puis reconnexion": [
            'Quand j\'ouvre la page "/invalider-session"',
            'Et j\'ouvre la page "/"',
            'Alors la page affiche le texte "Bienvenue"']})["invalidation puis reconnexion"]

        assert (v.execution_status, v.functional_status) == (st.EXEC_SUCCESS, st.FUNC_CONFORME), v.error[:400]
        assert _compteur(base_url) == 2, "before_all (1) + UNE reconnexion réparatrice (2)"
    finally:
        serveur.shutdown()


def test_falsifiable_une_seconde_invalidation_dans_le_meme_scenario_bloque_sans_retenter():
    serveur, base_url, etat = _demarrer("formulaire")
    try:
        v = _rejouer(base_url, {"deux invalidations": [
            'Quand j\'ouvre la page "/invalider-session"',
            'Et j\'ouvre la page "/"',
            'Et j\'ouvre la page "/invalider-session"',
            'Et j\'ouvre la page "/"']})["deux invalidations"]

        assert v.execution_status == st.EXEC_BLOCKED, (v.execution_status, v.functional_status, v.error[:300])
        assert v.functional_status != st.FUNC_CONFORME
    finally:
        serveur.shutdown()


# ── TOTP : un vrai secret, un vrai code ─────────────────────────────────────────────────────────────────────────────────────


def test_totp_se_connecte_avec_un_vrai_code_a_usage_unique():
    secret = pyotp.random_base32()
    serveur, base_url, etat = _demarrer("totp", totp_secret=secret)
    try:
        v = _rejouer(base_url, {"connexion totp": [
            'Soit j\'accède à la page d\'accueil de l\'application',
            'Alors la page affiche le texte "Bienvenue"']}, auth_strategie="totp", totp_secret=secret)["connexion totp"]

        assert (v.execution_status, v.functional_status) == (st.EXEC_SUCCESS, st.FUNC_CONFORME), v.error[:400]
        assert _compteur(base_url) == 1
    finally:
        serveur.shutdown()


def test_falsifiable_totp_avec_un_secret_errone_bloque_tout_le_run():
    serveur, base_url, etat = _demarrer("totp", totp_secret=pyotp.random_base32())
    try:
        v = _rejouer(base_url, {"secret erroné": [
            'Soit j\'accède à la page d\'accueil de l\'application',
            'Alors la page affiche le texte "Bienvenue"']}, auth_strategie="totp",
            totp_secret=pyotp.random_base32())["secret erroné"]  # un AUTRE secret que celui du serveur

        assert v.execution_status == st.EXEC_BLOCKED, (v.execution_status, v.functional_status, v.error[:300])
        assert _compteur(base_url) == 0, "aucune connexion ne doit avoir abouti"
    finally:
        serveur.shutdown()


# ── session_injectee : une session déjà ouverte, jamais un formulaire ───────────────────────────────────────────────────────


def _storage_state_pour(sid: str, port: int) -> str:
    return json.dumps({"cookies": [{"name": "sid", "value": sid, "domain": "127.0.0.1", "path": "/",
                                    "expires": -1, "httpOnly": False, "secure": False, "sameSite": "Lax"}],
                       "origins": []})


def test_session_injectee_authentifie_sans_aucun_formulaire():
    serveur, base_url, etat = _demarrer("formulaire")
    port = serveur.server_address[1]
    sid = "sid-fournie-par-le-porteur"
    etat["sessions"][sid] = "ok"   # posée directement (comme un jeton exporté d'un VRAI navigateur déjà connecté)
    try:
        v = _rejouer(base_url, {"session déjà ouverte": [
            'Soit j\'accède à la page d\'accueil de l\'application',
            'Alors la page affiche le texte "Bienvenue"']}, auth_strategie="session_injectee",
            injected_session=_storage_state_pour(sid, port))["session déjà ouverte"]

        assert (v.execution_status, v.functional_status) == (st.EXEC_SUCCESS, st.FUNC_CONFORME), v.error[:400]
        assert _compteur(base_url) == 0, "AUCUNE connexion par formulaire : la session fournie suffit"
    finally:
        serveur.shutdown()


def test_falsifiable_une_session_injectee_expiree_bloque_tout_le_run_des_avant_all():
    serveur, base_url, etat = _demarrer("formulaire")
    port = serveur.server_address[1]
    try:
        v = _rejouer(base_url, {"jeton expiré": [
            'Soit j\'accède à la page d\'accueil de l\'application',
            'Alors la page affiche le texte "Bienvenue"']}, auth_strategie="session_injectee",
            injected_session=_storage_state_pour("sid-jamais-authentifiee", port))["jeton expiré"]

        assert v.execution_status == st.EXEC_BLOCKED, (v.execution_status, v.functional_status, v.error[:300])
        assert v.functional_status != st.FUNC_CONFORME
    finally:
        serveur.shutdown()
