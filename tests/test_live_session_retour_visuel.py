"""Session en direct — deux défauts mesurés le 2026-10-07 sur la page de connexion SSO du portail
d'intégration Odoo (« il faut cliquer deux fois », « aucun signal que mon clic est bon ») :

1. un clic sur un élément sans (rôle, nom) rejouable (bloc dépliant `<summary>`, texte nu) partait à
   la page mais n'était pas retenu, SANS le moindre message ;
2. la session se déclarait prête dès l'événement `load`, pendant que le JavaScript de la page
   initialisait encore son formulaire : un premier clic y était annulé.

Test PUR (doublures de page/CDP, `accname.calculer` monkeypatché) : seule la logique de
`SessionLive` est vérifiée. La preuve en vrai navigateur vit dans `test_live_session_ws.py`.
"""

from __future__ import annotations

import threading

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from testpilot.api.services import live_session_service as svc


class _CDPFactice:
    def __init__(self):
        self.envoyes: list[dict] = []

    def on(self, *_a, **_kw):
        pass

    def send(self, methode, params=None):
        self.envoyes.append({"methode": methode, "params": params})


class _LocatorVide:
    def count(self):
        return 0


class _PageFactice:
    def locator(self, _selecteur):
        return _LocatorVide()


def _session() -> svc.SessionLive:
    session = svc.SessionLive(project={"id": 1}, queue_label="test")
    session._cdp = _CDPFactice()
    return session


def _messages(session) -> list[dict]:
    sortis = []
    while not session.sortantes.empty():
        sortis.append(session.sortantes.get_nowait())
    return sortis


def _cliquer(session, monkeypatch, resolu):
    monkeypatch.setattr(svc.accname, "calculer", lambda _p, _x, _y: resolu)
    session._traiter_clic(_PageFactice(), {"type": "clic", "x": 10, "y": 20})


def test_un_clic_sans_role_rejouable_est_envoye_mais_signale_comme_non_enregistre(monkeypatch):
    session = _session()

    _cliquer(session, monkeypatch, resolu=None)

    assert {"type": "clic_non_enregistre", "raison": "element_non_reconnu"} in _messages(session)
    assert session.etapes == []  # jamais retenu en silence…
    assert [e["methode"] for e in session._cdp.envoyes] == [
        "Input.dispatchMouseEvent", "Input.dispatchMouseEvent"]  # …mais le clic est bien parti


def test_un_clic_reconnu_n_emet_pas_de_signal_de_clic_non_enregistre(monkeypatch):
    """Falsifiabilité inverse : le signal ne doit pas devenir systématique."""
    session = _session()

    _cliquer(session, monkeypatch, resolu={"role": "button", "name": "Se connecter"})

    types = [m["type"] for m in _messages(session)]
    assert "clic_non_enregistre" not in types
    assert "etape_capturee" in types


def test_le_signal_vaut_aussi_pendant_les_trois_clics_guides_du_formulaire(monkeypatch):
    session = _session()
    session._capture_active = False
    session._mode_formulaire = True

    _cliquer(session, monkeypatch, resolu=None)

    assert {"type": "clic_non_enregistre", "raison": "element_non_reconnu"} in _messages(session)


# ── Stabilisation de la page avant d'ouvrir la session ─────────────────────────────────────────


class _PageDemarrage:
    """Page factice pour `_piloter` : journalise l'ordre des appels."""

    def __init__(self, journal: list[str], stabilisation_leve: bool = False):
        self._journal = journal
        self._leve = stabilisation_leve
        self.url = "https://exemple.test/"

    def goto(self, *_a, **_kw):
        self._journal.append("goto")

    def wait_for_load_state(self, etat, timeout=None):
        self._journal.append(f"stabilisation:{etat}:{timeout}")
        if self._leve:
            raise PlaywrightTimeoutError("networkidle jamais atteint")

    def screenshot(self, **_kw):
        self._journal.append("capture_initiale")
        return b"jpeg"


class _ContexteFactice:
    def __init__(self, page):
        self._page = page

    def new_page(self):
        return self._page

    def new_cdp_session(self, _page):
        return _CDPFactice()

    def close(self):
        pass


class _NavigateurFactice:
    def __init__(self, page):
        self._page = page

    def new_context(self, **_kw):
        return _ContexteFactice(self._page)


def _piloter_puis_fermer(session, page):
    fin = threading.Thread(target=session._piloter, args=(_NavigateurFactice(page),), daemon=True)
    fin.start()
    assert session.pret.wait(5), "la session ne s'est jamais déclarée prête"
    session.demander_fermeture()
    fin.join(5)


def test_la_session_attend_que_la_page_se_stabilise_avant_d_etre_prete():
    journal: list[str] = []
    session = _session()
    session._project = {"id": 1, "base_url": "https://exemple.test/"}

    _piloter_puis_fermer(session, _PageDemarrage(journal))

    assert journal.index("goto") < journal.index(f"stabilisation:networkidle:{svc._ATTENTE_STABILISATION_MS}") \
        < journal.index("capture_initiale")


def test_une_page_qui_n_atteint_jamais_networkidle_n_empeche_pas_la_session_de_demarrer():
    """Odoo (long-polling) n'est jamais « idle » : l'attente est bornée et son échec est avalé."""
    journal: list[str] = []
    session = _session()
    session._project = {"id": 1, "base_url": "https://exemple.test/"}

    _piloter_puis_fermer(session, _PageDemarrage(journal, stabilisation_leve=True))

    assert "capture_initiale" in journal


def test_un_clic_ambigu_n_emet_pas_aussi_un_clic_non_enregistre(monkeypatch):
    """Deux messages contradictoires pour un même clic (« plusieurs éléments » ET « aucun nom ») :
    l'ambiguïté est dite seule."""
    session = _session()

    def _ambigu(_p, _x, _y):
        raise svc.accname.ElementIntrouvableError("2 éléments identiques")

    monkeypatch.setattr(svc.accname, "calculer", _ambigu)
    session._traiter_clic(_PageFactice(), {"type": "clic", "x": 10, "y": 20})

    types = [m["type"] for m in _messages(session)]
    assert "clic_ambigu" in types
    assert "clic_non_enregistre" not in types
    assert len(session._cdp.envoyes) == 2  # le clic est parti quand même


def test_un_bloc_depliant_n_est_jamais_range_dans_les_trois_clics_du_formulaire(monkeypatch):
    """Revue 2026-10-07 : un jeton `summary` rangé dans `champ_identifiant`/`champ_mdp`/
    `bouton_soumission` serait confirmé comme « formulaire complet » puis échouerait à CHAQUE rejeu
    (ces emplacements passent par `get_by_role`). Le clic part, mais n'est pas retenu."""
    session = _session()
    session._capture_active = False
    session._mode_formulaire = True

    _cliquer(session, monkeypatch, resolu={"role": "summary", "name": "Options"})

    assert session.login_form is None and session._login_form == {}
    types = [m["type"] for m in _messages(session)]
    assert "clic_non_enregistre" in types
    assert "formulaire_connexion_champ_capture" not in types
    assert len(session._cdp.envoyes) == 2  # le clic est bien parti


def test_un_bloc_depliant_reste_une_etape_de_pre_connexion_valide(monkeypatch):
    session = _session()

    _cliquer(session, monkeypatch, resolu={"role": "summary", "name": "Connexion externe par email"})

    assert session.etapes == [{"role": "summary", "name": "Connexion externe par email"}]
