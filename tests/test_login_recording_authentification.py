"""`authentifier_selon_la_strategie` rejoue la séquence de connexion confirmée (sous-lot D) AVANT
toute stratégie — sauf `session_injectee`, où l'écran de connexion n'apparaît jamais (le
storage_state fourni a déjà authentifié le contexte).

Comportement Playwright réel de `rejouer_sequence_connexion` elle-même :
`test_rejouer_sequence_connexion.py`. Ici : l'ORDRE et le CÂBLAGE dans `_base_helpers.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
_STEPS_LIB = RACINE / "behave_runtime" / "steps_library"


def _charger_base_helpers():
    sys.path.insert(0, str(_STEPS_LIB))
    import _base_helpers as H
    return H


class _FakePage:
    def __init__(self, *, mot_de_passe_visible: bool):
        self.url = "https://app.example/pre-connexion"
        self._mot_de_passe_visible = mot_de_passe_visible

    def goto(self, url, wait_until=None):
        self.url = url

    def wait_for_load_state(self, state):
        pass


def test_la_sequence_est_rejouee_avant_la_detection_pour_la_strategie_formulaire(monkeypatch):
    H = _charger_base_helpers()
    appels = []
    monkeypatch.setattr(H, "rejouer_sequence_connexion",
                        lambda page, etapes: appels.append(("rejeu", etapes)) or bool(etapes))
    monkeypatch.setattr(H, "tenter_connexion_generique",
                        lambda page, user, password: appels.append(("detection", None)) or False)
    monkeypatch.setattr(H, "_mot_de_passe_visible", lambda page: False)
    monkeypatch.setattr(H, "connexion_reussie", lambda *a, **k: True)

    page = _FakePage(mot_de_passe_visible=False)
    etapes = [{"role": "combobox", "name": "Pays"}]

    H.authentifier_selon_la_strategie(page, strategie=H._auth.FORMULAIRE, web_url="https://app.example",
                                      user="bob", password="s3cret", totp_secret="",
                                      sequence_connexion=etapes)

    assert appels[0] == ("rejeu", etapes), "le rejeu doit précéder toute stratégie"
    assert appels[1][0] == "detection"


def test_session_injectee_ne_rejoue_jamais_la_sequence(monkeypatch):
    """L'écran de connexion n'apparaît jamais avec un storage_state déjà authentifié — rejouer la
    séquence contre une page complètement différente (déjà connectée) risquerait de cliquer sur
    n'importe quoi."""
    H = _charger_base_helpers()
    appels = []
    monkeypatch.setattr(H, "rejouer_sequence_connexion", lambda page, etapes: appels.append("rejeu"))
    monkeypatch.setattr(H, "_mot_de_passe_visible", lambda page: False)

    page = _FakePage(mot_de_passe_visible=False)

    H.authentifier_selon_la_strategie(page, strategie=H._auth.SESSION_INJECTEE, web_url="https://app.example",
                                      user="", password="", totp_secret="",
                                      sequence_connexion=[{"role": "button", "name": "Continuer"}])

    assert appels == [], "session_injectee ne doit jamais rejouer la séquence"


def test_falsifiable_une_sequence_obsolete_leve_precondition_non_remplie(monkeypatch):
    """Preuve que l'obsolescence remonte comme un PRÉREQUIS MANQUANT (→ `blocked`), jamais une
    tentative de connexion malgré tout — c'est le garde-fou de l'étape 8 qui doit traverser
    jusqu'ici, pas seulement rester au niveau du connecteur."""
    H = _charger_base_helpers()
    from testpilot.connectors._web_helpers import SequenceConnexionObsoleteError

    def _rejeu_en_echec(page, etapes):
        raise SequenceConnexionObsoleteError("étape « Continuer » introuvable")

    monkeypatch.setattr(H, "rejouer_sequence_connexion", _rejeu_en_echec)
    appels = []
    monkeypatch.setattr(H, "tenter_connexion_generique",
                        lambda page, user, password: appels.append("detection") or False)

    page = _FakePage(mot_de_passe_visible=False)

    with pytest.raises(H.PreconditionNonRemplieError):
        H.authentifier_selon_la_strategie(page, strategie=H._auth.FORMULAIRE, web_url="https://app.example",
                                          user="bob", password="s3cret", totp_secret="",
                                          sequence_connexion=[{"role": "button", "name": "Continuer"}])

    assert appels == [], "la détection générique n'aurait jamais dû être tentée après un rejeu en échec"


def test_sans_sequence_le_comportement_est_inchange(monkeypatch):
    """Non-régression explicite : `sequence_connexion=None`/absent ne change rien au comportement
    d'avant ce sous-lot — la détection générique tourne exactement comme avant."""
    H = _charger_base_helpers()
    appels = []
    monkeypatch.setattr(H, "rejouer_sequence_connexion",
                        lambda page, etapes: appels.append(etapes))
    monkeypatch.setattr(H, "tenter_connexion_generique", lambda page, user, password: True)
    monkeypatch.setattr(H, "_mot_de_passe_visible", lambda page: True)
    monkeypatch.setattr(H, "connexion_reussie", lambda *a, **k: True)

    page = _FakePage(mot_de_passe_visible=True)

    H.authentifier_selon_la_strategie(page, strategie=H._auth.FORMULAIRE, web_url="https://app.example",
                                      user="bob", password="s3cret", totp_secret="")

    assert appels == [[]], "sans sequence_connexion, rejouer_sequence_connexion reçoit une liste vide"
