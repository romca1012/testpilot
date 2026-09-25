"""§6 — connecteur Odoo : parties pures testables hors-ligne (sans navigateur ni RPC).

On couvre ce qui ne nécessite ni Odoo ni Chromium : l'extraction DOM d'un formulaire
(dont la capture des champs cachés injectés côté serveur), la construction d'URL de sonde,
la sonde HTTP (réseau isolé et surchargé), et la conformité à l'interface ``Connector``.
"""

from testpilot.connectors.base import Connector
from testpilot.connectors.odoo import (
    OdooConnector, _extract_odoo_form_fields, build_probe_url, extract_form,
)


class _FakeEl:
    def __init__(self, attrs):
        self._attrs = attrs

    def get_attribute(self, name):
        return self._attrs.get(name)


class _FakePage:
    """Page duck-typée : renvoie des éléments préparés selon le sélecteur."""

    def __init__(self, controls, form=None, trigger=None):
        self._controls = controls
        self._form = form
        self._trigger = trigger

    def query_selector_all(self, selector):
        return self._controls

    def query_selector(self, selector):
        if "form" in selector:
            return self._form
        if "submit" in selector or "btn-primary" in selector:
            return self._trigger
        return None


def test_extract_form_capture_champs_dont_le_cache_injecte():
    controls = [
        _FakeEl({"name": "description", "type": "text", "required": ""}),
        _FakeEl({"name": "team_id", "type": "hidden"}),          # champ injecté côté serveur
        _FakeEl({"name": "csrf_token", "type": "hidden"}),        # jeton technique → ignoré
        _FakeEl({"id": "_internal", "type": "hidden"}),           # préfixe _ → ignoré
    ]
    form = _FakeEl({"action": "/my/materiel/submit"})
    trigger = _FakeEl({"name": "envoyer"})
    result = extract_form(_FakePage(controls, form=form, trigger=trigger))

    names = [f["name"] for f in result["fields"]]
    assert "description" in names
    assert "team_id" in names          # le champ caché injecté DOIT remonter (cause §5)
    assert "csrf_token" not in names   # jeton ignoré
    assert "_internal" not in names    # préfixe _ ignoré
    # 'required' présent (attribut à vide) → True.
    assert next(f for f in result["fields"] if f["name"] == "description")["required"] is True
    assert next(f for f in result["fields"] if f["name"] == "team_id")["required"] is False


def test_extract_form_detecte_le_mecanisme_de_soumission():
    form = _FakeEl({"action": "/my/materiel/submit"})
    trigger = _FakeEl({"name": "envoyer"})
    result = extract_form(_FakePage([], form=form, trigger=trigger))
    sub = result["submission"]
    assert sub["mechanism"] == "button_click"
    assert sub["endpoint"] == "/my/materiel/submit"
    assert sub["trigger_selector"] == "[name='envoyer']"


def test_build_probe_url_substitue_id_et_absolutise():
    base = "http://localhost:10017"
    assert build_probe_url(base, "/my/materiel/{id}", 42) == "http://localhost:10017/my/materiel/42"
    assert build_probe_url(base, "/my/materiel", None) == "http://localhost:10017/my/materiel"
    # {id} sans échantillon → placeholder retiré proprement.
    assert build_probe_url(base, "/my/materiel/{id}", None) == "http://localhost:10017/my/materiel/"


def test_discover_route_delegue_a_la_sonde_http_isolee():
    conn = OdooConnector("http://localhost:10017", "db", "u", "p")
    conn._http_probe = lambda url: {"url": url, "status": 200, "method": "HEAD", "note": "ok"}
    info = conn.discover_route("/my/materiel/{id}", 7)
    assert info["url"] == "http://localhost:10017/my/materiel/7"
    assert info["status"] == 200
    assert info["method"] == "HEAD"


def test_inspect_form_ne_leve_jamais_et_signale_l_erreur():
    conn = OdooConnector("http://localhost:10017", "db", "u", "p")
    # Navigateur indisponible (simulé) : la perception est best-effort, jamais fatale.
    def _boom():
        raise RuntimeError("navigateur indisponible")
    conn._ensure_page = _boom
    result = conn.inspect_form("/my/materiel")
    assert result["fields"] == []
    assert result["error"]


def test_inspection_refuse_login_a_la_place_de_la_page_demandee():
    class Page:
        url = 'https://target.test/en/web/login'
        def goto(self, *args, **kwargs):
            pass
    conn = OdooConnector('https://target.test', 'db', 'u', 'p')
    conn._ensure_page = lambda: Page()
    result = conn.inspect_form('/web#action=42')
    assert result['fields'] == []
    assert 'Session web absente ou expirée' in result['error']
    conn.disconnect()


def test_echec_authentification_ne_fuit_pas_de_navigateur(monkeypatch):
    from types import SimpleNamespace
    from testpilot.connectors import odoo_login
    import playwright.sync_api
    closed = []
    page = SimpleNamespace(set_default_timeout=lambda _: None)
    browser = SimpleNamespace(new_context=lambda **_contexte: SimpleNamespace(new_page=lambda: page),
                              close=lambda: closed.append('browser'))
    runtime = SimpleNamespace(chromium=SimpleNamespace(launch=lambda **_: browser),
                              stop=lambda: closed.append('runtime'))
    monkeypatch.setattr(playwright.sync_api, 'sync_playwright',
                        lambda: SimpleNamespace(start=lambda: runtime))
    def refused(_):
        raise RuntimeError('session refusée')
    monkeypatch.setattr(odoo_login, 'playwright_login', refused)
    conn = OdooConnector('https://target.test', 'db', 'u', 'p')
    result = conn.inspect_form('/web')
    assert 'session refusée' in result['error']
    assert closed == ['browser', 'runtime'] and conn._page is None
    conn.disconnect()


# ── `/web#` back-office : attendre le rendu client avant d'extraire (Lot 2, 2026-09-23) ──────
#
# Mesuré en conditions réelles (Sapian, cas 128) : `extract_form` juste après `domcontentloaded`
# rendait 0 champ sur un formulaire de création Odoo (`/web#action=...&view_type=form`), alors
# que 3 champs réels y sont bien présents une fois le rendu client (OWL) terminé.

class _PageAvecAttente:
    def __init__(self, url, controls, attend_leve=False, champs_odoo=None):
        self.url = url
        self._controls = controls
        self.appels_wait = []
        self._attend_leve = attend_leve
        self._champs_odoo = champs_odoo if champs_odoo is not None else []

    def goto(self, *args, **kwargs):
        pass

    def wait_for_selector(self, selector, timeout=None):
        self.appels_wait.append(selector)
        if self._attend_leve:
            raise TimeoutError("jamais apparu")

    def query_selector_all(self, selector):
        return self._controls

    def query_selector(self, selector):
        return None

    def evaluate(self, _script):
        # `_extract_odoo_form_fields` (route `/web#`) lit le DOM via UN SEUL `evaluate` — jamais
        # `query_selector_all` (contrairement à `extract_form`, générique, pour une page portail).
        return self._champs_odoo


def test_inspect_form_attend_le_rendu_client_sur_une_url_web_hash():
    page = _PageAvecAttente(
        "https://target.test/web#action=907&model=survey.survey&view_type=form&cids=1", [],
        champs_odoo=[{"name": "title", "tag": "textarea", "type": "text", "required": True,
                     "visible": True, "label": "", "options": []}])
    conn = OdooConnector("https://target.test", "db", "u", "p")
    conn._ensure_page = lambda: page

    result = conn.inspect_form("/web#action=907&model=survey.survey&view_type=form&cids=1")

    assert page.appels_wait == [".o_field_widget"]
    # Le nom STABLE du wrapper (`title`), jamais l'`id` volatil d'un contrôle interne — c'est
    # exactement la différence que `_extract_odoo_form_fields` existe pour faire (Sapian,
    # 2026-09-23, cas 127 : `title_0` observé à la génération ne correspondait à rien à
    # l'exécution).
    assert [f["name"] for f in result["fields"]] == ["title"]


def test_inspect_form_n_attend_rien_sur_une_page_portail_ordinaire():
    """Comportement STRICTEMENT inchangé pour toute page déjà servie complète côté serveur —
    une page portail n'a jamais de `.o_field_widget` : y attendre coûterait du temps pour rien."""
    page = _PageAvecAttente("https://target.test/myservices",
                            [_FakeEl({"name": "sujet", "type": "text"})])
    conn = OdooConnector("https://target.test", "db", "u", "p")
    conn._ensure_page = lambda: page

    result = conn.inspect_form("/myservices")

    assert page.appels_wait == []
    assert [f["name"] for f in result["fields"]] == ["sujet"]


def test_inspect_form_survit_si_le_widget_n_apparait_jamais():
    """Best-effort : un formulaire réellement sans champ (ou une vue non-formulaire) reste un
    résultat légitime — l'inspection ne doit jamais échouer À CAUSE de l'attente elle-même."""
    page = _PageAvecAttente("https://target.test/web#action=1&view_type=kanban", [],
                            attend_leve=True)
    conn = OdooConnector("https://target.test", "db", "u", "p")
    conn._ensure_page = lambda: page

    result = conn.inspect_form("/web#action=1&view_type=kanban")

    assert result["error"] == ""
    assert result["fields"] == []


def test_extract_odoo_form_fields_enveloppe_le_resultat_du_dom():
    """`_extract_odoo_form_fields` délègue TOUTE la lecture DOM à un unique `evaluate` (le
    sélecteur `.o_field_widget[name]` lui-même n'est vérifiable qu'en conditions réelles,
    documenté et vérifié manuellement — voir l'en-tête du module) ; ce test verrouille seulement
    le contrat d'enveloppe : champs relayés tels quels, url/langue renseignées, aucune soumission
    inventée (Odoo sauvegarde via un clic, jamais un `<form action=...>`)."""
    class _PageOdoo:
        url = "https://target.test/web#action=1&model=x&view_type=form"

        def evaluate(self, _script):
            return [{"name": "title", "tag": "textarea", "type": "text", "required": True,
                    "visible": True, "label": "", "options": []}]

    result = _extract_odoo_form_fields(_PageOdoo())

    assert result["fields"] == [{"name": "title", "tag": "textarea", "type": "text",
                                 "required": True, "visible": True, "label": "", "options": []}]
    assert result["submission"] == {}
    assert result["url"] == "https://target.test/web#action=1&model=x&view_type=form"


def test_odoo_connector_satisfait_l_interface():
    # Toutes les méthodes abstraites sont implémentées → instanciable.
    conn = OdooConnector("http://localhost:10017", "db", "u", "p")
    assert isinstance(conn, Connector)


def test_from_config_cable_les_valeurs_par_defaut():
    conn = OdooConnector.from_config()
    assert conn._url and conn._database and conn._user


# ── discover_menus — découverte des modèles back-office par énumération de menus ──────────────
#
# Formes JSON reprises TELLES QUE MESURÉES en direct sur l'instance Sapian (2026-09-18) : le web
# client Odoo construit son propre arbre de menus déjà filtré par les droits du compte, via
# `GET /web/webclient/load_menus/<jetable>` — c'est ce qui a révélé « Parc IT »
# (equipment.order / equipment.assignation.order / maintenance.equipment), invisible au crawl.

class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _FakeRequestContext:
    """Reprend `page.request` (API Playwright) : `.get`/`.post` renvoient un objet `.json()`."""

    def __init__(self, menus_payload, actions_payload):
        self._menus_payload = menus_payload
        self._actions_payload = actions_payload
        self.appels = []

    def get(self, url):
        self.appels.append(("GET", url))
        return _FakeResponse(self._menus_payload)

    def post(self, url, data=None, headers=None):
        self.appels.append(("POST", url, data))
        return _FakeResponse(self._actions_payload)


class _FakePageAvecRequest:
    def __init__(self, request):
        self.request = request


def test_discover_menus_resout_les_modeles_reels_depuis_les_menus():
    menus = {
        "688": {"id": 688, "name": "Générer des équipements", "actionID": 966,
                "actionModel": "ir.actions.act_window"},
        "689": {"id": 689, "name": "Affectation d'équipements", "actionID": 968,
                "actionModel": "ir.actions.act_window"},
        "740": {"id": 740, "name": "Équipements", "actionID": 983,
                "actionModel": "ir.actions.act_window"},
        # bruit à ignorer : sans actionModel act_window, ou sans actionID.
        "1": {"id": 1, "name": "Séparateur", "actionID": False, "actionModel": False},
        "2": {"id": 2, "name": "Serveur", "actionID": 12, "actionModel": "ir.actions.server"},
    }
    actions = {"jsonrpc": "2.0", "id": None, "result": [
        {"id": 966, "res_model": "equipment.order"},
        {"id": 968, "res_model": "equipment.assignation.order"},
        {"id": 983, "res_model": "maintenance.equipment"},
    ]}
    request = _FakeRequestContext(menus, actions)
    conn = OdooConnector("http://sapian.local", "db", "u", "p")

    resultat = conn.discover_menus(_FakePageAvecRequest(request))

    modeles = {r["model"] for r in resultat}
    assert modeles == {"equipment.order", "equipment.assignation.order", "maintenance.equipment"}
    assert {"menu": "Générer des équipements", "model": "equipment.order",
           "action_id": 966} in resultat
    # Un seul aller-retour de RÉSOLUTION groupée — pas un appel par action.
    assert sum(1 for a in request.appels if a[0] == "POST") == 1


def test_discover_menus_conserve_l_action_id_pour_le_formulaire_de_creation():
    """Lot 2 du plan de fiabilisation (2026-09-23) : `action_id` permet de construire l'URL du
    formulaire de CRÉATION (`.../web#action=<id>&model=<model>&view_type=form&cids=1`, vérifiée
    en conditions réelles sur Sapian) sans jamais naviguer par le menu — c'est ce qui manquait
    pour qu'`inspect_page_form` observe le vrai formulaire avant que le Gherkin ne soit écrit."""
    menus = {"688": {"id": 688, "name": "Générer des équipements", "actionID": 966,
                     "actionModel": "ir.actions.act_window"}}
    actions = {"result": [{"id": 966, "res_model": "equipment.order"}]}
    request = _FakeRequestContext(menus, actions)
    conn = OdooConnector("http://sapian.local", "db", "u", "p")

    resultat = conn.discover_menus(_FakePageAvecRequest(request))

    assert resultat[0]["action_id"] == 966


def test_discover_menus_ne_leve_jamais_si_le_reseau_echoue():
    class _RequestQuiExplose:
        def get(self, url):
            raise RuntimeError("session expirée")

    conn = OdooConnector("http://sapian.local", "db", "u", "p")
    resultat = conn.discover_menus(_FakePageAvecRequest(_RequestQuiExplose()))
    assert resultat == []


def test_discover_menus_rend_vide_sans_action_act_window():
    menus = {"1": {"id": 1, "name": "Serveur", "actionID": 12, "actionModel": "ir.actions.server"}}
    request = _FakeRequestContext(menus, {"result": []})
    conn = OdooConnector("http://sapian.local", "db", "u", "p")
    assert conn.discover_menus(_FakePageAvecRequest(request)) == []


def test_discover_menus_est_le_defaut_vide_sur_l_interface_de_base():
    """Un connecteur qui n'a pas ce mécanisme (défaut de `Connector`) ne casse rien — best
    effort, comme partout ailleurs dans ce dépôt."""
    from testpilot.connectors.generic_web import GenericWebConnector
    assert GenericWebConnector(url="http://app.local").discover_menus(object()) == []


def test_discover_menus_conserve_les_chemins_et_les_feuilles_homonymes():
    menus = {
        'root': {'children': [1, 2]},
        '1': {'name': 'Assistance', 'children': [3]},
        '2': {'name': 'Ventes', 'children': [4]},
        '3': {'name': 'Tickets', 'actionID': 10, 'actionModel': 'ir.actions.act_window'},
        '4': {'name': 'Tickets', 'actionID': 10, 'actionModel': 'ir.actions.act_window'},
    }
    actions = {'result': [{'id': 10, 'res_model': 'helpdesk.ticket'}]}
    request = _FakeRequestContext(menus, actions)
    conn = OdooConnector('http://sapian.local', 'db', 'u', 'p')
    result = conn.discover_menus(_FakePageAvecRequest(request))
    assert {r['menu_path'] for r in result} == {'Assistance / Tickets', 'Ventes / Tickets'}
    assert all(r['menu'] == 'Tickets' for r in result)
    from types import SimpleNamespace

    from testpilot.generation.prompt import _section_modeles_backoffice
    from testpilot.generation.smoke_check import smoke_check

    modele = {'modeles_backoffice': result}
    prompt = _section_modeles_backoffice(
        SimpleNamespace(module_name='assistance', models=['helpdesk.ticket']), modele)
    assert 'chemin mesuré « Assistance / Tickets »' in prompt
    assert smoke_check('Quand je navigue vers le menu Odoo "Assistance / Tickets"',
                       modele=modele) == []
