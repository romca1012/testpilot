"""Câblage du rejeu de la séquence de connexion (sous-lot D) dans `GenericWebConnector` —
`crawl_relogin_hook` (exploration) et `_tenter_connexion_generique` (perception UI, génération).

Logique de rejeu elle-même (ordre, garde-fou, message) : `test_rejouer_sequence_connexion.py`.
Ici : la séquence est bien LUE depuis le projet et REJOUÉE AVANT la détection générique, sur les
DEUX points d'appel — jamais à sa place.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import testpilot.connectors.generic_web as gw
from testpilot.connectors.generic_web import GenericWebConnector

RACINE = Path(__file__).resolve().parent.parent


def test_from_project_lit_la_sequence_connexion_du_projet():
    etapes = [{"role": "combobox", "name": "Pays"}]
    conn = GenericWebConnector.from_project({
        "base_url": "http://intranet.exemple.local", "sequence_connexion": etapes,
    })
    assert conn._sequence_connexion == etapes


def test_from_project_sans_sequence_rend_une_liste_vide():
    conn = GenericWebConnector.from_project({"base_url": "http://intranet.exemple.local"})
    assert conn._sequence_connexion == []


def test_tenter_connexion_generique_rejoue_la_sequence_avant_la_detection(monkeypatch):
    appels: list[str] = []
    monkeypatch.setattr(gw, "rejouer_sequence_connexion",
                        lambda page, etapes: appels.append("rejeu") or bool(etapes))
    monkeypatch.setattr(gw, "tenter_connexion_generique",
                        lambda page, user, password: appels.append("detection") or True)

    conn = GenericWebConnector(url="http://app.local", user="bob", password="secret",
                               sequence_connexion=[{"role": "button", "name": "Continuer"}])
    conn._tenter_connexion_generique(page=object())

    assert appels == ["rejeu", "detection"], "le rejeu doit précéder la détection, jamais l'inverse"
    assert conn._tentative_connexion_faite is True


def test_crawl_relogin_hook_rejoue_la_sequence_avant_la_detection(monkeypatch):
    sys.path.insert(0, str(RACINE / "scripts"))
    appels: list[str] = []
    monkeypatch.setattr(gw, "rejouer_sequence_connexion",
                        lambda page, etapes: appels.append("rejeu") or bool(etapes))
    monkeypatch.setattr(gw, "tenter_connexion_generique",
                        lambda page, user, password: appels.append("detection") or True)

    class _PageConnexion:
        url = "http://app.local/login"

        def goto(self, _url, **_k):
            pass

        def wait_for_load_state(self, *_a, **_k):
            pass

        # Pas de `.evaluate` : la mesure de la page échoue proprement (best-effort), sans
        # perturber ce test — il ne porte que sur l'ORDRE rejeu/détection.

    conn = GenericWebConnector(url="http://app.local", user="bob", password="secret",
                               sequence_connexion=[{"role": "button", "name": "Continuer"}])
    ctx = types.SimpleNamespace(page=_PageConnexion())

    conn.crawl_relogin_hook()(ctx)

    assert appels == ["rejeu", "detection"], "le rejeu doit précéder la détection, jamais l'inverse"


def test_falsifiable_une_sequence_obsolete_arrete_net_sans_tenter_la_detection(monkeypatch):
    """Preuve que le garde-fou de l'étape 8 (jamais un repli silencieux) traverse bien jusqu'au
    connecteur : `SequenceConnexionObsoleteError` doit se propager, la détection générique ne
    doit JAMAIS être tentée après un rejeu en échec."""
    import pytest

    from testpilot.connectors._web_helpers import SequenceConnexionObsoleteError

    appels: list[str] = []

    def _rejeu_en_echec(page, etapes):
        raise SequenceConnexionObsoleteError("étape « Continuer » introuvable")

    monkeypatch.setattr(gw, "rejouer_sequence_connexion", _rejeu_en_echec)
    monkeypatch.setattr(gw, "tenter_connexion_generique",
                        lambda page, user, password: appels.append("detection") or True)

    conn = GenericWebConnector(url="http://app.local", user="bob", password="secret",
                               sequence_connexion=[{"role": "button", "name": "Continuer"}])

    with pytest.raises(SequenceConnexionObsoleteError):
        conn._tenter_connexion_generique(page=object())

    assert appels == [], "la détection générique n'aurait jamais dû être tentée après un rejeu en échec"
