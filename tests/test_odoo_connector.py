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
