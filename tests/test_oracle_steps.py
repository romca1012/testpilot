"""Lot 07e (C5, D7) — les steps d'oracle côté harnais Behave (`_base_helpers.py`) : résolution du
prérequis (`blocked` si absent/mal configuré), exécution de la requête NOMMÉE, et marquage du
constat `source: "oracle"` (lu par `verdict/status.py` pour `ground_truth`).
"""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

_STEPS_LIB = Path(__file__).resolve().parent.parent / "behave_runtime" / "steps_library"
sys.path.insert(0, str(_STEPS_LIB))

import _base_helpers as H  # noqa: E402


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/tickets":
            corps = json.dumps([{"id": 1, "statut": "ouvert"}, {"id": 2, "statut": "ouvert"}]).encode()
        elif self.path == "/ticket":
            corps = json.dumps({"statut": "ferme"}).encode()
        elif self.path == "/etat":
            corps = json.dumps({"commandes": [], "panier": {"lignes": [{"nom": "a"}, {"nom": "b"}]}}).encode()
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(corps)


@pytest.fixture
def serveur():
    httpd = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


@pytest.fixture
def sidecar(tmp_path, monkeypatch):
    chemin = tmp_path / "constats.jsonl"
    monkeypatch.setenv(H.CONSTATS_FILE_ENV, str(chemin))
    H.definir_etat_constat(scenario="[Nominal] test", step_type="then")

    def lignes():
        if not chemin.exists():
            return []
        return [json.loads(l) for l in chemin.read_text(encoding="utf-8").splitlines()]

    return lignes


def _contexte(serveur, requetes):
    oracle, erreur = H.construire_oracle(
        {H._oracle_config.ENV_ORACLE: json.dumps({"base_url": serveur, "auth": {}, "queries": requetes})})
    return SimpleNamespace(oracle=oracle, oracle_erreur=erreur)


# ── construire_oracle ────────────────────────────────────────────────────────────────────────────


def test_construire_oracle_absent_rend_none_sans_erreur():
    oracle, erreur = H.construire_oracle({})
    assert oracle is None and erreur == ""


def test_falsifiable_une_configuration_illisible_est_signalee():
    oracle, erreur = H.construire_oracle({H._oracle_config.ENV_ORACLE: "pas du json"})
    assert oracle is None and erreur != ""


# ── oracle_renvoie_n_resultats ──────────────────────────────────────────────────────────────────


def test_oracle_renvoie_n_resultats_reussit_et_consigne_un_constat_oracle(serveur, sidecar):
    context = _contexte(serveur, [{"name": "tickets", "method": "GET", "path": "/tickets"}])

    H.oracle_renvoie_n_resultats(context, "tickets", 2)

    lignes = sidecar()
    assert lignes == [{"scenario": "[Nominal] test", "step_type": "then", "ok": True, "source": "oracle"}]


def test_falsifiable_oracle_renvoie_n_resultats_echoue_sur_un_ecart(serveur, sidecar):
    context = _contexte(serveur, [{"name": "tickets", "method": "GET", "path": "/tickets"}])

    with pytest.raises(AssertionError):
        H.oracle_renvoie_n_resultats(context, "tickets", 99)

    assert sidecar()[0]["ok"] is False and sidecar()[0]["source"] == "oracle"


def test_oracle_absent_du_projet_est_un_prerequis_manquant_pas_un_defaut_applicatif():
    context = SimpleNamespace(oracle=None, oracle_erreur="")
    with pytest.raises(H.PreconditionNonRemplieError):
        H.oracle_renvoie_n_resultats(context, "tickets", 1)


def test_falsifiable_une_requete_non_declaree_est_un_prerequis_manquant(serveur):
    context = _contexte(serveur, [{"name": "tickets", "method": "GET", "path": "/tickets"}])
    with pytest.raises(H.PreconditionNonRemplieError, match="autre_chose"):
        H.oracle_renvoie_n_resultats(context, "autre_chose", 1)


def test_falsifiable_une_panne_reseau_en_cours_de_run_est_un_prerequis_manquant_pas_une_erreur_technique():
    """`verifier_connexion` prouve l'oracle joignable AVANT le run — une panne réseau EN COURS de
    run doit rester `blocked` (environnement), jamais `technical_error` (script cassé) : même
    confusion que F5 (lot 02), fermée ici pour l'oracle."""
    context = _contexte("http://127.0.0.1:1", [{"name": "tickets", "method": "GET", "path": "/t"}])
    with pytest.raises(H.PreconditionNonRemplieError, match="injoignable"):
        H.oracle_renvoie_n_resultats(context, "tickets", 1)


def test_falsifiable_une_reponse_http_d_erreur_n_est_pas_convertie_en_prerequis_manquant(serveur):
    """Une réponse HTTP d'erreur (4xx/5xx) est un signal potentiellement significatif DE L'ORACLE
    lui-même — jamais avalée comme un prérequis manquant, contrairement à une vraie panne réseau."""
    import urllib.error

    context = _contexte(serveur, [{"name": "absente", "method": "GET", "path": "/route-inexistante"}])
    with pytest.raises(urllib.error.HTTPError):
        H.oracle_renvoie_n_resultats(context, "absente", 1)


# ── oracle_champ_vaut ────────────────────────────────────────────────────────────────────────────


def test_oracle_champ_vaut_reussit_et_consigne_un_constat_oracle(serveur, sidecar):
    context = _contexte(serveur, [{"name": "ticket", "method": "GET", "path": "/ticket"}])

    H.oracle_champ_vaut(context, "statut", "ticket", "ferme")

    assert sidecar() == [{"scenario": "[Nominal] test", "step_type": "then", "ok": True, "source": "oracle"}]


def test_falsifiable_oracle_champ_vaut_echoue_sur_une_valeur_differente(serveur, sidecar):
    context = _contexte(serveur, [{"name": "ticket", "method": "GET", "path": "/ticket"}])

    with pytest.raises(AssertionError):
        H.oracle_champ_vaut(context, "statut", "ticket", "ouvert")

    assert sidecar()[0]["ok"] is False and sidecar()[0]["source"] == "oracle"


def test_falsifiable_oracle_champ_vaut_echoue_sur_un_chemin_absent(serveur, sidecar):
    context = _contexte(serveur, [{"name": "ticket", "method": "GET", "path": "/ticket"}])

    with pytest.raises(AssertionError, match="introuvable"):
        H.oracle_champ_vaut(context, "champ_absent", "ticket", "x")

    assert sidecar()[0]["ok"] is False and sidecar()[0]["source"] == "oracle"


# ── oracle_champ_compte (banc d'agents, 2026-10-07) ────────────────────────────────────────────────


def _etat(serveur):
    return _contexte(serveur, [{"name": "etat", "method": "GET", "path": "/etat"}])


def test_oracle_champ_compte_reussit_sur_une_liste_vide_et_sur_une_liste_pleine(serveur, sidecar):
    context = _etat(serveur)

    H.oracle_champ_compte(context, "commandes", "etat", 0)
    H.oracle_champ_compte(context, "panier.lignes", "etat", 2)

    assert [(l["ok"], l["source"]) for l in sidecar()] == [(True, "oracle"), (True, "oracle")]


def test_falsifiable_oracle_champ_compte_echoue_sur_un_ecart(serveur, sidecar):
    with pytest.raises(AssertionError, match=r"compte 2 élément\(s\), 3 attendu"):
        H.oracle_champ_compte(_etat(serveur), "panier.lignes", "etat", 3)

    assert sidecar()[0]["ok"] is False


def test_falsifiable_oracle_champ_compte_ne_devine_pas_zero_sur_un_chemin_absent_ou_une_non_liste(serveur):
    """Un champ absent ou qui n'est pas une liste n'est JAMAIS « 0 élément » : sinon « aucune commande » réussirait à tort.

    Lot VH-08 (2026-10-16), changement DÉLIBÉRÉ de l'attendu pour la NON-LISTE seulement, comme VH-04 pour « renvoie N
    résultats » : ce test exigeait un constat échoué (`AssertionError` → `non_conforme`, une accusation de l'application),
    le seul faux rouge mesuré en base-6. Une non-liste est un test mal posé (`ReponseOracleNonComptableError`) — toujours
    jamais un vert. Le chemin absent reste un constat échoué."""
    with pytest.raises(AssertionError, match="introuvable"):
        H.oracle_champ_compte(_etat(serveur), "commande", "etat", 0)
    with pytest.raises(H.ReponseOracleNonComptableError, match="n'est pas une liste"):
        H.oracle_champ_compte(_etat(serveur), "panier", "etat", 0)


def test_falsifiable_oracle_champ_compte_sur_null_reste_un_constat_echoue(monkeypatch):
    """Revue du 2026-10-16 : `null` à la place d'une liste peut être une application cassée — constat échoué, comme avant."""
    monkeypatch.setattr(H, "_executer_oracle", lambda context, requete: {"commandes": None})
    with pytest.raises(AssertionError, match="vide"):
        H.oracle_champ_compte(SimpleNamespace(), "commandes", "etat", 0)


def test_renvoie_n_resultats_sur_un_objet_oriente_vers_le_comptage_d_un_champ(serveur, sidecar):
    """Mesuré : « renvoie 0 résultat » sur un objet (compté pour 1) donnait un faux rouge ; le message dit quoi faire.

    Lot VH-04 (2026-10-09), changement DÉLIBÉRÉ de l'attendu : ce test exigeait un constat échoué (`AssertionError` →
    `non_conforme`, une accusation de l'application) — exactement le faux rouge mesuré (base-2 : 9 essais sur 30 ; base-4 : 1).
    Un objet ne se compte pas : le test est mal posé (`ReponseOracleNonComptableError` → erreur technique), et aucun constat
    n'est consigné contre l'application."""
    with pytest.raises(H.ReponseOracleNonComptableError, match="objet.*compte <n> élément"):
        H.oracle_renvoie_n_resultats(_etat(serveur), "etat", 0)
    assert sidecar() == []
