"""§6 — connecteur web générique : couvre ce qui distingue ``GenericWebConnector`` d'Odoo.

La perception UI pure (extraction de formulaire, sonde HTTP) est déjà couverte par
`test_odoo_connector.py` — c'est la MÊME implémentation partagée (`connectors/_web_helpers.py`).
Ici : l'absence de modèle interrogeable (RPC), et la détection de connexion GÉNÉRIQUE (sans
convention d'URL propre à un ERP).
"""

import pytest

from testpilot.connectors.base import Connector
from testpilot.connectors.generic_web import GenericWebConnector


class _FakeChamp:
    def __init__(self):
        self.rempli = None
        self.touche_pressee = None

    def fill(self, value, force=False):
        self.rempli = value

    def press(self, key):
        self.touche_pressee = key


class _FakePage:
    """Page duck-typée : renvoie un champ préparé selon le sélecteur, ou None."""

    def __init__(self, mdp=None, identifiant=None):
        self._mdp = mdp
        self._identifiant = identifiant
        self.attente_reseau_appelee = False

    def query_selector(self, selector):
        if "password" in selector:
            return self._mdp
        if "email" in selector or "text" in selector:
            return self._identifiant
        return None

    def wait_for_load_state(self, *_args, **_kwargs):
        self.attente_reseau_appelee = True


def test_generic_web_connector_satisfait_l_interface():
    conn = GenericWebConnector("http://localhost:9999")
    assert isinstance(conn, Connector)


@pytest.mark.parametrize("methode,args", [
    ("get_schema", ("un_modele",)),
    ("search", ("un_modele", [])),
    ("read", ("un_modele", [1], ["nom"])),
    ("create", ("un_modele", {})),
    ("delete", ("un_modele", [1])),
])
def test_aucune_methode_de_modele_n_est_geree(methode, args):
    """Pas d'API générique de modèle (à la différence d'Odoo) — le refus doit être EXPLICITE,
    jamais un résultat vide qui se ferait passer pour « rien trouvé »."""
    conn = GenericWebConnector("http://localhost:9999")
    with pytest.raises(NotImplementedError):
        getattr(conn, methode)(*args)


def test_discover_route_delegue_a_la_sonde_http_isolee():
    conn = GenericWebConnector("http://localhost:9999")
    conn._http_probe = lambda url: {"url": url, "status": 200, "method": "HEAD", "note": "ok"}
    info = conn.discover_route("/contact/{id}", 3)
    assert info["url"] == "http://localhost:9999/contact/3"
    assert info["status"] == 200


def test_inspect_form_ne_leve_jamais_et_signale_l_erreur():
    conn = GenericWebConnector("http://localhost:9999")
    def _boom():
        raise RuntimeError("navigateur indisponible")
    conn._ensure_page = _boom
    result = conn.inspect_form("/contact")
    assert result["fields"] == []
    assert result["error"]


# ── Détection de connexion GÉNÉRIQUE (sans convention d'URL type Odoo) ────────────────────────

def test_sans_identifiant_ni_mot_de_passe_fournis_aucune_tentative():
    """Rien à saisir : mieux vaut explorer sans connexion que deviner une identité fausse."""
    conn = GenericWebConnector("http://localhost:9999")  # user/password vides par défaut
    page = _FakePage(mdp=_FakeChamp(), identifiant=_FakeChamp())
    conn._tenter_connexion_generique(page)
    assert page._mdp.rempli is None
    assert conn._tentative_connexion_faite is False


def test_aucun_champ_mot_de_passe_sur_la_page_aucune_tentative():
    """Application accessible sans connexion (ou page qui n'en est pas une) : on continue tel
    quel plutôt que de chercher une connexion qui n'existe pas."""
    conn = GenericWebConnector("http://localhost:9999", user="alice", password="s3cret")
    page = _FakePage(mdp=None, identifiant=_FakeChamp())
    conn._tenter_connexion_generique(page)
    assert conn._tentative_connexion_faite is False


def test_mot_de_passe_sans_champ_identifiant_ne_soumet_rien():
    """Un mot de passe seul, sans champ identifiant reconnu, ne doit JAMAIS être soumis à
    l'aveugle — une soumission partielle serait pire qu'aucune tentative."""
    conn = GenericWebConnector("http://localhost:9999", user="alice", password="s3cret")
    champ_mdp = _FakeChamp()
    page = _FakePage(mdp=champ_mdp, identifiant=None)
    conn._tenter_connexion_generique(page)
    assert champ_mdp.rempli is None
    assert conn._tentative_connexion_faite is False


def test_identifiant_et_mot_de_passe_trouves_la_connexion_est_tentee():
    conn = GenericWebConnector("http://localhost:9999", user="alice", password="s3cret")
    champ_mdp, champ_identifiant = _FakeChamp(), _FakeChamp()
    page = _FakePage(mdp=champ_mdp, identifiant=champ_identifiant)
    conn._tenter_connexion_generique(page)
    assert champ_identifiant.rempli == "alice"
    assert champ_mdp.rempli == "s3cret"
    assert champ_mdp.touche_pressee == "Enter"
    assert page.attente_reseau_appelee is True
    assert conn._tentative_connexion_faite is True


def test_from_project_lit_les_colonnes_generiques_du_projet():
    conn = GenericWebConnector.from_project({
        "base_url": "http://intranet.exemple.local", "username": "bob", "password": "pwd",
    })
    assert conn._url == "http://intranet.exemple.local"
    assert conn._user == "bob"
    assert conn._password == "pwd"


def test_from_project_avec_projet_vide_ne_leve_pas():
    conn = GenericWebConnector.from_project(None, url="http://localhost:9999")
    assert conn._url == "http://localhost:9999"
    assert conn._user == ""
