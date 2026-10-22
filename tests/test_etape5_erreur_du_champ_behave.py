"""Étape 5 du plan unique (A101) — « une erreur de validation est affichée pour le champ X », de bout en bout : vrai Behave, vrai
Chromium (marqueur `conformance`). Prouve le branchement du harnais (`environment.before_step` : relevé au début de chaque
action, bloc clos par un « Alors ») sur les cas de la seconde passe de revue du 2026-10-22.
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


def _fiche(action: str, erreur: str = "") -> str:
    return ("<html><body><h1>Nouveau client</h1>"
            f"<form method='post' action='{action}'><div class='champ'><label for='nom'>Nom</label>"
            "<input id='nom' name='nom'><small class='text-danger'>Champ obligatoire</small>"
            f"{erreur}</div><button type='submit'>Enregistrer</button></form></body></html>")


_PAGES = {
    "/accepte.html": _fiche("/accepte.html"),
    "/refuse.html": _fiche("/refuse.html"),
    "/vers-la-liste.html": _fiche("/liste"),
    "/nouveau.html": _fiche("/creer"),
    "/clients/5": _fiche("/clients/5"),
    "/etoile.html": ("<html><body><form method='post' action='/etoile.html'><div class='champ'><label for='x1'>Nom *</label>"
                     "<input id='x1'><small class='text-danger'>Champ obligatoire</small></div>"
                     "<button type='submit'>Enregistrer</button></form></body></html>"),
    "/sortie.html": ("<html><body><form onsubmit='return false'><div class='champ'><label for='nom'>Nom</label>"
                     "<input id='nom' name='nom' onblur=\"if(!this.value){var p=document.createElement('p');"
                     "p.className='invalid-feedback';p.textContent='Le nom est obligatoire';this.parentNode.appendChild(p);}\">"
                     "</div><div class='champ'><label for='ville'>Ville</label><input id='ville' name='ville'></div>"
                     "<button type='submit'>Enregistrer</button></form></body></html>"),
}


class _Application(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _rendre(self, corps: str):
        donnees = corps.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(donnees)))
        self.end_headers()
        self.wfile.write(donnees)

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if self.path == "/refuse.html":   # l'application refuse : le formulaire revient avec son erreur
            return self._rendre(_fiche("/refuse.html", "<p class='invalid-feedback'>Le nom est obligatoire</p>"))
        if self.path == "/liste":         # défaut : le nom vide est accepté, on passe à la liste
            return self._rendre("<html><body><h1>Clients</h1></body></html>")
        if self.path == "/creer":         # défaut : accepté, puis la fiche créée, en modification (303 vers une AUTRE adresse)
            self.send_response(303)
            self.send_header("Location", "/clients/5")
            self.send_header("Content-Length", "0")
            return self.end_headers()
        if self.path == "/etoile.html":
            return self._rendre(_PAGES["/etoile.html"])
        return self._rendre(_fiche(self.path))   # défaut : accepté, le même formulaire est réaffiché (même adresse)

    def do_GET(self):
        self._rendre(_PAGES.get(self.path.split("?")[0], "<html><body>Accueil</body></html>"))


@pytest.fixture(scope="module")
def verdicts():
    serveur = ThreadingHTTPServer(("127.0.0.1", 0), _Application)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    application = f"http://127.0.0.1:{serveur.server_address[1]}"
    alors = 'Alors une erreur de validation est affichée pour le champ "nom"'
    scenarios = {
        "refusé": ['Soit j\'ouvre la page "/refuse.html"', 'Quand je laisse le champ "nom" vide',
                   'Et je clique sur le bouton "Enregistrer"', alors],
        "accepté puis réaffiché": ['Soit j\'ouvre la page "/accepte.html"', 'Quand je laisse le champ "nom" vide',
                                   'Et je clique sur le bouton "Enregistrer"', alors],
        "accepté puis la liste": ['Soit j\'ouvre la page "/vers-la-liste.html"', 'Quand je laisse le champ "nom" vide',
                                  'Et je clique sur le bouton "Enregistrer"', alors],
        "accepté puis la fiche créée": ['Soit j\'ouvre la page "/nouveau.html"', 'Quand je laisse le champ "nom" vide',
                                        'Et je clique sur le bouton "Enregistrer"', alors],
        "libellé Nom étoile, accepté": ['Soit j\'ouvre la page "/etoile.html"', 'Quand je laisse le champ "Nom" vide',
                                       'Et je clique sur le bouton "Enregistrer"',
                                       'Alors une erreur de validation est affichée pour le champ "Nom"'],
        "à la sortie du champ": ['Soit j\'ouvre la page "/sortie.html"', 'Quand je laisse le champ "nom" vide',
                                 'Et je renseigne le champ "ville" avec la valeur "Lyon"',
                                 'Et je clique sur le bouton "Enregistrer"', alors],
    }
    lignes = ["Fonctionnalité: Erreur du champ", ""]
    for nom, steps in scenarios.items():
        lignes += [f"  Scénario: {nom}"] + [f"    {s}" for s in steps] + [""]
    dossier = Path(tempfile.mkdtemp(prefix="erreur_du_champ_"))
    (dossier / "ec.feature").write_text("\n".join(lignes), encoding="utf-8")
    runner = BehaveRunner(connection={"WEB_URL": application, "WEB_USER": "", "WEB_PASSWORD": ""},
                          connector_type="web", generated_dir=dossier)
    outcome = Executor(runner, max_retries=0).execute("ec")
    serveur.shutdown()
    assert outcome.dry_run_passed, outcome.error
    return {v.name: (v.execution_status, v.functional_status)
            for v in st.derive_verdict(outcome, connector_type="web").scenarios}


def test_une_erreur_apparue_au_renvoi_du_formulaire_est_passee(verdicts):
    assert verdicts["refusé"][1] == st.FUNC_CONFORME


def test_falsifiable_formulaire_accepte_puis_reaffiche_jamais_conforme(verdicts):
    """La mention rouge fixe était là avant les actions : elle ne prouve rien (avant la revue : « conforme »)."""
    assert verdicts["accepté puis réaffiché"][1] == st.FUNC_INDETERMINE


def test_falsifiable_formulaire_accepte_puis_la_liste_est_un_defaut_pas_une_panne(verdicts):
    assert verdicts["accepté puis la liste"][1] == st.FUNC_NON_CONFORME


def test_une_validation_a_la_sortie_du_champ_est_vue_malgre_les_actions_suivantes(verdicts):
    assert verdicts["à la sortie du champ"][1] == st.FUNC_CONFORME


def test_falsifiable_formulaire_accepte_puis_la_fiche_creee_ailleurs_jamais_conforme(verdicts):
    """Revue, 3e passe : 303 vers une autre adresse, même formulaire et même mention fixe — avant : « conforme »."""
    assert verdicts["accepté puis la fiche créée"][1] == st.FUNC_INDETERMINE


def test_falsifiable_champ_cite_par_une_partie_de_son_libelle_accepte_jamais_conforme(verdicts):
    """Revue, 4e passe : « Nom » pour le libellé « Nom * », sans `name` — avant : « conforme »."""
    assert verdicts["libellé Nom étoile, accepté"][1] == st.FUNC_INDETERMINE
