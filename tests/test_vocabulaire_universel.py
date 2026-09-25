"""Lot 07d (C4) — le vocabulaire universel, prouvé de bout en bout : Behave + Chromium RÉELS contre une application locale.

Chaque step est exercé par de VRAIS scénarios rejoués dans le sous-processus complet (`BehaveRunner`, bibliothèque de steps réelle, connecteur
`web`) contre la fixture « torture » servie par un petit serveur HTTP local — aucun réseau, rien de propre à une application tierce.
Deux familles, et la seconde est la plus importante (falsifiabilité, CLAUDE.md §4) :

- des scénarios qui DOIVENT être `conforme` (la vérification réussit sur une page qui la satisfait) ;
- des scénarios qui DOIVENT ne pas l'être : `non_conforme` quand l'application se comporte mal, `technical_error` quand le test est mal posé
  (ambiguïté, page vide, fichier jamais téléchargé…) — **jamais un vert**.

Marqueur `conformance` (navigateur réel) : exécuté par le job « browser-evidence ».
"""

from __future__ import annotations

import json
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from testpilot.execution.behave_runner import BehaveRunner
from testpilot.execution.executor import Executor
from testpilot.verdict import status as st

pytestmark = pytest.mark.conformance

RACINE = Path(__file__).resolve().parent.parent
_PAGES = RACINE / "tests" / "fixtures" / "torture_app"


def _pdf(texte: str) -> bytes:
    """Un PDF minimal d'une page contenant `texte` (lisible par pdfplumber)."""
    contenu = f"BT /F1 18 Tf 72 720 Td ({texte}) Tj ET".encode("latin-1")
    objets = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
              b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
              b"/Resources << /Font << /F1 5 0 R >> >> >>",
              b"<< /Length " + str(len(contenu)).encode() + b" >>\nstream\n" + contenu + b"\nendstream",
              b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    sortie, positions = b"%PDF-1.4\n", []
    for i, objet in enumerate(objets, 1):
        positions.append(len(sortie))
        sortie += f"{i} 0 obj\n".encode() + objet + b"\nendobj\n"
    debut_xref = len(sortie)
    sortie += f"xref\n0 {len(objets) + 1}\n0000000000 65535 f \n".encode()
    for pos in positions:
        sortie += f"{pos:010d} 00000 n \n".encode()
    return sortie + f"trailer\n<< /Size {len(objets) + 1} /Root 1 0 R >>\nstartxref\n{debut_xref}\n%%EOF".encode()


class _Application(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence
        pass

    def _envoyer(self, code, corps: bytes, type_="text/plain; charset=utf-8", entetes=None):
        self.send_response(code)
        self.send_header("Content-Type", type_)
        self.send_header("Content-Length", str(len(corps)))
        for cle, valeur in (entetes or {}).items():
            self.send_header(cle, valeur)
        self.end_headers()
        self.wfile.write(corps)

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if self.path in ("/api/creer", "/api/contact"):
            return self._envoyer(201, b'{"ok": true}', "application/json")
        self._envoyer(404, b"absent")

    def do_GET(self):
        chemin = self.path.split("?")[0]
        if chemin == "/api/ping":
            return self._envoyer(200, b'{"ok": true}', "application/json")
        if chemin == "/api/refuse":
            return self._envoyer(403, json.dumps({"erreur": "interdit"}).encode(), "application/json")
        if chemin == "/export.csv":
            return self._envoyer(200, "id;client\n1;Acme\n2;Globex\n".encode(), "text/csv; charset=utf-8",
                                 {"Content-Disposition": 'attachment; filename="export_2026.csv"'})
        if chemin == "/rapport.pdf":
            return self._envoyer(200, _pdf("Rapport mensuel Acme"), "application/pdf",
                                 {"Content-Disposition": 'attachment; filename="rapport.pdf"'})
        page = _PAGES / ("accueil.html" if chemin == "/" else chemin.lstrip("/"))
        if page.is_file() and page.suffix == ".html":
            return self._envoyer(200, page.read_bytes(), "text/html; charset=utf-8")
        self._envoyer(404, b"absent")


@pytest.fixture(scope="module")
def application():
    serveur = ThreadingHTTPServer(("127.0.0.1", 0), _Application)
    fil = threading.Thread(target=serveur.serve_forever, daemon=True)
    fil.start()
    yield f"http://127.0.0.1:{serveur.server_address[1]}"
    serveur.shutdown()


def _rejouer(application: str, scenarios: dict[str, list[str]]) -> dict:
    """Rejoue UNE feature dont chaque scénario ouvre l'accueil puis enchaîne ses steps ; rend `{titre: ScenarioVerdict}`."""
    lignes = ["Fonctionnalité: Vocabulaire universel", ""]
    for titre, etapes in scenarios.items():
        lignes += [f"  Scénario: {titre}", "    Soit j'accède à la page d'accueil de l'application", *[f"    {e}" for e in etapes], ""]
    dossier = Path(tempfile.mkdtemp(prefix="l07d_"))
    (dossier / "vu.feature").write_text("\n".join(lignes), encoding="utf-8")
    runner = BehaveRunner(connection={"WEB_URL": application, "WEB_USER": "", "WEB_PASSWORD": ""},
                          connector_type="web", generated_dir=dossier)
    outcome = Executor(runner, max_retries=0).execute("vu")
    assert outcome.dry_run_passed, f"les steps ne se résolvent pas (non définis / ambigus) : {outcome.error}"
    verdict = st.derive_verdict(outcome, connector_type="web")
    return {v.name: v for v in verdict.scenarios}


VERTS = {
    "texte, URL et absence de texte": [
        'Quand j\'ouvre la page "/tableau.html"',
        'Alors la page affiche le texte "Suivi des commandes"',
        'Et la page n\'affiche pas le texte "Erreur critique"',
        'Et l\'URL courante contient "/tableau.html"'],
    "un texte rendu avec retard est attendu": [
        'Quand j\'ouvre la page "/asynchrone.html"',
        'Alors la page affiche le texte "Données chargées"',
        'Et la page n\'affiche pas le texte "Texte caché"'],
    "tableaux : ligne et comptage": [
        'Quand j\'ouvre la page "/tableau.html"',
        'Alors le tableau "Commandes" contient une ligne avec "Acme" et "Payée"',
        'Et le tableau "Commandes" compte 3 lignes',
        'Et le tableau "Clients" compte 2 lignes'],
    "clic dans une ligne et boîte native acceptée": [
        'Quand j\'ouvre la page "/tableau.html"',
        'Et j\'accepte la boîte de dialogue',
        'Et je clique sur "Supprimer" dans la ligne contenant "CMD-1"',
        'Alors la page affiche le texte "CMD-1 supprimée"'],
    "boîte native refusée": [
        'Quand j\'ouvre la page "/tableau.html"',
        'Et je refuse la boîte de dialogue',
        'Et je clique sur "Supprimer" dans la ligne contenant "CMD-2"',
        'Alors la page n\'affiche pas le texte "CMD-2 supprimée"'],
    "modale ARIA confirmée": [
        'Quand j\'ouvre la page "/tableau.html"',
        'Et je clique sur le bouton "Supprimer avec confirmation"',
        'Et j\'accepte la boîte de dialogue',
        'Alors la page affiche le texte "Supprimé après confirmation"'],
    "téléchargement CSV": [
        'Quand j\'ouvre la page "/telechargements.html"',
        'Et je télécharge le fichier via "Exporter en CSV"',
        'Alors le fichier téléchargé se nomme "export_*.csv"',
        'Et le fichier téléchargé contient "Acme"'],
    "téléchargement PDF": [
        'Quand j\'ouvre la page "/telechargements.html"',
        'Et je télécharge le fichier via "Rapport PDF"',
        'Alors le fichier téléchargé contient "Rapport mensuel"'],
    "saisie et clic dans un cadre": [
        'Quand j\'ouvre la page "/cadre.html"',
        'Et dans le cadre "formulaire", je renseigne le champ "Nom du contact" avec la valeur "Awa"',
        'Et dans le cadre "formulaire", je clique sur le bouton "Envoyer"',
        'Alors la requête "POST /api/contact" répond 201'],
    "nouvel onglet": [
        'Quand j\'ouvre la page "/onglet.html"',
        'Et je clique sur le bouton "Ouvrir le guide"',
        'Alors un nouvel onglet s\'ouvre sur "/destination.html"',
        'Et la page affiche le texte "Guide utilisateur"'],
    "réponses réseau": [
        'Quand j\'ouvre la page "/reseau.html"',
        'Et je clique sur le bouton "Ping"',
        'Alors la requête "GET /api/ping" répond 200',
        'Quand je clique sur le bouton "Refuser"',
        'Alors la requête "GET /api/refuse" répond 403'],
}

# titre → (étapes, ce que le verdict DOIT être). `non_conforme` : l'application se comporte mal ; `technique` : le test est mal posé.
ROUGES = {
    "texte absent": (['Quand j\'ouvre la page "/tableau.html"', 'Alors la page affiche le texte "Texte inexistant"'], "non_conforme"),
    "texte présent alors qu'il ne devrait pas": (
        ['Quand j\'ouvre la page "/tableau.html"', 'Alors la page n\'affiche pas le texte "Suivi des commandes"'], "non_conforme"),
    "mauvais fragment d'URL": (['Quand j\'ouvre la page "/tableau.html"', 'Alors l\'URL courante contient "/autre"'], "non_conforme"),
    "ligne inexistante": (
        ['Quand j\'ouvre la page "/tableau.html"', 'Alors le tableau "Commandes" contient une ligne avec "Globex" et "Payée"'],
        "non_conforme"),
    "mauvais nombre de lignes": (
        ['Quand j\'ouvre la page "/tableau.html"', 'Alors le tableau "Commandes" compte 4 lignes'], "non_conforme"),
    "tableau inconnu": (
        ['Quand j\'ouvre la page "/tableau.html"', 'Alors le tableau "Fournisseurs" compte 1 ligne'], "technique"),
    "ligne ambiguë": (
        ['Quand j\'ouvre la page "/tableau.html"', 'Et je clique sur "Voir" dans la ligne contenant "Acme"',
         'Alors la page affiche le texte "consultée"'], "technique"),
    "boîte native acceptée alors qu'on la refuse": (
        ['Quand j\'ouvre la page "/tableau.html"', 'Et j\'accepte la boîte de dialogue',
         'Et je clique sur "Supprimer" dans la ligne contenant "CMD-1"',
         'Alors la page n\'affiche pas le texte "CMD-1 supprimée"'], "non_conforme"),
    "absence constatée sur une page vide": (
        ['Quand j\'ouvre la page "/vide.html"', 'Alors la page n\'affiche pas le texte "Erreur"'], "technique"),
    "mauvais nom de fichier": (
        ['Quand j\'ouvre la page "/telechargements.html"', 'Et je télécharge le fichier via "Exporter en CSV"',
         'Alors le fichier téléchargé se nomme "rapport_*.csv"'], "non_conforme"),
    "contenu de fichier absent": (
        ['Quand j\'ouvre la page "/telechargements.html"', 'Et je télécharge le fichier via "Exporter en CSV"',
         'Alors le fichier téléchargé contient "Initech"'], "non_conforme"),
    "fichier jamais téléchargé": (
        ['Quand j\'ouvre la page "/telechargements.html"', 'Alors le fichier téléchargé contient "Acme"'], "technique"),
    "aucun nouvel onglet": (
        ['Quand j\'ouvre la page "/onglet.html"', 'Alors un nouvel onglet s\'ouvre sur "/destination.html"'], "non_conforme"),
    "mauvais code de réponse": (
        ['Quand j\'ouvre la page "/reseau.html"', 'Et je clique sur le bouton "Refuser"',
         'Alors la requête "GET /api/refuse" répond 200'], "non_conforme"),
    "requête jamais émise": (
        ['Quand j\'ouvre la page "/reseau.html"', 'Alors la requête "GET /api/ping" répond 200'], "non_conforme"),
    "cadre inconnu": (
        ['Quand j\'ouvre la page "/cadre.html"',
         'Et dans le cadre "inexistant", je clique sur le bouton "Envoyer"'], "technique"),
    "page d'une autre origine": (['Quand j\'ouvre la page "https://autre.example/x"'], "technique"),
}


def test_les_scenarios_qui_doivent_etre_conformes_le_sont(application):
    verdicts = _rejouer(application, VERTS)

    assert set(verdicts) == set(VERTS)
    for titre, v in verdicts.items():
        assert (v.execution_status, v.functional_status) == (st.EXEC_SUCCESS, st.FUNC_CONFORME), (
            f"« {titre} » : {v.execution_status}/{v.functional_status} — {v.error[:300]}")


def test_falsifiable_chaque_verification_echoue_quand_l_application_se_comporte_mal_ou_que_le_test_est_mal_pose(application):
    """LA GARDE : aucun de ces scénarios ne peut être `conforme`. `non_conforme` = l'application est fautive ; `technique` = le test est mal
    posé (ambiguïté, page vide, fichier jamais téléchargé, cible inconnue) — une erreur, jamais un vert."""
    verdicts = _rejouer(application, {titre: etapes for titre, (etapes, _) in ROUGES.items()})

    fautes = []
    for titre, (_, attendu) in ROUGES.items():
        v = verdicts[titre]
        if v.functional_status == st.FUNC_CONFORME:
            fautes.append(f"« {titre} » est `conforme` — FAUX VERT")
        elif attendu == "non_conforme" and v.functional_status != st.FUNC_NON_CONFORME:
            fautes.append(f"« {titre} » : attendu non_conforme, obtenu {v.execution_status}/{v.functional_status} ({v.error[:200]})")
        elif attendu == "technique" and v.execution_status != st.EXEC_TECHNICAL_ERROR:
            fautes.append(f"« {titre} » : attendu technical_error, obtenu {v.execution_status}/{v.functional_status} ({v.error[:200]})")
    assert not fautes, "\n".join(fautes)


def test_aucun_step_generique_ne_reference_context_odoo():
    """Critère du lot : la bibliothèque `generic/` reste indépendante d'Odoo (le vocabulaire universel vaut pour toute application web).
    Lu par AST : un COMMENTAIRE ou une docstring qui cite `context.odoo` pour dire qu'il n'y en a pas n'est pas une référence."""
    import ast

    fautes = []
    for fichier in (RACINE / "behave_runtime" / "steps_library" / "generic").glob("*.py"):
        for noeud in ast.walk(ast.parse(fichier.read_text(encoding="utf-8"))):
            if (isinstance(noeud, ast.Attribute) and noeud.attr == "odoo" and isinstance(noeud.value, ast.Name)
                    and noeud.value.id == "context"):
                fautes.append(f"{fichier.name}:{noeud.lineno} context.odoo")
            if isinstance(noeud, ast.Constant) and isinstance(noeud.value, str) and noeud.value.startswith("ODOO_")                     and len(noeud.value) < 40:
                fautes.append(f"{fichier.name}:{noeud.lineno} {noeud.value}")

    assert not fautes, fautes
