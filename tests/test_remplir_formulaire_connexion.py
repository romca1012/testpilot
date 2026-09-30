"""`remplir_et_soumettre_formulaire_connexion` — extension du lot « Enregistrement assisté du
chemin de connexion » (2026-09-30) : remplit et soumet le formulaire de connexion via les
rôles/noms ENREGISTRÉS (3 clics guidés), jamais la détection générique par balayage du DOM. Pages
factices (même motif que `test_rejouer_sequence_connexion.py`) — la preuve avec un vrai Chromium
vit dans `test_login_recording_rejeu_reel.py`.
"""

from __future__ import annotations

import pytest

from testpilot.connectors._web_helpers import (
    FormulaireConnexionObsoleteError,
    remplir_et_soumettre_formulaire_connexion,
    tenter_connexion_et_lire_resultat,
)

_LOGIN_FORM = {
    "champ_identifiant": {"role": "textbox", "name": "E-mail"},
    "champ_mdp": {"role": "textbox", "name": "Mot de passe"},
    "bouton_soumission": {"role": "button", "name": "Se connecter"},
}


class _FakeLocator:
    def __init__(self, *, existe: bool = True, ambigu: bool = False):
        self._existe = existe
        self._ambigu = ambigu
        self.rempli: str | None = None
        self.clique = False

    def _verifier(self):
        if not self._existe:
            raise TimeoutError("élément introuvable dans le délai imparti")
        if self._ambigu:
            raise Exception("strict mode violation: locator resolved to 2 elements")

    def fill(self, valeur, timeout=None):
        self._verifier()
        self.rempli = valeur

    def click(self, timeout=None):
        self._verifier()
        self.clique = True


class _FakePage:
    """Voir `_FakePage` de `test_rejouer_sequence_connexion.py` : même motif, lookup exact par
    tuple (role, name), `exact=True` obligatoire."""

    def __init__(self, resultats: dict[tuple[str, str], _FakeLocator]):
        self._resultats = resultats
        self.url = "https://exemple.test/login"
        self.attente_reseau_appelee = False

    def get_by_role(self, role, name=None, exact=False):
        assert exact is True, "doit toujours appeler exact=True"
        return self._resultats.get((role, name), _FakeLocator(existe=False))

    def wait_for_load_state(self, state):
        self.attente_reseau_appelee = True

    def wait_for_timeout(self, _ms):
        pass  # attente post-connexion bornée (voir `_attendre_confirmation_post_connexion`)

    def query_selector(self, _selecteur):
        return None  # comportement par défaut : formulaire disparu, connexion « confirmée »

    def locator(self, _selecteur):
        # `tenter_connexion_et_lire_resultat` lit un message d'erreur affiché après soumission
        # (`lire_message_erreur_visible`) — aucun ici, page factice sans bannière d'erreur.
        return _LocatorVide()


class _LocatorVide:
    def count(self):
        return 0


def _page_complete():
    identifiant = _FakeLocator()
    mdp = _FakeLocator()
    bouton = _FakeLocator()
    page = _FakePage({
        ("textbox", "E-mail"): identifiant,
        ("textbox", "Mot de passe"): mdp,
        ("button", "Se connecter"): bouton,
    })
    return page, identifiant, mdp, bouton


def test_remplit_les_2_champs_puis_clique_le_bouton_et_attend_le_reseau():
    page, identifiant, mdp, bouton = _page_complete()

    remplir_et_soumettre_formulaire_connexion(page, _LOGIN_FORM, "sidi@exemple.test", "s3cret")

    assert identifiant.rempli == "sidi@exemple.test"
    assert mdp.rempli == "s3cret"
    assert bouton.clique is True
    assert page.attente_reseau_appelee is True


class _FakePageSPA(_FakePage):
    """Reproduit la mesure faite sur `yros` (2026-09-30) : la connexion répond par `fetch`/XHR
    puis redirige côté client (History API) — `wait_for_load_state("networkidle")` se résout
    SANS AUCUNE navigation à attendre, la vraie redirection n'arrive que quelques instants plus
    tard. `query_selector("input[type='password']")` reste non-`None` (champ encore visible) et
    `url` reste celui de la page de connexion tant que `_polls_avant_redirection` n'est pas
    atteint — exactement le décalage mesuré (0.6 s, 3 paliers de 100 ms dans ce test)."""

    def __init__(self, resultats, *, polls_avant_redirection: int):
        super().__init__(resultats)
        self._polls_avant_redirection = polls_avant_redirection
        self._polls = 0

    def query_selector(self, _selecteur):
        return object() if self._polls < self._polls_avant_redirection else None

    def wait_for_timeout(self, _ms):
        self._polls += 1
        if self._polls >= self._polls_avant_redirection:
            self.url = "https://exemple.test/dashboard"


def test_falsifiable_attend_la_vraie_redirection_spa_au_dela_du_networkidle_premature():
    """Sans `_attendre_confirmation_post_connexion`, cette fonction rendrait la main juste après
    `networkidle` — l'appelant (`crawl_roots`) lirait encore `page.url` = la page de connexion,
    exactement le symptôme mesuré sur `yros` (crawl bloqué à 3 routes, jamais d'erreur levée).
    Ce test échoue si l'attente bornée post-connexion est retirée ou court-circuitée."""
    identifiant, mdp, bouton = _FakeLocator(), _FakeLocator(), _FakeLocator()
    page = _FakePageSPA({
        ("textbox", "E-mail"): identifiant,
        ("textbox", "Mot de passe"): mdp,
        ("button", "Se connecter"): bouton,
    }, polls_avant_redirection=3)

    remplir_et_soumettre_formulaire_connexion(page, _LOGIN_FORM, "sidi@exemple.test", "s3cret")

    assert page.url == "https://exemple.test/dashboard"


def test_falsifiable_jamais_de_secret_dans_le_message_d_erreur():
    """Le message d'erreur porte le rôle/nom enregistrés (utile pour diagnostiquer), jamais la
    valeur du mot de passe soumis — même garde que `steps_json`/`login_form_json`."""
    page = _FakePage({
        ("textbox", "E-mail"): _FakeLocator(),
        ("textbox", "Mot de passe"): _FakeLocator(existe=False),
    })

    with pytest.raises(FormulaireConnexionObsoleteError) as exc_info:
        remplir_et_soumettre_formulaire_connexion(page, _LOGIN_FORM, "sidi@exemple.test", "s3cret")

    assert "s3cret" not in str(exc_info.value)
    assert "champ_mdp" in str(exc_info.value)


def test_falsifiable_champ_identifiant_introuvable_arrete_net_avant_le_mot_de_passe():
    mdp_jamais_atteint = _FakeLocator()
    page = _FakePage({
        ("textbox", "E-mail"): _FakeLocator(existe=False),
        ("textbox", "Mot de passe"): mdp_jamais_atteint,
        ("button", "Se connecter"): _FakeLocator(),
    })

    with pytest.raises(FormulaireConnexionObsoleteError, match="champ_identifiant"):
        remplir_et_soumettre_formulaire_connexion(page, _LOGIN_FORM, "u", "p")

    assert mdp_jamais_atteint.rempli is None


def test_falsifiable_bouton_ambigu_arrete_net_apres_avoir_rempli_les_2_champs():
    page, identifiant, mdp, _ = _page_complete()
    page._resultats[("button", "Se connecter")] = _FakeLocator(ambigu=True)

    with pytest.raises(FormulaireConnexionObsoleteError, match="bouton"):
        remplir_et_soumettre_formulaire_connexion(page, _LOGIN_FORM, "u", "p")

    # Les champs ont bien été remplis avant l'échec — l'arrêt net porte sur le clic, pas avant.
    assert identifiant.rempli == "u" and mdp.rempli == "p"


def test_falsifiable_le_bouton_n_est_jamais_clique_si_un_champ_a_deja_echoue():
    bouton_jamais_atteint = _FakeLocator()
    page = _FakePage({
        ("textbox", "E-mail"): _FakeLocator(),
        ("textbox", "Mot de passe"): _FakeLocator(existe=False),
        ("button", "Se connecter"): bouton_jamais_atteint,
    })

    with pytest.raises(FormulaireConnexionObsoleteError):
        remplir_et_soumettre_formulaire_connexion(page, _LOGIN_FORM, "u", "p")

    assert bouton_jamais_atteint.clique is False


# ── `tenter_connexion_et_lire_resultat` : préfère TOUJOURS le formulaire enregistré ──────────

def test_tenter_connexion_et_lire_resultat_utilise_le_formulaire_enregistre_si_fourni():
    page, identifiant, mdp, bouton = _page_complete()
    page._resultats = dict(page._resultats)

    resultat = tenter_connexion_et_lire_resultat(page, "u", "p", login_form=_LOGIN_FORM)

    assert resultat["submitted"] is True
    assert identifiant.rempli == "u" and mdp.rempli == "p" and bouton.clique is True


def test_falsifiable_un_formulaire_enregistre_obsolete_rend_une_erreur_jamais_une_exception():
    """`tenter_connexion_et_lire_resultat` reste un best-effort d'observation (comme avant cette
    extension) : une `FormulaireConnexionObsoleteError` ne doit jamais remonter telle quelle,
    seulement `error` dans le dict rendu."""
    page = _FakePage({("textbox", "E-mail"): _FakeLocator(existe=False)})

    resultat = tenter_connexion_et_lire_resultat(page, "u", "p", login_form=_LOGIN_FORM)

    assert resultat["submitted"] is False
    assert "champ_identifiant" in resultat["error"]
