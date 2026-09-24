"""Sonde de saisie (lot 12, D10 bis) — le garde-fou PRINCIPAL et ses voisins.

Écrire dans un formulaire sans le soumettre n'est pas sans risque : certaines applications
enregistrent un brouillon en tapant, le back-office Odoo sauvegarde en quittant la vue. Le test
central de ce fichier : **une requête POST, PUT ou PATCH émise pendant la sonde l'interrompt**, dans
le contexte AUTHENTIFIÉ (jamais un contexte neuf, qui n'aurait pas la session).
"""
from __future__ import annotations

import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from testpilot.connectors import _sonde_saisie as sonde


# ── Doublures : une page persistante authentifiée et sa page jetable ───────────────────────────

class _Requete:
    def __init__(self, method, url):
        self.method, self.url = method, url


class _Route:
    """Ce que Playwright passe au gestionnaire d'interception : abandonner ou laisser passer."""

    def __init__(self, requete):
        self.request = requete
        self.abandonnee = self.continuee = False

    def abort(self):
        self.abandonnee = True

    def continue_(self):
        self.continuee = True


class _Locator:
    def __init__(self, page, nom):
        self._page, self._nom = page, nom

    @property
    def first(self):
        return self

    def fill(self, valeur):
        self._page.remplir(self._nom, valeur)

    def evaluate(self, _js):
        return self._page.lire(self._nom)


class _PageJetable:
    """Pas de `click`, pas de `keyboard` : tout clic lèverait `AttributeError` (test « aucun clic »)."""

    def __init__(self, champs, retention=None, ecritures=None, valide=r"\d{7}(/\d{7})*",
                 poster_au_fill=None):
        self.valide = re.compile(valide)            # ce que le navigateur juge valide
        self.poster_au_fill = poster_au_fill        # n° (1-based) du remplissage qui émet un POST
        self.champs = champs                        # {nom: valeur courante}
        self.retention = retention or {}            # {nom: fonction(saisi) -> retenu}
        self.ecritures = ecritures or {}            # {nom: (méthode, url)} émis au remplissage
        self.handlers, self.remplissages, self.gotos, self.routes = [], [], [], []
        self.fermeture = None

    def route(self, motif, handler):
        assert motif == "**/*"
        self.handlers.append(handler)

    def goto(self, url, **_kw):
        self.gotos.append(url)

    def wait_for_timeout(self, _ms):
        pass

    def evaluate(self, _js):
        return list(self.champs)

    def locator(self, selecteur):
        return _Locator(self, re.search(r'name="([^"]+)"', selecteur).group(1))

    def remplir(self, nom, valeur):
        self.remplissages.append((nom, valeur))
        self.champs[nom] = self.retention.get(nom, lambda v: v)(valeur)
        if nom in self.ecritures or self.poster_au_fill == len(self.remplissages):
            methode, url = self.ecritures.get(nom, ("POST", "https://app.test/draft"))
            for h in self.handlers:
                route = _Route(_Requete(methode, url))
                h(route)
                self.routes.append(route)

    def lire(self, nom):
        valeur = self.champs[nom]
        ok = bool(self.valide.fullmatch(valeur))
        return {"valeur": valeur, "valide": ok, "message": "" if ok else "Format invalide"}

    def close(self, run_before_unload=None, **_kw):
        self.fermeture = {"run_before_unload": run_before_unload}


class _ContexteAuthentifie:
    """`new_page()` seulement : un `new_context()` (session perdue) n'existe PAS ici."""

    def __init__(self, page_jetable):
        self._jetable, self.pages_ouvertes = page_jetable, 0

    def new_page(self):
        self.pages_ouvertes += 1
        return self._jetable


class _PagePersistante:
    def __init__(self, page_jetable):
        self.context = _ContexteAuthentifie(page_jetable)


def _groupes(taille, separateur):
    def filtre(saisi):
        chiffres = "".join(c for c in saisi if c.isdigit())
        return separateur.join(chiffres[i:i + taille] for i in range(0, len(chiffres), taille))
    return filtre


_filtre_facture = _groupes(7, "/")


# ── LE garde-fou principal ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("methode", ["POST", "PUT", "PATCH", "DELETE"])
def test_GARDE_une_requete_d_ecriture_pendant_la_sonde_l_interrompt(methode):
    jetable = _PageJetable({"brouillon": "", "numero_facture1": ""},
                           ecritures={"brouillon": (methode, "https://app.test/draft/save")})
    persistante = _PagePersistante(jetable)

    resultat = sonde.sonder_formulaire(persistante, "https://app.test/en/retenue_garantie/1")

    assert resultat["statut"] == "interrompue"
    assert "sauvegarde automatique détectée, pas de sonde" in resultat["raison"]
    assert methode in resultat["raison"]
    # INTERCEPTION : la requête est ABANDONNÉE avant de partir (jamais seulement observée).
    assert [r.abandonnee for r in jetable.routes] == [True]
    assert not any(r.continuee for r in jetable.routes)
    # La sonde s'arrête SUR ce formulaire : le champ suivant n'a jamais été touché.
    assert all(nom == "brouillon" for nom, _ in jetable.remplissages)
    assert len(jetable.remplissages) == 1, "aucune saisie après la requête d'écriture"
    # Contexte AUTHENTIFIÉ : une page jetable ouverte dans le contexte de la page persistante.
    assert persistante.context.pages_ouvertes == 1
    # Fermeture SANS `beforeunload`.
    assert jetable.fermeture == {"run_before_unload": False}


def test_une_requete_de_lecture_ou_du_bruit_de_fond_n_interrompt_pas():
    jetable = _PageJetable({"numero_facture1": ""},
                           ecritures={"numero_facture1": ("POST", "https://app.test/longpolling/poll")},
                           retention={"numero_facture1": _filtre_facture})
    assert sonde.sonder_formulaire(_PagePersistante(jetable), "https://app.test/f")["statut"] == "ok"
    assert jetable.routes and all(r.continuee and not r.abandonnee for r in jetable.routes)

    jetable = _PageJetable({"numero_facture1": ""},
                           ecritures={"numero_facture1": ("GET", "https://app.test/x")})
    assert sonde.sonder_formulaire(_PagePersistante(jetable), "https://app.test/f")["statut"] == "ok"


# ── Les autres garde-fous ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("url", [
    "https://x.odoo.com/web#action=180&model=helpdesk.ticket&view_type=form",
    "https://x.odoo.com/web#model=helpdesk.ticket&view_type=form&id=42",
    "https://x.odoo.com/odoo/action-180/42",
])
def test_aucune_sonde_sur_le_back_office_odoo(url):
    jetable = _PageJetable({"name": ""})
    persistante = _PagePersistante(jetable)

    resultat = sonde.sonder_formulaire(persistante, url)

    assert resultat["statut"] == "ignoree" and "back-office Odoo" in resultat["raison"]
    assert persistante.context.pages_ouvertes == 0 and not jetable.remplissages


def test_un_portail_dont_le_chemin_commence_par_web_reste_sondable():
    """`/website/…`, `/web_x` : pas le back-office (`/web` exactement, avec fragment)."""
    assert sonde.url_sondable("https://x.odoo.com/website/form/1")[0] is True


def test_aucune_sonde_si_le_garde_fou_anti_production_est_actif(monkeypatch):
    monkeypatch.setenv("ODOO_ENV", "prod")
    jetable = _PageJetable({"name": ""})
    persistante = _PagePersistante(jetable)

    resultat = sonde.sonder_formulaire(persistante, "https://app.test/f")

    assert resultat["statut"] == "ignoree" and "anti-production" in resultat["raison"]
    assert persistante.context.pages_ouvertes == 0


def test_la_page_jetable_est_fermee_sans_beforeunload_meme_apres_une_erreur():
    class _Explose(_PageJetable):
        def evaluate(self, _js):
            raise RuntimeError("navigateur mort")

    jetable = _Explose({"name": ""})
    resultat = sonde.sonder_formulaire(_PagePersistante(jetable), "https://app.test/f")

    assert resultat["statut"] == "erreur"
    assert jetable.fermeture == {"run_before_unload": False}


def test_ni_clic_ni_navigation_apres_une_saisie():
    jetable = _PageJetable({"numero_facture1": ""}, retention={"numero_facture1": _filtre_facture})

    sonde.sonder_formulaire(_PagePersistante(jetable), "https://app.test/f")

    assert jetable.gotos == ["https://app.test/f"], "une seule navigation, AVANT toute saisie"
    assert jetable.remplissages, "la sonde a bien écrit"
    assert not hasattr(jetable, "click"), "la doublure n'a pas de clic : tout clic aurait levé"
    # Le champ est vidé à la fin (dernière saisie = chaîne vide).
    assert jetable.remplissages[-1] == ("numero_facture1", "")


# ── Ce que la sonde apprend, et un exemple STABLE seulement ────────────────────────────────────

def test_la_sonde_revele_le_masque_de_numero_facture1():
    jetable = _PageJetable({"numero_facture1": ""}, retention={"numero_facture1": _filtre_facture})

    champ = sonde.sonder_formulaire(_PagePersistante(jetable), "https://app.test/f")[
        "champs"]["numero_facture1"]

    assert champ["sondes"]["lettres"]["retenu"] == ""
    assert champ["sondes"]["chiffres"]["ecrit"] == "123456789012345678901234567890"
    # 30 chiffres : le dernier groupe est incomplet → invalide, et la sonde le DIT (pas d'exemple).
    assert champ["sondes"]["chiffres"]["valide"] is False
    assert champ["sondes"]["melange"]["retenu"] == "1234"
    assert champ["sondes"]["melange"]["message"] == "Format invalide"
    assert "→ retenu" in sonde.resume_pour_agent("numero_facture1", champ)


@pytest.mark.parametrize("taille,separateur", [(7, "/"), (4, " "), (2, " ")])
def test_un_exemple_stable_est_trouve_pour_un_masque_de_toute_taille_de_groupe(taille, separateur):
    """Sonde non calibrée sur le cas mesuré : groupes de 7, de 4 et de 2 — la longueur (30) n'est
    un multiple d'aucun sauf 2 ; la recherche par retrait de fin trouve le groupe complet."""
    motif = rf"\d{{{taille}}}({re.escape(separateur)}\d{{{taille}}})*"
    jetable = _PageJetable({"champ": ""}, retention={"champ": _groupes(taille, separateur)},
                           valide=motif)

    champ = sonde.sonder_formulaire(_PagePersistante(jetable), "https://app.test/f")[
        "champs"]["champ"]

    exemple = champ["exemple_stable"]
    assert exemple and re.fullmatch(motif, exemple), exemple
    assert _groupes(taille, separateur)(exemple) == exemple, "stable : retapé, identique"
    assert "exemple stable" in sonde.resume_pour_agent("champ", champ)
    assert len(jetable.remplissages) <= 3 + sonde._ESSAIS_RECHERCHE_MAX + 1, "recherche bornée"


def test_un_masque_impossible_a_satisfaire_ne_donne_aucun_exemple():
    """Le champ exige des lettres (`[A-Z]{2}` puis des chiffres) mais ne retient que des chiffres : rien à
    proposer, et la recherche s'arrête à son budget."""
    jetable = _PageJetable({"iban": ""}, valide=r"[A-Z]{2}\d+",
                           retention={"iban": lambda v: "".join(c for c in v if c.isdigit())})

    champ = sonde.sonder_formulaire(_PagePersistante(jetable), "https://app.test/f")[
        "champs"]["iban"]

    assert champ["exemple_stable"] is None
    assert "exemple stable" not in sonde.resume_pour_agent("iban", champ)
    assert len(jetable.remplissages) <= 3 + sonde._ESSAIS_RECHERCHE_MAX + 1


def test_un_exemple_valide_mais_non_reproductible_n_est_pas_transmis():
    """Le retenu est valide une fois, mais retapé il devient autre chose : PAS un exemple."""
    appels = {"n": 0}

    def capricieux(saisi):
        appels["n"] += 1
        return "1234567" if saisi and appels["n"] % 2 == 1 else "1234567/1234567/"

    jetable = _PageJetable({"code": ""}, retention={"code": capricieux})

    champ = sonde.sonder_formulaire(_PagePersistante(jetable), "https://app.test/f")[
        "champs"]["code"]

    assert champ["exemple_stable"] is None


def test_la_recherche_s_interrompt_sur_une_requete_d_ecriture():
    """Une requête d'écriture pendant la RECHERCHE de l'exemple (après les 3 sondes) interrompt
    aussi : plus aucune saisie ensuite."""
    jetable = _PageJetable({"numero_facture1": ""}, retention={"numero_facture1": _filtre_facture},
                           poster_au_fill=5)

    resultat = sonde.sonder_formulaire(_PagePersistante(jetable), "https://app.test/f")

    assert resultat["statut"] == "interrompue"
    assert len(jetable.remplissages) == 5, "aucune saisie après la requête d'écriture"
    assert resultat["champs"]["numero_facture1"]["exemple_stable"] is None


def test_le_resume_cite_le_texte_de_l_application_comme_donnee_et_le_tronque():
    champ = {"sondes": {"chiffres": {"ecrit": "1" * 20, "retenu": "2" * 500, "valide": False,
                                     "message": "M" * 500}}, "exemple_stable": None}

    ligne = sonde.resume_pour_agent("champ", champ)

    assert "«" in ligne and "»" in ligne
    assert len(ligne) <= 400


# ── Vrai navigateur, contexte authentifié (marqueur `conformance`, hors suite par défaut) ──────

class _Appli(BaseHTTPRequestHandler):
    ecritures: list = []
    brouillon = ""

    # Trois façons d'enregistrer un brouillon en tapant : fetch, sendBeacon, XHR PUT.
    _JS = {
        "fetch": "fetch('/draft',{method:'POST',body:this.value});",
        "beacon": "navigator.sendBeacon('/draft', this.value);",
        "xhr": "var x=new XMLHttpRequest();x.open('PUT','/draft');x.send(this.value);",
    }

    def log_message(self, *_a):
        pass

    def _authentifie(self):
        return "session=ok" in (self.headers.get("Cookie") or "")

    def do_GET(self):
        if self.path == "/form" and self._authentifie():
            corps = ("<html><body><form><input name='numero_facture1' type='text' oninput=\""
                     r"this.value=this.value.replace(/\D/g,'').replace(/(\d{7})(?=\d)/g,'$1/');"
                     + self._JS.get(self.brouillon, "") + "\"></form></body></html>")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(corps.encode("utf-8"))
        else:
            self.send_response(403)
            self.end_headers()

    def _ecriture(self):
        type(self).ecritures.append(f"{self.command} {self.path}")
        self.send_response(204)
        self.end_headers()

    do_POST = do_PUT = do_PATCH = do_DELETE = _ecriture


def _serveur(brouillon):
    _Appli.ecritures = []
    _Appli.brouillon = brouillon
    srv = HTTPServer(("127.0.0.1", 0), _Appli)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


@pytest.mark.conformance
@pytest.mark.parametrize("brouillon", ["", "fetch", "beacon", "xhr"])
def test_reel_la_sonde_tourne_dans_le_contexte_authentifie_et_le_serveur_ne_recoit_aucune_ecriture(
        brouillon):
    from playwright.sync_api import sync_playwright

    srv = _serveur(brouillon)
    url = f"http://127.0.0.1:{srv.server_port}/form"
    try:
        with sync_playwright() as p:
            navigateur = p.chromium.launch(headless=True)
            contexte = navigateur.new_context()
            contexte.add_cookies([{"name": "session", "value": "ok", "url": url}])
            page = contexte.new_page()

            resultat = sonde.sonder_formulaire(page, url)
            navigateur.close()
    finally:
        srv.shutdown()

    # La page jetable a vu le formulaire (403 sans cookie) : le contexte authentifié est bien utilisé.
    assert resultat["statut"] != "erreur", resultat
    if brouillon:
        assert resultat["statut"] == "interrompue"
        assert "sauvegarde automatique détectée" in resultat["raison"]
        assert _Appli.ecritures == [], "ZÉRO écriture reçue par le serveur : interceptée avant d'y partir"
    else:
        assert resultat["statut"] == "ok" and not _Appli.ecritures
        champ = resultat["champs"]["numero_facture1"]
        assert champ["sondes"]["chiffres"]["retenu"].startswith("1234567/8901234")
        assert champ["exemple_stable"], "aucun `pattern` : tout retenu est valide, donc stable"


# ── Mesure « cas NON VUS » : masques conçus APRÈS la sonde (fixture `torture_app/masques.html`) ─

@pytest.mark.conformance
def test_reel_mesure_sur_des_masques_jamais_vus_pendant_la_conception():
    """Chiffres de la mesure du lot 12, à présenter SÉPARÉMENT des cas de conception (99, 101,
    126, qui ont servi à concevoir la sonde) : téléphone par paires (plafond 10 chiffres), carte
    par groupes de 4 sans plafond (recherche par retrait de fin), IBAN à préfixe de lettres (hors
    de portée d'une sonde qui tape des chiffres : AUCUN exemple attendu — limite assumée)."""
    from pathlib import Path

    from playwright.sync_api import sync_playwright

    url = (Path(__file__).resolve().parent / "fixtures" / "torture_app"
           / "masques.html").resolve().as_uri()
    with sync_playwright() as p:
        navigateur = p.chromium.launch(headless=True)
        page = navigateur.new_context().new_page()
        resultat = sonde.sonder_formulaire(page, url)
        navigateur.close()

    assert resultat["statut"] == "ok", resultat
    champs = resultat["champs"]
    assert re.fullmatch(r"\d\d( \d\d){4}", champs["telephone"]["exemple_stable"] or "")
    assert re.fullmatch(r"\d{4}( \d{4})*", champs["carte"]["exemple_stable"] or "")
    assert champs["iban"]["exemple_stable"] is None
    assert not sonde.resume_pour_agent("commentaire", champs["commentaire"]),         "un champ sans masque ne produit aucune observation"


# ── Champ que le navigateur refuse de remplir (`type=number` et lettres) — mesuré le 2026-09-24 ─────

def _refuse_les_lettres(saisi):
    if not saisi.isdigit():
        raise ValueError("Cannot type text into input[type=number]")
    return saisi


def test_un_champ_qui_refuse_les_lettres_ne_fait_pas_echouer_le_formulaire():
    """Sur retenue_garantie/1, `fill("abcdefgh")` dans un `type=number` levait et faisait tomber
    TOUT le formulaire (statut « erreur ») : les champs texte suivants n'étaient jamais sondés."""
    page = _PageJetable({"montant": "", "code": ""}, valide=r"\d+",
                        retention={"montant": _refuse_les_lettres})

    resultat = sonde.sonder_formulaire(_PagePersistante(page), "https://app.test/en/form/1")

    assert resultat["statut"] == "ok", resultat
    montant = resultat["champs"]["montant"]
    assert montant["sondes"]["lettres"] == {"ecrit": "abcdefgh", "refuse": True}
    assert montant["sondes"]["chiffres"]["retenu"] == "123456789012345678901234567890"
    assert set(resultat["champs"]["code"]["sondes"]) == {"lettres", "chiffres", "melange"}
    assert "refuse" not in sonde.resume_pour_agent("montant", montant)


def test_une_erreur_imprevue_sur_un_champ_laisse_les_autres_champs_sondes():
    page = _PageJetable({"a": "", "b": ""}, valide=r"\d+")
    lire_normal = page.lire

    def lire(nom):
        if nom == "a":
            raise RuntimeError("page fermee")
        return lire_normal(nom)

    page.lire = lire

    resultat = sonde.sonder_formulaire(_PagePersistante(page), "https://app.test/en/form/1")

    assert resultat["statut"] == "ok"
    assert "page fermee" in resultat["champs"]["a"]["erreur"]
    assert set(resultat["champs"]["b"]["sondes"]) == {"lettres", "chiffres", "melange"}


@pytest.mark.conformance
def test_reel_un_champ_type_number_ne_fait_pas_echouer_le_formulaire():
    """Non-régression mesurée le 2026-09-24 sur retenue_garantie/1 : Playwright refuse de taper des
    lettres dans un `type=number` ; le champ texte qui SUIT doit quand même être sondé."""
    from playwright.sync_api import sync_playwright

    page_html = ('data:text/html,<form><input name="montant" type="number" min="0" step="any">'
                 '<input name="code" type="text"></form>')
    with sync_playwright() as p:
        navigateur = p.chromium.launch(headless=True)
        page = navigateur.new_context().new_page()
        resultat = sonde.sonder_formulaire(page, page_html)
        navigateur.close()

    assert resultat["statut"] == "ok", resultat
    assert resultat["champs"]["montant"]["sondes"]["lettres"].get("refuse") is True
    assert resultat["champs"]["montant"]["sondes"]["chiffres"]["retenu"]
    assert set(resultat["champs"]["code"]["sondes"]) == {"lettres", "chiffres", "melange"}
