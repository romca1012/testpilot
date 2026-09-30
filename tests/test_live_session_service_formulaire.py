"""`live_session_service.SessionLive` — extension (2026-09-30) : après l'écran de pré-connexion,
3 clics guidés capturent le rôle/nom du champ identifiant, du champ mot de passe et du bouton de
soumission. Test PUR (aucun vrai Chromium, aucun CDP) : `accname.calculer` est monkeypatché, la
page/le CDP sont des doublures minimales — seule la MACHINE À ÉTATS de `SessionLive` est vérifiée
ici. La preuve avec un vrai navigateur vit dans `test_live_session_ws.py` (marqueur `conformance`).
"""

from __future__ import annotations

from testpilot.api.services import live_session_service as svc


class _CDPFactice:
    def __init__(self):
        self.envoyes: list[dict] = []

    def send(self, methode, params=None):
        self.envoyes.append({"methode": methode, "params": params})


class _PageFactice:
    """`_mot_de_passe_visible` appelle `page.locator("input[type='password']")` — jamais utilisé
    directement par `_traiter_clic_formulaire`/`accname.calculer` (monkeypatché), donc peu importe
    ce qu'elle contient vraiment."""

    def locator(self, _selecteur):
        return _LocatorVide()


class _LocatorVide:
    def count(self):
        return 0

    def nth(self, _i):
        raise AssertionError("jamais appelé : count() == 0")


def _session() -> svc.SessionLive:
    session = svc.SessionLive(project={"id": 1}, queue_label="test")
    session._cdp = _CDPFactice()
    return session


def _vider_sortantes(session: svc.SessionLive) -> list[dict]:
    messages = []
    while not session.sortantes.empty():
        messages.append(session.sortantes.get_nowait())
    return messages


def _cliquer(session, page, x, y, monkeypatch, resolu=None, leve=None):
    """Simule un clic entrant en monkeypatchant `accname.calculer` pour ce SEUL appel."""
    def _calculer(_page, _x, _y):
        if leve is not None:
            raise leve
        return resolu
    monkeypatch.setattr(svc.accname, "calculer", _calculer)
    session._traiter_clic(page, {"type": "clic", "x": x, "y": y})


def test_les_3_clics_guides_capturent_dans_l_ordre_identifiant_mdp_bouton(monkeypatch):
    session = _session()
    session._mode_formulaire = True  # comme si `capture_arretee` venait déjà d'avoir lieu
    page = _PageFactice()

    _cliquer(session, page, 10, 10, monkeypatch,
             resolu={"role": "textbox", "name": "E-mail"})
    _cliquer(session, page, 20, 20, monkeypatch,
             resolu={"role": "textbox", "name": "Mot de passe"})
    _cliquer(session, page, 30, 30, monkeypatch,
             resolu={"role": "button", "name": "Se connecter"})

    assert session.login_form == {
        "champ_identifiant": {"role": "textbox", "name": "E-mail"},
        "champ_mdp": {"role": "textbox", "name": "Mot de passe"},
        "bouton_soumission": {"role": "button", "name": "Se connecter"},
    }


def test_les_messages_sortants_annoncent_chaque_champ_puis_l_invite_suivante(monkeypatch):
    session = _session()
    session._mode_formulaire = True
    page = _PageFactice()

    _cliquer(session, page, 10, 10, monkeypatch,
             resolu={"role": "textbox", "name": "E-mail"})
    messages = _vider_sortantes(session)

    assert {"type": "formulaire_connexion_champ_capture", "champ": "champ_identifiant",
            "role": "textbox", "name": "E-mail"} in messages
    assert {"type": "formulaire_connexion_invite", "champ": "champ_mdp"} in messages


def test_falsifiable_un_clic_ambigu_ne_capture_rien_et_ne_fait_pas_avancer(monkeypatch):
    """Sans le correctif, un clic ambigu (aucune résolution) ferait quand même avancer l'index
    (ou pire, capturerait `None`) — ici, il doit être ignoré et laisser la même invite active."""
    session = _session()
    session._mode_formulaire = True
    page = _PageFactice()

    _cliquer(session, page, 10, 10, monkeypatch,
             leve=svc.accname.ElementIntrouvableError("ambigu"))

    messages = _vider_sortantes(session)
    assert any(m["type"] == "clic_ambigu" for m in messages)
    assert not any(m["type"].startswith("formulaire_connexion") for m in messages)
    assert session.login_form is None  # rien capturé, jamais un descripteur partiel


def test_falsifiable_un_4e_clic_apres_completion_n_ecrase_pas_le_bouton(monkeypatch):
    session = _session()
    session._mode_formulaire = True
    page = _PageFactice()
    _cliquer(session, page, 10, 10, monkeypatch, resolu={"role": "textbox", "name": "E-mail"})
    _cliquer(session, page, 20, 20, monkeypatch, resolu={"role": "textbox", "name": "Mdp"})
    _cliquer(session, page, 30, 30, monkeypatch, resolu={"role": "button", "name": "Valider"})
    complet_avant = session.login_form

    _cliquer(session, page, 40, 40, monkeypatch, resolu={"role": "button", "name": "Autre chose"})

    assert session.login_form == complet_avant


def test_login_form_rend_none_si_incomplet(monkeypatch):
    session = _session()
    session._mode_formulaire = True
    page = _PageFactice()

    _cliquer(session, page, 10, 10, monkeypatch, resolu={"role": "textbox", "name": "E-mail"})

    assert session.login_form is None


def test_reinitialiser_etapes_vide_aussi_le_formulaire_en_cours(monkeypatch):
    session = _session()
    session._mode_formulaire = True
    page = _PageFactice()
    _cliquer(session, page, 10, 10, monkeypatch, resolu={"role": "textbox", "name": "E-mail"})
    _cliquer(session, page, 20, 20, monkeypatch, resolu={"role": "textbox", "name": "Mdp"})
    _cliquer(session, page, 30, 30, monkeypatch, resolu={"role": "button", "name": "Valider"})
    assert session.login_form is not None

    session.reinitialiser_etapes()

    assert session.login_form is None
    # Le mode formulaire reste actif : le navigateur réel n'a pas été renavigué en arrière.
    assert session._mode_formulaire is True

    # Et les 3 clics peuvent être refaits depuis le début, proprement.
    _cliquer(session, page, 10, 10, monkeypatch, resolu={"role": "textbox", "name": "E-mail"})
    assert session.login_form is None
    messages = _vider_sortantes(session)
    assert any(m == {"type": "formulaire_connexion_champ_capture", "champ": "champ_identifiant",
                     "role": "textbox", "name": "E-mail"} for m in messages)


def test_un_clic_en_mode_sequence_normal_ne_declenche_pas_le_mode_formulaire(monkeypatch):
    """Régression du chemin historique (sous-lot C) : tant que le mot de passe n'est pas visible,
    un clic reste une étape normale de la séquence de pré-connexion."""
    session = _session()
    page = _PageFactice()  # `_mot_de_passe_visible` -> False (aucun champ mot de passe)

    _cliquer(session, page, 10, 10, monkeypatch, resolu={"role": "button", "name": "France"})

    assert session.etapes == [{"role": "button", "name": "France"}]
    assert session._mode_formulaire is False
    messages = _vider_sortantes(session)
    assert {"type": "etape_capturee", "role": "button", "name": "France"} in messages
    assert not any(m["type"] == "capture_arretee" for m in messages)


def test_falsifiable_formulaire_a_un_seul_ecran_ne_decale_pas_la_sequence_des_3_clics(monkeypatch):
    """Reproduction mesurée sur SauceDemo (2026-09-30, projet 11) : un formulaire à un SEUL écran
    a son mot de passe visible DÈS AVANT le premier clic — sans ce correctif, ce premier clic
    partait à tort dans `_etapes` (écran intercalé), décalant toute la séquence : `champ_identifiant`
    et `champ_mdp` capturaient tous les deux le même élément (le vrai champ mot de passe), et
    `bouton_soumission` restait mal capturé. Ce test échoue si le clic « identifiant » est à
    nouveau routé vers `_etapes` au lieu du formulaire guidé."""
    session = _session()

    class _PageMdpDejaVisible(_PageFactice):
        def locator(self, _selecteur):
            return _LocatorAvecUnChampVisible()

    class _LocatorAvecUnChampVisible:
        def count(self):
            return 1

        def nth(self, _i):
            return self

        def is_visible(self):
            return True

    page = _PageMdpDejaVisible()

    _cliquer(session, page, 10, 10, monkeypatch, resolu={"role": "textbox", "name": "Username"})
    _cliquer(session, page, 20, 20, monkeypatch, resolu={"role": "textbox", "name": "Password"})
    _cliquer(session, page, 30, 30, monkeypatch, resolu={"role": "button", "name": "Login"})

    assert session.etapes == []  # aucun clic ne doit partir dans l'écran intercalé
    assert session.login_form == {
        "champ_identifiant": {"role": "textbox", "name": "Username"},
        "champ_mdp": {"role": "textbox", "name": "Password"},
        "bouton_soumission": {"role": "button", "name": "Login"},
    }


def test_le_mot_de_passe_visible_bascule_en_mode_formulaire_avec_l_invite_initiale(monkeypatch):
    session = _session()

    class _PageAvecMdp(_PageFactice):
        def locator(self, _selecteur):
            return _LocatorAvecUnChampVisible()

    class _LocatorAvecUnChampVisible:
        def count(self):
            return 1

        def nth(self, _i):
            return self

        def is_visible(self):
            return True

    _cliquer(session, _PageAvecMdp(), 10, 10, monkeypatch,
             resolu={"role": "button", "name": "France"})

    assert session._mode_formulaire is True
    messages = _vider_sortantes(session)
    assert any(m == {"type": "capture_arretee", "raison": "mot_de_passe_visible"} for m in messages)
    assert any(m == {"type": "formulaire_connexion_invite", "champ": "champ_identifiant"}
              for m in messages)
