"""§6 — connecteur Odoo : parties pures testables hors-ligne (sans navigateur ni RPC).

On couvre ce qui ne nécessite ni Odoo ni Chromium : l'extraction DOM d'un formulaire
(dont la capture des champs cachés injectés côté serveur), la construction d'URL de sonde,
la sonde HTTP (réseau isolé et surchargé), et la conformité à l'interface ``Connector``.
"""

from testpilot.connectors.base import Connector
from testpilot.connectors.odoo import OdooConnector, build_probe_url, extract_form


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
    assert {"menu": "Générer des équipements", "model": "equipment.order"} in resultat
    # Un seul aller-retour de RÉSOLUTION groupée — pas un appel par action.
    assert sum(1 for a in request.appels if a[0] == "POST") == 1


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
