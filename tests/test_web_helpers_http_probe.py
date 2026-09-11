"""`_web_helpers.http_probe` — le repli HEAD→GET (bug SauceDemo, 2026-09-11).

⚠️ Le vrai bug qui a atteint `/dev` : la branche `HTTPError` rendait immédiatement dès le HEAD
sans jamais essayer le GET que le nom de la fonction promet. Beaucoup de serveurs (WAF, certains
hébergeurs statiques) répondent 405 « Method Not Allowed » à un HEAD tout en servant le GET
correspondant sans problème — `discover_route` (outil LLM de la passe technique, §6 : ce qu'il
rapporte doit être un FAIT MESURÉ) rapportait alors une route comme cassée à tort.

Ces tests simulent `urllib.request.urlopen` (aucun réseau réel) pour isoler la logique de repli
elle-même, plutôt que de dépendre d'un vrai serveur qui pourrait changer de comportement demain.
"""

from __future__ import annotations

import urllib.error

from testpilot.connectors._web_helpers import http_probe


class _FauxeReponse:
    def __init__(self, status: int):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


def test_head_405_retombe_sur_get_200():
    """⚠️ Le cœur du bug : un WAF/hébergeur qui refuse HEAD mais sert GET ne doit JAMAIS être
    rapporté comme une route cassée — le repli doit aboutir sur le GET qui, lui, fonctionne."""
    appels = []

    def _faux_urlopen(req, timeout=10):
        appels.append(req.get_method())
        if req.get_method() == "HEAD":
            raise urllib.error.HTTPError(req.full_url, 405, "Method Not Allowed", {}, None)
        return _FauxeReponse(200)

    import testpilot.connectors._web_helpers as mod
    mod.urllib.request.urlopen = _faux_urlopen
    try:
        info = http_probe("http://app.local/produit")
    finally:
        import urllib.request as ur
        mod.urllib.request.urlopen = ur.urlopen

    assert appels == ["HEAD", "GET"], "le GET doit être tenté après l'échec du HEAD"
    assert info == {"url": "http://app.local/produit", "status": 200, "method": "GET",
                    "note": "accessible"}


def test_head_et_get_en_echec_rapporte_le_dernier_essai():
    """Une route VRAIMENT absente (404 sur les deux méthodes) doit rester un échec — le repli ne
    doit jamais transformer un vrai 404 en faux succès."""
    def _faux_urlopen(req, timeout=10):
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)

    import testpilot.connectors._web_helpers as mod
    mod.urllib.request.urlopen = _faux_urlopen
    try:
        info = http_probe("http://app.local/inexistant")
    finally:
        import urllib.request as ur
        mod.urllib.request.urlopen = ur.urlopen

    assert info == {"url": "http://app.local/inexistant", "status": 404, "method": "GET",
                    "note": "Not Found"}


def test_head_ok_ne_tente_jamais_le_get():
    """GARDE NÉGATIVE : un HEAD qui aboutit ne doit PAS déclencher une requête GET superflue."""
    appels = []

    def _faux_urlopen(req, timeout=10):
        appels.append(req.get_method())
        return _FauxeReponse(200)

    import testpilot.connectors._web_helpers as mod
    mod.urllib.request.urlopen = _faux_urlopen
    try:
        info = http_probe("http://app.local/")
    finally:
        import urllib.request as ur
        mod.urllib.request.urlopen = ur.urlopen

    assert appels == ["HEAD"]
    assert info["status"] == 200 and info["method"] == "HEAD"


def test_injoignable_sur_les_deux_methodes_garde_le_comportement_historique():
    """GARDE NÉGATIVE : le repli pour une panne réseau (pas un code HTTP) fonctionnait déjà —
    ce test fige ce comportement pour qu'un futur changement ne le casse pas au passage."""
    def _faux_urlopen(req, timeout=10):
        raise OSError("connexion refusée")

    import testpilot.connectors._web_helpers as mod
    mod.urllib.request.urlopen = _faux_urlopen
    try:
        info = http_probe("http://app.local/hs")
    finally:
        import urllib.request as ur
        mod.urllib.request.urlopen = ur.urlopen

    assert info["status"] == 0 and info["method"] == "GET"
    assert "injoignable" in info["note"]
