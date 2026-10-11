"""Lot VH-07 (T10, décision D26) — « exécuter puis écrire » : l'agent joue des ACTIONS sur un bac à sable avant d'écrire.

Mesuré (banc base-4 et base-5) : la première cause d'erreur technique après génération est une page qui change après une action.
L'outil `essayer_les_actions` joue les actions dans le vrai harnais et rend la page d'arrivée. Ses quatre conditions (D26) sont
prouvées ici : (1) bac à sable DÉCLARÉ par le projet, (2) remise à zéro PROUVÉE avant et après, (3) aucun contournement du
harnais, (4) seules des actions sont jouées, aucune valeur de la page ne revient à l'agent, et rien de ce qu'il n'a vu qu'à
l'essai ne devient un attendu. Les cinq défauts relevés à la relecture du 2026-10-11 ont chacun leur test de falsifiabilité.
"""

from __future__ import annotations

import contextlib
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

from testpilot import config
from testpilot.execution.behave_result import SANS_REPLI_ENV, BehaveResult
from testpilot.generation.litteraux_observes import Annuaire
from testpilot.generation.tools import OUTILS_OPTIONNELS, TOOLS_DEFINITIONS, ToolContext, dispatch, outils_optionnels
from testpilot.generation.tools import essai as e
from testpilot.generation.tools import write as w
from testpilot.generation.tools.api_definitions import tools_for_api
from testpilot.guardrails import bac_a_sable

RACINE = Path(__file__).resolve().parent.parent
ACTIONS = ['Quand j\'ouvre la page "/produits"', 'Et je clique sur le bouton "Ajouter"']
APP = "http://app:80"
PROJET = {"connector_type": "web", "base_url": "http://app", "calibration_writes_enabled": 1,
          "bac_a_sable_reset": "http://app/reset"}


@pytest.fixture(autouse=True)
def bac_neuf(tmp_path, monkeypatch):
    """Aucun verrou ni marque ne fuit d'un test à l'autre ; les reprises de remise à zéro n'attendent pas."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(e.time, "sleep", lambda _s: None)
    bac_a_sable.reinitialiser_pour_les_tests()
    yield
    bac_a_sable.reinitialiser_pour_les_tests()


# ── Doubles ───────────────────────────────────────────────────────────────────────────────────────────────


class _Runner:
    def __init__(self, journal, variables, *, a_blanc=True, echec=None, etat=None):
        self.journal, self.variables, self._a_blanc, self._echec, self._etat = journal, variables, a_blanc, echec, etat

    def dry_run(self, module):
        self.journal.append("essai à blanc")
        return BehaveResult(success=self._a_blanc, returncode=0 if self._a_blanc else 1, dry_run=True,
                            undefined_steps=[] if self._a_blanc else ["je fais n'importe quoi"])

    def real_run(self, module):
        self.journal.append("run réel")
        if self._etat is not None:
            Path(self.variables[e.ESSAI_ETAT_FILE_ENV]).write_text(json.dumps(self._etat), encoding="utf-8")
        echecs = [self._echec] if self._echec else []
        return BehaveResult(success=not echecs, returncode=1 if echecs else 0, failures=echecs)


ETAT = {"url": "http://app/panier", "elements": [{"role": "textbox", "nom": "Code promo", "type": "text"},
                                                 {"role": "button", "nom": "Valider la commande", "texte": "Valider"}]}


def _contexte(tmp_path, *, reset=None, annuaire=None, **runner):
    journal: list[str] = []

    def remettre():
        journal.append("remise à zéro")
        if reset:
            reset(journal)

    essai = e.EssaiBacASable(remettre_a_zero=remettre, cle=APP,
                             fabriquer_runner=lambda dossier, variables: _Runner(journal, variables, **runner),
                             apres_essai=lambda: journal.append("session d'observation rouverte"),
                             marquer_non_remis=lambda: journal.append("marque posée"))
    return ToolContext(module_name="m", generated_dir=tmp_path, essai=essai, annuaire=annuaire or Annuaire()), journal


# ── Condition 1 : seulement sur un bac à sable déclaré ────────────────────────────────────────────────────


def test_falsifiable_sans_bac_a_sable_declare_l_outil_n_existe_pas(tmp_path):
    ctx = ToolContext(module_name="m", generated_dir=tmp_path)

    assert outils_optionnels(ctx) == ()
    assert e.NOM_OUTIL not in {t["name"] for t in tools_for_api(avec=outils_optionnels(ctx))}
    sortie = dispatch(e.NOM_OUTIL, {"etapes": ACTIONS}, ctx)
    assert not sortie.ok and "indisponible" in sortie.observation


def test_avec_un_bac_a_sable_l_outil_est_propose_en_fin_de_liste_sans_toucher_au_reste(tmp_path):
    ctx, _ = _contexte(tmp_path, etat=ETAT)

    outils = tools_for_api(avec=outils_optionnels(ctx))

    assert [t["name"] for t in outils][:-1] == [t["name"] for t in tools_for_api()]
    assert outils[-1]["name"] == e.NOM_OUTIL and e.NOM_OUTIL not in {t["name"] for t in TOOLS_DEFINITIONS}
    assert OUTILS_OPTIONNELS[e.NOM_OUTIL] is e.DEFINITION


def test_la_consigne_d_usage_n_est_pas_dans_le_prompt_de_tous_les_projets():
    """§8 : un projet ordinaire garde son prompt (et son empreinte) d'avant le lot ; la consigne voyage avec l'outil."""
    prompt = (RACINE / "src" / "testpilot" / "generation" / "prompts" / "system_prompt.md").read_text(encoding="utf-8")

    assert e.NOM_OUTIL not in prompt and "bac à sable" not in prompt
    assert "AUCUN « Alors »" in e.DEFINITION["description"] and "spécification" in e.DEFINITION["description"]


@pytest.mark.parametrize("projet", [
    {**PROJET, "calibration_writes_enabled": 0},                                    # pas autorisé
    {**PROJET, "bac_a_sable_reset": ""},                                            # pas de remise à zéro
    {**PROJET, "bac_a_sable_reset": "http://autre.example/reset"},                  # autre machine
    {**PROJET, "bac_a_sable_reset": "/reset"},                                      # déclaration incomplète (jamais l'API)
    {**PROJET, "base_url": "https://production.example"},                           # l'adresse du projet a changé depuis
    {**PROJET, "connector_type": "odoo"},
    None,
])
def test_falsifiable_le_mode_n_est_construit_que_si_le_projet_le_declare(projet):
    assert e.construire(projet, SimpleNamespace(connection={})) is None


def test_un_projet_bac_a_sable_construit_le_mode_sans_repli_par_l_ia():
    runner = SimpleNamespace(connection={"WEB_URL": "http://app"}, project_id=7, connector_type="web", profil_instance=None)
    ferme = []

    essai = e.construire(PROJET, runner, SimpleNamespace(disconnect=lambda: ferme.append(1)))

    assert essai is not None and essai.cle == APP
    fabrique = essai.fabriquer_runner(Path("."), {e.ESSAI_ETAT_FILE_ENV: "x"})
    assert fabrique.connection[SANS_REPLI_ENV] == "1" and fabrique.connection["WEB_URL"] == "http://app"
    assert fabrique.essai is True and fabrique.real_timeout == e.DELAI_ESSAI_S and fabrique.project_id == 7
    essai.apres_essai()
    assert ferme == [1]


def test_un_runner_sans_projet_n_ouvre_pas_l_exclusion():
    """Relecture : l'exclusion était prise sur l'identifiant du runner — absent, plus aucune exclusion. Elle tient à l'application."""
    essai = e.construire(PROJET, SimpleNamespace(connection={"WEB_URL": "http://app"}))

    assert essai is not None and essai.cle == APP


@pytest.mark.parametrize("chemin, attendu", [("/reset", "http://app:8000/reset"), ("reset", "http://app:8000/reset"),
                                             ("http://app:8000/x/reset", "http://app:8000/x/reset"),
                                             ("http://APP:8000/reset", "http://APP:8000/reset")])
def test_l_adresse_de_remise_a_zero_reste_dans_l_application(chemin, attendu):
    assert e.adresse_de_remise_a_zero("http://app:8000", chemin) == attendu


@pytest.mark.parametrize("chemin", ["http://autre.example/reset", "https://app:8000/reset", "ftp://app:8000/reset", "",
                                    "http://app:8000@autre.example/reset", "http://app:8001/reset", "http://quelqu-un@app:8000/reset",
                                    "http://app:8000.autre.example/reset"])
def test_falsifiable_une_autre_machine_n_est_jamais_remise_a_zero(chemin):
    with pytest.raises(ValueError):
        e.adresse_de_remise_a_zero("http://app:8000", chemin)


@pytest.mark.parametrize("url, cle", [("http://App.Example/x", "http://app.example:80"), ("https://app.example", "https://app.example:443"),
                                      ("http://app.example:8080/", "http://app.example:8080"), ("", None), ("app.example", None),
                                      ("ftp://app.example", None), (None, None)])
def test_une_application_se_reconnait_a_son_origine(url, cle):
    assert bac_a_sable.cle_d_application(url) == cle


# ── Condition 2 : remise à zéro PROUVÉE, avant et après ───────────────────────────────────────────────────


class _Remise(BaseHTTPRequestHandler):
    vus: list[str] = []

    def log_message(self, *args):
        pass

    def _repondre(self, code, entetes=None):
        self.send_response(code)
        for cle, valeur in (entetes or {}).items():
            self.send_header(cle, valeur)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        type(self).vus.append(f"GET {self.path}")
        self._repondre(200)

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        type(self).vus.append(f"POST {self.path}")
        if self.path == "/reset":
            return self._repondre(204)
        if self.path == "/reset-vers-connexion":
            return self._repondre(302, {"Location": "/login"})
        if self.path == "/reset-vers-ailleurs":
            return self._repondre(303, {"Location": f"http://localhost:{self.server.server_address[1]}/ailleurs"})
        self._repondre(503)


@pytest.fixture
def serveur_de_remise():
    _Remise.vus = []
    serveur = ThreadingHTTPServer(("127.0.0.1", 0), _Remise)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{serveur.server_address[1]}"
    serveur.shutdown()


def test_une_reponse_2xx_directe_prouve_la_remise_a_zero(serveur_de_remise):
    bac_a_sable.remettre_a_zero(f"{serveur_de_remise}/reset")

    assert _Remise.vus == ["POST /reset"]


@pytest.mark.parametrize("chemin", ["/reset-vers-connexion", "/reset-vers-ailleurs", "/reset-en-panne"])
def test_falsifiable_une_redirection_ou_une_erreur_ne_prouve_rien(serveur_de_remise, chemin):
    """Relecture (B4) : `POST /reset` → 302 `/login` → 200 passait pour une remise à zéro — l'essai laissait ses commandes et
    le run réel les prenait pour celles du test. Une redirection n'est plus suivie, ni vers la connexion ni vers un autre hôte."""
    with pytest.raises(Exception):
        bac_a_sable.remettre_a_zero(f"{serveur_de_remise}{chemin}")

    assert _Remise.vus == [f"POST {chemin}"], "aucune requête n'a suivi la redirection"


def test_l_essai_est_encadre_par_deux_remises_a_zero(tmp_path):
    ctx, journal = _contexte(tmp_path, etat=ETAT)

    sortie = e.essayer_les_actions(ctx, ACTIONS)

    assert sortie.ok and "rien de ce qu'il a fait ne subsiste" in sortie.observation
    assert journal == ["essai à blanc", "remise à zéro", "run réel", "remise à zéro", "session d'observation rouverte"]
    assert ctx.essai.journal == [{"etapes": ACTIONS, "reussi": True, "url": "http://app/panier", "remis_a_zero": True}]


def test_falsifiable_sans_remise_a_zero_prouvee_aucun_essai_ni_maintenant_ni_ensuite(tmp_path):
    def panne(_journal):
        raise RuntimeError("503")

    ctx, journal = _contexte(tmp_path, reset=panne, etat=ETAT)

    sortie = e.essayer_les_actions(ctx, ACTIONS)
    suivant = e.essayer_les_actions(ctx, ACTIONS)

    assert not sortie.ok and "REMISE_A_ZERO_IMPOSSIBLE" in sortie.observation
    assert "run réel" not in journal
    assert not suivant.ok and "ESSAIS_EPUISES" in suivant.observation and journal.count("remise à zéro") == 1, \
        "l'agent ne relance pas la remise à zéro à chaque tour"


def test_falsifiable_une_remise_a_zero_finale_en_echec_est_dite_marquee_et_arrete_les_essais(tmp_path):
    """Relecture (B5) : l'outil répondait « rien de ce qu'il a fait ne subsiste » alors que l'état de l'essai restait, et
    rien ne retenait l'exécution réelle suivante."""
    appels = []

    def seule_la_premiere_reussit(_journal):
        appels.append(1)
        if len(appels) > 1:
            raise RuntimeError("503")

    ctx, journal = _contexte(tmp_path, reset=seule_la_premiere_reussit, etat=ETAT)

    sortie = e.essayer_les_actions(ctx, ACTIONS)
    suivant = e.essayer_les_actions(ctx, ACTIONS)

    assert sortie.ok and "n'a PAS pu être remis à zéro" in sortie.observation
    assert "rien de ce qu'il a fait ne subsiste" not in sortie.observation
    assert journal.count("remise à zéro") == 1 + e.REPRISES_REMISE_A_ZERO and "marque posée" in journal
    assert ctx.essai.etat_laisse and ctx.essai.journal[0]["remis_a_zero"] is False
    assert not suivant.ok and "ESSAIS_EPUISES" in suivant.observation and journal.count("run réel") == 1


def test_une_panne_passagere_de_la_remise_a_zero_finale_est_reprise(tmp_path):
    appels = []

    def la_deuxieme_echoue(_journal):
        appels.append(1)
        if len(appels) == 2:
            raise RuntimeError("503")

    ctx, journal = _contexte(tmp_path, reset=la_deuxieme_echoue, etat=ETAT)

    sortie = e.essayer_les_actions(ctx, ACTIONS)

    assert sortie.ok and "rien de ce qu'il a fait ne subsiste" in sortie.observation
    assert "marque posée" not in journal and not ctx.essai.etat_laisse


def test_le_nombre_d_essais_est_borne(tmp_path):
    ctx, journal = _contexte(tmp_path, etat=ETAT)

    resultats = [e.essayer_les_actions(ctx, ACTIONS).ok for _ in range(e.MAX_ESSAIS_PAR_GENERATION + 1)]

    assert resultats == [True] * e.MAX_ESSAIS_PAR_GENERATION + [False]
    assert journal.count("run réel") == e.MAX_ESSAIS_PAR_GENERATION


def test_falsifiable_les_appels_refuses_sont_bornes_eux_aussi(tmp_path):
    ctx, journal = _contexte(tmp_path, etat=ETAT)

    refus = [e.essayer_les_actions(ctx, ['Alors la page affiche le texte "x"']).observation for _ in range(e.MAX_TENTATIVES)]
    apres = e.essayer_les_actions(ctx, ACTIONS)

    assert all("ESSAI_REFUSE" in r for r in refus)
    assert not apres.ok and "ESSAIS_EPUISES" in apres.observation and journal == []


# ── Un essai ne fausse jamais une exécution réelle ────────────────────────────────────────────────────────


def test_falsifiable_pendant_une_execution_reelle_aucun_essai_ni_remise_a_zero(tmp_path, monkeypatch):
    """Le faux vert que cette exclusion ferme : une remise à zéro au milieu d'un run réel effacerait ce qu'un défaut de
    l'application vient de créer — un scénario négatif sortirait `conforme`."""
    monkeypatch.setattr(bac_a_sable, "ATTENTE_ESSAI_S", 0.05)
    ctx, journal = _contexte(tmp_path, etat=ETAT)

    with bac_a_sable.execution_reelle(APP):
        sortie = e.essayer_les_actions(ctx, ACTIONS)

    assert not sortie.ok and "BAC_A_SABLE_OCCUPE" in sortie.observation
    assert "remise à zéro" not in journal and "run réel" not in journal
    assert e.essayer_les_actions(ctx, ACTIONS).ok, "l'exécution finie, l'essai redevient possible"


def test_falsifiable_une_execution_reelle_attend_la_fin_de_l_essai():
    ordre: list[str] = []
    dans_l_essai, relache = threading.Event(), threading.Event()

    def un_essai():
        with bac_a_sable.essai(APP):
            ordre.append("essai : remise à zéro, actions, remise à zéro")
            dans_l_essai.set()
            relache.wait(5)
            ordre.append("essai fini")

    def une_execution():
        # Un AUTRE projet, la même application (casse et port par défaut) : c'est l'application qui est remise à zéro.
        with bac_a_sable.execution_reelle(bac_a_sable.cle_d_application("http://APP/commandes")):
            ordre.append("exécution réelle")

    fil_essai = threading.Thread(target=un_essai)
    fil_essai.start()
    assert dans_l_essai.wait(5)
    fil_execution = threading.Thread(target=une_execution)
    fil_execution.start()
    fil_execution.join(0.3)
    assert fil_execution.is_alive() and "exécution réelle" not in ordre, "l'exécution ne démarre pas pendant l'essai"
    with bac_a_sable.execution_reelle("http://autre:80"):
        ordre.append("autre application : libre")
    relache.set()
    fil_essai.join(5)
    fil_execution.join(5)

    assert ordre == ["essai : remise à zéro, actions, remise à zéro", "autre application : libre", "essai fini",
                     "exécution réelle"]


def test_deux_executions_reelles_de_la_meme_application_ne_se_genent_pas():
    with bac_a_sable.execution_reelle(APP), bac_a_sable.execution_reelle(APP), bac_a_sable.execution_reelle(None):
        pass
    with bac_a_sable.essai(APP, attente_s=0):
        pass
    with pytest.raises(bac_a_sable.BacASableOccupe):
        with bac_a_sable.essai(None):
            pass


def test_falsifiable_une_application_laissee_par_un_essai_est_remise_a_zero_avant_tout_run_ou_le_run_n_est_pas_joue(monkeypatch):
    """Relecture (B5) : sans cela, le run réel suivant trouvait la commande de l'essai et pouvait sortir `conforme` sur une
    application qui n'enregistre rien."""
    appels: list[str] = []

    def en_panne(url, delai_s=0):
        appels.append(url)
        raise RuntimeError("503")

    bac_a_sable.marquer_non_remis(APP, "http://app/reset")
    monkeypatch.setattr(bac_a_sable, "remettre_a_zero", en_panne)

    with pytest.raises(bac_a_sable.BacASableNonRemisAZero):
        with bac_a_sable.execution_reelle(APP):
            pytest.fail("le run ne doit pas être joué")
    assert appels == ["http://app/reset"] and bac_a_sable.non_remis(APP) is not None, "la marque reste tant que ça échoue"
    with bac_a_sable.execution_reelle("http://autre:80"):
        pass  # une autre application n'est pas retenue

    monkeypatch.setattr(bac_a_sable, "remettre_a_zero", lambda url, delai_s=0: appels.append(url))
    with bac_a_sable.execution_reelle(APP):
        pass
    with bac_a_sable.execution_reelle(APP):
        pass
    assert appels == ["http://app/reset"] * 2 and bac_a_sable.non_remis(APP) is None, "remise à zéro une fois, marque retirée"


def test_falsifiable_la_marque_tient_meme_si_le_disque_la_refuse(monkeypatch):
    """Contre-relecture : `marquer_non_remis` journalisait l'échec d'écriture et continuait — rien ne retenait le run suivant."""
    monkeypatch.setattr(bac_a_sable.Path, "write_text", lambda *a, **k: (_ for _ in ()).throw(OSError("disque plein")))

    def en_panne(url, delai_s=0):
        raise RuntimeError("503")

    monkeypatch.setattr(bac_a_sable, "remettre_a_zero", en_panne)
    bac_a_sable.marquer_non_remis(APP, "http://app/reset")

    assert bac_a_sable.non_remis(APP) is not None
    with pytest.raises(bac_a_sable.BacASableNonRemisAZero):
        with bac_a_sable.execution_reelle(APP):
            pytest.fail("le run ne doit pas être joué")


def test_falsifiable_une_marque_impossible_a_retirer_retient_le_run_au_lieu_de_remettre_a_zero_a_chaque_fois(monkeypatch):
    """Contre-relecture, reproduit : `unlink` en échec laissait la marque, et chaque run suivant remettait l'application à
    zéro à son démarrage — y compris pendant qu'un autre run tournait (le faux vert que ce module ferme)."""
    remises: list[str] = []
    monkeypatch.setattr(bac_a_sable, "remettre_a_zero", lambda url, delai_s=0: remises.append(url))
    bac_a_sable.marquer_non_remis(APP, "http://app/reset")
    monkeypatch.setattr(bac_a_sable.Path, "unlink", lambda *a, **k: (_ for _ in ()).throw(OSError("fichier verrouillé")))

    for _ in range(2):
        with pytest.raises(bac_a_sable.BacASableNonRemisAZero):
            with bac_a_sable.execution_reelle(APP):
                pytest.fail("le run ne doit pas être joué")
    assert bac_a_sable.non_remis(APP) is not None


def test_falsifiable_le_retablissement_attend_d_etre_seul(monkeypatch):
    """Rétablir, c'est remettre à zéro : jamais pendant qu'une autre exécution de la même application tourne."""
    ordre: list[str] = []
    monkeypatch.setattr(bac_a_sable, "remettre_a_zero", lambda url, delai_s=0: ordre.append("remise à zéro"))
    en_cours, relache = threading.Event(), threading.Event()

    def premier_run():
        with bac_a_sable.execution_reelle(APP):
            ordre.append("run A")
            en_cours.set()
            relache.wait(5)
            ordre.append("run A fini")

    def second_run():
        with bac_a_sable.execution_reelle(APP):
            ordre.append("run B")

    fil_a = threading.Thread(target=premier_run)
    fil_a.start()
    assert en_cours.wait(5)
    bac_a_sable.marquer_non_remis(APP, "http://app/reset")
    fil_b = threading.Thread(target=second_run)
    fil_b.start()
    fil_b.join(0.3)
    assert fil_b.is_alive() and "remise à zéro" not in ordre, "aucune remise à zéro pendant le run A"
    relache.set()
    fil_a.join(5)
    fil_b.join(5)

    assert ordre == ["run A", "run A fini", "remise à zéro", "run B"]


def test_le_porteur_leve_la_marque_quand_la_remise_a_zero_ne_peut_plus_aboutir(monkeypatch):
    """Contre-relecture : sans sortie, une route de remise à zéro disparue retenait tous les runs indéfiniment."""
    def en_panne(url, delai_s=0):
        raise RuntimeError("404")

    monkeypatch.setattr(bac_a_sable, "remettre_a_zero", en_panne)
    bac_a_sable.marquer_non_remis(APP, "http://app/reset")
    with pytest.raises(bac_a_sable.BacASableNonRemisAZero, match="réglages du projet"):
        with bac_a_sable.execution_reelle(APP):
            pass

    assert bac_a_sable.lever_la_marque(APP) is True and bac_a_sable.lever_la_marque(APP) is False
    with bac_a_sable.execution_reelle(APP):
        pass


def test_une_remise_a_zero_prouvee_par_un_essai_fait_tomber_la_marque(monkeypatch):
    monkeypatch.setattr(bac_a_sable, "remettre_a_zero", lambda url, delai_s=0: None)
    bac_a_sable.marquer_non_remis(APP, "http://app/reset")

    bac_a_sable.remettre_a_zero_et_demarquer(APP, "http://app/reset")

    assert bac_a_sable.non_remis(APP) is None


def test_falsifiable_une_marque_illisible_ou_d_une_autre_application_retient_le_run(monkeypatch):
    monkeypatch.setattr(bac_a_sable, "remettre_a_zero", lambda url, delai_s=0: pytest.fail("aucune requête vers une autre machine"))
    bac_a_sable.marquer_non_remis(APP, "http://autre.example/reset")

    with pytest.raises(bac_a_sable.BacASableNonRemisAZero):
        with bac_a_sable.execution_reelle(APP):
            pass


def _runner_sans_sous_processus(tmp_path, monkeypatch, **kw):
    from testpilot.execution import behave_runner as br

    lances: list[int] = []
    monkeypatch.setattr(br.subprocess, "run",
                        lambda *a, **k: lances.append(1) or SimpleNamespace(stdout="", stderr="", returncode=0))
    monkeypatch.setattr(br.BehaveRunner, "_assemble", lambda *a, **k: None)
    (tmp_path / "m.feature").write_text("# language: fr\nFonctionnalité: x\n", encoding="utf-8")
    return br, lances, (lambda **plus: br.BehaveRunner(generated_dir=tmp_path, **{**kw, **plus}))


def test_falsifiable_le_run_retenu_sort_erreur_technique_jamais_un_verdict(tmp_path, monkeypatch):
    from testpilot.execution.executor import ExecutionOutcome
    from testpilot.verdict import status

    br, lances, runner = _runner_sans_sous_processus(tmp_path, monkeypatch, connection={"WEB_URL": "http://app"})
    bac_a_sable.marquer_non_remis(APP, "http://app/reset")

    def en_panne(url, delai_s=0):
        raise RuntimeError("503")

    monkeypatch.setattr(bac_a_sable, "remettre_a_zero", en_panne)

    resultat = runner().real_run("m")

    assert lances == [], "Behave n'est pas lancé"
    assert resultat.returncode < 0 and not resultat.success and "PRÉREQUIS MANQUANT" in resultat.raw_stderr
    verdict = status.derive_verdict(ExecutionOutcome(module_name="m", dry_run_passed=True, real_run=resultat))
    assert (verdict.execution_status, verdict.functional_status) == (status.EXEC_TECHNICAL_ERROR, status.FUNC_INDETERMINE)


def test_le_runner_d_une_execution_reelle_passe_par_l_exclusion_pas_celui_d_un_essai(tmp_path, monkeypatch):
    br, _, runner = _runner_sans_sous_processus(tmp_path, monkeypatch, connection={"WEB_URL": "http://App/"}, project_id=7)
    vus: list[tuple] = []

    @contextlib.contextmanager
    def espion(cle):
        vus.append(("exécution réelle", cle))
        yield

    monkeypatch.setattr(br.bac_a_sable, "execution_reelle", espion)

    runner().dry_run("m")
    runner(essai=True).real_run("m")
    assert vus == [], "ni un essai à blanc ni un essai ne prennent la place d'une exécution réelle"
    runner().real_run("m")
    runner(connection={"ODOO_URL": "https://erp.example"}).real_run("m")
    runner(connection={}).real_run("m")
    assert vus == [("exécution réelle", APP), ("exécution réelle", "https://erp.example:443"), ("exécution réelle", None)]


def test_falsifiable_un_essai_n_apprend_rien_au_projet(tmp_path, monkeypatch):
    """Un refus rencontré en tâtonnant échapperait à D32 (aucun métier validé à confronter) et deviendrait une règle du projet."""
    from testpilot.execution import behave_runner as br
    from testpilot.execution import selector_memory
    from testpilot.generation import menu_appris, regles_apprises

    appris: list[str] = []
    monkeypatch.setattr(regles_apprises, "enregistrer", lambda *a, **k: appris.append("refus") or 1)
    monkeypatch.setattr(selector_memory, "enregistrer", lambda *a, **k: appris.append("sélecteur") or [])
    monkeypatch.setattr(menu_appris, "enregistrer", lambda *a, **k: appris.append("menu") or 1)
    resultat = BehaveResult(success=True, returncode=0)
    resultat.refus_mesures = [{"champ": "email", "valeur_refusee": "x", "raison": "format"}]
    resultat.selector_tiers = [{"ident": "Nom", "tier": "label"}]
    resultat.menus_appris = [{"demande": "Ventes", "trouve": "Sales"}]

    essai = br.BehaveRunner(generated_dir=tmp_path, project_id=7, essai=True)
    for apprendre in (essai._apprendre, essai._apprendre_menus):
        apprendre(resultat, dry_run=False)
    essai._detecter_derive(resultat, "m", dry_run=False)
    assert appris == []

    reel = br.BehaveRunner(generated_dir=tmp_path, project_id=7)
    reel._apprendre(resultat, dry_run=False)
    reel._detecter_derive(resultat, "m", dry_run=False)
    reel._apprendre_menus(resultat, dry_run=False)
    assert appris == ["refus", "sélecteur", "menu"], "une exécution réelle apprend toujours, comme avant"


# ── Condition 4 : des actions seulement ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("etapes, raison", [
    (['Quand j\'ouvre la page "/x"', 'Alors la page affiche le texte "129,51"'], "vérification"),
    (['Donc la page affiche le texte "x"'], "vérification"),
    (['je clique sur le bouton "Ajouter"'], "mot-clé"),
    (['Et je clique sur le bouton "Ajouter"'], "première action"),
    ([], "entre 1 et"),
    (['Quand j\'ouvre la page "/x"'] * (e.MAX_ETAPES + 1), "entre 1 et"),
    (['Quand j\'ouvre la page "/x"\nAlors la page affiche le texte "y"'], "une action par ligne"),
])
def test_falsifiable_un_essai_ne_joue_que_des_actions(tmp_path, etapes, raison):
    ctx, journal = _contexte(tmp_path, etat=ETAT)

    sortie = e.essayer_les_actions(ctx, etapes)

    assert not sortie.ok and "ESSAI_REFUSE" in sortie.observation and raison in sortie.observation
    assert journal == [], "rien n'est joué ni remis à zéro pour un essai refusé"


# Tout ce que `str.splitlines()` — donc l'analyseur de Behave — prend pour une fin de ligne.
_FINS_DE_LIGNE = [" ", " ", "\x85", "\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\r"]


@pytest.mark.parametrize("separateur", _FINS_DE_LIGNE)
def test_falsifiable_un_alors_glisse_derriere_un_separateur_unicode_est_refuse(tmp_path, separateur):
    """Relecture (B2), reproduit sur le vrai harnais : le contrôle ne refusait que `\\n` et `\\r` ; Behave lisait deux steps,
    jouait le « Alors », et son message d'échec rendait la valeur de la page (« 129,15 € »)."""
    ctx, journal = _contexte(tmp_path, etat=ETAT)
    glisse = f'Quand j\'ouvre la page "/panier"{separateur}Alors la valeur affichée pour "Total TTC" est "0"'

    sortie = e.essayer_les_actions(ctx, [glisse])

    assert not sortie.ok and "ESSAI_REFUSE" in sortie.observation and journal == []


@pytest.mark.parametrize("lignes, attendues, raison", [
    (['Quand j\'ouvre la page "/x"', 'Alors la page affiche le texte "y"'], 2, "vérification"),
    (['Quand j\'ouvre la page "/x"', 'Et je clique sur le bouton "A"', 'Alors je vois "y"', 'Et je vois "z"'], 4, "vérification"),
    (['Quand j\'ouvre la page "/x"', '| a | b |'], 2, "une action par ligne"),
    (['Quand j\'ouvre la page "/x"', '"""', 'texte', '"""'], 4, "une action par ligne"),
    (['Quand j\'ouvre la page "/x"', '', '  Scénario: second', '    Quand j\'ouvre la page "/y"'], 4, "un seul scénario"),
])
def test_falsifiable_le_fichier_joue_est_relu_par_behave(lignes, attendues, raison):
    """La garantie est de STRUCTURE (ce que Behave lit), pas une liste de caractères interdits."""
    assert raison in e._refus_de_structure(e._texte_du_scenario(lignes), attendues)


def test_des_actions_seules_passent_la_relecture_par_behave():
    assert e._refus_de_structure(e._texte_du_scenario(ACTIONS), len(ACTIONS)) == ""
    assert e._refus_de_structure(e._texte_du_scenario(['Soit j\'ouvre la page "/x"', 'Mais je clique sur le bouton "A"']), 2) == ""


def test_des_actions_hors_catalogue_sont_refusees_avant_tout_run(tmp_path):
    ctx, journal = _contexte(tmp_path, a_blanc=False, etat=ETAT)

    sortie = e.essayer_les_actions(ctx, ['Quand je fais n\'importe quoi'])

    assert not sortie.ok and "STEP_INCONNU" in sortie.observation and "n'importe quoi" in sortie.observation
    assert journal == ["essai à blanc"]


# ── Condition 4 : rien qu'un « Alors » puisse recopier ────────────────────────────────────────────────────


def test_l_observation_dit_ou_l_on_arrive_et_nourrit_le_controle_des_libelles(tmp_path):
    connu = Annuaire(champs={"/panier": {"Code promo"}})
    ctx, _ = _contexte(tmp_path, annuaire=connu, etat=ETAT)

    sortie = e.essayer_les_actions(ctx, ACTIONS)

    assert "http://app/panier" in sortie.observation and "textbox « Code promo »" in sortie.observation
    assert "viennent de la spécification" in sortie.observation
    assert {"Code promo", "Valider la commande", "Valider"} <= ctx.annuaire.observes_session, "cibles d'ACTION acceptées"
    assert ctx.essai.vus == {} and ctx.essai.textes == {}, "des noms de champs et de boutons ne sont pas des données"


def test_les_donnees_vues_a_l_essai_sont_relevees_avec_leur_origine(tmp_path):
    """Contre-relecture : l'espace insécable d'un montant et les paramètres de l'adresse échappaient à la garde."""
    etat = {"url": "http://app/confirmation/CMD-0042?numero=CMD-0042&client=Dupont&total=129%2C15#etape-2",
            "elements": [{"role": "button", "nom": "Payer 129,15\u00a0€"}, {"role": "a", "nom": "Commande CMD-0042"},
                         {"role": "a", "nom": "Retour"}, {"role": "textbox", "nom": "Code promo"},
                         {"role": "a", "nom": "Panier (3)"}]}
    connu = Annuaire(champs={"/confirmation": {"Code promo"}}, boutons={"/confirmation": {"Retour"}})
    ctx, _ = _contexte(tmp_path, annuaire=connu, etat=etat)

    e.essayer_les_actions(ctx, ACTIONS)

    assert set(ctx.essai.vus) == {"129,15", "cmd-0042", "0042", "3", "etape-2", "2"}, \
        "le jeton entier et le nombre qu'il renferme"
    assert ctx.essai.vus["129,15"] == "Payer 129,15\u00a0€"
    assert set(ctx.essai.textes) == {"dupont"}, \
        "une valeur de paramètre d'adresse ; ni un texte de lien, ni « confirmation », nom de page"


@pytest.mark.parametrize("texte, attendus", [
    ("Payer:129,15€", {"payer:129,15", "129,15"}),          # collé à son libellé
    ("3kg", {"3kg", "3"}), ("Commande CMD-0042", {"cmd-0042", "0042"}),
    ("le 11/10/2026", {"11/10/2026", "2026"}),               # d'une date, ni « 11 » ni « 10 »
    ("1\u202f129,15\u00a0€", {"1", "129,15"}), ("Retour", set()),
])
def test_les_jetons_a_chiffres_et_le_nombre_qu_ils_renferment(texte, attendus):
    assert e._jetons_a_chiffres(texte) == attendus


def test_la_relecture_par_behave_est_bien_appelee_par_l_outil(tmp_path, monkeypatch):
    """Contre-relecture : les deux contrôles se couvraient l'un l'autre — aucun test ne prouvait que l'outil appelle le second."""
    monkeypatch.setattr(e, "_refus_des_etapes", lambda etapes: "")
    ctx, journal = _contexte(tmp_path, etat=ETAT)

    sortie = e.essayer_les_actions(ctx, ['Quand j\'ouvre la page "/x"', 'Alors la page affiche le texte "y"'])

    assert not sortie.ok and "ESSAI_REFUSE" in sortie.observation and "vérification" in sortie.observation and journal == []


def test_falsifiable_un_echec_ne_rend_que_le_type_de_l_erreur_jamais_son_message(tmp_path):
    """Relecture (B3), reproduit : le message brut rendait « Aucun champ … dans la ligne contenant « 129,15 € » »."""
    echec = SimpleNamespace(step_text='Et je renseigne "Quantité" avec "1" dans la ligne contenant "Câble"',
                            page_url="http://app/produits", traceback_summary="",
                            raw='Traceback (most recent call last):\n  File "x.py", line 3, in f\n'
                                '_base_helpers.ElementIntrouvableError: Aucun champ « Quantité » dans la ligne contenant '
                                '« 129,15 € » ; valeurs différentes (\'CMD-0042\', \'CMD-0043\')')
    ctx, _ = _contexte(tmp_path, echec=echec, etat={"url": "http://app/produits", "elements": []})

    sortie = e.essayer_les_actions(ctx, ACTIONS)

    assert sortie.ok and "ÉCHEC à l'action" in sortie.observation and "(ElementIntrouvableError)" in sortie.observation
    assert "http://app/produits" in sortie.observation
    assert "129,15" not in sortie.observation and "CMD-0042" not in sortie.observation


@pytest.mark.parametrize("brut, attendu", [
    ("playwright._impl._errors.TimeoutError: Locator.click: Timeout 5000ms exceeded.", "TimeoutError"),
    ("ASSERT FAILED: La valeur affichée pour « Total TTC » est « 129,15 € »", "AssertionError"),
    ("quelque chose d'illisible", "erreur"),
])
def test_le_type_d_erreur_est_lu_sans_le_message(brut, attendu):
    assert e._type_d_erreur(SimpleNamespace(raw=brut, traceback_summary="")) == attendu


_FEATURE = """# language: fr
Fonctionnalité: Commande

  Scénario: Validation
    Quand j'ouvre la page "/panier"
    Et je clique sur le bouton "{bouton}"
    Alors la page affiche le texte "{attendu}"
"""
_STEPS = """from behave import then
from _base_helpers import constater


@then('la commande apparaît')
def verifier(context):
    constater("{attendu}" in context.page.inner_text("body"), "commande affichée")
"""


def _apres_un_essai(tmp_path, exigences):
    ctx, _ = _contexte(tmp_path, etat=ETAT)
    ctx.requirements = exigences
    ctx.essai.vus = {"cmd-0042": "Commande CMD-0042", "0042": "Commande CMD-0042", "129,15": "Payer 129,15\u00a0€",
                     "3": "Panier (3)", "2": "Page 2", "107,93": "Payer 107,93 €"}
    ctx.essai.textes = {"commande cmd-0042": "Commande CMD-0042", "dupond": "l'adresse /confirmation"}
    ctx.annuaire.observes_session.update({"Valider la commande", "Total"})  # comme après un essai (lot VH-05)
    return ctx


_SPEC = {"expected_result": "La commande est enregistrée, son numéro est affiché et le total TTC est de 129,51 €."}


@pytest.mark.parametrize("attendu", [
    "CMD-0042", "Commande CMD-0042 enregistrée", "cmd-0042", "0042",
    "129,15 €",                      # espace ORDINAIRE, la page portait une espace insécable
    "129,15\u202f€", "Total : 129,15",
    "Client Dupond",                 # valeur d'un paramètre de l'adresse
])
def test_falsifiable_ce_qui_n_a_ete_vu_qu_a_l_essai_ne_devient_pas_un_attendu(tmp_path, attendu):
    """Relecture (B1) puis contre-relecture, reproduit de bout en bout : l'agent jouait une action, lisait « Payer 129,15 € »
    sur la page d'arrivée (la spécification dit 129,51 €) et l'écrivait comme attendu — `conforme` sur l'application fautive."""
    ctx = _apres_un_essai(tmp_path, _SPEC)

    sortie = w.write_feature_file(ctx, _FEATURE.format(bouton="Valider la commande", attendu=attendu))

    assert not sortie.ok and "VALEUR_TIREE_DE_L_ESSAI" in sortie.observation, sortie.observation
    assert "vu à l'essai dans" in sortie.observation, "le refus nomme ce qui l'a déclenché"
    assert not (tmp_path / "m.feature").exists()


_AUTRES_FORMES = {
    "sans guillemets": """# language: fr
Fonctionnalité: Commande

  Scénario: Validation
    Quand j'ouvre la page "/panier"
    Alors la page affiche le numéro CMD-0042
""",
    "dans un tableau": """# language: fr
Fonctionnalité: Commande

  Scénario: Validation
    Quand j'ouvre la page "/panier"
    Alors le récapitulatif affiche
      | libellé | valeur   |
      | Total   | 129,15 € |
""",
    "dans un texte joint": ("# language: fr\nFonctionnalité: Commande\n\n  Scénario: Validation\n"
                            "    Quand j'ouvre la page \"/panier\"\n    Alors la page affiche\n"
                            "      " + '"' * 3 + "\n      Commande CMD-0042\n      " + '"' * 3 + "\n"),
    "dans le contexte": """# language: fr
Fonctionnalité: Commande

  Contexte:
    Soit j'ouvre la page "/panier"
    Alors la page affiche le texte "CMD-0042"

  Scénario: Validation
    Quand je clique sur le bouton "Valider la commande"
""",
    "par les exemples": """# language: fr
Fonctionnalité: Commande

  Plan du Scénario: Validation
    Quand j'ouvre la page "/panier"
    Alors la page affiche le texte "<total>"

    Exemples:
      | total    |
      | 129,15 € |
""",
    "un Et après Alors": """# language: fr
Fonctionnalité: Commande

  Scénario: Validation
    Quand j'ouvre la page "/panier"
    Alors la page affiche le texte "Merci"
    Et la page affiche le texte "CMD-0042"
""",
}


@pytest.mark.parametrize("forme", sorted(_AUTRES_FORMES))
def test_falsifiable_la_garde_lit_tout_ce_qu_un_alors_dit(tmp_path, forme):
    """Contre-relecture : seuls les littéraux entre guillemets des scénarios étaient lus."""
    sortie = w.write_feature_file(_apres_un_essai(tmp_path, _SPEC), _AUTRES_FORMES[forme])

    assert not sortie.ok and "VALEUR_TIREE_DE_L_ESSAI" in sortie.observation, sortie.observation


_STEPS_A_LA_MAIN = {
    "dans le @then": """from behave import then
from _base_helpers import constater


@then('la commande apparaît')
def verifier(context):
    constater("CMD-0042" in context.page.inner_text("body"), "commande affichée")
""",
    "dans une constante du module": """from behave import then
from _base_helpers import constater

ATTENDU = 'CMD-0042'


@then('la commande apparaît')
def verifier(context):
    constater(ATTENDU in context.page.inner_text("body"), "commande affichée")
""",
    "dans une fonction d'aide": """from behave import then
from _base_helpers import constater


def _attendu():
    return "129,15 €"


@then('le total est affiché')
def verifier(context):
    constater(_attendu() in context.page.inner_text("body"), "total affiché")
""",
}


@pytest.mark.parametrize("forme", sorted(_STEPS_A_LA_MAIN))
def test_falsifiable_un_alors_ecrit_a_la_main_ne_recopie_pas_l_essai(tmp_path, forme):
    sortie = w.write_steps_file(_apres_un_essai(tmp_path, _SPEC), _STEPS_A_LA_MAIN[forme])

    assert not sortie.ok and "VALEUR_TIREE_DE_L_ESSAI" in sortie.observation, sortie.observation


def test_une_action_ecrite_a_la_main_peut_viser_ce_que_l_essai_a_montre(tmp_path):
    code = """from behave import when


@when('j ouvre la commande créée')
def ouvrir(context):
    context.page.get_by_role("link", name="Commande CMD-0042").click()
"""
    ctx = _apres_un_essai(tmp_path, _SPEC)
    ctx.annuaire.observes_session.add("Commande CMD-0042")  # montré par l'essai : cible d'action connue du lot VH-05

    sortie = w.write_steps_file(ctx, code)

    assert sortie.ok, sortie.observation


def test_ce_que_la_specification_dit_et_les_cibles_d_action_restent_permis(tmp_path):
    ctx = _apres_un_essai(tmp_path, {"expected_result": "Le numéro CMD-0042 est affiché.", "step:1": "Valider la commande"})

    # « Valider la commande » vu à l'essai est une cible d'ACTION ; « CMD-0042 » est dit par la spécification.
    assert w.write_feature_file(ctx, _FEATURE.format(bouton="Valider la commande", attendu="CMD-0042")).ok
    assert w.write_steps_file(ctx, _STEPS.format(attendu="CMD-0042")).ok

    sans_essai = ToolContext(module_name="m", generated_dir=tmp_path)
    assert w.write_feature_file(sans_essai, _FEATURE.format(bouton="Valider la commande", attendu="CMD-0042")).ok, \
        "sans essai, rien ne change"


@pytest.mark.parametrize("etape", [
    'Alors la page affiche le texte "Merci pour votre achat"',
    'Alors la page affiche le texte "Nombre d\'articles : 2"',     # un champ « Nom » vu à l'essai n'y fait rien
    'Alors la valeur affichée pour "Total" est "129,51 €"',         # « Total » : un NOM vu à l'essai, la valeur vient de la spec
    'Alors l\'URL courante contient "/confirmation"',               # un nom de page
    'Alors la page affiche le texte "129,51 euros"',
    'Alors le tableau "Valider la commande" compte 1 ligne',
    'Alors le tableau "Commandes" compte 2 lignes',                 # la spécification dit « deux lignes », un « 2 » de pagination a été vu
    'Alors la page affiche le texte "Aucun retour possible"',       # un lien « Retour » vu à l'essai n'y fait rien
])
def test_les_faux_refus_releves_a_la_contre_relecture_ne_se_produisent_plus(tmp_path, etape):
    """Une première garde, par sous-chaîne, refusait des littéraux sans rapport et les NOMS vus à l'essai : tours perdus."""
    ctx = _apres_un_essai(tmp_path, {**_SPEC, "step:1": "La liste affiche deux lignes."})
    feature = ('# language: fr\nFonctionnalité: Commande\n\n  Scénario: Validation\n'
               '    Quand j\'ouvre la page "/panier"\n    ' + etape + '\n')

    sortie = w.write_feature_file(ctx, feature)

    assert "VALEUR_TIREE_DE_L_ESSAI" not in sortie.observation, sortie.observation


# ── Ce que la garde ne peut pas voir va au relecteur ──────────────────────────────────────────────────────

_SPEC_HT_TTC = {"expected_result": "3 câbles à 43,17 € pièce : total HT 107,93 €, total TTC 129,51 €."}
_ALORS_FAUX = 'Alors la valeur affichée pour "Total TTC" est "107,93 €"'


def _feature_avec(etape: str) -> str:
    return ('# language: fr\nFonctionnalité: Commande\n\n  Scénario: Validation\n'
            '    Quand j\'ouvre la page "/panier"\n    ' + etape + '\n')


def test_falsifiable_une_valeur_vue_a_l_essai_et_dite_ailleurs_par_la_specification_est_signalee_au_relecteur(tmp_path):
    """Troisième relecture, reproduit de bout en bout : l'application fautive affiche le hors taxes à la place du TTC, l'essai
    montre « Payer 107,93 € », « Total TTC est 107,93 € » est écrit (le nombre EST dans la spécification) et le run sort
    `conforme`. Aucune liste de jetons ne peut le refuser ; le relecteur, lui, doit le voir — et la version ne s'approuve pas seule."""
    from testpilot.api.services import generation_service as gs

    ctx = _apres_un_essai(tmp_path, _SPEC_HT_TTC)
    assert w.write_feature_file(ctx, _feature_avec(_ALORS_FAUX)).ok, "la garde d'écriture ne le voit pas : c'est la limite"

    version = {"id": 1, "feature_content": _feature_avec(_ALORS_FAUX), "steps_content": "",
               "generation_provenance": json.dumps({"essais": {"joues": 1, "donnees_vues": sorted(ctx.essai.vus)}})}
    signaux = gs._valeurs_vues_a_l_essai([version], version)

    assert [sig["kind"] for sig in signaux] == [gs.VALEUR_VUE_A_L_ESSAI]
    assert "107,93" in signaux[0]["message"] and "spécification" in signaux[0]["message"]
    assert signaux[0]["step"] == 'la valeur affichée pour "Total TTC" est "107,93 €"'


def test_sans_essai_ou_sans_donnee_citee_aucun_signal(tmp_path):
    from testpilot.api.services import generation_service as gs

    juste = {"id": 1, "feature_content": _feature_avec('Alors la valeur affichée pour "Total TTC" est "129,51 €"'),
             "steps_content": "", "generation_provenance": json.dumps({"essais": {"donnees_vues": ["107,93", "cmd-0042"]}})}
    sans_essai = {"id": 2, "feature_content": _feature_avec(_ALORS_FAUX), "steps_content": "", "generation_provenance": "{}"}
    illisible = {"id": 3, "feature_content": _feature_avec(_ALORS_FAUX), "steps_content": "", "generation_provenance": "{"}

    for version in (juste, sans_essai, illisible):
        assert gs._valeurs_vues_a_l_essai([version], version) == []
    assert e.alors_qui_citent(_feature_avec('Quand je clique sur le bouton "Payer 107,93 €"'), ["107,93"]) == [], \
        "une action peut viser ce que l'essai a montré"


def test_la_provenance_consigne_les_donnees_vues(tmp_path):
    """Le signal du relecteur se lit dans la provenance de la version : elle doit porter ce que les essais ont montré."""
    agent = (RACINE / "src" / "testpilot" / "generation" / "agent.py").read_text(encoding="utf-8")

    assert "'donnees_vues': sorted(ctx.essai.vus)" in agent


# ── Réglage du projet : API ───────────────────────────────────────────────────────────────────────────────


def test_l_api_enregistre_une_declaration_complete_et_refuse_une_autre_application(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from testpilot.api import app as app_mod
    from testpilot.store.db import get_initialized_db
    from testpilot.store.repositories import ProjectRepo

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    conn = get_initialized_db(tmp_path / "api.db")
    pid = ProjectRepo(conn).create(name="P", connector_type="web", base_url="http://app:8000")
    client = TestClient(app_mod.app)

    ok = client.patch(f"/api/projects/{pid}", json={"bac_a_sable_reset": "/reset"})
    refuse = client.patch(f"/api/projects/{pid}", json={"name": "Renommé", "bac_a_sable_reset": "http://autre.example/reset"})

    assert ok.status_code == 200 and ok.json()["bac_a_sable_reset"] == "http://app:8000/reset"
    assert refuse.status_code == 422
    projet = ProjectRepo(conn).get(pid)
    assert projet["bac_a_sable_reset"] == "http://app:8000/reset"
    assert projet["name"] == "P", "un refus ne laisse pas la moitié du corps enregistrée"
    conn.close()


def test_falsifiable_la_declaration_ne_suit_pas_un_changement_d_adresse(tmp_path, monkeypatch):
    """Relecture : un chemin relatif était rejoint à l'adresse DU MOMENT — une recette devenue production restait bac à sable."""
    from fastapi.testclient import TestClient

    from testpilot.api import app as app_mod
    from testpilot.store.db import get_initialized_db
    from testpilot.store.repositories import ProjectRepo

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    conn = get_initialized_db(tmp_path / "api.db")
    pid = ProjectRepo(conn).create(name="P", connector_type="web", base_url="http://recette.example")
    client = TestClient(app_mod.app)
    client.patch(f"/api/projects/{pid}", json={"calibration_writes_enabled": True, "bac_a_sable_reset": "/reset"})
    runner = SimpleNamespace(connection={"WEB_URL": "http://recette.example"})
    assert e.construire(ProjectRepo(conn).get(pid), runner) is not None

    assert client.patch(f"/api/projects/{pid}", json={"base_url": "https://production.example"}).status_code == 200

    assert e.construire(ProjectRepo(conn).get(pid), runner) is None, "plus de bac à sable tant qu'il n'est pas redéclaré"
    # L'écran renvoie la déclaration enregistrée avec la nouvelle adresse : refusée, le porteur doit décider.
    assert client.patch(f"/api/projects/{pid}", json={"base_url": "https://production.example",
                                                      "bac_a_sable_reset": "http://recette.example/reset"}).status_code == 422
    redeclare = client.patch(f"/api/projects/{pid}", json={"bac_a_sable_reset": "/reset"})
    assert redeclare.json()["bac_a_sable_reset"] == "https://production.example/reset"
    assert client.patch(f"/api/projects/{pid}", json={"bac_a_sable_reset": ""}).json()["bac_a_sable_reset"] == ""
    conn.close()


def test_l_api_montre_la_marque_et_le_porteur_la_leve(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from testpilot.api import app as app_mod
    from testpilot.store.db import get_initialized_db
    from testpilot.store.repositories import ProjectRepo

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    conn = get_initialized_db(tmp_path / "api.db")
    pid = ProjectRepo(conn).create(name="P", connector_type="web", base_url="http://app:8000")
    client = TestClient(app_mod.app)
    assert client.patch(f"/api/projects/{pid}", json={"description": "x"}).json()["bac_a_sable_non_remis"] is False

    bac_a_sable.marquer_non_remis("http://app:8000", "http://app:8000/reset")

    assert client.patch(f"/api/projects/{pid}", json={"description": "y"}).json()["bac_a_sable_non_remis"] is True, \
        "une modification ordinaire du projet ne lève pas la marque"
    levee = client.patch(f"/api/projects/{pid}", json={"bac_a_sable_remis_a_zero": True})
    assert levee.status_code == 200 and levee.json()["bac_a_sable_non_remis"] is False
    assert bac_a_sable.non_remis("http://app:8000") is None
    conn.close()


def test_les_noms_de_la_variable_sont_d_accord():
    sys.path.insert(0, str(RACINE))
    from behave_runtime import environment

    assert environment.ESSAI_ETAT_FILE_ENV == e.ESSAI_ETAT_FILE_ENV


# ── Vrai Chromium : ce que le harnais relève à la fin d'un essai ──────────────────────────────────────────

_PAGE_D_ARRIVEE = """<html><body>
<h1>Commande enregistrée</h1>
<p role="status">Commande CMD-0042 enregistrée, total TTC 129,15 €</p>
<div role="alert">Stock restant : 7</div>
<table><tr role="row"><td role="cell">Câble HDMI</td><td>19,90 €</td></tr></table>
<input name="quantite" value="3">
<label>Code promo <input name="code" value="ETE2026"></label>
<textarea aria-label="Commentaire">Livrer avant midi</textarea>
<label>Pays <select name="pays"><option>France</option><option selected>Belgique</option></select></label>
<span tabindex="0">Solde : 12 points</span>
<a href="/commande/CMD-0042">Voir la commande</a>
<button aria-label="Valider la commande">Valider</button>
<input type="submit" value="Envoyer">
<input type="hidden" name="jeton" value="secret-123">
</body></html>"""


@pytest.mark.conformance
def test_falsifiable_le_releve_d_essai_ne_rend_ni_texte_libre_ni_valeur_de_champ():
    """Relecture (B1), reproduit sur Chromium : le relevé des outils d'observation rendait le texte de tout élément à `role`
    ou `tabindex` et la valeur d'un champ sans libellé."""
    from playwright.sync_api import sync_playwright

    sys.path.insert(0, str(RACINE))
    from behave_runtime import environment

    with sync_playwright() as p:
        navigateur = p.chromium.launch()
        page = navigateur.new_page()
        page.set_content(_PAGE_D_ARRIVEE)
        elements = page.evaluate(environment._JS_CONTROLES_D_ESSAI, 120)
        navigateur.close()

    rendu = json.dumps(elements, ensure_ascii=False)
    for interdit in ("129,15", "CMD-0042 enregistrée", "Stock restant", "19,90", "ETE2026", "Livrer avant midi", "Belgique",
                     "12 points", "secret-123", '"3"'):
        assert interdit not in rendu, f"« {interdit} » ne doit pas revenir à l'agent"
    noms = {(el["role"], el["nom"]) for el in elements}
    assert {("input", "quantite"), ("input", "Code promo"), ("textarea", "Commentaire"), ("select", "pays"),
            ("a", "Voir la commande"), ("button", "Valider la commande"), ("input", "Envoyer")} <= noms
    assert [el.get("texte") for el in elements if el["nom"] == "Valider la commande"] == ["Valider"]


# ── Bout en bout : vrai Behave, vrai Chromium, vraie remise à zéro ────────────────────────────────────────

_ETAT_SERVEUR = {"panier": 0, "resets": 0}


class _Boutique(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _html(self, corps: str, code=200, entetes=None):
        donnees = ("<html><body>" + corps + "</body></html>").encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(donnees)))
        for cle, valeur in (entetes or {}).items():
            self.send_header(cle, valeur)
        self.end_headers()
        self.wfile.write(donnees)

    def do_GET(self):
        chemin = self.path.split("?")[0]
        if chemin in ("/", "/produits"):
            return self._html('<h1>Produits</h1><form method="post" action="/panier/ajouter"><button>Ajouter</button></form>')
        if chemin == "/panier":
            return self._html(f'<h1>Panier</h1><p role="status">Commande CMD-0042, total TTC {_ETAT_SERVEUR["panier"] * 42},00 €</p>'
                              '<input name="quantite" value="3"><label>Code promo <input name="code"></label>'
                              '<a href="/commande/CMD-0042">Commande CMD-0042</a><button>Valider la commande</button>')
        self._html("absent", 404)

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if self.path == "/panier/ajouter":
            _ETAT_SERVEUR["panier"] += 1
            self.send_response(302)
            self.send_header("Location", "/panier")
            self.send_header("Content-Length", "0")
            return self.end_headers()
        if self.path == "/reset":
            _ETAT_SERVEUR["panier"] = 0
            _ETAT_SERVEUR["resets"] += 1
            return self._html("ok")
        if self.path == "/reset-sans-session":
            self.send_response(302)
            self.send_header("Location", "/produits")
            self.send_header("Content-Length", "0")
            return self.end_headers()
        self._html("absent", 404)


@pytest.fixture
def boutique():
    serveur = ThreadingHTTPServer(("127.0.0.1", 0), _Boutique)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    _ETAT_SERVEUR.update(panier=0, resets=0)
    yield f"http://127.0.0.1:{serveur.server_address[1]}"
    serveur.shutdown()


def _contexte_reel(url, tmp_path, reset="/reset"):
    from testpilot.execution.behave_runner import BehaveRunner

    projet = {"connector_type": "web", "base_url": url, "calibration_writes_enabled": 1, "bac_a_sable_reset": f"{url}{reset}"}
    runner = BehaveRunner(connection={"WEB_URL": url, "WEB_USER": "", "WEB_PASSWORD": ""}, connector_type="web",
                          generated_dir=tmp_path)
    return ToolContext(module_name="m", generated_dir=tmp_path, essai=e.construire(projet, runner), annuaire=Annuaire(),
                       requirements={"expected_result": "Le produit est ajouté au panier."})


@pytest.mark.conformance
def test_de_bout_en_bout_l_essai_montre_la_page_d_arrivee_et_ne_laisse_rien(boutique, tmp_path):
    ctx = _contexte_reel(boutique, tmp_path)

    sortie = e.essayer_les_actions(ctx, ACTIONS)

    assert sortie.ok, sortie.observation
    assert "Les 2 action(s) ont réussi" in sortie.observation and f"{boutique}/panier" in sortie.observation
    assert "Code promo" in sortie.observation and "Valider la commande" in sortie.observation
    # Condition 4 : ni le message d'état, ni le total, ni la valeur d'un champ ne reviennent à l'agent.
    assert "42,00" not in sortie.observation and "total TTC" not in sortie.observation and "« 3 »" not in sortie.observation
    # Condition 2 : remis à zéro avant et après — rien ne subsiste de l'essai.
    assert _ETAT_SERVEUR == {"panier": 0, "resets": 2}
    assert "Code promo" in ctx.annuaire.observes_session
    # Le lien de la page d'arrivée porte un numéro : cible d'action permise, attendu refusé.
    assert "Commande CMD-0042" in sortie.observation and ctx.essai.vus.get("cmd-0042") == "Commande CMD-0042"
    refus = w.write_feature_file(ctx, _FEATURE.format(bouton="Valider la commande", attendu="CMD-0042"))
    assert not refus.ok and "VALEUR_TIREE_DE_L_ESSAI" in refus.observation, refus.observation


@pytest.mark.conformance
def test_de_bout_en_bout_un_alors_glisse_n_est_jamais_joue(boutique, tmp_path):
    ctx = _contexte_reel(boutique, tmp_path)
    glisse = 'Quand j\'ouvre la page "/panier" Alors la page affiche le texte "0,00 €"'

    sortie = e.essayer_les_actions(ctx, [glisse])

    assert not sortie.ok and "ESSAI_REFUSE" in sortie.observation
    assert _ETAT_SERVEUR["resets"] == 0 and "0,00" not in sortie.observation.replace(glisse, "")


@pytest.mark.conformance
def test_de_bout_en_bout_une_remise_a_zero_qui_redirige_interdit_l_essai(boutique, tmp_path):
    ctx = _contexte_reel(boutique, tmp_path, reset="/reset-sans-session")

    sortie = e.essayer_les_actions(ctx, ACTIONS)

    assert not sortie.ok and "REMISE_A_ZERO_IMPOSSIBLE" in sortie.observation
    assert _ETAT_SERVEUR == {"panier": 0, "resets": 0}, "aucune action n'a été jouée sur une application non remise à zéro"
