"""`odoo_login.py::playwright_login` — essai (2026-09-30) : réutilise le mécanisme d'enregistrement
assisté du connecteur `web` générique, À LA DEMANDE, pour un projet Odoo qui en a un
(`context.sequence_connexion`/`context.login_form`). Prouve la DÉLÉGATION et le GARDE-FOU
« jamais un mélange avec la détection codée en dur » — le comportement RÉEL de
`remplir_et_soumettre_formulaire_connexion`/`rejouer_sequence_connexion` est déjà couvert par
leurs propres tests dédiés, jamais reproduit ici.
"""

from __future__ import annotations

import types

from testpilot.connectors import odoo_login


class _PageNeJamaisToucherLesChampsCodesEnDur:
    """Toute méthode utilisée par la détection Odoo codée en dur (`locator`, `get_by_text`,
    `wait_for_url`) lève — preuve que la branche `login_form`/`sequence_connexion` retourne AVANT
    d'atteindre ce code, jamais un mélange des deux chemins."""

    url = "https://odoo.exemple.test/web/login?db=demo"

    def goto(self, *a, **k):
        pass

    def wait_for_load_state(self, *a, **k):
        pass

    def locator(self, *a, **k):
        raise AssertionError("la détection codée en dur ne doit jamais être atteinte ici")

    def get_by_text(self, *a, **k):
        raise AssertionError("la détection codée en dur ne doit jamais être atteinte ici")

    def wait_for_url(self, *a, **k):
        pass  # seule méthode de la détection par défaut réutilisée par la branche login_form


def _contexte(**kw):
    base = dict(page=_PageNeJamaisToucherLesChampsCodesEnDur(), odoo_url="https://odoo.exemple.test",
               odoo_db="demo", odoo_user="admin", odoo_password="s3cret",
               sequence_connexion=[], login_form=None)
    base.update(kw)
    return types.SimpleNamespace(**base)


_LOGIN_FORM = {
    "champ_identifiant": {"role": "textbox", "name": "Identifiant"},
    "champ_mdp": {"role": "textbox", "name": "Mot de passe"},
    "bouton_soumission": {"role": "button", "name": "Se connecter"},
}


def test_avec_login_form_delegue_et_saute_la_detection_codee_en_dur(monkeypatch):
    appels = []
    monkeypatch.setattr(odoo_login, "remplir_et_soumettre_formulaire_connexion",
                        lambda *a, **k: appels.append((a, k)))
    ctx = _contexte(login_form=_LOGIN_FORM)

    odoo_login.playwright_login(ctx)  # ne lève pas -> preuve que le code codé en dur n'a pas tourné

    assert len(appels) == 1
    args, kwargs = appels[0]
    assert args[0] is ctx.page
    assert args[1] == _LOGIN_FORM
    assert args[2:] == ("admin", "s3cret")
    assert kwargs == {"attendre_reseau": False}


def test_sans_login_form_ne_delegue_jamais_a_remplir_et_soumettre(monkeypatch):
    """Régression : un projet SANS formulaire enregistré doit continuer à emprunter la détection
    Odoo codée en dur (jamais testée ici — c'est le rôle de la conformance) — on vérifie seulement
    que la nouvelle branche ne s'active PAS pour ce cas."""
    appels = []
    monkeypatch.setattr(odoo_login, "remplir_et_soumettre_formulaire_connexion",
                        lambda *a, **k: appels.append((a, k)))

    class _PageQuiAccepteLaDetectionParDefaut(_PageNeJamaisToucherLesChampsCodesEnDur):
        def locator(self, *a, **k):
            raise _SortieAttendue

        def get_by_text(self, *a, **k):
            raise _SortieAttendue

    class _SortieAttendue(Exception):
        pass

    ctx = _contexte(page=_PageQuiAccepteLaDetectionParDefaut())

    try:
        odoo_login.playwright_login(ctx)
    except _SortieAttendue:
        pass  # attendu : on A ATTEINT la détection codée en dur, preuve qu'elle n'a pas été sautée

    assert appels == []


def test_falsifiable_la_sequence_de_pre_connexion_est_rejouee_avant_le_formulaire(monkeypatch):
    """Le franchissement d'un écran intercalé enregistré doit se produire AVANT toute détection du
    formulaire — même ordre que le connecteur `web` générique."""
    ordre = []
    monkeypatch.setattr(odoo_login, "rejouer_sequence_connexion",
                        lambda *a, **k: ordre.append("sequence") or True)
    monkeypatch.setattr(odoo_login, "remplir_et_soumettre_formulaire_connexion",
                        lambda *a, **k: ordre.append("formulaire"))
    ctx = _contexte(sequence_connexion=[{"role": "button", "name": "France"}],
                    login_form=_LOGIN_FORM)

    odoo_login.playwright_login(ctx)

    assert ordre == ["sequence", "formulaire"]
