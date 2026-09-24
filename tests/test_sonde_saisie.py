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

    def select_option(self, valeur, **_kw):
        self._page.choisir(self._nom, valeur)


class _PageJetable:
    """Pas de `click`, pas de `keyboard` : tout clic lèverait `AttributeError` (test « aucun clic »)."""

    def __init__(self, champs, retention=None, ecritures=None, valide=r"\d{7}(/\d{7})*",
                 poster_au_fill=None, selects=None, au_choix=None, au_remplissage=None,
                 ecritures_differees=None):
        self.ecritures_differees = ecritures_differees or {}  # {champ: (méthode, url)} au vidage
        self.file = []  # évènements réseau traités seulement au PROCHAIN `wait_for_timeout`
        self.url = "https://app.test/en/form/1"
        self.selects = selects or {}                # {nom: [valeurs d'option]} — état COURANT
        self.au_choix = au_choix or {}              # {nom du select choisi: fonction(page)}
        self.au_remplissage = au_remplissage or {}  # {nom du champ tapé: fonction(page)}
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

    def add_init_script(self, script):
        self.scripts_init = getattr(self, "scripts_init", []) + [script]

    def goto(self, url, **_kw):
        self.gotos.append(url)

    def wait_for_timeout(self, _ms):
        """Playwright ne traite les évènements réseau que pendant une attente : on le simule."""
        while self.file:
            methode, url = self.file.pop(0)
            for h in self.handlers:
                route = _Route(_Requete(methode, url))
                h(route)
                self.routes.append(route)

    def evaluate(self, js):
        if js == sonde._JS_SELECTS:
            return [{"nom": n, "options": list(o)} for n, o in self.selects.items()]
        return list(self.champs)

    def choisir(self, nom, valeur):
        self.remplissages.append((nom, f"select:{valeur}"))
        if nom in self.au_choix:
            self.au_choix[nom](self)

    def locator(self, selecteur):
        return _Locator(self, re.search(r'name="([^"]+)"', selecteur).group(1))

    def remplir(self, nom, valeur):
        self.remplissages.append((nom, valeur))
        self.champs[nom] = self.retention.get(nom, lambda v: v)(valeur)
        if valeur == "" and nom in self.ecritures_differees:
            self.file.append(self.ecritures_differees[nom])
        if nom in self.au_remplissage:
            self.au_remplissage[nom](self, valeur)
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


class _PageAnnexe:
    def __init__(self):
        self.fermeture = None

    def close(self, run_before_unload=None, **_kw):
        self.fermeture = {"run_before_unload": run_before_unload}


class _ContexteAuthentifie:
    """`new_page()`, la garde et l'écoute des pages : un `new_context()` (session perdue) n'existe
    PAS ici. La garde est posée sur le CONTEXTE (une popup n'hérite pas d'une garde de page)."""

    def __init__(self, page_jetable):
        self._jetable, self.pages_ouvertes = page_jetable, 0
        self.gardes, self.ecouteurs, self.annexes = [], [], []
        self.retirees, self.ecouteurs_retires = [], []
        self.unroute_echoue = False
        self.pages = []                 # `context.pages` : pages déjà ouvertes (la persistante)

    def new_page(self):
        self.pages_ouvertes += 1
        return self._jetable

    def route(self, motif, handler):
        assert motif == "**/*"
        self.gardes.append(handler)
        self._jetable.handlers.append(handler)

    def unroute(self, motif, handler=None):
        if self.unroute_echoue:
            raise RuntimeError("unroute en échec")
        self.retirees.append(handler)
        if handler in self._jetable.handlers:
            self._jetable.handlers.remove(handler)

    def on(self, evenement, rappel):
        assert evenement == "page"
        self.ecouteurs.append(rappel)

    def remove_listener(self, evenement, rappel):
        self.ecouteurs_retires.append(rappel)

    def ouvrir_page_annexe(self):
        """Simule `window.open` : une page NOUVELLE du même contexte."""
        annexe = _PageAnnexe()
        self.annexes.append(annexe)
        for rappel in list(self.ecouteurs):
            rappel(annexe)
        return annexe


class _PagePersistante:
    def __init__(self, page_jetable):
        self.context = _ContexteAuthentifie(page_jetable)
        page_jetable.contexte = self.context


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
        # Lot 12, revue : le client Odoo LIT en POST (JSON-RPC) — seule la méthode du corps décide.
        "rpc_read": "fetch('/web/dataset/call_kw/res.users/read',{method:'POST',headers:"
                    "{'Content-Type':'application/json'},body:JSON.stringify({jsonrpc:'2.0',"
                    "method:'call',params:{model:'res.users',method:'read',args:[[1]],kwargs:{}}})});",
        "rpc_write": "fetch('/web/dataset/call_kw/res.users/read',{method:'POST',headers:"
                     "{'Content-Type':'application/json'},body:JSON.stringify({jsonrpc:'2.0',"
                     "method:'call',params:{model:'res.users',method:'write',args:[[1],{}],"
                     "kwargs:{}}})});",
        "session_destroy": "fetch('/web/session/destroy',{method:'POST',headers:"
                           "{'Content-Type':'application/json'},body:'{}'});",
    }

    def log_message(self, *_a):
        pass

    def _authentifie(self):
        return "session=ok" in (self.headers.get("Cookie") or "")

    _PAGE_SELECTS = (
        "<html><body><form>"
        "<select name='pays' onchange=\"var v=document.getElementById('ville');"
        "v.innerHTML=this.value=='be'?'<option value=&quot;&quot;>-</option>"
        "<option value=bruxelles>Bruxelles</option><option value=liege>Liege</option>'"
        ":'<option value=&quot;&quot;>-</option><option value=paris>Paris</option>"
        "<option value=lyon>Lyon</option>'\">"
        "<option value=''>-</option><option value=fr>France</option><option value=be>Belgique"
        "</option></select>"
        "<select name='ville' id='ville'><option value=''>-</option><option value=paris>Paris"
        "</option><option value=lyon>Lyon</option></select>"
        "<select name='type'><option value=''>-</option><option value=a>A</option>"
        "<option value=b>B</option></select>"
        "<input name='code' type='text'></form></body></html>")

    _PAGE_NAVIGUE = (
        "<html><body><form>"
        "<select name='lang' onchange=\"location='/arrivee?l='+this.value\">"
        "<option value=''>-</option><option value=fr>fr</option><option value=en>en</option></select>"
        "<select name='devise'><option value=''>-</option><option value=eur>EUR</option>"
        "<option value=usd>USD</option></select>"
        "<input name='champ_origine' type='text'></form></body></html>")
    lectures: list = []
    popups: list = []
    popup_js = "window.open('/popup?l='+this.value)"

    def _page_popup_select(self):
        return ("<html><body><form>"
                "<select name='lang' onchange=\"" + self.popup_js + "\">"
                "<option value=''>-</option><option value=fr>fr</option><option value=en>en</option>"
                "</select><select name='devise'><option value=''>-</option>"
                "<option value=eur>EUR</option><option value=usd>USD</option></select>"
                "<input name='champ_origine' type='text'></form></body></html>")

    _PAGE_BEACONS = (
        "<html><body><form><input name='champ' type='text'></form><script>"
        "window.addEventListener('pagehide',function(){navigator.sendBeacon('/b_pagehide','x');"
        "fetch('/b_keepalive',{method:'POST',keepalive:true,body:'x'});});"
        "window.addEventListener('unload',function(){navigator.sendBeacon('/b_unload','x');});"
        "window.addEventListener('visibilitychange',function(){if(document.visibilityState==="
        "'hidden'){navigator.sendBeacon('/b_hidden','x');}});</script></body></html>")
    _PAGE_BEACONS_FORMES = (
        "<html><body><form><input name='champ' type='text'></form><script>"
        "'use strict';"
        # une page qui RÉASSIGNE sendBeacon (polyfill enveloppant l'existant) : ne doit pas lever
        "try { const prec = navigator.sendBeacon.bind(navigator);"
        "navigator.sendBeacon = function (u, d) { return prec(u, d); }; }"
        "catch (e) { fetch('/erreur_assign'); }"
        "window.addEventListener('pagehide', function () {"
        "fetch('/k_options', {method: 'POST', keepalive: true, body: 'x'});"
        "fetch(new Request('/k_request', {method: 'POST', keepalive: true, body: 'x'}));"
        "fetch(new Request('/k_init', {method: 'POST', body: 'x'}), {keepalive: true});"
        "Navigator.prototype.sendBeacon.call(navigator, '/k_proto', 'x');"
        "navigator.sendBeacon('/k_ecrase', 'x');"
        "});</script></body></html>")
    _PAGE_OUVRE = ("<html><body><form><input name='champ' type='text'></form><script>"
                   "window.open('/popup?boot=1');</script></body></html>")

    def do_GET(self):
        if self.path.startswith("/erreur_assign"):
            type(self).lectures.append(self.path)
            self.send_response(204)
            self.end_headers()
        elif self.path == "/beacons_formes" and self._authentifie():
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(self._PAGE_BEACONS_FORMES.encode("utf-8"))
        elif self.path == "/beacons" and self._authentifie():
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(self._PAGE_BEACONS.encode("utf-8"))
        elif self.path == "/ouvre_au_chargement" and self._authentifie():
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(self._PAGE_OUVRE.encode("utf-8"))
        elif self.path.startswith("/popup?") and self._authentifie():
            type(self).popups.append(self.path)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<html><body>popup</body></html>")
        elif self.path == "/popup_select" and self._authentifie():
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(self._page_popup_select().encode("utf-8"))
        elif self.path.startswith("/arrivee") and self._authentifie():
            type(self).lectures.append(self.path)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<html><body><input name='champ_arrivee' type='text'></body></html>")
        elif self.path == "/navigue" and self._authentifie():
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(self._PAGE_NAVIGUE.encode("utf-8"))
        elif self.path == "/selects" and self._authentifie():
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(self._PAGE_SELECTS.encode("utf-8"))
        elif self.path == "/form" and self._authentifie():
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
    _Appli.lectures = []
    _Appli.popups = []
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


# ── Garde par MÉTHODE JSON-RPC (faux positif mesuré le 2026-09-24 : POST res.users/read) ────────

class _RequeteRpc:
    def __init__(self, methode=None, url="http://localhost:10017/web/dataset/call_kw/res.users/read",
                 corps="ok", http="POST"):
        self.method, self.url, self._corps, self._m = http, url, corps, methode

    @property
    def post_data_json(self):
        if self._corps == "illisible":
            raise ValueError("corps non JSON")
        return {"jsonrpc": "2.0", "params": {"method": self._m}} if self._m is not None else None


@pytest.mark.parametrize("methode", ["read", "search_read", "search", "search_count",
                                     "name_search", "name_get", "fields_get"])
def test_une_lecture_rpc_en_post_ne_l_interrompt_pas(methode):
    requete = _RequeteRpc(methode)

    assert sonde._est_ecriture_reelle(requete) is False
    route = _Route(requete)
    sonde._garde_reseau([])(route)
    assert route.continuee and not route.abandonnee


@pytest.mark.parametrize("methode", ["write", "create", "unlink", "action_confirm", "web_save",
                                     "onchange", "methode_inconnue", "", None])
def test_toute_autre_methode_rpc_interrompt_comme_avant(methode):
    ecritures: list = []
    route = _Route(_RequeteRpc(methode))

    sonde._garde_reseau(ecritures)(route)

    assert route.abandonnee and not route.continuee and len(ecritures) == 1


def test_un_corps_illisible_ou_un_autre_chemin_reste_une_ecriture():
    assert sonde._est_ecriture_reelle(_RequeteRpc("read", corps="illisible")) is True
    # « read » sur un chemin qui n'est PAS call_kw n'est pas une lecture reconnue.
    assert sonde._est_ecriture_reelle(
        _RequeteRpc("read", url="https://app.test/api/brouillon/read")) is True
    # Le suffixe d'URL ne décide de rien : `/read` dans l'URL mais méthode `write` dans le corps.
    assert sonde._est_ecriture_reelle(_RequeteRpc("write")) is True


# ── Dépendance des selects (revue du lot 12) : indépendant SEULEMENT si observé inchangé ────────

_PAYS = ["", "fr", "be"]
_VILLES_FR = ["", "paris", "lyon"]


def _villes_belges(page):
    page.selects["ville"] = ["", "bruxelles", "liege"]


def test_un_select_dont_les_options_changent_apres_un_autre_select_est_dependant():
    page = _PageJetable({"code": ""}, selects={"pays": list(_PAYS), "ville": list(_VILLES_FR)},
                        au_choix={"pays": _villes_belges}, valide=r"\d*")

    resultat = sonde.sonder_formulaire(_PagePersistante(page), "https://app.test/en/form/1")

    assert resultat["selects"] == {"pays": {"independant": True}, "ville": {"independant": False}}


def test_un_select_dont_les_options_changent_apres_une_saisie_texte_est_dependant():
    page = _PageJetable({"cp": ""}, selects={"ville": list(_VILLES_FR)}, valide=r"\d*",
                        au_remplissage={"cp": lambda p, v: p.selects.update(ville=["", "gand"])})

    resultat = sonde.sonder_formulaire(_PagePersistante(page), "https://app.test/en/form/1")

    assert resultat["selects"] == {"ville": {"independant": False}}


def test_deux_selects_dont_rien_ne_bouge_sont_confirmes_independants():
    page = _PageJetable({"code": ""}, selects={"type": ["", "a", "b"], "pays": list(_PAYS)},
                        valide=r"\d*")

    resultat = sonde.sonder_formulaire(_PagePersistante(page), "https://app.test/en/form/1")

    assert resultat["selects"] == {"type": {"independant": True}, "pays": {"independant": True}}
    assert ("type", "select:b") in page.remplissages


def test_une_observation_incomplete_ne_declare_aucun_select_independant():
    def echoue(_page):
        raise RuntimeError("navigation pendant le changement")

    page = _PageJetable({"code": ""}, selects={"type": ["", "a", "b"], "pays": list(_PAYS)},
                        au_choix={"type": echoue}, valide=r"\d*")

    resultat = sonde.sonder_formulaire(_PagePersistante(page), "https://app.test/en/form/1")

    assert resultat["selects"] == {"type": {"independant": False}, "pays": {"independant": False}}


def test_une_ecriture_pendant_le_changement_de_select_interrompt_et_ne_confirme_rien():
    page = _PageJetable({"code": ""}, selects={"type": ["", "a", "b"], "pays": list(_PAYS)},
                        au_choix={"type": lambda p: [h(_Route(_Requete("POST", "https://app.test/d")))
                                                     for h in p.handlers]}, valide=r"\d*")

    resultat = sonde.sonder_formulaire(_PagePersistante(page), "https://app.test/en/form/1")

    assert resultat["statut"] == "interrompue"
    assert all(not v["independant"] for v in resultat["selects"].values())


# ── /web/session/destroy est une ÉCRITURE (déconnexion), pas du bruit de fond ───────────────────

@pytest.mark.parametrize("chemin", ["/web/session/destroy", "/web/session/logout",
                                    "/web/session/authenticate", "/web/session/change_password"])
def test_une_action_de_session_reste_une_ecriture_a_abandonner(chemin):
    ecritures: list = []
    route = _Route(_Requete("POST", f"https://app.test{chemin}"))

    sonde._garde_reseau(ecritures)(route)

    assert route.abandonnee and not route.continuee and ecritures


@pytest.mark.parametrize("chemin", ["/web/session/check", "/web/session/get_session_info"])
def test_le_battement_de_session_en_lecture_reste_ignore(chemin):
    route = _Route(_Requete("POST", f"https://app.test{chemin}"))

    sonde._garde_reseau([])(route)

    assert route.continuee and not route.abandonnee


def _sonder_en_reel(brouillon, chemin="form"):
    from playwright.sync_api import sync_playwright

    srv = _serveur(brouillon)
    url = f"http://127.0.0.1:{srv.server_port}/{chemin}"
    try:
        with sync_playwright() as p:
            navigateur = p.chromium.launch(headless=True)
            contexte = navigateur.new_context()
            contexte.add_cookies([{"name": "session", "value": "ok", "url": url}])
            resultat = sonde.sonder_formulaire(contexte.new_page(), url)
            navigateur.close()
    finally:
        srv.shutdown()
    return resultat


@pytest.mark.conformance
def test_reel_une_lecture_rpc_en_post_n_interrompt_pas_la_sonde():
    """Le faux positif mesuré le 2026-09-24 (POST res.users/read) : en vrai navigateur, la lecture
    PASSE (le serveur la reçoit) et la sonde va au bout."""
    resultat = _sonder_en_reel("rpc_read")

    assert resultat["statut"] == "ok", resultat
    assert resultat["champs"]["numero_facture1"]["exemple_stable"]
    assert _Appli.ecritures and all("/web/dataset/call_kw/res.users/read" in e
                                    for e in _Appli.ecritures)


@pytest.mark.conformance
@pytest.mark.parametrize("brouillon", ["rpc_write", "session_destroy"])
def test_reel_une_ecriture_rpc_ou_une_deconnexion_interrompt_et_n_atteint_pas_le_serveur(brouillon):
    """Même URL `.../read` mais méthode `write` dans le corps : écriture. `/web/session/destroy` :
    déconnexion, jamais ignorée."""
    resultat = _sonder_en_reel(brouillon)

    assert resultat["statut"] == "interrompue", resultat
    assert _Appli.ecritures == []


@pytest.mark.conformance
def test_reel_pays_ville_sont_detectes_dependants_et_un_select_libre_est_independant():
    resultat = _sonder_en_reel("", chemin="selects")

    assert resultat["statut"] == "ok", resultat
    assert resultat["selects"] == {"pays": {"independant": True}, "ville": {"independant": False},
                                   "type": {"independant": True}}
    assert not _Appli.ecritures


# ── Navigation en GET pendant la sonde (revue du lot 12, point 9) ───────────────────────────────

class _RequeteNavigation(_Requete):
    def is_navigation_request(self):
        return True


def test_une_navigation_pendant_la_sonde_est_abandonnee_et_l_interrompt():
    ecritures: list = []
    route = _Route(_RequeteNavigation("GET", "https://app.test/website/lang/en"))

    sonde._garde_reseau(ecritures)(route)

    assert route.abandonnee and not route.continuee
    assert ecritures[0].startswith(sonde._MARQUE_NAVIGATION)


def test_un_get_qui_n_est_pas_une_navigation_reste_autorise():
    route = _Route(_Requete("GET", "https://app.test/api/lecture"))

    sonde._garde_reseau([])(route)

    assert route.continuee and not route.abandonnee


def test_un_changement_d_url_sans_requete_apres_un_select_interrompt_la_sonde():
    def pousse_l_url(page):
        page.url = "https://app.test/en/autre-page"

    page = _PageJetable({"code": ""}, selects={"type": ["", "a", "b"], "pays": list(_PAYS)},
                        au_choix={"type": pousse_l_url}, valide=r"\d*")

    resultat = sonde.sonder_formulaire(_PagePersistante(page), "https://app.test/en/form/1")

    assert resultat["statut"] == "interrompue" and "navigation" in resultat["raison"]
    assert resultat["champs"] == {}, "aucun champ sondé sur la page d'arrivée"
    assert all(not v["independant"] for v in resultat["selects"].values())


def test_un_simple_changement_de_fragment_n_est_pas_une_navigation():
    def fragment(page):
        page.url = "https://app.test/en/form/1#etape2"

    page = _PageJetable({"code": ""}, selects={"type": ["", "a", "b"], "pays": list(_PAYS)},
                        au_choix={"type": fragment}, valide=r"\d*")

    assert sonde.sonder_formulaire(_PagePersistante(page), "https://app.test/en/form/1")[
        "statut"] == "ok"


@pytest.mark.conformance
def test_reel_un_select_qui_navigue_en_get_est_abandonne_et_aucun_champ_d_arrivee_n_est_lu():
    """`<select onchange="location=…">` : la navigation GET est abandonnée AVANT le serveur (zéro
    lecture reçue) et aucun champ de la page d'arrivée n'est attribué à la route d'origine."""
    resultat = _sonder_en_reel("", chemin="navigue")

    assert resultat["statut"] == "interrompue", resultat
    assert "navigation détectée" in resultat["raison"]
    assert _Appli.lectures == [], "la page d'arrivée n'a jamais été demandée au serveur"
    assert "champ_arrivee" not in resultat["champs"]
    assert resultat["champs"] == {}


def test_un_select_qui_redevient_identique_une_fois_le_champ_vide_est_quand_meme_dependant():
    """Code postal → ville : la ville ne change que tant que le champ contient une valeur ; le
    vidage la restaure. Comparer APRÈS le vidage la ferait passer pour indépendante."""
    def villes_du_code(page, valeur):
        page.selects["ville"] = ["", "gand"] if valeur else list(_VILLES_FR)

    page = _PageJetable({"cp": ""}, selects={"ville": list(_VILLES_FR)}, valide=r"\d*",
                        au_remplissage={"cp": villes_du_code})

    resultat = sonde.sonder_formulaire(_PagePersistante(page), "https://app.test/en/form/1")

    assert page.selects["ville"] == _VILLES_FR, "l'état final est bien revenu à l'identique"
    assert resultat["selects"] == {"ville": {"independant": False}}


def test_un_select_que_la_saisie_texte_ne_touche_jamais_reste_independant():
    page = _PageJetable({"cp": ""}, selects={"ville": list(_VILLES_FR)}, valide=r"\d*")

    assert sonde.sonder_formulaire(_PagePersistante(page), "https://app.test/en/form/1")[
        "selects"] == {"ville": {"independant": True}}


# ── Garde au niveau du CONTEXTE : window.open / target=_blank (mesuré le 2026-09-24) ───────────

def test_la_garde_est_posee_sur_le_contexte_et_retiree_a_la_fin():
    page = _PageJetable({"code": ""}, valide=r"\d*")
    persistante = _PagePersistante(page)

    sonde.sonder_formulaire(persistante, "https://app.test/en/form/1")

    contexte = persistante.context
    assert len(contexte.gardes) == 1 and contexte.retirees == contexte.gardes
    assert contexte.ecouteurs_retires == contexte.ecouteurs and len(contexte.ecouteurs) == 1


def test_une_panne_avant_la_pose_de_la_garde_ne_laisse_rien_a_retirer_et_ne_plante_pas():
    page = _PageJetable({"code": ""}, valide=r"\d*")
    page.goto = lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("page morte"))
    persistante = _PagePersistante(page)

    resultat = sonde.sonder_formulaire(persistante, "https://app.test/en/form/1")

    assert resultat["statut"] == "erreur"
    assert persistante.context.gardes == [], "jamais posée : rien à retirer"
    assert page.fermeture == {"run_before_unload": False}


def test_la_garde_posee_est_retiree_meme_si_la_sonde_echoue_APRES_sa_pose():
    """La panne survient une fois la garde posée (lecture des champs) : elle doit être retirée."""
    page = _PageJetable({"code": ""}, valide=r"\d*")
    evaluer = page.evaluate

    def evaluer_puis_casser(js):
        if js == sonde._JS_CHAMPS:
            raise RuntimeError("page morte apres la pose de la garde")
        return evaluer(js)

    page.evaluate = evaluer_puis_casser
    persistante = _PagePersistante(page)

    resultat = sonde.sonder_formulaire(persistante, "https://app.test/en/form/1")

    contexte = persistante.context
    assert resultat["statut"] == "erreur"
    assert len(contexte.gardes) == 1 and contexte.retirees == contexte.gardes
    assert contexte.ecouteurs_retires == contexte.ecouteurs and len(contexte.ecouteurs) == 1


def test_une_page_ouverte_pendant_la_sonde_l_interrompt_et_est_fermee():
    annexes: list = []

    def popup(page):
        annexes.append(page.contexte.ouvrir_page_annexe())

    page = _PageJetable({"code": ""}, selects={"type": ["", "a", "b"], "pays": list(_PAYS)},
                        au_choix={"type": popup}, valide=r"\d*")

    resultat = sonde.sonder_formulaire(_PagePersistante(page), "https://app.test/en/form/1")

    assert resultat["statut"] == "interrompue" and "navigation" in resultat["raison"]
    assert resultat["champs"] == {}
    assert annexes and all(a.fermeture == {"run_before_unload": False} for a in annexes), (
        "aucune fenêtre orpheline : la page annexe est fermée sans beforeunload")
    assert page.fermeture == {"run_before_unload": False}


@pytest.mark.conformance
@pytest.mark.parametrize("ouverture", ["window.open('/popup?l='+this.value)",
                                       "var a=document.createElement('a');a.href='/popup?l='+"
                                       "this.value;a.target='_blank';document.body.appendChild(a);"
                                       "a.click()"])
def test_reel_window_open_et_target_blank_n_atteignent_pas_le_serveur_et_ne_laissent_rien_ouvert(
        ouverture):
    """Reproduit la mesure du 2026-09-24 : `<select onchange="window.open(…)">` envoyait un GET
    au serveur (statut « ok »). Garde sur le contexte : zéro GET reçu, sonde interrompue, et
    aucune page orpheline dans le contexte à la fin."""
    from playwright.sync_api import sync_playwright

    _Appli.popup_js = ouverture
    srv = _serveur("")
    url = f"http://127.0.0.1:{srv.server_port}/popup_select"
    try:
        with sync_playwright() as p:
            navigateur = p.chromium.launch(headless=True)
            contexte = navigateur.new_context()
            contexte.add_cookies([{"name": "session", "value": "ok", "url": url}])
            page = contexte.new_page()

            resultat = sonde.sonder_formulaire(page, url)
            pages_restantes = len(contexte.pages)
            # La garde a bien été retirée du contexte partagé : la page d'origine navigue à nouveau.
            page.goto(f"http://127.0.0.1:{srv.server_port}/form")
            navigateur.close()
    finally:
        srv.shutdown()

    assert resultat["statut"] == "interrompue", resultat
    assert "navigation détectée" in resultat["raison"]
    assert _Appli.popups == [], "aucun GET de la fenêtre ouverte n'a atteint le serveur"
    assert pages_restantes == 1, "ni la page jetable ni la fenêtre annexe ne sont restées ouvertes"


# ── Fermeture propre : beacons, unroute en échec, pages apparues avant la garde ─────────────────

def test_la_page_jetable_recoit_le_script_de_neutralisation_avant_son_chargement():
    page = _PageJetable({"code": ""}, valide=r"\d*")
    ordre: list = []
    goto, add = page.goto, page.add_init_script
    page.goto = lambda *a, **k: (ordre.append("goto"), goto(*a, **k))[1]
    page.add_init_script = lambda s: (ordre.append("script"), add(s))[1]

    sonde.sonder_formulaire(_PagePersistante(page), "https://app.test/en/form/1")

    assert ordre[:2] == ["script", "goto"], "le script doit précéder tout script de la page"
    assert "sendBeacon" in page.scripts_init[0] and "keepalive" in page.scripts_init[0]


def test_la_garde_devient_inerte_meme_si_unroute_echoue():
    page = _PageJetable({"code": ""}, valide=r"\d*")
    persistante = _PagePersistante(page)
    persistante.context.unroute_echoue = True

    resultat = sonde.sonder_formulaire(persistante, "https://app.test/en/form/1")

    assert resultat["statut"] == "ok"
    (garde,) = persistante.context.gardes
    assert garde in page.handlers, "l'échec d'unroute a bien laissé la garde posée"
    ecriture = _Route(_Requete("POST", "https://app.test/draft"))
    navigation = _Route(_RequeteNavigation("GET", "https://app.test/page-suivante"))
    garde(ecriture)
    garde(navigation)
    assert ecriture.continuee and navigation.continuee
    assert not ecriture.abandonnee and not navigation.abandonnee, (
        "la garde restée sur le contexte partagé ne bloque plus rien")


def test_une_page_apparue_avant_la_garde_est_fermee_a_la_fin():
    """Fenêtre ouverte par le chargement même de la page (avant `context.on("page")`) : elle est
    vue dans `context.pages` mais n'a déclenché aucun évènement."""
    page = _PageJetable({"code": ""}, valide=r"\d*")
    persistante = _PagePersistante(page)
    orpheline = _PageAnnexe()
    contexte = persistante.context
    contexte.pages = [persistante]
    new_page = contexte.new_page

    def new_page_puis_popup():
        jetable = new_page()
        contexte.pages.extend([jetable, orpheline])  # la page jetable et une fenêtre du chargement
        return jetable

    contexte.new_page = new_page_puis_popup

    sonde.sonder_formulaire(persistante, "https://app.test/en/form/1")

    assert orpheline.fermeture == {"run_before_unload": False}


@pytest.mark.conformance
def test_reel_les_beacons_de_fermeture_n_atteignent_pas_le_serveur():
    """Mesuré le 2026-09-24 : sans le script de neutralisation, `pagehide`, `unload` et
    `visibilitychange` (sendBeacon) et un `fetch keepalive` envoyaient 4 POST APRÈS la fermeture."""
    from playwright.sync_api import sync_playwright

    srv = _serveur("")
    url = f"http://127.0.0.1:{srv.server_port}/beacons"
    try:
        with sync_playwright() as p:
            navigateur = p.chromium.launch(headless=True)
            contexte = navigateur.new_context()
            contexte.add_cookies([{"name": "session", "value": "ok", "url": url}])
            page = contexte.new_page()

            resultat = sonde.sonder_formulaire(page, url)
            page.wait_for_timeout(800)  # les requêtes de fermeture partent APRÈS le close()
            navigateur.close()
    finally:
        srv.shutdown()

    assert resultat["statut"] == "ok", resultat
    assert _Appli.ecritures == [], "aucun beacon de fermeture n'a atteint le serveur"


@pytest.mark.conformance
def test_reel_une_garde_dont_unroute_echoue_ne_bloque_plus_la_navigation_suivante():
    """Sans le drapeau, la garde restée sur le contexte partagé abandonnait la navigation de
    l'exploration suivante (`net::ERR_FAILED`)."""
    from playwright.sync_api import sync_playwright

    srv = _serveur("")
    url = f"http://127.0.0.1:{srv.server_port}/form"
    try:
        with sync_playwright() as p:
            navigateur = p.chromium.launch(headless=True)
            contexte = navigateur.new_context()
            contexte.add_cookies([{"name": "session", "value": "ok", "url": url}])
            page = contexte.new_page()
            unroute = contexte.unroute

            def unroute_en_echec(*_a, **_k):
                raise RuntimeError("unroute en échec")

            contexte.unroute = unroute_en_echec
            resultat = sonde.sonder_formulaire(page, url)
            contexte.unroute = unroute

            reponse = page.goto(f"http://127.0.0.1:{srv.server_port}/form")
            statut_http = reponse.status if reponse else None
            navigateur.close()
    finally:
        srv.shutdown()

    assert resultat["statut"] == "ok", resultat
    assert statut_http == 200, "la garde restée posée laisse passer la navigation suivante"


@pytest.mark.conformance
def test_reel_une_fenetre_ouverte_par_le_chargement_meme_de_la_page_est_fermee():
    """`window.open` exécuté au chargement, avant la pose de la garde et de l'écouteur : la page
    n'est ni gardée ni suivie ; le snapshot des pages du contexte la ferme à la fin."""
    from playwright.sync_api import sync_playwright

    srv = _serveur("")
    url = f"http://127.0.0.1:{srv.server_port}/ouvre_au_chargement"
    try:
        with sync_playwright() as p:
            navigateur = p.chromium.launch(headless=True)
            contexte = navigateur.new_context()
            contexte.add_cookies([{"name": "session", "value": "ok", "url": url}])
            page = contexte.new_page()

            resultat = sonde.sonder_formulaire(page, url)
            pages_restantes = len(contexte.pages)
            navigateur.close()
    finally:
        srv.shutdown()

    assert resultat["statut"] != "erreur", resultat
    assert pages_restantes == 1, "ni la page jetable ni la fenêtre du chargement ne sont restées"


def test_le_marqueur_de_fermeture_est_pose_juste_avant_le_close_et_pas_avant():
    """Pendant la sonde les beacons passent (un brouillon reste détecté) ; ils ne sont neutralisés
    qu'une fois le marqueur posé, donc juste avant la fermeture."""
    page = _PageJetable({"code": ""}, valide=r"\d*")
    ordre: list = []
    evaluer, fermer = page.evaluate, page.close

    def evaluer_trace(js):
        if js == sonde._JS_MARQUE_FERMETURE:
            ordre.append("marqueur")
            return None
        return evaluer(js)

    page.evaluate = evaluer_trace
    page.close = lambda **k: (ordre.append("close"), fermer(**k))[1]

    sonde.sonder_formulaire(_PagePersistante(page), "https://app.test/en/form/1")

    assert ordre == ["marqueur", "close"]
    assert "__tpFermeture" in page.scripts_init[0]
    assert "Navigator.prototype" in page.scripts_init[0]
    assert "writable: true" in page.scripts_init[0]


@pytest.mark.conformance
def test_reel_toutes_les_formes_de_fetch_keepalive_et_de_sendbeacon_sont_neutralisees():
    """Mesuré le 2026-09-24 : `fetch(new Request(…, {keepalive:true}))` et
    `Navigator.prototype.sendBeacon.call(navigator, …)` atteignaient le serveur à la fermeture malgré
    la première version du script. Couvre : options directes, `Request` keepalive, options qui
    activent keepalive sur un `Request`, appel par le prototype, et un `sendBeacon` réassigné par la
    page (mode strict : la réassignation ne doit pas lever)."""
    from playwright.sync_api import sync_playwright

    srv = _serveur("")
    url = f"http://127.0.0.1:{srv.server_port}/beacons_formes"
    try:
        with sync_playwright() as p:
            navigateur = p.chromium.launch(headless=True)
            contexte = navigateur.new_context()
            contexte.add_cookies([{"name": "session", "value": "ok", "url": url}])
            page = contexte.new_page()

            resultat = sonde.sonder_formulaire(page, url)
            page.wait_for_timeout(800)
            navigateur.close()
    finally:
        srv.shutdown()

    assert resultat["statut"] == "ok", resultat
    assert "/erreur_assign" not in _Appli.lectures, (
        "réassigner sendBeacon ne doit pas lever (writable: true)")
    assert _Appli.ecritures == [], f"requêtes de fermeture reçues : {_Appli.ecritures}"


def test_une_ecriture_emise_par_le_dernier_vidage_est_interceptee_avant_de_couper_la_garde():
    """Le vidage du champ (`fill("")`) émet un POST que Playwright ne traite qu'à l'attente suivante :
    sans attente avant de rendre la garde inerte, l'écriture passait (`continue_`) sans être
    consignée et le statut restait « ok »."""
    page = _PageJetable({"code": ""}, selects={"type": ["", "a", "b"], "pays": list(_PAYS)},
                        valide=r"\d*",
                        ecritures_differees={"code": ("POST", "https://app.test/draft")})

    resultat = sonde.sonder_formulaire(_PagePersistante(page), "https://app.test/en/form/1")

    assert resultat["statut"] == "interrompue", resultat
    assert "sauvegarde automatique" in resultat["raison"]
    assert page.routes[-1].abandonnee and not page.routes[-1].continuee, (
        "l'écriture a été abandonnée, pas laissée passer")
    assert all(not v["independant"] for v in resultat["selects"].values()), (
        "observation invalidée : aucun select ne reste déclaré indépendant")


def test_sans_ecriture_dans_la_fenetre_finale_le_resultat_est_inchange():
    page = _PageJetable({"code": ""}, selects={"type": ["", "a", "b"], "pays": list(_PAYS)},
                        valide=r"\d*")

    resultat = sonde.sonder_formulaire(_PagePersistante(page), "https://app.test/en/form/1")

    assert resultat["statut"] == "ok"
    assert all(v["independant"] for v in resultat["selects"].values())
